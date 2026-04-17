"""
scheduler.py — Планировщик задач Аргоса
  "аргос, напомни в 09:00 сделать бэкап"
  "аргос, каждый час сканируй сеть"
  "аргос, покажи расписание"
"""

import threading
import time
import json
import os
import re
import datetime
from src.argos_logger import get_logger

log = get_logger("argos.scheduler")
TASKS_FILE = "config/scheduled_tasks.json"


class ArgosScheduler:
    def __init__(self, core=None):
        self.core = core
        self.tasks = self._load()
        self._running = False

    def _load(self) -> list:
        if os.path.exists(TASKS_FILE):
            try:
                return json.load(open(TASKS_FILE, encoding="utf-8"))
            except Exception:
                pass
        return []

    def _save(self):
        os.makedirs("config", exist_ok=True)
        json.dump(self.tasks, open(TASKS_FILE, "w", encoding="utf-8"), indent=2, ensure_ascii=False)

    def start(self) -> str:
        self._running = True
        threading.Thread(target=self._loop, daemon=True).start()
        log.info("Scheduler запущен. Задач: %d", len(self.tasks))
        return f"⏰ Планировщик запущен. Активных задач: {len(self.tasks)}"

    def stop(self):
        self._running = False

    def _loop(self):
        # При старте — сразу проверим пропущенные задачи (ARGOS мог быть выключен)
        self._catch_up_missed()
        while self._running:
            now = time.localtime()
            for task in list(self.tasks):
                if self._should_run(task, now):
                    self._execute(task)
                    if task.get("repeat") == "once":
                        self.tasks.remove(task)
                        self._save()
            time.sleep(10)  # проверка каждые 10 секунд (было 30)

    def _catch_up_missed(self):
        """Выполняет задачи, пропущенные пока ARGOS был выключен."""
        now_ts = time.time()
        today = datetime.date.today()
        midnight_today = datetime.datetime.combine(today, datetime.time(0, 0)).timestamp()

        for task in list(self.tasks):
            t_type = task.get("type")
            last = task.get("last_run", 0)

            if t_type == "daily":
                h, m = task.get("hour", 9), task.get("minute", 0)
                scheduled_today = datetime.datetime.combine(
                    today, datetime.time(h, m)
                ).timestamp()
                # Если плановое время уже прошло сегодня, но не выполнялось сегодня — запускаем
                if now_ts > scheduled_today and last < midnight_today:
                    log.info("Catch-up: пропущена задача #%s (%s), запускаю", task.get("id"), task.get("command","")[:40])
                    self._execute(task)

            elif t_type == "once":
                run_at = task.get("run_at", 0)
                if now_ts >= run_at and last == 0:
                    log.info("Catch-up: разовая задача #%s, запускаю", task.get("id"))
                    self._execute(task)
                    self.tasks.remove(task)
                    self._save()
                    break  # список мог измениться, начнём сначала на следующей итерации

    def _should_run(self, task: dict, now) -> bool:
        t_type = task.get("type")
        last = task.get("last_run", 0)
        now_ts = time.time()

        if t_type == "daily":
            h, m = task.get("hour", 9), task.get("minute", 0)
            # Вариант 1: точное совпадение времени (±10 сек)
            # Вариант 2: catch-up — время уже прошло, но задача не выполнялась сегодня
            today = datetime.date.today()
            midnight_today = datetime.datetime.combine(today, datetime.time(0, 0)).timestamp()
            scheduled_today = datetime.datetime.combine(
                today, datetime.time(h, m)
            ).timestamp()

            # Выполнить если: плановое время прошло сегодня И не выполнялось сегодня
            if now_ts >= scheduled_today and last < midnight_today:
                return True

        elif t_type == "interval":
            interval = task.get("interval_sec", 3600)
            if now_ts - last >= interval:
                return True

        elif t_type == "once":
            run_at = task.get("run_at", 0)
            if now_ts >= run_at and last == 0:
                return True

        return False

    def _execute(self, task: dict):
        cmd = task.get("command", "")
        task_id = task.get("id", "?")
        log.info("Выполняю задачу #%s: %s", task_id, cmd)
        task["last_run"] = time.time()
        self._save()

        if self.core:
            # Эмулируем ввод пользователя
            try:
                from src.admin import ArgosAdmin
                admin = ArgosAdmin()
            except Exception as e:
                log.warning("Задача #%s — ArgosAdmin недоступен: %s", task_id, e)
                admin = None

            flasher = None
            try:
                from src.factory.flasher import AirFlasher
                flasher = AirFlasher()
            except Exception:
                pass  # flasher необязателен

            try:
                res = self.core.process_logic(cmd, admin, flasher)
                log.info("Задача #%s завершена: %s", task_id, str(res.get("answer", "") if isinstance(res, dict) else res)[:100])
            except Exception as e:
                log.error("Задача #%s ошибка выполнения: %s", task_id, e)
        else:
            print(f"[SCHEDULER] Задача: {cmd}")

    def add_daily(self, command: str, hour: int, minute: int = 0) -> str:
        task = {
            "id": len(self.tasks) + 1,
            "type": "daily",
            "command": command,
            "hour": hour,
            "minute": minute,
            "last_run": 0,
        }
        self.tasks.append(task)
        self._save()
        return (
            f"✅ Задача #{task['id']} добавлена: '{command}' каждый день в {hour:02d}:{minute:02d}"
        )

    def add_interval(self, command: str, interval_sec: int) -> str:
        task = {
            "id": len(self.tasks) + 1,
            "type": "interval",
            "command": command,
            "interval_sec": interval_sec,
            "last_run": 0,
        }
        self.tasks.append(task)
        self._save()
        mins = interval_sec // 60
        return f"✅ Задача #{task['id']}: '{command}' каждые {mins} мин."

    def add_once(self, command: str, delay_sec: int) -> str:
        task = {
            "id": len(self.tasks) + 1,
            "type": "once",
            "repeat": "once",
            "command": command,
            "run_at": time.time() + delay_sec,
            "last_run": 0,
        }
        self.tasks.append(task)
        self._save()
        return f"✅ Задача #{task['id']}: '{command}' через {delay_sec//60} мин."

    def remove(self, task_id: int) -> str:
        before = len(self.tasks)
        self.tasks = [t for t in self.tasks if t.get("id") != task_id]
        if len(self.tasks) < before:
            self._save()
            return f"✅ Задача #{task_id} удалена."
        return f"❌ Задача #{task_id} не найдена."

    def list_tasks(self) -> str:
        if not self.tasks:
            return "📭 Расписание пустое."
        lines = ["⏰ РАСПИСАНИЕ АРГОСА:"]
        for t in self.tasks:
            if t["type"] == "daily":
                when = f"каждый день {t['hour']:02d}:{t['minute']:02d}"
            elif t["type"] == "interval":
                when = f"каждые {t['interval_sec']//60} мин"
            else:
                import datetime

                when = f"однажды в {datetime.datetime.fromtimestamp(t['run_at']).strftime('%H:%M')}"
            lines.append(f"  #{t['id']} [{t['type']}] {when}: {t['command'][:50]}")
        return "\n".join(lines)

    def parse_and_add(self, text: str) -> str:
        """Парсит натуральный язык:
          'каждый час статус системы'
          'статус системы каждый час'
          'напомни в 9 утра сделать бэкап'
          'через 30 мин проверь диск'
        """
        t = text.lower().strip()
        if not t:
            return "❓ Пустая команда. Примеры:\n  'каждый час статус системы'\n  'в 09:00 дайджест'"

        # ── Сокращения единиц времени ────────────────────────────────────
        # Нормализуем: "каждые полчаса" → "каждые 30 мин"
        t = re.sub(r"каждые\s+полчаса", "каждые 30 мин", t)
        t = re.sub(r"каждые\s+полминуты", "каждые 30 секунд", t)

        # ── Интервал с числом: "каждые N час/мин/сек" ────────────────────
        m = re.search(r"каждые?\s+(\d+)\s*(час|мин|секунд)", t)
        if m:
            n, unit = int(m.group(1)), m.group(2)
            secs = n * (3600 if "час" in unit else 60 if "мин" in unit else 1)
            cmd = re.sub(r"каждые?\s+\d+\s*\w+\s*", "", t).strip()
            cmd = re.sub(r"(запуск|делай|выполняй)\s*", "", cmd).strip()
            return self.add_interval(cmd or text, secs)

        # ── Интервал без числа: "каждый час X" или "X каждый час" ────────
        m_unit = re.search(r"каждый\s+(час|день|минуту|минут)", t)
        if m_unit:
            unit_word = m_unit.group(1)
            secs = {"час": 3600, "день": 86400, "минуту": 60, "минут": 60}.get(unit_word, 3600)
            cmd = re.sub(r"каждый\s+\w+\s*", "", t).strip()
            if unit_word == "день":
                # "каждый день" → ежедневно в 09:00 если нет времени
                return self.add_daily(cmd or text, 9, 0)
            return self.add_interval(cmd or text, secs)

        # ── Ежедневно в HH:MM ─────────────────────────────────────────────
        m = re.search(r"в\s+(\d{1,2})(?::(\d{2}))?\s*(утра|вечера|ночи|дня)?", t)
        if m:
            h = int(m.group(1))
            mins = int(m.group(2)) if m.group(2) else 0
            suffix = m.group(3) or ""
            if suffix in ("вечера", "дня") and h < 12:
                h += 12
            elif suffix == "ночи" and h >= 8:
                h = h  # "в 2 ночи" = 02:00
            cmd = re.sub(r"(напомни|ежедневно|каждый день)\s*", "", t)
            cmd = re.sub(r"в\s+\d{1,2}(?::\d{2})?\s*\w*\s*", "", cmd).strip()
            return self.add_daily(cmd or text, h, mins)

        # ── Через N минут/часов ───────────────────────────────────────────
        m = re.search(r"через\s+(\d+)\s*(мин|час|секунд)", t)
        if m:
            n, unit = int(m.group(1)), m.group(2)
            secs = n * (3600 if "час" in unit else 60 if "мин" in unit else 1)
            cmd = re.sub(r"через\s+\d+\s*\w+\s*", "", t).strip()
            return self.add_once(cmd or text, secs)

        return (
            "❓ Не понял расписание. Примеры:\n"
            "  'каждый час статус системы'\n"
            "  'каждые 30 мин сканируй сеть'\n"
            "  'в 09:00 дайджест'\n"
            "  'через 30 мин проверь диск'\n"
            "  'каждый день бэкап'"
        )
