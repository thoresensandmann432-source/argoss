"""
src/event_bus.py — Шина событий ARGOS
=====================================
EventBus с async/sync публикацией, историей, wildcard-подпиской.
"""
from __future__ import annotations

import threading
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Callable, Optional

__all__ = ["EventBus", "Event", "Events", "get_bus"]

_global_bus: Optional["EventBus"] = None


def get_bus() -> "EventBus":
    global _global_bus
    if _global_bus is None:
        _global_bus = EventBus()
    return _global_bus


@dataclass
class Event:
    topic: str
    data: dict
    timestamp: float = field(default_factory=time.time)


class Events:
    """Константы тем событий."""
    # P2P
    P2P_NODE_JOINED   = "p2p.node.joined"
    P2P_NODE_LEFT     = "p2p.node.left"
    P2P_SKILL_SYNCED  = "p2p.skill.synced"
    # DAG
    DAG_STARTED       = "dag.started"
    DAG_NODE_DONE     = "dag.node.done"
    DAG_COMPLETED     = "dag.completed"
    # Система
    SYSTEM_ALERT      = "system.alert"
    SYSTEM_SHUTDOWN   = "system.shutdown"
    CORE_COMMAND      = "core.command"
    CORE_RESPONSE     = "core.response"
    # IoT
    IOT_DEVICE_ONLINE = "iot.device.online"
    IOT_SENSOR_UPDATE = "iot.sensor.update"


class EventBus:
    """
    Шина событий ARGOS.

    Поддерживает:
    - Синхронную и асинхронную доставку
    - Wildcard-подписку (topic="*")
    - Историю последних N событий по теме
    - Потокобезопасность
    """

    def __init__(self, history_size: int = 100) -> None:
        self._handlers: dict[str, list[Callable]] = {}
        self._history: dict[str, deque] = {}
        self._history_size = history_size
        self._lock = threading.Lock()
        self._running = True

    def subscribe(self, topic: str, handler: Callable[[Event], None]) -> None:
        with self._lock:
            self._handlers.setdefault(topic, []).append(handler)

    def unsubscribe(self, topic: str, handler: Callable) -> None:
        with self._lock:
            if topic in self._handlers:
                self._handlers[topic] = [h for h in self._handlers[topic] if h != handler]

    def publish(self, topic: str, data: dict, sync: bool = False) -> None:
        event = Event(topic=topic, data=data)
        with self._lock:
            self._history.setdefault(topic, deque(maxlen=self._history_size)).append(event)
            handlers = list(self._handlers.get(topic, []))
            wildcard = list(self._handlers.get("*", []))

        all_handlers = handlers + wildcard
        if sync:
            for h in all_handlers:
                try:
                    h(event)
                except Exception:
                    pass
        else:
            t = threading.Thread(
                target=self._dispatch, args=(event, all_handlers), daemon=True
            )
            t.start()

    # emit = publish (алиас)
    def emit(self, topic: str, data: dict) -> None:
        self.publish(topic, data, sync=False)

    def history(self, topic: str, limit: int = 50) -> list[Event]:
        with self._lock:
            dq = self._history.get(topic, deque())
            return list(dq)[-limit:]

    def stop(self) -> None:
        self._running = False

    @staticmethod
    def _dispatch(event: Event, handlers: list[Callable]) -> None:
        for h in handlers:
            try:
                h(event)
            except Exception:
                pass
