from __future__ import annotations


def handle_direct_telegram(text: str, core) -> str | None:
    t = (text or "").lower().strip()

    if not getattr(core, "constitution_hooks", None):
        return None

    if t in {"конституция статус", "режим системы", "argos status", "статус конституции"}:
        return core.constitution_hooks.telegram_status()

    if t in {"safe mode", "безопасный режим", "режим safe"}:
        return core.constitution_hooks.telegram_enter_safe_mode()

    if t in {"normal mode", "обычный режим"}:
        return core.constitution_hooks.telegram_enter_normal_mode()

    if t in {"autopatch status", "статус автопатча"}:
        return core.constitution_hooks.telegram_can_autopatch()

    if t in {"rollback last", "откати последний патч"}:
        rm = getattr(core, "rollback_manager", None)
        if not rm:
            return "Rollback manager не инициализирован"
        ok = rm.rollback_last()
        return "Откат последнего патча выполнен" if ok else "Нет патча для отката"

    if t.startswith("tail ") or t == "tail":
        return _read_last_log_lines(core, text)

    if t.startswith("logs ") or t == "logs":
        return _read_last_log_lines(core, text)

    if t in {"останови агента", "agent stop", "выключи агент"}:
        setattr(core, "_agent_enabled", False)
        if getattr(core, "agent", None):
            try:
                core.agent.stop()
            except Exception:
                pass
        return "Агент остановлен"

    if t in {"запусти агента", "agent start", "включи агент"}:
        setattr(core, "_agent_enabled", True)
        return "Агент запущен"

    return None


def _read_last_log_lines(core, text: str) -> str:
    raw = (text or "").strip().lower().split()
    count = 50
    if len(raw) >= 2 and raw[1].isdigit():
        count = max(1, min(int(raw[1]), 200))
    log_path = getattr(core, "_debug_log_path", "logs/argos_debug.log")
    try:
        with open(log_path, "r", encoding="utf-8", errors="ignore") as f:
            lines = f.readlines()[-count:]
            return "".join(lines).strip() or "Лог пуст"
    except Exception as e:
        return f"Ошибка чтения лога: {e}"
