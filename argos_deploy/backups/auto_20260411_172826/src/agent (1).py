"""
agent.py — ArgosAgent: автономный агент цепочек задач и напоминаний.

Отвечает за:
  - Выполнение цепочек задач (pipeline)
  - Проверку и отправку напоминаний (check_reminders)
  - Управление очередью агентных задач
  - Отчёт о состоянии агента
"""

from __future__ import annotations

import threading
import time
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional


class ArgosAgent:
    """Автономный агент Аргоса — цепочки задач и напоминания."""

    def __init__(self, core):
        self.core = core
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._task_chain: List[str] = []
        self._chain_results: List[dict] = []
        self._reminders: List[Dict[str, Any]] = []
        self._reminder_lock = threading.Lock()
        self._report: Dict[str, Any] = {
            "started_at": None,
            "tasks_done": 0,
            "errors": 0,
            "last_task": None,
        }

    # ──────────────────────────────────────────────────────────────
    # НАПОМИНАНИЯ
    # ──────────────────────────────────────────────────────────────

    def add_reminder(
        self, text: str, fire_at: float, repeat_seconds: Optional[float] = None
    ) -> str:
        """
        Добавить напоминание.

        :param text: Текст напоминания
        :param fire_at: Unix-timestamp когда сработать
        :param repeat_seconds: Интервал повтора (None = однократно)
        :return: ID напоминания
        """
        rid = f"rem_{int(time.time() * 1000)}"
        with self._reminder_lock:
            self._reminders.append(
                {
                    "id": rid,
                    "text": text,
                    "fire_at": fire_at,
                    "repeat_seconds": repeat_seconds,
                    "fired": False,
                }
            )
        return rid

    def check_reminders(self) -> List[str]:
        """
        Проверить напоминания и вернуть список сработавших текстов.
        Вызывается планировщиком или вручную.

        :return: Список текстов напоминаний которые нужно показать
        """
        now = time.time()
        fired_texts: List[str] = []

        with self._reminder_lock:
            for rem in self._reminders:
                if rem["fired"] and rem["repeat_seconds"] is None:
                    continue  # однократное уже сработало

                if now >= rem["fire_at"]:
                    fired_texts.append(rem["text"])
                    rem["fired"] = True

                    # Если повторяющееся — сдвигаем время следующего срабатывания
                    if rem["repeat_seconds"]:
                        rem["fire_at"] = now + rem["repeat_seconds"]
                        rem["fired"] = False

            # Чистим однократные отработанные
            self._reminders = [
                r for r in self._reminders if not (r["fired"] and r["repeat_seconds"] is None)
            ]

        # Отправляем в core если есть алерты или Telegram
        for text in fired_texts:
            self._dispatch_reminder(text)

        return fired_texts

    def _dispatch_reminder(self, text: str) -> None:
        """Отправить напоминание через доступные каналы."""
        try:
            # Через EventBus если доступен
            if hasattr(self.core, "event_bus") and self.core.event_bus:
                self.core.event_bus.publish("agent.reminder", {"text": text, "ts": time.time()})
            # Через Telegram если доступен
            if hasattr(self.core, "tg") and self.core.tg:
                self.core.tg.send_message(f"⏰ Напоминание: {text}")
            # В лог в любом случае
            if hasattr(self.core, "logger"):
                self.core.logger.info("Reminder fired: %s", text)
        except Exception:
            pass  # никогда не роняем агента из-за ошибки доставки

    def list_reminders(self) -> str:
        """Вернуть список активных напоминаний в виде строки."""
        with self._reminder_lock:
            active = [r for r in self._reminders if not r["fired"]]
        if not active:
            return "📭 Активных напоминаний нет."
        lines = ["⏰ НАПОМИНАНИЯ:"]
        for i, r in enumerate(active, 1):
            fire_dt = datetime.fromtimestamp(r["fire_at"]).strftime("%d.%m %H:%M")
            repeat = f" (каждые {int(r['repeat_seconds'])}с)" if r["repeat_seconds"] else ""
            lines.append(f"  {i}. [{fire_dt}]{repeat} {r['text']}")
        return "\n".join(lines)

    def remove_reminder(self, index: int) -> str:
        """Удалить напоминание по номеру (1-based)."""
        with self._reminder_lock:
            active = [r for r in self._reminders if not r["fired"]]
            if index < 1 or index > len(active):
                return f"❌ Напоминание #{index} не найдено."
            rid = active[index - 1]["id"]
            self._reminders = [r for r in self._reminders if r["id"] != rid]
        return f"✅ Напоминание #{index} удалено."

    # ──────────────────────────────────────────────────────────────
    # ЦЕПОЧКИ ЗАДАЧ
    # ──────────────────────────────────────────────────────────────

    def run_chain(
        self, tasks: List[str], callback: Optional[Callable[[str, str], None]] = None
    ) -> str:
        """
        Запустить цепочку задач асинхронно.

        :param tasks: Список команд для последовательного выполнения
        :param callback: fn(task, result) вызывается после каждой задачи
        :return: Статус запуска
        """
        if self._running:
            return "⚠️ Агент уже выполняет цепочку задач. Подожди или останови."

        self._task_chain = list(tasks)
        self._chain_results = []
        self._running = True
        self._report["started_at"] = time.time()
        self._report["tasks_done"] = 0
        self._report["errors"] = 0

        self._thread = threading.Thread(
            target=self._execute_chain,
            args=(callback,),
            daemon=True,
            name="argos-agent-chain",
        )
        self._thread.start()
        return f"🤖 Агент запущен: {len(tasks)} задач в цепочке."

    def _execute_chain(self, callback: Optional[Callable[[str, str], None]]) -> None:
        """Внутренний метод — последовательное выполнение цепочки."""
        for task in self._task_chain:
            if not self._running:
                break
            try:
                self._report["last_task"] = task
                result = self.core.process(task)
                answer = (
                    result.get("answer", str(result)) if isinstance(result, dict) else str(result)
                )
                self._chain_results.append({"task": task, "result": answer, "ok": True})
                self._report["tasks_done"] += 1
                if callback:
                    callback(task, answer)
            except Exception as e:
                err = str(e)
                self._chain_results.append({"task": task, "result": err, "ok": False})
                self._report["errors"] += 1
                if callback:
                    callback(task, f"❌ {err}")
            time.sleep(0.3)  # небольшая пауза между задачами

        self._running = False

    def stop(self) -> str:
        """Остановить выполнение цепочки задач."""
        if not self._running:
            return "ℹ️ Агент не запущен."
        self._running = False
        return "🛑 Агент остановлен."

    # ──────────────────────────────────────────────────────────────
    # ОТЧЁТ
    # ──────────────────────────────────────────────────────────────

    def report(self) -> str:
        """Вернуть отчёт о состоянии агента."""
        status = "🟢 Работает" if self._running else "⚫ Простаивает"
        elapsed = ""
        if self._report["started_at"]:
            secs = int(time.time() - self._report["started_at"])
            elapsed = f" | Время: {secs}с"

        lines = [
            f"🤖 АГЕНТ АРГОСА",
            f"  Статус: {status}{elapsed}",
            f"  Задач выполнено: {self._report['tasks_done']}",
            f"  Ошибок: {self._report['errors']}",
            f"  Последняя задача: {self._report['last_task'] or '—'}",
        ]

        if self._chain_results:
            lines.append("  Результаты:")
            for r in self._chain_results[-5:]:  # последние 5
                icon = "✅" if r["ok"] else "❌"
                lines.append(f"    {icon} {r['task'][:40]} → {r['result'][:60]}")

        with self._reminder_lock:
            active_rem = sum(1 for r in self._reminders if not r["fired"])
        lines.append(f"  Активных напоминаний: {active_rem}")

        return "\n".join(lines)

    def status(self) -> str:
        """Краткий статус для встраивания в другие отчёты."""
        s = "работает" if self._running else "простаивает"
        return (
            f"Агент: {s} | "
            f"задач: {self._report['tasks_done']} | "
            f"ошибок: {self._report['errors']}"
        )
