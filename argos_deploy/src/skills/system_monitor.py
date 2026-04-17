"""
system_monitor.py — Системный монитор ARGOS
═══════════════════════════════════════════════════════
Мониторинг ресурсов в реальном времени:
  • CPU: нагрузка, частота, ядра
  • RAM: использование, своп
  • Диск: занято/свободно по разделам
  • Температура: CPU, GPU (если доступно)
  • Сеть: трафик, скорость
  • Процессы: топ по CPU/RAM
  • Алерты: авто-уведомление в Telegram при превышении порогов
═══════════════════════════════════════════════════════
"""

from __future__ import annotations

SKILL_DESCRIPTION = "Мониторинг CPU/RAM/диска/сети в реальном времени"

import os
import sys
import time
import json
import threading
from typing import Optional

try:
    import psutil
    _PSUTIL = True
except ImportError:
    _PSUTIL = False

try:
    import requests
    _REQ = True
except ImportError:
    _REQ = False

from src.argos_logger import get_logger

log = get_logger("argos.sysmon")

THRESHOLDS_FILE = "config/sysmon_thresholds.json"
METRICS_FILE    = "data/sysmon_metrics.json"

DEFAULT_THRESHOLDS = {
    "cpu_pct":    85.0,   # % загрузки CPU → алерт
    "ram_pct":    90.0,   # % RAM → алерт
    "disk_pct":   90.0,   # % диска → алерт
    "temp_cpu":   80.0,   # °C → алерт
    "interval":   30,     # секунд между проверками
}


class SystemMonitor:
    """Мониторинг ресурсов системы с алертами в Telegram."""

    def __init__(self, core=None):
        self.core       = core
        self._running   = False
        self._thresholds = self._load_thresholds()
        self._last_alert: dict[str, float] = {}   # тип → время последнего алерта
        self._alert_cooldown = 300                # сек между повторными алертами
        self._tg_token  = os.getenv("TELEGRAM_BOT_TOKEN", "")
        self._tg_chat   = os.getenv("USER_ID", "")

    def _load_thresholds(self) -> dict:
        merged = dict(DEFAULT_THRESHOLDS)
        if os.path.exists(THRESHOLDS_FILE):
            try:
                t = json.load(open(THRESHOLDS_FILE, encoding="utf-8"))
                merged.update(t)
            except Exception:
                pass
        # Применяем порог RAM из .env (ARGOS_RAM_ALERT_PCT=90 для 26GB-машины)
        _ram_env = os.getenv("ARGOS_RAM_ALERT_PCT")
        if _ram_env:
            try:
                merged["ram_pct"] = float(_ram_env)
            except ValueError:
                pass
        return merged

    def save_thresholds(self):
        os.makedirs("config", exist_ok=True)
        json.dump(self._thresholds, open(THRESHOLDS_FILE, "w", encoding="utf-8"), indent=2)

    # ── Сбор метрик ──────────────────────────────────────────────────────────

    def cpu_info(self) -> dict:
        if not _PSUTIL:
            return self._cpu_fallback()
        return {
            "pct":     psutil.cpu_percent(interval=0.5),
            "cores":   psutil.cpu_count(logical=False),
            "threads": psutil.cpu_count(logical=True),
            "freq_mhz": round(psutil.cpu_freq().current, 0) if psutil.cpu_freq() else 0,
        }

    def _cpu_fallback(self) -> dict:
        """CPU без psutil — через /proc/stat (Linux)."""
        try:
            lines = open("/proc/stat").readlines()
            vals  = [int(x) for x in lines[0].split()[1:]]
            idle1, total1 = vals[3], sum(vals)
            time.sleep(0.1)
            lines = open("/proc/stat").readlines()
            vals  = [int(x) for x in lines[0].split()[1:]]
            idle2, total2 = vals[3], sum(vals)
            pct = round(100 * (1 - (idle2 - idle1) / max(total2 - total1, 1)), 1)
            return {"pct": pct, "cores": os.cpu_count() or 1}
        except Exception:
            return {"pct": 0, "cores": os.cpu_count() or 1}

    def ram_info(self) -> dict:
        if not _PSUTIL:
            return self._ram_fallback()
        vm = psutil.virtual_memory()
        sw = psutil.swap_memory()
        return {
            "total_mb":  round(vm.total / 1024**2),
            "used_mb":   round(vm.used  / 1024**2),
            "free_mb":   round(vm.available / 1024**2),
            "pct":       vm.percent,
            "swap_mb":   round(sw.used / 1024**2),
            "swap_pct":  sw.percent,
        }

    def _ram_fallback(self) -> dict:
        try:
            info = {}
            for line in open("/proc/meminfo"):
                k, v = line.split(":", 1)
                info[k.strip()] = int(v.strip().split()[0])
            total = info.get("MemTotal", 0)
            avail = info.get("MemAvailable", 0)
            used  = total - avail
            pct   = round(100 * used / max(total, 1), 1)
            return {"total_mb": total//1024, "used_mb": used//1024,
                    "free_mb": avail//1024, "pct": pct, "swap_mb": 0, "swap_pct": 0}
        except Exception:
            return {"total_mb": 0, "used_mb": 0, "free_mb": 0, "pct": 0, "swap_mb": 0, "swap_pct": 0}

    def disk_info(self) -> list[dict]:
        if not _PSUTIL:
            return self._disk_fallback()
        # Если заданы конкретные диски в .env (DISK_MONITOR_PATHS=C:/,D:/,E:/,H:/)
        disk_paths_env = os.getenv("DISK_MONITOR_PATHS", "")
        if disk_paths_env:
            explicit_paths = [p.strip() for p in disk_paths_env.split(",") if p.strip()]
        else:
            explicit_paths = [part.mountpoint for part in psutil.disk_partitions(all=False)]
        disks = []
        for path in explicit_paths:
            try:
                usage = psutil.disk_usage(path)
                disks.append({
                    "mount":    path,
                    "device":   path,
                    "fstype":   "",
                    "total_gb": round(usage.total / 1024**3, 1),
                    "used_gb":  round(usage.used  / 1024**3, 1),
                    "free_gb":  round(usage.free  / 1024**3, 1),
                    "pct":      usage.percent,
                })
            except Exception:
                continue
        return disks

    def _disk_fallback(self) -> list[dict]:
        try:
            import subprocess
            out = subprocess.check_output(["df", "-h", "/"], text=True).splitlines()
            if len(out) > 1:
                parts = out[1].split()
                return [{"mount": "/", "total_gb": parts[1], "used_gb": parts[2],
                         "free_gb": parts[3], "pct": int(parts[4].strip("%"))}]
        except Exception:
            pass
        return []

    def temperature(self) -> dict:
        temps = {}
        if not _PSUTIL:
            return self._temp_fallback()
        try:
            sensors = psutil.sensors_temperatures()
            for name, entries in (sensors or {}).items():
                for entry in entries:
                    if entry.current and entry.current > 0:
                        temps[f"{name}/{entry.label or 'core'}"] = round(entry.current, 1)
        except Exception:
            pass
        return temps

    def _temp_fallback(self) -> dict:
        """Температура через /sys/class/thermal (Linux/RPi)."""
        temps = {}
        try:
            for i in range(5):
                path = f"/sys/class/thermal/thermal_zone{i}/temp"
                if os.path.exists(path):
                    val = int(open(path).read().strip()) / 1000
                    temps[f"zone{i}"] = round(val, 1)
        except Exception:
            pass
        return temps

    def net_info(self) -> dict:
        if not _PSUTIL:
            return {}
        io = psutil.net_io_counters()
        return {
            "bytes_sent_mb": round(io.bytes_sent / 1024**2, 1),
            "bytes_recv_mb": round(io.bytes_recv / 1024**2, 1),
            "packets_sent":  io.packets_sent,
            "packets_recv":  io.packets_recv,
        }

    def top_processes(self, n: int = 5) -> list[dict]:
        if not _PSUTIL:
            return []
        procs = []
        for p in psutil.process_iter(["pid", "name", "cpu_percent", "memory_percent"]):
            try:
                procs.append(p.info)
            except Exception:
                pass
        return sorted(procs, key=lambda x: x.get("cpu_percent", 0), reverse=True)[:n]

    # ── Форматирование отчёта ─────────────────────────────────────────────────

    def report(self) -> str:
        cpu  = self.cpu_info()
        ram  = self.ram_info()
        disk = self.disk_info()
        temp = self.temperature()

        # CPU бар
        cpu_bar = self._bar(cpu.get("pct", 0))
        ram_bar = self._bar(ram.get("pct", 0))

        lines = [
            "🖥  СИСТЕМНЫЙ МОНИТОР ARGOS",
            "─" * 36,
            f"⚡ CPU:  {cpu.get('pct', 0):5.1f}%  {cpu_bar}",
        ]
        if cpu.get("freq_mhz"):
            lines.append(f"   Частота: {cpu['freq_mhz']:.0f} MHz  |  Ядер: {cpu.get('cores',1)} ({cpu.get('threads',1)} потоков)")

        lines.append(f"🧠 RAM:  {ram.get('pct', 0):5.1f}%  {ram_bar}")
        lines.append(f"   {ram.get('used_mb',0)} / {ram.get('total_mb',0)} МБ  |  Своп: {ram.get('swap_mb',0)} МБ")

        if disk:
            lines.append("💾 Диски:")
            for d in disk[:4]:
                bar = self._bar(d.get("pct", 0))
                lines.append(f"   {d['mount']:<12} {d.get('pct',0):4.0f}%  {bar}  {d.get('free_gb',0)} ГБ свободно")

        if temp:
            temp_str = "  ".join(f"{k.split('/')[-1]}={v}°C" for k, v in list(temp.items())[:4])
            lines.append(f"🌡  Темп: {temp_str}")

        net = self.net_info()
        if net:
            lines.append(f"🌐 Сеть: ↑{net['bytes_sent_mb']} МБ  ↓{net['bytes_recv_mb']} МБ")

        lines.append("─" * 36)
        lines.append(f"🕐 {time.strftime('%d.%m.%Y %H:%M:%S')}")

        # Алерты
        alerts = self._check_thresholds(cpu, ram, disk, temp)
        if alerts:
            lines.append("⚠️  " + " | ".join(alerts))

        return "\n".join(lines)

    @staticmethod
    def _bar(pct: float, width: int = 12) -> str:
        filled = int(pct / 100 * width)
        bar = "█" * filled + "░" * (width - filled)
        color = "🟢" if pct < 70 else "🟡" if pct < 85 else "🔴"
        return f"{color}[{bar}]"

    # ── Алерты ───────────────────────────────────────────────────────────────

    def _check_thresholds(self, cpu, ram, disk, temp) -> list[str]:
        alerts = []
        now = time.time()

        def _should_alert(key: str) -> bool:
            last = self._last_alert.get(key, 0)
            if now - last > self._alert_cooldown:
                self._last_alert[key] = now
                return True
            return False

        if cpu.get("pct", 0) > self._thresholds["cpu_pct"] and _should_alert("cpu"):
            alerts.append(f"CPU {cpu['pct']:.0f}%")
        if ram.get("pct", 0) > self._thresholds["ram_pct"] and _should_alert("ram"):
            alerts.append(f"RAM {ram['pct']:.0f}%")
        for d in disk:
            if d.get("pct", 0) > self._thresholds["disk_pct"] and _should_alert(f"disk_{d['mount']}"):
                alerts.append(f"Диск {d['mount']} {d['pct']:.0f}%")
        for k, v in temp.items():
            if v > self._thresholds["temp_cpu"] and _should_alert(f"temp_{k}"):
                alerts.append(f"🌡{k}={v}°C")

        if alerts:
            self._send_alert("⚠️ ARGOS АЛЕРТ: " + ", ".join(alerts))
        return alerts

    def _send_alert(self, text: str):
        """Отправляет алерт в Telegram."""
        if not (_REQ and self._tg_token and self._tg_chat):
            log.warning("Alert: %s", text)
            return
        try:
            requests.post(
                f"https://api.telegram.org/bot{self._tg_token}/sendMessage",
                json={"chat_id": self._tg_chat, "text": text},
                timeout=5,
            )
        except Exception as e:
            log.warning("Alert send failed: %s", e)

    # ── Фоновый мониторинг ────────────────────────────────────────────────────

    def start(self) -> str:
        if self._running:
            return "⚠️ Монитор уже запущен"
        self._running = True
        threading.Thread(target=self._loop, daemon=True, name="sysmon").start()
        interval = self._thresholds["interval"]
        log.info("SystemMonitor запущен, интервал %d сек", interval)
        return f"✅ Системный монитор запущен (интервал {interval} сек)"

    def stop(self) -> str:
        self._running = False
        return "⏹ Системный монитор остановлен"

    def _loop(self):
        while self._running:
            try:
                cpu  = self.cpu_info()
                ram  = self.ram_info()
                disk = self.disk_info()
                temp = self.temperature()
                self._check_thresholds(cpu, ram, disk, temp)
                # Сохраняем последние метрики
                metrics = {"ts": time.time(), "cpu": cpu, "ram": ram,
                           "disk": disk[:2], "temp": temp}
                try:
                    json.dump(metrics, open(METRICS_FILE, "w"), ensure_ascii=False)
                except Exception:
                    pass
            except Exception as e:
                # Suppress performance counter warnings - non-critical
                pass
            time.sleep(self._thresholds.get("interval", 30))

    def set_threshold(self, key: str, value: float) -> str:
        if key not in self._thresholds:
            return f"❌ Неизвестный параметр. Доступные: {', '.join(self._thresholds.keys())}"
        self._thresholds[key] = value
        self.save_thresholds()
        return f"✅ Порог {key} = {value}"

    def execute(self) -> str:
        return self.report()
