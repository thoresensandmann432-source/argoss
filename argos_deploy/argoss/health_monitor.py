"""
src/health_monitor.py — Фоновый монитор здоровья системы ARGOS
===============================================================
Периодически собирает метрики CPU/RAM/диск/SQLite и хранит историю.
Вызывает alert_callback при переходе в состояние degraded/critical.
"""
from __future__ import annotations

import os
import sqlite3
import threading
import time
from dataclasses import dataclass, field
from typing import Callable, Optional

__all__ = [
    "HealthMonitor",
    "HealthSnapshot",
    "ComponentStatus",
]

_ALERT_COOLDOWN_SEC = 300  # 5 минут между алертами


@dataclass
class ComponentStatus:
    """Статус одного компонента системы."""
    name: str
    ok: bool
    detail: str = ""


@dataclass
class HealthSnapshot:
    """Снимок состояния системы в момент времени."""
    timestamp: float
    status: str          # "healthy" | "degraded" | "critical"
    cpu_pct: float
    ram_pct: float
    disk_pct: float
    components: list[ComponentStatus]
    uptime_sec: float

    def to_dict(self) -> dict:
        return {
            "timestamp": self.timestamp,
            "status": self.status,
            "cpu_pct": self.cpu_pct,
            "ram_pct": self.ram_pct,
            "disk_pct": self.disk_pct,
            "uptime_sec": self.uptime_sec,
            "components": [
                {"name": c.name, "ok": c.ok, "detail": c.detail}
                for c in self.components
            ],
        }


class HealthMonitor:
    """
    Фоновый монитор здоровья ARGOS.

    Запускается в daemon-потоке и периодически собирает метрики.
    При деградации вызывает alert_callback(message: str).
    """

    def __init__(
        self,
        db_path: str = "data/argos.db",
        interval: float = 30.0,
        alert_callback: Optional[Callable[[str], None]] = None,
    ) -> None:
        self._db_path = db_path
        self._interval = interval
        self._alert_callback = alert_callback
        self._start_time = time.time()
        self._history: list[HealthSnapshot] = []
        self._max_history = 100
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._lock = threading.Lock()
        self._last_alert_time = 0.0

    # ── Управление ────────────────────────────────────────────────────────────

    def start(self) -> None:
        """Запускает мониторинг в фоновом потоке."""
        self._running = True
        self._thread = threading.Thread(
            target=self._loop,
            daemon=True,
            name="ArgosHealthMonitor",
        )
        self._thread.start()

    def stop(self) -> None:
        """Останавливает мониторинг."""
        self._running = False
        if self._thread:
            self._thread.join(timeout=5)

    # ── Данные ────────────────────────────────────────────────────────────────

    def latest(self) -> Optional[HealthSnapshot]:
        """Возвращает последний снимок или None."""
        with self._lock:
            return self._history[-1] if self._history else None

    def history(self, limit: int = 50) -> list[HealthSnapshot]:
        """Возвращает последние N снимков."""
        with self._lock:
            return list(self._history[-limit:])

    # ── Внутренние методы ─────────────────────────────────────────────────────

    def _loop(self) -> None:
        while self._running:
            try:
                snap = self._collect()
                with self._lock:
                    self._history.append(snap)
                    if len(self._history) > self._max_history:
                        self._history = self._history[-self._max_history // 2:]
                self._check_alerts(snap)
            except Exception:
                pass
            # Прерываемый sleep
            deadline = time.time() + self._interval
            while self._running and time.time() < deadline:
                time.sleep(min(1.0, deadline - time.time()))

    def _collect(self) -> HealthSnapshot:
        """Собирает метрики системы."""
        cpu_pct = 0.0
        ram_pct = 0.0
        disk_pct = 0.0

        try:
            import psutil
            cpu_pct = psutil.cpu_percent(interval=0.1)
            ram_pct = psutil.virtual_memory().percent
            disk_pct = psutil.disk_usage("/").percent
        except Exception:
            pass

        components = [self._check_db()]

        # Определяем общий статус
        if cpu_pct > 90 or ram_pct > 90 or disk_pct > 95:
            status = "critical"
        elif cpu_pct > 75 or ram_pct > 80 or disk_pct > 85:
            status = "degraded"
        elif any(not c.ok for c in components):
            status = "degraded"
        else:
            status = "healthy"

        return HealthSnapshot(
            timestamp=time.time(),
            status=status,
            cpu_pct=cpu_pct,
            ram_pct=ram_pct,
            disk_pct=disk_pct,
            components=components,
            uptime_sec=time.time() - self._start_time,
        )

    def _check_db(self) -> ComponentStatus:
        """Проверяет доступность SQLite БД."""
        try:
            conn = sqlite3.connect(self._db_path, timeout=2)
            conn.execute("SELECT 1")
            conn.close()
            return ComponentStatus("sqlite", True, self._db_path)
        except Exception as e:
            return ComponentStatus("sqlite", False, str(e)[:60])

    def _check_alerts(self, snap: HealthSnapshot) -> None:
        """Отправляет алерт если система деградировала (с кулдауном)."""
        if snap.status not in ("degraded", "critical"):
            return
        if not self._alert_callback:
            return
        now = time.time()
        if now - self._last_alert_time < _ALERT_COOLDOWN_SEC:
            return
        self._last_alert_time = now
        msg = (
            f"⚠️ ARGOS HealthMonitor: {snap.status.upper()}\n"
            f"CPU: {snap.cpu_pct:.1f}% | RAM: {snap.ram_pct:.1f}% | Disk: {snap.disk_pct:.1f}%"
        )
        try:
            self._alert_callback(msg)
        except Exception:
            pass
