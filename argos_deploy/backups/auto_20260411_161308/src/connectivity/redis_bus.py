"""
redis_bus.py — Redis Pub/Sub транспорт для ARGOS P2P.

Простой синхронный обёрткой:
  - publish(channel, payload_dict)
  - callback per channel
  - start()/stop() с отдельным потоком подписки
"""

from __future__ import annotations

import json
import threading
import time
from typing import Callable, Dict, Optional

import redis


class RedisBus:
    def __init__(
        self,
        redis_url: Optional[str] = None,
        host: str = "localhost",
        port: int = 6379,
        password: Optional[str] = None,
        prefix: str = "argos",
    ):
        self.redis_url = (redis_url or "").strip() or None
        self.host = host
        self.port = port
        self.password = password
        self.prefix = prefix.rstrip(".")
        if self.redis_url:
            self._redis = redis.from_url(self.redis_url, decode_responses=True)
        else:
            self._redis = redis.Redis(
                host=host,
                port=port,
                password=password,
                decode_responses=True,
            )
        self._pubsub = self._redis.pubsub()
        self._callbacks: Dict[str, Callable[[dict], None]] = {}
        self._thread: Optional[threading.Thread] = None
        self._stop = threading.Event()

    def channel(self, name: str) -> str:
        return f"{self.prefix}.{name}"

    def register(self, name: str, cb: Callable[[dict], None]):
        ch = self.channel(name)
        self._callbacks[ch] = cb

    def start(self):
        if self._thread and self._thread.is_alive():
            return
        channels = list(self._callbacks.keys())
        if channels:
            self._pubsub.subscribe(channels)
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, daemon=True, name="RedisBus")
        self._thread.start()

    def stop(self):
        self._stop.set()
        try:
            self._pubsub.close()
        except Exception:
            pass

    def publish(self, name: str, payload: dict):
        ch = self.channel(name)
        try:
            self._redis.publish(ch, json.dumps(payload, ensure_ascii=False))
        except Exception:
            pass

    # internal
    def _loop(self):
        while not self._stop.is_set():
            try:
                msg = self._pubsub.get_message(ignore_subscribe_messages=True, timeout=1.0)
                if not msg:
                    continue
                ch = msg.get("channel")
                data = msg.get("data")
                if ch in self._callbacks:
                    try:
                        obj = json.loads(data)
                    except Exception:
                        obj = {"raw": data}
                    try:
                        self._callbacks[ch](obj)
                    except Exception:
                        pass
            except Exception:
                time.sleep(1.0)
