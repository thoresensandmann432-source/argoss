"""
src/tool_calling.py — JSON Tool Calling Engine для ARGOS
========================================================
Планирует вызовы инструментов, выполняет их и синтезирует ответ.
"""
from __future__ import annotations

import json
import os
from typing import Any, Optional

__all__ = ["ArgosToolCallingEngine"]

_MAX_ROUNDS = 4
_OLLAMA_TIMEOUT = int(os.getenv("OLLAMA_TIMEOUT", "600"))

_TOOL_SCHEMAS = [
    {
        "name": "get_system_stats",
        "description": "Получить статистику системы (CPU, RAM, диск, температура)",
        "parameters": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "get_iot_status",
        "description": "Получить статус IoT устройств",
        "parameters": {
            "type": "object",
            "properties": {
                "protocol": {"type": "string", "description": "zigbee|mqtt|modbus|all"}
            },
        },
    },
    {
        "name": "search_memory",
        "description": "Поиск в долгосрочной памяти ARGOS",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Поисковый запрос"}
            },
            "required": ["query"],
        },
    },
    {
        "name": "execute_command",
        "description": "Выполнить системную команду ARGOS",
        "parameters": {
            "type": "object",
            "properties": {
                "command": {"type": "string", "description": "Команда для выполнения"}
            },
            "required": ["command"],
        },
    },
    {
        "name": "web_search",
        "description": "Поиск в интернете через DuckDuckGo",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Поисковый запрос"}
            },
            "required": ["query"],
        },
    },
]


class ArgosToolCallingEngine:
    """
    Движок Tool Calling с многораундовым выполнением.

    Алгоритм:
    1. _plan_calls(user_text) → {confidence, tool_calls, final_answer}
    2. Если confidence < 0.8 и есть tool_calls → выполняем инструменты
    3. Повторяем до MAX_ROUNDS или до confidence >= 0.8
    4. Если planner вернул None → _synthesize_answer()
    """

    def __init__(self, core) -> None:
        self._core = core

    def try_handle(self, text: str, admin=None, flasher=None) -> Optional[str]:
        """
        Пытается обработать запрос через Tool Calling.
        Возвращает строку-ответ или None если не может.
        """
        previous_outputs: list[dict] = []
        executed_tools: set[tuple] = set()

        for _ in range(_MAX_ROUNDS):
            plan = self._plan_calls(
                text,
                context_text=self._get_context(text),
                previous_outputs=previous_outputs,
            )

            if plan is None:
                if previous_outputs:
                    return self._synthesize_answer(text, previous_outputs)
                return None

            # Достаточно уверен — возвращаем финальный ответ
            if plan.get("confidence", 0) >= 0.8 or plan.get("final_answer"):
                return plan.get("final_answer") or self._synthesize_answer(text, previous_outputs)

            # Выполняем инструменты
            tool_calls = plan.get("tool_calls", [])
            if not tool_calls:
                return plan.get("final_answer") or self._synthesize_answer(text, previous_outputs)

            made_new = False
            for call in tool_calls:
                name = call.get("name", "")
                args = call.get("arguments", {})
                key  = (name, json.dumps(args, sort_keys=True))
                if key in executed_tools:
                    continue
                executed_tools.add(key)
                made_new = True
                result = self._execute_tool(name, args, admin, flasher)
                previous_outputs.append({"tool": name, "arguments": args, "result": result})

            if not made_new:
                break

        return self._synthesize_answer(text, previous_outputs)

    def _plan_calls(
        self,
        user_text: str,
        context_text: str = "",
        previous_outputs: Optional[list[dict]] = None,
    ) -> Optional[dict]:
        """Запрашивает у LLM план вызовов инструментов."""
        import requests as req

        tools_json = json.dumps(_TOOL_SCHEMAS, ensure_ascii=False, indent=2)
        prev_json  = json.dumps(previous_outputs or [], ensure_ascii=False)

        system = (
            "Ты — планировщик инструментов ARGOS. "
            "Отвечай ТОЛЬКО валидным JSON без markdown.\n"
            f"Доступные инструменты:\n{tools_json}"
        )
        prompt = (
            f"Запрос пользователя: {user_text}\n"
            f"Контекст: {context_text[:500]}\n"
            f"Предыдущие результаты: {prev_json}\n\n"
            "Верни JSON: {{\"confidence\": 0.0-1.0, \"tool_calls\": [...], \"final_answer\": \"\"}}"
        )

        try:
            resp = req.post(
                self._core.ollama_url,
                json={"model": "llama3", "prompt": f"{system}\n\n{prompt}", "stream": False},
                timeout=_OLLAMA_TIMEOUT,
            )
            text_resp = resp.json().get("response", "")
            # Очищаем markdown если есть
            text_resp = text_resp.strip().lstrip("```json").lstrip("```").rstrip("```").strip()
            return json.loads(text_resp)
        except Exception:
            return None

    def _execute_tool(
        self,
        name: str,
        arguments: dict,
        admin: Any,
        flasher: Any,
    ) -> str:
        """Выполняет один инструмент по имени."""
        try:
            if name == "get_system_stats":
                sensors = getattr(self._core, "sensors", None)
                if sensors:
                    return sensors.get_full_report()
                return "CPU: N/A, RAM: N/A"

            if name == "get_iot_status":
                iot = getattr(self._core, "iot_bridge", None)
                if iot and hasattr(iot, "status"):
                    return iot.status()
                return "IoT недоступен"

            if name == "search_memory":
                memory = getattr(self._core, "memory", None)
                if memory and hasattr(memory, "search"):
                    return memory.search(arguments.get("query", ""))
                return "Память недоступна"

            if name == "execute_command":
                cmd = arguments.get("command", "")
                if cmd:
                    from src.core import ArgosCore
                    result = self._core.process(cmd)
                    if isinstance(result, dict):
                        return result.get("answer", str(result))
                    return str(result)
                return "Команда не указана"

            if name == "web_search":
                query = arguments.get("query", "")
                return f"[Веб-поиск: {query}] — результаты недоступны в offline режиме"

            return f"Инструмент {name!r} не реализован"

        except Exception as e:
            return f"Ошибка инструмента {name}: {e}"

    def _synthesize_answer(self, user_text: str, outputs: list[dict]) -> str:
        """Синтезирует финальный ответ из результатов инструментов."""
        if not outputs:
            return f"Не удалось получить данные для ответа на: {user_text}"
        parts = []
        for o in outputs:
            parts.append(f"[{o['tool']}]: {str(o['result'])[:200]}")
        return "\n".join(parts)

    def _get_context(self, query: str) -> str:
        ctx = getattr(self._core, "context", None)
        if ctx and hasattr(ctx, "get_prompt_context"):
            try:
                return ctx.get_prompt_context(query)
            except Exception:
                pass
        return ""
