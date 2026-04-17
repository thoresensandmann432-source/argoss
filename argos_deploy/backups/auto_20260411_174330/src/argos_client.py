"""
argos_client.py — Универсальный клиент для ARGOS API

Простой Python-клиент для работы с ARGOS из внешних приложений.

Использование:
    from src.argos_client import ArgosClient
    
    client = ArgosClient("http://localhost:5000")
    
    # Отправить сообщение
    response = client.chat("Привет, Аргос!")
    print(response)
    
    # Список навыков
    skills = client.list_skills()
    
    # Найти Claude агента
    agent = client.find_agent("python developer")
"""

import requests
import json
from typing import Optional, Dict, List, Generator
from dataclasses import dataclass


@dataclass
class ArgosMessage:
    """Сообщение от ARGOS."""
    role: str
    content: str
    timestamp: Optional[str] = None


class ArgosClient:
    """
    Универсальный клиент для ARGOS API.
    
    Поддерживает:
      • HTTP API (если включен Web сервер)
      • Локальный вызов (если ARGOS в том же процессе)
    """
    
    def __init__(self, base_url: str = "http://localhost:5000", api_key: Optional[str] = None):
        """
        Инициализация клиента.
        
        Args:
            base_url: URL сервера ARGOS (по умолчанию localhost:5000)
            api_key: API ключ для авторизации (если включена)
        """
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self._session = requests.Session()
        
        if api_key:
            self._session.headers.update({"Authorization": f"Bearer {api_key}"})
        
    def is_alive(self) -> bool:
        """Проверка доступности сервера."""
        try:
            response = self._session.get(f"{self.base_url}/health", timeout=5)
            return response.status_code == 200
        except:
            return False
    
    def chat(self, message: str, stream: bool = False) -> str:
        """
        Отправить сообщение ARGOS.
        
        Args:
            message: Текст сообщения
            stream: Использовать потоковую передачу
            
        Returns:
            Ответ от ARGOS
        """
        payload = {
            "message": message,
            "stream": stream
        }
        
        try:
            if stream:
                return self._chat_stream(payload)
            
            response = self._session.post(
                f"{self.base_url}/api/chat",
                json=payload,
                timeout=60
            )
            response.raise_for_status()
            data = response.json()
            return data.get("response", "[Ошибка: пустой ответ]")
            
        except requests.exceptions.ConnectionError:
            return "[Ошибка: сервер ARGOS недоступен]"
        except requests.exceptions.Timeout:
            return "[Ошибка: таймаут запроса]"
        except Exception as e:
            return f"[Ошибка: {e}]"
    
    def _chat_stream(self, payload: dict) -> str:
        """Потоковая передача ответа."""
        full_response = ""
        
        with self._session.post(
            f"{self.base_url}/api/chat/stream",
            json=payload,
            stream=True,
            timeout=60
        ) as response:
            response.raise_for_status()
            
            for line in response.iter_lines():
                if line:
                    data = json.loads(line)
                    chunk = data.get("chunk", "")
                    full_response += chunk
                    print(chunk, end="", flush=True)
        
        return full_response
    
    def list_skills(self) -> List[Dict]:
        """Получить список всех навыков."""
        try:
            response = self._session.get(f"{self.base_url}/api/skills", timeout=10)
            response.raise_for_status()
            return response.json().get("skills", [])
        except:
            return []
    
    def execute_skill(self, skill_name: str, query: str) -> str:
        """
        Выполнить конкретный навык.
        
        Args:
            skill_name: Имя навыка (например "weather", "net_scanner")
            query: Запрос для навыка
        """
        try:
            response = self._session.post(
                f"{self.base_url}/api/skills/{skill_name}/execute",
                json={"query": query},
                timeout=30
            )
            response.raise_for_status()
            return response.json().get("result", "[Ошибка выполнения навыка]")
        except Exception as e:
            return f"[Ошибка: {e}]"
    
    def find_agent(self, task: str) -> Optional[Dict]:
        """
        Найти Claude агента для задачи.
        
        Args:
            task: Описание задачи (например "создать python api")
            
        Returns:
            Информация об агенте или None
        """
        try:
            response = self._session.post(
                f"{self.base_url}/api/claude/find-agent",
                json={"task": task},
                timeout=10
            )
            response.raise_for_status()
            return response.json().get("agent")
        except:
            return None
    
    def list_claude_agents(self, category: Optional[str] = None) -> List[Dict]:
        """
        Получить список Claude агентов.
        
        Args:
            category: Фильтр по категории (опционально)
        """
        params = {"category": category} if category else {}
        try:
            response = self._session.get(
                f"{self.base_url}/api/claude/agents",
                params=params,
                timeout=10
            )
            response.raise_for_status()
            return response.json().get("agents", [])
        except:
            return []
    
    def get_system_status(self) -> Dict:
        """Получить статус системы ARGOS."""
        try:
            response = self._session.get(f"{self.base_url}/api/status", timeout=5)
            response.raise_for_status()
            return response.json()
        except:
            return {"error": "server_unavailable"}
    
    def switch_ai_mode(self, mode: str) -> str:
        """
        Переключить режим AI.
        
        Args:
            mode: Режим (auto/gemini/ollama/kimi/...)
        """
        try:
            response = self._session.post(
                f"{self.base_url}/api/config/ai-mode",
                json={"mode": mode},
                timeout=10
            )
            response.raise_for_status()
            return response.json().get("message", "OK")
        except Exception as e:
            return f"[Ошибка: {e}]"
    
    def run_pip_command(self, command: str) -> Dict:
        """
        Выполнить команду pip.
        
        Args:
            command: Команда pip (например "установи requests" или "pip install --upgrade pip")
            
        Returns:
            Результат выполнения команды
        """
        import re
        
        # Парсим команду
        parts = command.lower().split()
        if not parts:
            return {"success": False, "error": "Empty command"}
        
        if parts[0] in ["установи", "install"]:
            # pip install
            package = None
            for i, p in enumerate(parts):
                if p in ["пакет", "пакета", "package"]:
                    if i + 1 < len(parts):
                        package = parts[i + 1]
                        break
            if not package:
                # Ищем имя пакета в конце
                package = parts[-1] if len(parts) > 1 else None
            
            if package:
                return self._pip_install(package, upgrade="--upgrade" in command)
        
        elif parts[0] in ["удали", "uninstall"]:
            package = parts[-1] if len(parts) > 1 else None
            if package:
                return self._pip_uninstall(package)
        
        elif parts[0] in ["список", "list"]:
            return self._pip_list()
        
        elif parts[0] in ["проверь", "check", "outdated"]:
            return self._pip_check()
        
        return {"success": False, "error": f"Unknown command: {command}"}
    
    def _pip_install(self, package: str, upgrade: bool = False) -> Dict:
        """Установить пакет."""
        try:
            response = self._session.post(
                f"{self.base_url}/api/pip/install",
                json={"package": package, "upgrade": upgrade},
                timeout=60
            )
            response.raise_for_status()
            return response.json()
        except Exception as e:
            return {"success": False, "error": str(e), "package": package}
    
    def _pip_uninstall(self, package: str) -> Dict:
        """Удалить пакет."""
        try:
            response = self._session.post(
                f"{self.base_url}/api/pip/uninstall",
                json={"package": package},
                timeout=30
            )
            response.raise_for_status()
            return response.json()
        except Exception as e:
            return {"success": False, "error": str(e), "package": package}
    
    def _pip_list(self) -> Dict:
        """Список пакетов."""
        try:
            response = self._session.get(f"{self.base_url}/api/pip/list", timeout=10)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    def _pip_check(self) -> Dict:
        """Проверка зависимостей."""
        try:
            response = self._session.get(f"{self.base_url}/api/pip/check", timeout=10)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    def run_evolution(self) -> Dict:
        """
        Запустить эволюцию ARGOS.
        
        Returns:
            Результат запуска эволюции
        """
        try:
            response = self._session.post(
                f"{self.base_url}/api/evolution/run",
                timeout=120
            )
            response.raise_for_status()
            return response.json()
        except Exception as e:
            return {"status": "error", "message": str(e)}


# ══════════════════════════════════════════════════════════════════════════════
# Синхронный клиент (без HTTP, прямой вызов)
# ══════════════════════════════════════════════════════════════════════════════

class ArgosLocalClient:
    """
    Локальный клиент для работы с ARGOS без HTTP.
    Требует импорта модулей ARGOS.
    """
    
    def __init__(self, core=None):
        """
        Инициализация с существующим ядром.
        
        Args:
            core: Экземпляр ArgosCore (если None — создаётся новый)
        """
        if core is None:
            from src.core import ArgosCore
            core = ArgosCore()
        
        self.core = core
    
    def chat(self, message: str) -> str:
        """Отправить сообщение через ядро."""
        if hasattr(self.core, 'process'):
            return self.core.process(message)
        return self.core.execute_intent(message)
    
    def list_skills(self) -> List[Dict]:
        """Получить навыки."""
        if hasattr(self.core, 'get_all_skills'):
            return self.core.get_all_skills()
        elif hasattr(self.core, 'skill_loader'):
            return list(self.core.skill_loader._skills.keys())
        return []
    
    def find_agent(self, task: str) -> Optional[Dict]:
        """Найти Claude агента."""
        if hasattr(self.core, 'find_claude_agent'):
            return self.core.find_claude_agent(task)
        return None


# ══════════════════════════════════════════════════════════════════════════════
# Тестирование
# ══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    import sys
    
    print("🌐 ArgosClient Demo")
    print("=" * 50)
    
    # Создаём клиента
    client = ArgosClient("http://localhost:5000")
    
    # Проверяем доступность
    print("\n📡 Проверка связи...")
    if client.is_alive():
        print("   ✅ Сервер ARGOS доступен")
    else:
        print("   ❌ Сервер недоступен (проверьте localhost:5000)")
        sys.exit(1)
    
    # Тестируем чат
    print("\n💬 Тест чата:")
    test_msg = "Привет! Какая у тебя версия?"
    print(f"   Я: {test_msg}")
    response = client.chat(test_msg)
    print(f"   ARGOS: {response[:100]}...")
    
    # Список навыков
    print("\n📦 Навыки:")
    skills = client.list_skills()
    print(f"   Найдено: {len(skills)} навыков")
    
    # Статус системы
    print("\n📊 Статус системы:")
    status = client.get_system_status()
    print(f"   {json.dumps(status, indent=2, ensure_ascii=False)[:200]}...")
    
    print("\n✅ Тест завершён")