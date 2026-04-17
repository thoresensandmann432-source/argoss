"""
iot_watchdog.py — IoT Watchdog ARGOS
═══════════════════════════════════════════════════════
Мониторинг доступности IoT-устройств с алертами:
  • Ping-мониторинг IP-устройств
  • MQTT-топик heartbeat
  • COM-порт / Serial-устройства
  • Telegram-алерт при отключении/восстановлении
  • Авто-перезапуск сервисов (опционально)
  • История событий с временными метками
═══════════════════════════════════════════════════════
"""

from __future__ import annotations

SKILL_DESCRIPTION = "Мониторинг доступности IoT-устройств + алерты"

import os
import json
import time
import socket
import subprocess
import platform
import threading
from typing import Optional

try:
    import requests
    _REQ = True
except ImportError:
    _REQ = False

try:
    import serial.tools.list_ports
    _SERIAL = True
except ImportError:
    _SERIAL = False

from src.argos_logger import get_logger

log = get_logger("argos.watchdog")

DEVICES_FILE = "config/watchdog_devices.json"
EVENTS_FILE  = "data/watchdog_events.json"
os.makedirs("data", exist_ok=True)
os.makedirs("config", exist_ok=True)


class WatchedDevice:
    """Одно наблюдаемое устройство."""

    def __init__(self, device_id: str, dtype: str, target: str,
                 name: str = "", interval: int = 30, timeout: int = 5,
                 auto_restart: str = ""):
        self.id           = device_id
        self.type         = dtype          # "ping" | "mqtt" | "serial" | "tcp"
        self.target       = target         # IP, COM-порт, MQTT топик, host:port
        self.name         = name or device_id
        self.interval     = interval       # секунд между проверками
        self.timeout      = timeout        # таймаут проверки
        self.auto_restart = auto_restart   # команда для авто-перезапуска
        self.status       = "unknown"      # "online" | "offline" | "unknown"
        self.last_seen: Optional[float] = None
        self.last_check: Optional[float] = None
        self.fail_count   = 0
        self.ok_count     = 0

    def to_dict(self) -> dict:
        return {
            "id": self.id, "type": self.type, "target": self.target,
            "name": self.name, "interval": self.interval, "timeout": self.timeout,
            "auto_restart": self.auto_restart, "status": self.status,
            "last_seen": self.last_seen, "fail_count": self.fail_count,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "WatchedDevice":
        dev = cls(d["id"], d["type"], d["target"],
                  d.get("name", ""), d.get("interval", 30), d.get("timeout", 5),
                  d.get("auto_restart", ""))
        dev.status     = d.get("status", "unknown")
        dev.last_seen  = d.get("last_seen")
        dev.fail_count = d.get("fail_count", 0)
        return dev


class IoTWatchdog:
    """IoT Watchdog — следит за доступностью устройств."""

    def __init__(self, core=None):
        self.core      = core
        self._devices: dict[str, WatchedDevice] = {}
        self._running  = False
        self._events: list = []
        self._tg_token = os.getenv("TELEGRAM_BOT_TOKEN", "")
        self._tg_chat  = os.getenv("USER_ID", "")
        self._load()

    # ── Устройства ────────────────────────────────────────────────────────────

    def _load(self):
        if os.path.exists(DEVICES_FILE):
            try:
                with open(DEVICES_FILE, encoding="utf-8") as f:
                    data = json.load(f)
                for d in data:
                    dev = WatchedDevice.from_dict(d)
                    self._devices[dev.id] = dev
                log.info("Watchdog: загружено %d устройств", len(self._devices))
            except Exception as e:
                log.warning("Watchdog load: %s", e)
        if os.path.exists(EVENTS_FILE):
            try:
                with open(EVENTS_FILE, encoding="utf-8") as f:
                    self._events = json.load(f)[-500:]
            except Exception:
                pass

    def _save(self):
        try:
            with open(DEVICES_FILE, "w", encoding="utf-8") as f:
                json.dump([d.to_dict() for d in self._devices.values()],
                          f, indent=2, ensure_ascii=False)
            with open(EVENTS_FILE, "w", encoding="utf-8") as f:
                json.dump(self._events[-500:], f, indent=2, ensure_ascii=False)
        except Exception as e:
            log.warning("Watchdog save: %s", e)

    def add_device(self, device_id: str, dtype: str, target: str,
                   name: str = "", interval: int = 30) -> str:
        """Добавляет устройство в мониторинг."""
        valid_types = ("ping", "tcp", "serial", "mqtt", "http")
        dtype = dtype.lower()
        if dtype not in valid_types:
            return f"❌ Тип устройства: {', '.join(valid_types)}"

        dev = WatchedDevice(device_id, dtype, target, name or device_id, interval)
        self._devices[device_id] = dev
        self._save()
        log.info("Watchdog: добавлено %s [%s] %s", device_id, dtype, target)
        return f"✅ Устройство '{name or device_id}' добавлено в мониторинг\n   Тип: {dtype}  Цель: {target}"

    def remove_device(self, device_id: str) -> str:
        if device_id not in self._devices:
            return f"❌ Устройство '{device_id}' не найдено"
        name = self._devices.pop(device_id).name
        self._save()
        return f"✅ '{name}' удалено из мониторинга"

    # ── Проверки ──────────────────────────────────────────────────────────────

    def check_device(self, dev: WatchedDevice) -> bool:
        """Проверяет доступность устройства. Возвращает True если онлайн."""
        dev.last_check = time.time()
        try:
            if dev.type == "ping":
                return self._ping(dev.target, dev.timeout)
            elif dev.type == "tcp":
                return self._tcp_check(dev.target, dev.timeout)
            elif dev.type == "serial":
                return self._serial_check(dev.target)
            elif dev.type == "http":
                return self._http_check(dev.target, dev.timeout)
            elif dev.type == "mqtt":
                return self._mqtt_check(dev.target, dev.timeout)
        except Exception as e:
            log.warning("Check %s: %s", dev.id, e)
        return False

    @staticmethod
    def _ping(host: str, timeout: int) -> bool:
        flag = "-n" if platform.system() == "Windows" else "-c"
        w_flag = ["-w", str(timeout * 1000)] if platform.system() == "Windows" else ["-W", str(timeout)]
        try:
            result = subprocess.run(
                ["ping", flag, "1"] + w_flag + [host],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                timeout=timeout + 2,
            )
            return result.returncode == 0
        except Exception:
            return False

    @staticmethod
    def _tcp_check(target: str, timeout: int) -> bool:
        """target = host:port"""
        try:
            host, port = target.rsplit(":", 1)
            with socket.create_connection((host, int(port)), timeout=timeout):
                return True
        except Exception:
            return False

    @staticmethod
    def _serial_check(port: str) -> bool:
        """Проверяет наличие COM/USB порта."""
        if not _SERIAL:
            return os.path.exists(port)
        ports = [p.device for p in serial.tools.list_ports.comports()]
        return port in ports

    @staticmethod
    def _http_check(url: str, timeout: int) -> bool:
        if not _REQ:
            return False
        try:
            r = requests.head(url, timeout=timeout, allow_redirects=True)
            return r.status_code < 500
        except Exception:
            return False

    @staticmethod
    def _mqtt_check(broker: str, timeout: int) -> bool:
        """Проверяет TCP-соединение с MQTT-брокером."""
        try:
            host = broker.split(":")[0].replace("mqtt://", "")
            port = int(broker.split(":")[-1]) if ":" in broker else 1883
            with socket.create_connection((host, port), timeout=timeout):
                return True
        except Exception:
            return False

    # ── Цикл мониторинга ──────────────────────────────────────────────────────

    def _monitor_device(self, dev: WatchedDevice):
        """Поток для одного устройства."""
        while self._running and dev.id in self._devices:
            online = self.check_device(dev)
            prev_status = dev.status

            if online:
                dev.ok_count += 1
                dev.fail_count = 0
                dev.last_seen = time.time()
                if prev_status != "online":
                    dev.status = "online"
                    self._event(dev, "online", f"✅ Устройство онлайн: {dev.name} [{dev.target}]")
                    if prev_status == "offline":
                        self._alert(f"✅ {dev.name} восстановлен | {dev.target}")
            else:
                dev.fail_count += 1
                if dev.fail_count >= 2 and prev_status != "offline":
                    dev.status = "offline"
                    self._event(dev, "offline", f"⚠️ Устройство офлайн: {dev.name} [{dev.target}]")
                    self._alert(f"🔴 {dev.name} недоступен | {dev.target} | offline {dev.fail_count}x")
                    if dev.auto_restart:
                        self._auto_restart(dev)

            self._save()
            time.sleep(dev.interval)

    def _auto_restart(self, dev: WatchedDevice):
        """Выполняет команду авто-перезапуска."""
        try:
            log.info("AutoRestart: %s → %s", dev.id, dev.auto_restart)
            import shlex
            # shell=True уязвим к инъекции команд — используем список аргументов
            cmd = shlex.split(dev.auto_restart) if dev.auto_restart else []
            if cmd:
                subprocess.run(cmd, shell=False, timeout=30)
            self._event(dev, "restart", f"🔄 Авто-перезапуск: {dev.auto_restart}")
        except Exception as e:
            log.warning("AutoRestart %s: %s", dev.id, e)

    def _event(self, dev: WatchedDevice, etype: str, msg: str):
        entry = {"ts": time.strftime("%Y-%m-%d %H:%M:%S"), "id": dev.id,
                 "type": etype, "msg": msg}
        self._events.append(entry)
        log.info("%s", msg)

    def _alert(self, text: str):
        if not (_REQ and self._tg_token and self._tg_chat):
            return
        try:
            requests.post(
                f"https://api.telegram.org/bot{self._tg_token}/sendMessage",
                json={"chat_id": self._tg_chat, "text": f"🐕 WatchDog\n{text}"},
                timeout=5,
            )
        except Exception:
            pass

    def start(self) -> str:
        if self._running:
            return "⚠️ Watchdog уже запущен"
        if not self._devices:
            return "⚠️ Нет устройств. Добавь: добавь в watchdog [id] [тип] [цель]"
        self._running = True
        for dev in list(self._devices.values()):
            t = threading.Thread(target=self._monitor_device, args=(dev,),
                                 daemon=True, name=f"wdog_{dev.id}")
            t.start()
        log.info("IoTWatchdog запущен: %d устройств", len(self._devices))
        return f"✅ Watchdog запущен: {len(self._devices)} устройств"

    def stop(self) -> str:
        self._running = False
        return "⏹ Watchdog остановлен"

    # ── Отчёты ────────────────────────────────────────────────────────────────

    def report(self) -> str:
        if not self._devices:
            return (
                "🐕 IoT Watchdog\n"
                "Устройств нет. Добавь:\n"
                "  • добавь в watchdog esp1 ping 192.168.1.100\n"
                "  • добавь в watchdog mqtt1 mqtt 192.168.1.1:1883\n"
                "  • добавь в watchdog usb1 serial COM3"
            )
        lines = [f"🐕 IoT WATCHDOG {'🟢 работает' if self._running else '🔴 остановлен'}",
                 "─" * 40]
        online = offline = unknown = 0
        for dev in self._devices.values():
            icon = {"online": "🟢", "offline": "🔴", "unknown": "⚪"}.get(dev.status, "⚪")
            since = ""
            if dev.last_seen:
                ago = int(time.time() - dev.last_seen)
                since = f"  {ago//60}м назад" if ago < 3600 else f"  {ago//3600}ч назад"
            lines.append(f"  {icon} {dev.name:<20} [{dev.type}] {dev.target}{since}")
            if dev.status == "online":   online += 1
            elif dev.status == "offline": offline += 1
            else: unknown += 1
        lines.append("─" * 40)
        lines.append(f"  🟢 {online} онлайн  |  🔴 {offline} офлайн  |  ⚪ {unknown} неизвестно")
        return "\n".join(lines)

    def events(self, n: int = 15) -> str:
        if not self._events:
            return "📋 Событий нет"
        lines = [f"📋 СОБЫТИЯ WATCHDOG (последние {n}):"]
        for e in self._events[-n:]:
            lines.append(f"  [{e['ts']}] {e['msg']}")
        return "\n".join(lines)

    def execute(self) -> str:
        return self.report()
