"""
auto_backup.py — Автобэкап ARGOS
═══════════════════════════════════════════════════════
Автоматический бэкап конфигов, скилов, данных ARGOS:
  • Инкрементальный ZIP-архив с датой/временем
  • Расписание: каждые N часов / ежедневно
  • Ротация: хранить последние N архивов
  • Опционально: отправка в Telegram как файл
  • Восстановление из архива по команде
═══════════════════════════════════════════════════════
"""

from __future__ import annotations

SKILL_DESCRIPTION = "Инкрементальный ZIP-бэкап конфигов и данных"

import os
import json
import time
import zipfile
import shutil
import threading
from typing import Optional

try:
    import requests
    _REQ = True
except ImportError:
    _REQ = False

from src.argos_logger import get_logger

log = get_logger("argos.backup")

BACKUP_DIR    = "data/backups"
BACKUP_CONFIG = "config/backup.json"
os.makedirs(BACKUP_DIR, exist_ok=True)

DEFAULT_CONFIG = {
    "interval_hours": 6,          # интервал авто-бэкапа
    "keep_last":      10,         # сколько архивов хранить
    "send_to_tg":     False,      # отправлять в Telegram
    "include": [                  # что бэкапить
        "config",
        "src/skills",
        "data",
        ".env",
        "src/argoss_evolver.py",
    ],
    "exclude": [                  # что исключать
        "data/backups",
        "data/fw_cache",
        "__pycache__",
        "*.pyc",
    ],
}


class AutoBackup:
    """Авто-бэкап ARGOS с ротацией и отправкой в Telegram."""

    def __init__(self, core=None):
        self.core      = core
        self._running  = False
        self._cfg      = self._load_config()
        self._tg_token = os.getenv("TELEGRAM_BOT_TOKEN", "")
        self._tg_chat  = os.getenv("USER_ID", "")

    def _load_config(self) -> dict:
        if os.path.exists(BACKUP_CONFIG):
            try:
                cfg = json.load(open(BACKUP_CONFIG, encoding="utf-8"))
                merged = dict(DEFAULT_CONFIG)
                merged.update(cfg)
                return merged
            except Exception:
                pass
        return dict(DEFAULT_CONFIG)

    def _save_config(self):
        os.makedirs("config", exist_ok=True)
        json.dump(self._cfg, open(BACKUP_CONFIG, "w", encoding="utf-8"), indent=2, ensure_ascii=False)

    # ── Создание бэкапа ───────────────────────────────────────────────────────

    def create_backup(self, label: str = "") -> str:
        """Создаёт ZIP-архив. Возвращает путь к файлу."""
        ts   = time.strftime("%Y%m%d_%H%M%S")
        name = f"argos_backup_{ts}" + (f"_{label}" if label else "") + ".zip"
        path = os.path.join(BACKUP_DIR, name)

        exclude_patterns = self._cfg.get("exclude", [])
        include_paths    = self._cfg.get("include", [])
        added = 0

        with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as zf:
            for src_path in include_paths:
                if not os.path.exists(src_path):
                    continue
                if os.path.isfile(src_path):
                    if not self._is_excluded(src_path, exclude_patterns):
                        zf.write(src_path)
                        added += 1
                else:
                    for root, dirs, files in os.walk(src_path):
                        # Исключаем директории
                        dirs[:] = [d for d in dirs
                                   if not self._is_excluded(os.path.join(root, d), exclude_patterns)]
                        for f in files:
                            fp = os.path.join(root, f)
                            if not self._is_excluded(fp, exclude_patterns):
                                zf.write(fp)
                                added += 1

        size_kb = round(os.path.getsize(path) / 1024, 1)
        log.info("Бэкап создан: %s (%d файлов, %s КБ)", name, added, size_kb)
        return path, added, size_kb

    @staticmethod
    def _is_excluded(path: str, patterns: list) -> bool:
        import fnmatch
        for pat in patterns:
            if fnmatch.fnmatch(path, f"*{pat}*") or pat in path:
                return True
        return False

    def backup_and_report(self, label: str = "") -> str:
        """Создаёт бэкап и возвращает отчёт."""
        try:
            path, added, size_kb = self.create_backup(label)
            self._rotate()
            result = (
                f"✅ Бэкап создан\n"
                f"   📦 {os.path.basename(path)}\n"
                f"   📁 Файлов: {added}\n"
                f"   💾 Размер: {size_kb} КБ"
            )
            if self._cfg.get("send_to_tg"):
                sent = self._send_to_telegram(path)
                result += f"\n   {'📤 Отправлен в Telegram' if sent else '⚠️ TG отправка не удалась'}"
            return result
        except Exception as e:
            log.error("Backup failed: %s", e)
            return f"❌ Бэкап: {e}"

    # ── Ротация архивов ───────────────────────────────────────────────────────

    def _rotate(self):
        """Удаляет старые архивы, оставляет последние keep_last."""
        keep = self._cfg.get("keep_last", 10)
        archives = sorted(
            [f for f in os.listdir(BACKUP_DIR) if f.endswith(".zip")],
            reverse=True,
        )
        for old in archives[keep:]:
            try:
                os.remove(os.path.join(BACKUP_DIR, old))
                log.info("Удалён старый бэкап: %s", old)
            except Exception:
                pass

    # ── Восстановление ────────────────────────────────────────────────────────

    def list_backups(self) -> str:
        archives = sorted(
            [f for f in os.listdir(BACKUP_DIR) if f.endswith(".zip")],
            reverse=True,
        )
        if not archives:
            return "📦 Бэкапов нет"
        lines = [f"📦 БЭКАПЫ ARGOS ({len(archives)} архивов):"]
        for i, name in enumerate(archives[:15], 1):
            path = os.path.join(BACKUP_DIR, name)
            size = round(os.path.getsize(path) / 1024, 1)
            mt   = time.strftime("%d.%m.%Y %H:%M", time.localtime(os.path.getmtime(path)))
            lines.append(f"  {i:2}. {name:<42} {size:>7} КБ  [{mt}]")
        return "\n".join(lines)

    def restore(self, archive_name: str, dry_run: bool = False) -> str:
        """Восстанавливает из архива (с осторожностью!)."""
        if not archive_name.endswith(".zip"):
            archive_name += ".zip"

        # Поиск по подстроке
        archives = [f for f in os.listdir(BACKUP_DIR) if archive_name in f and f.endswith(".zip")]
        if not archives:
            return f"❌ Архив не найден: {archive_name}"
        path = os.path.join(BACKUP_DIR, archives[0])

        if dry_run:
            with zipfile.ZipFile(path, "r") as zf:
                names = zf.namelist()
            return f"ℹ️ Архив {archives[0]}: {len(names)} файлов\n" + "\n".join(names[:20])

        # Создаём бэкап перед восстановлением
        self.create_backup("pre_restore")

        with zipfile.ZipFile(path, "r") as zf:
            zf.extractall(".")
        log.info("Восстановлено из %s", archives[0])
        return f"✅ Восстановлено из {archives[0]}"

    # ── Отправка в Telegram ───────────────────────────────────────────────────

    def _send_to_telegram(self, filepath: str) -> bool:
        if not (_REQ and self._tg_token and self._tg_chat):
            return False
        try:
            with open(filepath, "rb") as f:
                r = requests.post(
                    f"https://api.telegram.org/bot{self._tg_token}/sendDocument",
                    data={"chat_id": self._tg_chat,
                          "caption": f"📦 ARGOS Backup {time.strftime('%d.%m.%Y %H:%M')}"},
                    files={"document": f},
                    timeout=60,
                )
            return r.ok
        except Exception as e:
            log.warning("TG send backup: %s", e)
            return False

    # ── Расписание ────────────────────────────────────────────────────────────

    def start(self) -> str:
        if self._running:
            return "⚠️ Автобэкап уже запущен"
        self._running = True
        threading.Thread(target=self._loop, daemon=True, name="autobackup").start()
        hours = self._cfg["interval_hours"]
        log.info("AutoBackup запущен, интервал %d ч", hours)
        return f"✅ Автобэкап запущен (каждые {hours} ч, хранить {self._cfg['keep_last']} архивов)"

    def stop(self) -> str:
        self._running = False
        return "⏹ Автобэкап остановлен"

    def _loop(self):
        interval = self._cfg.get("interval_hours", 6) * 3600
        # Первый бэкап через 60 секунд после старта
        time.sleep(60)
        while self._running:
            try:
                log.info("AutoBackup: создаём плановый бэкап...")
                result = self.backup_and_report("auto")
                log.info("AutoBackup: %s", result.split("\n")[0])
            except Exception as e:
                log.error("AutoBackup loop: %s", e)
            time.sleep(interval)

    def set_interval(self, hours: float) -> str:
        self._cfg["interval_hours"] = hours
        self._save_config()
        return f"✅ Интервал бэкапа: {hours} ч"

    def set_send_tg(self, enabled: bool) -> str:
        self._cfg["send_to_tg"] = enabled
        self._save_config()
        return f"✅ Отправка в Telegram: {'вкл' if enabled else 'выкл'}"

    def execute(self) -> str:
        return self.backup_and_report()

    def report(self) -> str:
        return self.list_backups()
