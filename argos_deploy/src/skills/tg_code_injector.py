"""
tg_code_injector.py — Telegram Code Injector
═══════════════════════════════════════════════════════
Принимает код от ADMIN через Telegram и интегрирует его в ARGOS:
  • /code <filename.py>  + блок кода → сохраняет скил
  • /inject <filename>   → загружает в ядро без перезапуска
  • /patch               → применяет патч к существующему файлу
  • /rollback <name>     → откат к предыдущей версии
  • /skills              → список активных скилов

Безопасность:
  • Принимает ТОЛЬКО от USER_ID из .env (ADMIN)
  • Проверяет синтаксис Python перед сохранением
  • Создаёт бэкап перед перезаписью
  • Логирует все операции
═══════════════════════════════════════════════════════
"""

from __future__ import annotations

SKILL_DESCRIPTION = "Инъекция кода в ARGOS через Telegram от ADMIN"

import ast
import importlib
import importlib.util
import os
import sys
import time
import json
import shutil
import threading
import re
from typing import Optional

try:
    import requests
    _REQ = True
except ImportError:
    _REQ = False

from src.argos_logger import get_logger

log = get_logger("argos.tg_injector")

SKILLS_DIR   = "src/skills"
BACKUP_DIR   = "data/skill_backups"
INJECT_LOG   = "data/inject_history.json"
PENDING_FILE = "data/pending_code.json"     # временный буфер кода из TG

os.makedirs(BACKUP_DIR, exist_ok=True)
os.makedirs("data", exist_ok=True)


# ── Хранилище ожидающего кода ─────────────────────────────────────────────────

class _PendingBuffer:
    """Хранит код, переданный по частям через несколько сообщений TG."""

    def __init__(self):
        self._buf: dict[int, dict] = {}  # chat_id → {filename, lines, ts}

    def start(self, chat_id: int, filename: str):
        self._buf[chat_id] = {"filename": filename, "lines": [], "ts": time.time()}

    def append(self, chat_id: int, text: str):
        if chat_id in self._buf:
            self._buf[chat_id]["lines"].append(text)

    def finish(self, chat_id: int) -> Optional[dict]:
        return self._buf.pop(chat_id, None)

    def active(self, chat_id: int) -> bool:
        return chat_id in self._buf

    def cancel(self, chat_id: int):
        self._buf.pop(chat_id, None)


_pending = _PendingBuffer()


# ── Основной класс ────────────────────────────────────────────────────────────

class TGCodeInjector:
    """
    Слушает Telegram (long polling) и ждёт команд от администратора.
    Может использоваться и как standalone (start_polling) и как утилита (inject_code).
    """

    # Команды бота
    CMD_CODE     = "/code"      # /code filename.py → затем присылаешь код → /end
    CMD_INJECT   = "/inject"    # /inject filename → немедленная загрузка
    CMD_PATCH    = "/patch"     # /patch filename.py → diff/patch
    CMD_ROLLBACK = "/rollback"  # /rollback skillname
    CMD_SKILLS   = "/skills"    # список скилов
    CMD_END      = "/end"       # конец ввода кода
    CMD_CANCEL   = "/cancel"    # отмена
    CMD_STATUS   = "/status"    # статус инжектора

    def __init__(self, core=None):
        self.core    = core
        self._token  = os.getenv("TELEGRAM_BOT_TOKEN", "")
        self._admin  = int(os.getenv("USER_ID", "0"))
        self._running = False
        self._offset  = 0
        self._history: list = self._load_history()

    # ── История ──────────────────────────────────────────────────────────────

    def _load_history(self) -> list:
        if os.path.exists(INJECT_LOG):
            try:
                return json.load(open(INJECT_LOG, encoding="utf-8"))
            except Exception:
                pass
        return []

    def _save_history(self):
        try:
            json.dump(self._history[-200:], open(INJECT_LOG, "w", encoding="utf-8"),
                      indent=2, ensure_ascii=False)
        except Exception:
            pass

    def _log_op(self, op: str, filename: str, status: str, detail: str = ""):
        entry = {
            "ts": time.strftime("%Y-%m-%d %H:%M:%S"),
            "op": op,
            "file": filename,
            "status": status,
            "detail": detail,
        }
        self._history.append(entry)
        self._save_history()
        log.info("[%s] %s → %s | %s", op, filename, status, detail)

    # ── Telegram API helpers ──────────────────────────────────────────────────

    def _tg(self, method: str, **kwargs) -> dict:
        if not _REQ or not self._token:
            return {}
        try:
            r = requests.post(
                f"https://api.telegram.org/bot{self._token}/{method}",
                json=kwargs, timeout=10,
            )
            return r.json() if r.ok else {}
        except Exception as e:
            log.warning("TG API %s: %s", method, e)
            return {}

    def _reply(self, chat_id: int, text: str, parse_mode: str = "HTML"):
        # Telegram ограничение 4096 символов
        for chunk in [text[i:i+4000] for i in range(0, len(text), 4000)]:
            self._tg("sendMessage", chat_id=chat_id, text=chunk, parse_mode=parse_mode)

    def _get_updates(self) -> list:
        data = self._tg("getUpdates", offset=self._offset, timeout=20, limit=10)
        return data.get("result", []) if data.get("ok") else []

    # ── Проверка синтаксиса ───────────────────────────────────────────────────

    @staticmethod
    def validate_python(code: str) -> tuple[bool, str]:
        """Проверяет синтаксис Python. Возвращает (ok, error_message)."""
        try:
            ast.parse(code)
            return True, ""
        except SyntaxError as e:
            return False, f"SyntaxError line {e.lineno}: {e.msg}"

    @staticmethod
    def _strip_code_block(text: str) -> str:
        """Убирает ```python ... ``` обёртку если есть."""
        text = text.strip()
        text = re.sub(r"^```(?:python|py)?\s*\n?", "", text)
        text = re.sub(r"\n?```\s*$", "", text)
        return text

    # ── Операции с файлами ────────────────────────────────────────────────────

    def _backup(self, filepath: str) -> str:
        """Создаёт бэкап файла перед перезаписью."""
        if not os.path.exists(filepath):
            return ""
        ts = time.strftime("%Y%m%d_%H%M%S")
        base = os.path.basename(filepath)
        backup = os.path.join(BACKUP_DIR, f"{base}.{ts}.bak")
        shutil.copy2(filepath, backup)
        log.info("Бэкап: %s → %s", filepath, backup)
        return backup

    def save_skill(self, filename: str, code: str) -> tuple[bool, str]:
        """
        Сохраняет код как скил.
        Проверяет синтаксис, делает бэкап, записывает файл.
        """
        # Нормализация имени
        if not filename.endswith(".py"):
            filename += ".py"
        filename = re.sub(r"[^\w\-.]", "_", filename)

        # Проверка синтаксиса
        ok, err = self.validate_python(code)
        if not ok:
            return False, f"❌ Синтаксис: {err}"

        # Безопасность: запрет на ../
        if ".." in filename or "/" in filename:
            return False, "❌ Недопустимое имя файла"

        filepath = os.path.join(SKILLS_DIR, filename)
        backup_path = self._backup(filepath)

        try:
            os.makedirs(SKILLS_DIR, exist_ok=True)
            with open(filepath, "w", encoding="utf-8") as f:
                f.write(code)
            self._log_op("save", filename, "ok",
                         f"backup={os.path.basename(backup_path) if backup_path else 'none'}")
            return True, filepath
        except Exception as e:
            return False, f"❌ Запись: {e}"

    def inject_skill(self, filename: str) -> tuple[bool, str]:
        """
        Загружает/перезагружает скил в ядро ARGOS без рестарта.
        """
        if not filename.endswith(".py"):
            filename += ".py"
        filepath = os.path.join(SKILLS_DIR, filename)

        if not os.path.exists(filepath):
            return False, f"❌ Файл не найден: {filepath}"

        module_name = f"argos_skill_{filename[:-3]}"
        try:
            # Выгружаем старую версию из кэша
            for key in list(sys.modules.keys()):
                if filename[:-3] in key:
                    del sys.modules[key]

            spec = importlib.util.spec_from_file_location(module_name, filepath)
            mod  = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            sys.modules[module_name] = mod

            # Пробуем зарегистрировать в ядре
            if self.core and hasattr(self.core, "skill_loader") and self.core.skill_loader:
                try:
                    self.core.skill_loader.load_file(filepath, core=self.core)
                except Exception:
                    pass

            self._log_op("inject", filename, "ok", f"module={module_name}")
            return True, module_name
        except Exception as e:
            self._log_op("inject", filename, "fail", str(e))
            return False, f"❌ Inject: {e}"

    def rollback_skill(self, filename: str) -> tuple[bool, str]:
        """Откатывает скил к последнему бэкапу."""
        if not filename.endswith(".py"):
            filename += ".py"

        # Ищем самый свежий бэкап
        backups = sorted(
            [f for f in os.listdir(BACKUP_DIR) if f.startswith(filename)],
            reverse=True,
        )
        if not backups:
            return False, f"❌ Бэкапов нет для {filename}"

        latest = os.path.join(BACKUP_DIR, backups[0])
        dest   = os.path.join(SKILLS_DIR, filename)
        shutil.copy2(latest, dest)
        self._log_op("rollback", filename, "ok", f"from={backups[0]}")
        return True, f"✅ Откат из {backups[0]}"

    def list_skills(self) -> str:
        """Список скилов в папке src/skills."""
        files = sorted(f for f in os.listdir(SKILLS_DIR) if f.endswith(".py"))
        if not files:
            return "📦 Скилов нет"
        lines = ["📦 СКИЛЫ ARGOS:"]
        for f in files:
            path = os.path.join(SKILLS_DIR, f)
            size = os.path.getsize(path)
            mt   = time.strftime("%d.%m %H:%M", time.localtime(os.path.getmtime(path)))
            lines.append(f"  • {f:<30} {size:>6} байт  [{mt}]")
        return "\n".join(lines)

    def history(self, n: int = 10) -> str:
        """Последние n операций инжектора."""
        if not self._history:
            return "📋 История пуста"
        lines = ["📋 ИСТОРИЯ ИНЖЕКЦИЙ:"]
        for e in self._history[-n:]:
            icon = "✅" if e["status"] == "ok" else "❌"
            lines.append(f"  {icon} [{e['ts']}] {e['op']} {e['file']} {e.get('detail','')}")
        return "\n".join(lines)

    # ── Обработка сообщений ───────────────────────────────────────────────────

    def _handle_message(self, msg: dict):
        chat_id  = msg.get("chat", {}).get("id", 0)
        from_id  = msg.get("from", {}).get("id", 0)
        text     = (msg.get("text") or "").strip()

        # Проверяем права — только ADMIN
        if from_id != self._admin:
            self._reply(chat_id, "⛔ Доступ запрещён. Только администратор.")
            return

        # Если идёт накопление кода
        if _pending.active(chat_id):
            if text == self.CMD_END:
                buf = _pending.finish(chat_id)
                if buf:
                    code = self._strip_code_block("\n".join(buf["lines"]))
                    self._process_save(chat_id, buf["filename"], code)
                return
            if text == self.CMD_CANCEL:
                _pending.cancel(chat_id)
                self._reply(chat_id, "❌ Отменено.")
                return
            _pending.append(chat_id, text)
            return

        # Команды
        if text.startswith(self.CMD_CODE):
            # /code filename.py
            parts = text.split(maxsplit=1)
            if len(parts) < 2:
                self._reply(chat_id,
                    "📝 Формат: <code>/code имя_скила.py</code>\n"
                    "Затем отправь код по частям.\n"
                    "Закончи командой <code>/end</code>")
                return
            filename = parts[1].strip()
            _pending.start(chat_id, filename)
            self._reply(chat_id,
                f"📥 Жду код для <b>{filename}</b>\n"
                "Отправляй построчно или целым блоком.\n"
                "Можно обернуть в <code>```python</code>...<code>```</code>\n"
                "Закончи: <code>/end</code>  |  Отмена: <code>/cancel</code>")

        elif text.startswith(self.CMD_INJECT):
            parts = text.split(maxsplit=1)
            if len(parts) < 2:
                self._reply(chat_id, "Формат: <code>/inject filename.py</code>")
                return
            filename = parts[1].strip()
            ok, result = self.inject_skill(filename)
            self._reply(chat_id,
                f"{'✅ Загружен' if ok else '❌ Ошибка'}: <code>{result}</code>")

        elif text.startswith(self.CMD_PATCH):
            # /patch + код в одном сообщении (через ```)
            code_match = re.search(r"```(?:python|py)?\s*([\s\S]+?)```", text)
            if code_match:
                filename_match = re.search(r"/patch\s+(\S+)", text)
                filename = filename_match.group(1) if filename_match else "patch.py"
                code = code_match.group(1).strip()
                self._process_save(chat_id, filename, code, auto_inject=True)
            else:
                self._reply(chat_id,
                    "📝 Формат: <code>/patch filename.py</code>\n"
                    "```python\n# код\n```")

        elif text.startswith(self.CMD_ROLLBACK):
            parts = text.split(maxsplit=1)
            if len(parts) < 2:
                self._reply(chat_id, "Формат: <code>/rollback filename.py</code>")
                return
            ok, result = self.rollback_skill(parts[1].strip())
            self._reply(chat_id, result)

        elif text == self.CMD_SKILLS:
            self._reply(chat_id, f"<pre>{self.list_skills()}</pre>")

        elif text == self.CMD_STATUS:
            skills_count = len([f for f in os.listdir(SKILLS_DIR) if f.endswith(".py")])
            backups      = len(os.listdir(BACKUP_DIR))
            ops          = len(self._history)
            last_op      = self._history[-1] if self._history else {}
            status = (
                f"🤖 <b>TGCodeInjector</b>\n"
                f"  Скилов: {skills_count}\n"
                f"  Бэкапов: {backups}\n"
                f"  Операций: {ops}\n"
                f"  Последняя: {last_op.get('ts','—')} {last_op.get('op','')}\n"
                f"  Polling: {'✅' if self._running else '⏹'}"
            )
            self._reply(chat_id, status)

        elif text.startswith("/history"):
            self._reply(chat_id, f"<pre>{self.history(15)}</pre>")

        elif text == "/help":
            self._reply(chat_id,
                "🛠 <b>ARGOS Code Injector</b>\n\n"
                "<code>/code filename.py</code> — начать ввод кода\n"
                "<code>/end</code> — закончить ввод и сохранить\n"
                "<code>/cancel</code> — отмена\n"
                "<code>/patch filename.py</code> + ```код``` — сохранить + загрузить\n"
                "<code>/inject filename.py</code> — загрузить в ядро\n"
                "<code>/rollback filename.py</code> — откат к бэкапу\n"
                "<code>/skills</code> — список скилов\n"
                "<code>/status</code> — статус инжектора\n"
                "<code>/history</code> — последние операции")

    def _process_save(self, chat_id: int, filename: str, code: str,
                      auto_inject: bool = False):
        """Сохраняет код и опционально загружает в ядро."""
        ok, result = self.save_skill(filename, code)
        if not ok:
            self._reply(chat_id, result)
            return

        lines_count = code.count("\n") + 1
        msg = (
            f"✅ <b>Скил сохранён</b>: <code>{filename}</code>\n"
            f"   Строк кода: {lines_count}\n"
            f"   Путь: <code>{result}</code>\n\n"
            "Загрузить в ядро сейчас? → <code>/inject " + filename + "</code>"
        )

        if auto_inject:
            inj_ok, inj_res = self.inject_skill(filename)
            inject_line = f"\n{'✅ Загружен в ядро' if inj_ok else '⚠️ Ошибка загрузки'}: <code>{inj_res}</code>"
            msg = (
                f"✅ <b>Скил сохранён и загружен</b>: <code>{filename}</code>\n"
                f"   Строк: {lines_count}{inject_line}"
            )

        self._reply(chat_id, msg)

    # ── Polling loop ──────────────────────────────────────────────────────────

    def start_polling(self):
        """Запускает long polling в фоновом потоке."""
        if not self._token:
            log.error("TGCodeInjector: TELEGRAM_BOT_TOKEN не задан")
            return "❌ TELEGRAM_BOT_TOKEN не задан"
        if not self._admin:
            log.error("TGCodeInjector: USER_ID не задан")
            return "❌ USER_ID не задан"

        self._running = True
        threading.Thread(target=self._poll_loop, daemon=True, name="tg_injector").start()
        log.info("TGCodeInjector запущен. Admin ID: %d", self._admin)
        return f"✅ TGCodeInjector запущен. Слушаю admin {self._admin}"

    def stop(self):
        self._running = False

    def _poll_loop(self):
        log.info("TGCodeInjector: polling started")
        while self._running:
            try:
                updates = self._get_updates()
                for upd in updates:
                    self._offset = upd["update_id"] + 1
                    if "message" in upd:
                        self._handle_message(upd["message"])
            except Exception as e:
                log.warning("TGCodeInjector poll error: %s", e)
                time.sleep(5)

    # ── Публичный интерфейс для вызова из ARGOS ───────────────────────────────

    def execute(self) -> str:
        """Точка входа при вызове через skill_loader."""
        return self.start_polling()

    def report(self) -> str:
        return (
            f"🤖 TGCodeInjector\n"
            f"  Статус: {'🟢 работает' if self._running else '🔴 остановлен'}\n"
            f"  Admin: {self._admin}\n"
            f"  Скилов: {len([f for f in os.listdir(SKILLS_DIR) if f.endswith('.py')])}\n"
            f"  Операций: {len(self._history)}"
        )
