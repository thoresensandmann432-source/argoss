"""
tool_calling.py — ArgosToolCallingEngine
Реальное выполнение инструментов через прямой вызов функций.
НЕ использует LLM для выбора инструмента — сопоставление по ключевым словам.
"""
from __future__ import annotations
import os
import re
from src.argos_logger import get_logger

log = get_logger("argos.tool_calling")


class ArgosToolCallingEngine:
    """
    Движок инструментов Аргоса.
    try_handle() сопоставляет текст с реальными функциями напрямую.
    Никаких LLM-вызовов внутри — только детерминированный роутинг.
    """

    def __init__(self, core):
        self.core = core

    def tool_schemas(self) -> list:
        return [
            {"name": "create_file",  "description": "Создать файл",   "trigger": "создай файл"},
            {"name": "read_file",    "description": "Прочитать файл",  "trigger": "прочитай файл"},
            {"name": "list_dir",     "description": "Список файлов",   "trigger": "покажи файлы"},
            {"name": "delete_item",  "description": "Удалить файл",    "trigger": "удали файл"},
            {"name": "run_cmd",      "description": "Команда в терминале", "trigger": "консоль"},
            {"name": "get_stats",    "description": "Статус системы",  "trigger": "статус системы"},
        ]

    def try_handle(self, text: str, admin, flasher) -> str | None:
        """
        Возвращает строку-результат если команда распознана и выполнена,
        иначе None (тогда управление переходит к AI).
        """
        t = text.lower().strip()

        # Гарантируем admin
        if admin is None:
            admin = getattr(self.core, "_internal_admin", None)
        if admin is None:
            try:
                from src.admin import ArgosAdmin
                admin = ArgosAdmin()
                if hasattr(self.core, "_internal_admin"):
                    self.core._internal_admin = admin
            except Exception:
                pass

        if admin is None:
            return None  # не можем выполнить файловые команды

        # ── ФАЙЛЫ ─────────────────────────────────────────────────────────────
        if any(t.startswith(k) for k in ("создай файл", "напиши файл")):
            body = text
            for k in ("создай файл", "напиши файл"):
                body = body.replace(k, "").strip()
            parts = body.split(maxsplit=1)
            fname    = parts[0] if parts else "note.txt"
            fcontent = parts[1] if len(parts) > 1 else ""
            log.info("tool: create_file(%s)", fname)
            return admin.create_file(fname, fcontent)

        if any(t.startswith(k) for k in ("прочитай файл", "открой файл")):
            path = text
            for k in ("прочитай файл", "открой файл"):
                path = path.replace(k, "").strip()
            log.info("tool: read_file(%s)", path)
            return admin.read_file(path)

        if any(t.startswith(k) for k in ("покажи файлы", "список файлов")):
            path = text
            for k in ("покажи файлы", "список файлов"):
                path = path.replace(k, "").strip()
            return admin.list_dir(path or ".")

        if t.startswith("файлы "):
            path = text[6:].strip()
            return admin.list_dir(path or ".")

        if any(t.startswith(k) for k in ("удали файл", "удали папку")):
            path = text
            for k in ("удали файл", "удали папку"):
                path = path.replace(k, "").strip()
            return admin.delete_item(path)

        if any(t.startswith(k) for k in ("добавь в файл", "допиши в файл", "дополни файл")):
            tail = text
            for k in ("добавь в файл", "допиши в файл", "дополни файл"):
                if k in t:
                    tail = text.split(k, 1)[-1].strip()
                    break
            parts = tail.split(maxsplit=1)
            if len(parts) >= 2:
                return admin.append_file(parts[0], parts[1])
            return "Формат: добавь в файл [путь] [текст]"

        if any(t.startswith(k) for k in ("отредактируй файл", "измени файл", "замени в файле")):
            tail = text
            for k in ("отредактируй файл", "измени файл", "замени в файле"):
                if k in t:
                    tail = text.split(k, 1)[-1].strip()
                    break
            parts = tail.split("→", 1) if "→" in tail else tail.split("->", 1)
            if len(parts) == 2:
                path_and_old = parts[0].strip().split(maxsplit=1)
                if len(path_and_old) == 2:
                    return admin.edit_file(path_and_old[0], path_and_old[1], parts[1].strip())
            return "Формат: отредактируй файл [путь] [старый текст] → [новый текст]"

        if t.startswith("скопируй файл"):
            tail = text.replace("скопируй файл", "").strip()
            parts = tail.split(maxsplit=1)
            if len(parts) == 2:
                return admin.copy_file(parts[0], parts[1])
            return "Формат: скопируй файл [откуда] [куда]"

        if t.startswith("переименуй файл"):
            tail = text.replace("переименуй файл", "").strip()
            parts = tail.split(maxsplit=1)
            if len(parts) == 2:
                return admin.rename_file(parts[0], parts[1])
            return "Формат: переименуй файл [старое] [новое]"

        # ── ТЕРМИНАЛ ──────────────────────────────────────────────────────────
        if t.startswith("консоль ") or t.startswith("терминал "):
            cmd = text.split(None, 1)[1].strip() if len(text.split()) > 1 else ""
            if cmd:
                return admin.run_cmd(cmd, user="telegram")
            return "Формат: консоль [команда]"

        # ── ПРОЦЕССЫ ──────────────────────────────────────────────────────────
        if t.startswith("список процессов"):
            return admin.list_processes()

        if any(t.startswith(k) for k in ("убей процесс", "завершить процесс")):
            name = text.split(None, 2)[-1].strip()
            return admin.kill_process(name) if name else "Укажи имя процесса"

        # ── СИСТЕМА ───────────────────────────────────────────────────────────
        if any(t.startswith(k) for k in ("статус системы", "чек-ап", "состояние здоровья")):
            try:
                from src.connectivity.system_health import format_full_report
                return format_full_report()
            except Exception:
                return admin.get_stats()

        # Ничего не совпало — пусть AI отвечает
        return None
