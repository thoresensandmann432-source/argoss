"""
tool_calling.py — ЗАМЕНА старого ArgosToolCallingEngine

Этот файл заменяет старую версию которая отправляла все запросы в LLM.
Новая версия: прямое выполнение команд без LLM.
"""
from __future__ import annotations
from src.argos_logger import get_logger

log = get_logger("argos.tool_calling")


class ArgosToolCallingEngine:
    """Прямой диспетчер команд. Никакого LLM внутри."""

    def __init__(self, core):
        self.core = core
        log.info("ToolCalling: новая версия загружена (прямой диспетчер)")

    def tool_schemas(self) -> list:
        return []

    def try_handle(self, text: str, admin, flasher) -> str | None:
        """Всегда возвращает None — execute_intent обрабатывает команды."""
        return None
