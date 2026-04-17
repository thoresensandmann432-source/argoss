"""
src/graceful_shutdown.py — Корректное завершение ARGOS
=======================================================
Регистрирует callback-и с приоритетами и вызывает их
в порядке убывания приоритета при завершении процесса.
"""

from __future__ import annotations

import signal
import threading
import time
from dataclasses import dataclass, field
from typing import Callable, Optional

__all__ = ["GracefulShutdown", "get_shutdown_manager"]

_global_manager: Optional["GracefulShutdown"] = None


def get_shutdown_manager(timeout: float = 10.0) -> "GracefulShutdown":
    """Возвращает глобальный менеджер завершения (singleton)."""
    global _global_manager
    if _global_manager is None:
        _global_manager = GracefulShutdown(timeout=timeout)
    return _global_manager


@dataclass(order=True)
class _ShutdownCallback:
    priority: int
    name: str = field(compare=False)
    fn: Callable[[], None] = field(compare=False)


class GracefulShutdown:
    """
    Менеджер корректного завершения процесса.

    Callback-и вызываются в порядке убывания приоритета
    (высокий приоритет = вызывается первым).

    Пример::

        mgr = GracefulShutdown(timeout=5)
        mgr.register("stop_monitoring", monitor.stop, priority=8)
        mgr.register("save_state",      core.save,    priority=5)
        mgr.setup_signals()     # SIGTERM / SIGINT → mgr.trigger()
        mgr.trigger()
        mgr.wait()
    """

    def __init__(self, timeout: float = 10.0) -> None:
        self._timeout = timeout
        self._callbacks: list[_ShutdownCallback] = []
        self._triggered = False
        self._done = threading.Event()
        self._lock = threading.Lock()

    # ── Регистрация ───────────────────────────────────────────────────────────

    def register(
        self,
        name: str,
        fn: Callable[[], None],
        priority: int = 5,
    ) -> None:
        """Добавляет callback в список завершения."""
        with self._lock:
            self._callbacks.append(_ShutdownCallback(priority=-priority, name=name, fn=fn))
            self._callbacks.sort()  # сортируем по -priority (наименьшее = высший приоритет)

    # ── Управление ────────────────────────────────────────────────────────────

    def trigger(self) -> None:
        """Запускает последовательность завершения (идемпотентно)."""
        with self._lock:
            if self._triggered:
                return
            self._triggered = True

        t = threading.Thread(target=self._run, daemon=True, name="GracefulShutdown")
        t.start()

    def wait(self, timeout: Optional[float] = None) -> None:
        """Блокирует до завершения всех callback-ов или таймаута."""
        self._done.wait(timeout=timeout or self._timeout + 1)

    def setup_signals(self) -> None:
        """Подключает SIGTERM/SIGINT к trigger()."""
        try:
            signal.signal(signal.SIGTERM, lambda *_: self.trigger())
            signal.signal(signal.SIGINT, lambda *_: self.trigger())
        except (OSError, ValueError):
            # В потоках или на Windows некоторые сигналы недоступны
            pass

    # ── Внутренние методы ─────────────────────────────────────────────────────

    def _run(self) -> None:
        deadline = time.time() + self._timeout

        with self._lock:
            callbacks = list(self._callbacks)

        for cb in callbacks:
            if time.time() > deadline:
                break
            try:
                cb.fn()
            except Exception:
                pass

        self._done.set()
