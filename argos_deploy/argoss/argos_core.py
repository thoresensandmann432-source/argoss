"""
argoss/argos_core.py — Ядро ARGOS с безопасными флагами
======================================================
"""
from __future__ import annotations

import os
from typing import Optional, Callable

__all__ = ["ArgosCore"]


class ArgosCore:
    """
    Центральное ядро ARGOS.
    Управляет агентом, каналами, памятью и безопасностью.
    """

    def __init__(self, config_path: Optional[str] = None) -> None:
        # Безопасные флаги
        self._agent_enabled = True
        self._agent_self_modify_allowed = False
        self._auto_patch_allowed = False

        # GigaChat интеграция
        self._gigachat_api_key = os.getenv("GIGACHAT_API_KEY", "")
        self._gigachat_enabled = bool(self._gigachat_api_key)
        self._gigachat_model = "GigaChat-Pro"

        # Провайдеры
        self._providers = {
            "gemini": True,
            "ollama": True,
            "gigachat": self._gigachat_enabled,
            "watson": False,
            "yandexgpt": False,
        }

        # Callback для команд
        self._command_handler: Optional[Callable[[str], str]] = None

    # ═══════════════════════════════════════════════════════════════════════════
    # Properties для безопасности
    # ═══════════════════════════════════════════════════════════════════════════

    @property
    def agent_enabled(self) -> bool:
        return self._agent_enabled

    @property
    def self_modify_allowed(self) -> bool:
        return self._agent_self_modify_allowed

    @property
    def auto_patch_allowed(self) -> bool:
        return self._auto_patch_allowed

    @property
    def gigachat_enabled(self) -> bool:
        return self._gigachat_enabled

    # ═══════════════════════════════════════════════════════════════════════════
    # Управление агентом
    # ═══════════════════════════════════════════════════════════════════════════

    def stop_agent(self) -> str:
        """Останавливает агента безопасно."""
        self._agent_enabled = False
        return "🛑 Агент остановлен"

    def start_agent(self) -> str:
        """Запускает агента."""
        self._agent_enabled = True
        return "✅ Агент запущен"

    def enable_safe_mode(self) -> str:
        """Включает безопасный режим."""
        self._agent_self_modify_allowed = False
        self._auto_patch_allowed = False
        return "🔒 Безопасный режим включён. Self-modify и auto-patch отключены."

    # ═══════════════════════════════════════════════════════════════════════════
    # GigaChat
    # ═══════════════════════════════════════════════════════════════════════════

    def setup_gigachat(self, api_key: str) -> str:
        """Настраивает GigaChat."""
        if not api_key or len(api_key) < 10:
            return "❌ Неверный API ключ GigaChat"
        self._gigachat_api_key = api_key
        self._gigachat_enabled = True
        self._providers["gigachat"] = True
        return "✅ GigaChat настроен и готов к работе"

    def check_gigachat_status(self) -> str:
        """Проверяет статус GigaChat."""
        if not self._gigachat_enabled:
            return "⚠️ GigaChat не настроен. Установите GIGACHAT_API_KEY в окружение."
        return (
            f"⚡ GigaChat: {'✅ активен' if self._gigachat_enabled else '❌ недоступен'}\n"
            f"  Модель: {self._gigachat_model}\n"
            f"  API ключ: {'✅' if self._gigachat_api_key else '❌'}"
        )

    # ═══════════════════════════════════════════════════════════════════════════
    # Обработка команд
    # ═══════════════════════════════════════════════════════════════════════════

    def handle_command(self, text: str) -> str:  # noqa: C901
        """Обрабатывает команды управления."""
        t = text.strip().lower()

        # Управление агентом
        if t in {"останови агента", "agent stop", "выключи агент"}:
            return self.stop_agent()

        if t in {"запусти агента", "agent start", "включи агент"}:
            return self.start_agent()

        if t in {"безопасный режим", "safe mode"}:
            return self.enable_safe_mode()

        # GigaChat
        if t in {"gigachat статус", "гигачат статус"}:
            return self.check_gigachat_status()

        if t.startswith("gigachat ключ "):
            key = text[len("gigachat ключ "):].strip()
            return self.setup_gigachat(key)

        if t in {"инфра", "infrastructure"}:
            return self._get_infrastructure_status()

        if t in {"провайдеры", "providers"}:
            return self._list_providers()

        # Команда tail для логов (из конституции shell.allowed_commands)
        if t.startswith("tail ") or t == "tail":
            return self._handle_tail_command(t)

        return (
            "🤖 ARGOS Core команды:\n"
            "  Агент: останови агента | запусти агента | безопасный режим\n"
            "  GigaChat: гигачат статус | gigachat ключ <API_KEY>\n"
            "  Инфра: инфра | провайдеры"
        )

    def _get_infrastructure_status(self) -> str:
        """Статус инфраструктуры."""
        return (
            "🏗️ ARGOS Core\n"
            f"  Агент: {'✅' if self._agent_enabled else '❌'}\n"
            f"  Self-modify: {'✅' if self._agent_self_modify_allowed else '❌'}\n"
            f"  Auto-patch: {'✅' if self._auto_patch_allowed else '❌'}\n"
            f"  GigaChat: {'✅' if self._gigachat_enabled else '❌'}"
        )

    def _list_providers(self) -> str:
        """Список провайдеров."""
        lines = ["🌐 Провайдеры:"]
        for name, enabled in self._providers.items():
            status = "✅" if enabled else "❌"
            lines.append(f"  {status} {name}")
        return "\n".join(lines)

    def _handle_tail_command(self, t: str) -> str:
        """Обработка команды tail для логов."""
        count = 50
        parts = t.split()
        if len(parts) > 1 and parts[1].isdigit():
            count = max(1, min(int(parts[1]), 200))
        try:
            import os
            log_path = os.path.join("logs", "argos_debug.log")
            if not os.path.exists(log_path):
                return "📭 Лог-файл не найден"
            with open(log_path, "r", encoding="utf-8", errors="ignore") as f:
                lines = f.readlines()
                return "".join(lines[-count:]) or "Лог пуст"
        except Exception as e:
            return f"❌ Ошибка чтения лога: {e}"

