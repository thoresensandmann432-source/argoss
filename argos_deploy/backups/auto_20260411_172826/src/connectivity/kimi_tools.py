"""
kimi_tools.py — Tool Calling для Kimi K2.5

Позволяет Kimi динамически вызывать ARGOS навыки и инструменты.

Использование:
    from src.connectivity.kimi_tools import KimiToolCalling
    
    tool_caller = KimiToolCalling(core)
    result = tool_caller.chat_with_tools("Какая погода в Москве?")
    # Kimi увидит доступные инструменты, выберет нужный и выполнит
"""

import json
import re
from typing import Dict, List, Optional, Any, Callable
from dataclasses import dataclass

from src.argos_logger import get_logger
from src.connectivity.kimi_bridge import KimiBridge

log = get_logger("argos.kimi.tools")


@dataclass
class ToolDefinition:
    """Определение инструмента для Kimi."""
    name: str
    description: str
    parameters: Dict[str, Any]
    function: Callable


class KimiToolCalling:
    """
    Tool Calling система для Kimi.
    
    Kimi получает список инструментов в system prompt,
    может "вызвать" их через специальный формат ответа.
    """
    
    def __init__(self, core=None, api_key: Optional[str] = None):
        self.core = core
        self.kimi = KimiBridge(api_key=api_key)
        self.tools: Dict[str, ToolDefinition] = {}
        self._register_builtin_tools()
        
    def _register_builtin_tools(self):
        """Регистрация встроенных инструментов."""
        # Погода
        self.register_tool(
            name="get_weather",
            description="Получить текущую погоду в указанном городе",
            parameters={
                "type": "object",
                "properties": {
                    "city": {
                        "type": "string",
                        "description": "Название города на русском или английском"
                    }
                },
                "required": ["city"]
            },
            function=self._tool_weather
        )
        
        # Список навыков
        self.register_tool(
            name="list_skills",
            description="Получить список всех доступных навыков ARGOS",
            parameters={"type": "object", "properties": {}},
            function=self._tool_list_skills
        )
        
        # Время
        self.register_tool(
            name="get_time",
            description="Получить текущее время",
            parameters={"type": "object", "properties": {}},
            function=self._tool_get_time
        )
        
        # Статус системы
        self.register_tool(
            name="system_status",
            description="Получить статус системы ARGOS",
            parameters={"type": "object", "properties": {}},
            function=self._tool_system_status
        )
        
        # Поиск в интернете
        self.register_tool(
            name="web_search",
            description="Выполнить поиск в интернете",
            parameters={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Поисковый запрос"
                    }
                },
                "required": ["query"]
            },
            function=self._tool_web_search
        )
        
        # Выполнить навык напрямую
        self.register_tool(
            name="execute_skill",
            description="Выполнить конкретный навык ARGOS",
            parameters={
                "type": "object",
                "properties": {
                    "skill_name": {
                        "type": "string",
                        "description": "Имя навыка (например 'weather', 'net_scanner')"
                    },
                    "query": {
                        "type": "string",
                        "description": "Запрос для навыка"
                    }
                },
                "required": ["skill_name", "query"]
            },
            function=self._tool_execute_skill
        )
    
    def register_tool(self, name: str, description: str, 
                     parameters: Dict, function: Callable):
        """Регистрация нового инструмента."""
        self.tools[name] = ToolDefinition(
            name=name,
            description=description,
            parameters=parameters,
            function=function
        )
        log.info(f"Tool registered: {name}")
    
    def get_tools_prompt(self) -> str:
        """Генерация промпта с описанием инструментов."""
        lines = ["Доступные инструменты:"]
        
        for tool in self.tools.values():
            lines.append(f"\n{tool.name}: {tool.description}")
            if tool.parameters.get("properties"):
                lines.append("  Параметры:")
                for param_name, param_info in tool.parameters["properties"].items():
                    req = " (обязательно)" if param_name in tool.parameters.get("required", []) else ""
                    lines.append(f"    - {param_name}: {param_info.get('description', '')}{req}")
        
        lines.append("\nЧтобы использовать инструмент, ответь ТОЧНО в формате:")
        lines.append('TOOL_CALL: {"name": "имя_инструмента", "arguments": {"параметр": "значение"}}')
        lines.append("\nЕсли инструменты не нужны, отвечай обычно.")
        
        return "\n".join(lines)
    
    def chat_with_tools(self, message: str, temperature: float = 0.7,
                       max_iterations: int = 3) -> str:
        """
        Чат с поддержкой инструментов.
        
        Kimi может вызвать инструмент, получить результат и продолжить диалог.
        """
        if not self.kimi.is_available:
            return "[Kimi Tools] API не настроен"
        
        # Устанавливаем system prompt с инструментами
        system_prompt = f"""Ты полезный ассистент ARGOS. У тебя есть доступ к инструментам системы.

{self.get_tools_prompt()}

Используй инструменты только когда это необходимо для ответа на вопрос пользователя."""
        
        self.kimi.set_system_prompt(system_prompt)
        
        # История для мульти-тур диалога
        conversation = [{"role": "user", "content": message}]
        
        for iteration in range(max_iterations):
            # Отправляем запрос
            response = self.kimi.chat(
                conversation[-1]["content"] if iteration == 0 else self._format_conversation(conversation),
                temperature=temperature,
                max_tokens=2048
            )
            
            # Проверяем, хочет ли Kimi вызвать инструмент
            tool_call = self._parse_tool_call(response)
            
            if not tool_call:
                # Обычный ответ, return
                return response
            
            # Выполняем инструмент
            log.info(f"Tool call: {tool_call['name']}")
            result = self._execute_tool(tool_call["name"], tool_call.get("arguments", {}))
            
            # Добавляем в контекст
            conversation.append({"role": "assistant", "content": response})
            conversation.append({
                "role": "user", 
                "content": f"Результат выполнения {tool_call['name']}: {result}\n\nОтветь на основе этих данных."
            })
        
        # Достигли max_iterations
        return response
    
    def _format_conversation(self, messages: List[Dict]) -> str:
        """Форматирование conversation для Kimi (упрощенный формат)."""
        lines = []
        for msg in messages[-3:]:  # Берем последние 3 сообщения
            prefix = "Пользователь:" if msg["role"] == "user" else "Ассистент:"
            lines.append(f"{prefix} {msg['content']}")
        return "\n\n".join(lines)
    
    def _parse_tool_call(self, response: str) -> Optional[Dict]:
        """Парсинг TOOL_CALL из ответа Kimi."""
        # Ищем TOOL_CALL: и всё что после него до конца строки или end of string
        import re
        
        # Пытаемся найти TOOL_CALL: {...}
        # Ищем позицию TOOL_CALL:
        marker = "TOOL_CALL:"
        idx = response.find(marker)
        if idx != -1:
            json_start = idx + len(marker)
            # Пропускаем пробелы
            while json_start < len(response) and response[json_start] in ' \t':
                json_start += 1
            
            if json_start < len(response) and response[json_start] == '{':
                # Нашли начало JSON - парсим с учётом вложенности
                brace_count = 0
                json_end = json_start
                in_string = False
                escape_next = False
                
                for i in range(json_start, len(response)):
                    char = response[i]
                    
                    if escape_next:
                        escape_next = False
                        continue
                    
                    if char == '\\' and in_string:
                        escape_next = True
                        continue
                    
                    if char == '"' and not escape_next:
                        in_string = not in_string
                        continue
                    
                    if not in_string:
                        if char == '{':
                            brace_count += 1
                        elif char == '}':
                            brace_count -= 1
                            if brace_count == 0:
                                json_end = i + 1
                                break
                
                json_str = response[json_start:json_end]
                try:
                    data = json.loads(json_str)
                    if "name" in data:
                        return {
                            "name": data.get("name"),
                            "arguments": data.get("arguments", data.get("parameters", {}))
                        }
                except json.JSONDecodeError:
                    pass
        
        # Альтернативный формат: JSON в ```
        import re
        match = re.search(r'```json\s*\n?(.*?)\n?```', response, re.DOTALL)
        if match:
            try:
                data = json.loads(match.group(1))
                if "name" in data:
                    return {
                        "name": data.get("name"),
                        "arguments": data.get("arguments", data.get("parameters", {}))
                    }
            except json.JSONDecodeError:
                pass
        
        return None
    
    def _execute_tool(self, name: str, arguments: Dict) -> str:
        """Выполнение инструмента."""
        if name not in self.tools:
            return f"[Ошибка: инструмент '{name}' не найден]"
        
        try:
            tool = self.tools[name]
            return tool.function(**arguments)
        except Exception as e:
            log.error(f"Tool {name} error: {e}")
            return f"[Ошибка выполнения {name}: {e}]"
    
    # ═══════════════════════════════════════════════════════════════════════
    # Реализации инструментов
    # ═══════════════════════════════════════════════════════════════════════
    
    def _tool_weather(self, city: str) -> str:
        """Получить погоду."""
        try:
            from skills.weather import WeatherSkill
            skill = WeatherSkill()
            return skill.handle(f"погода в {city}", self.core) or "Не удалось получить погоду"
        except Exception as e:
            log.error(f"Weather tool error: {e}")
            return f"[Ошибка погоды: {e}]"
    
    def _tool_list_skills(self) -> str:
        """Список навыков."""
        if self.core and hasattr(self.core, 'skill_loader'):
            skills = self.core.skill_loader.list_skills()
            return skills
        return "Навыки недоступны"
    
    def _tool_get_time(self) -> str:
        """Текущее время."""
        from datetime import datetime
        return f"Текущее время: {datetime.now().strftime('%H:%M:%S, %d.%m.%Y')}\nДень недели: {datetime.now().strftime('%A')}"
    
    def _tool_system_status(self) -> str:
        """Статус системы."""
        if self.core and hasattr(self.core, 'system_check'):
            return self.core.system_check()
        try:
            from src.connectivity.system_health import format_full_report
            return format_full_report()
        except:
            return "Статус системы недоступен"
    
    def _tool_web_search(self, query: str) -> str:
        """Веб-поиск."""
        try:
            from src.connectivity.web_search import WebSearcher
            searcher = WebSearcher()
            results = searcher.quick_search(query)
            return f"Результаты поиска по '{query}':\n{results}"
        except Exception as e:
            log.error(f"Web search error: {e}")
            return f"[Ошибка поиска: {e}]"
    
    def _tool_execute_skill(self, skill_name: str, query: str) -> str:
        """Выполнить навык."""
        if self.core and hasattr(self.core, 'skill_loader'):
            # Ищем навык
            for name, inst in self.core.skill_loader._skills.items():
                if skill_name.lower() in name.lower():
                    result = inst.handle(query, self.core)
                    if result:
                        return result
        return f"Навык '{skill_name}' не найден или не вернул результат"


# ══════════════════════════════════════════════════════════════════════════════
# Интеграция с core.py
# ══════════════════════════════════════════════════════════════════════════════

def chat_with_kimi_tools(core, message: str, use_tools: bool = True) -> str:
    """
    Утилита для вызова из core.py.
    
    Args:
        core: ArgosCore экземпляр
        message: Сообщение пользователя
        use_tools: Использовать ли инструменты
        
    Returns:
        Ответ от Kimi с возможным использованием инструментов
    """
    if not use_tools:
        # Простой запрос без инструментов
        kimi = KimiBridge()
        return kimi.chat(message) if kimi.is_available else "[Kimi недоступен]"
    
    # С инструментами
    tool_caller = KimiToolCalling(core=core)
    return tool_caller.chat_with_tools(message)


# ══════════════════════════════════════════════════════════════════════════════
# Демо
# ══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    print("🌙 Kimi Tool Calling Demo")
    print("=" * 50)
    
    tool_caller = KimiToolCalling()
    
    if not tool_caller.kimi.is_available:
        print("❌ KIMI_API_KEY не настроен")
        exit(1)
    
    # Показываем доступные инструменты
    print("\n📦 Доступные инструменты:")
    for name, tool in tool_caller.tools.items():
        print(f"   • {name}: {tool.description}")
    
    # Тестовые запросы
    test_queries = [
        "Который час?",
        "Какие навыки у тебя есть?",
        "Найди информацию о Python",
    ]
    
    for query in test_queries:
        print(f"\n💬 Запрос: {query}")
        response = tool_caller.chat_with_tools(query)
        print(f"   Ответ: {response[:200]}..." if len(response) > 200 else f"   Ответ: {response}")