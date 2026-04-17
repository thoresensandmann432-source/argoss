"""
system_health.py — Реальный мониторинг системы для Аргоса
src/connectivity/system_health.py

Заменяет и дополняет ArgosSensorBridge: все показатели реальные,
получены через psutil. Никаких заглушек 0%.

Возможности:
  • CPU    — загрузка, частота, температура, ядра
  • RAM    — использование, своп
  • Диск   — все разделы, свободное место
  • Сеть   — интерфейсы, трафик, соединения
  • GPU    — через nvidia-smi (NVIDIA) или ROCm (AMD)
  • Батарея — заряд, статус зарядки
  • Температура — CPU, GPU, диск (lm-sensors)
  • P2P Node Power — честный индекс мощности для авторитета
  • Ввод/Вывод — список доступных устройств (Serial, GPIO, I2C, USB)
"""

from __future__ import annotations

import os
import platform
import shutil
import socket
import subprocess
import time
from pathlib import Path
from typing import Optional

import psutil

from src.argos_logger import get_logger

log = get_logger("argos.health")


# ── РЕАЛЬНЫЕ МЕТРИКИ ──────────────────────────────────────────────────────────

def get_cpu() -> dict:
    """Реальная загрузка CPU."""
    try:
        # interval=0.3 даёт точное значение, не кешированное
        percent = psutil.cpu_percent(interval=0.3)
        freq    = psutil.cpu_freq()
        cores_l = psutil.cpu_count(logical=True)
        cores_p = psutil.cpu_count(logical=False)
        per_core = psutil.cpu_percent(interval=0.1, percpu=True)
        return {
            "percent":   round(percent, 1),
            "free":      round(100.0 - percent, 1),
            "cores_logical":  cores_l,
            "cores_physical": cores_p,
            "freq_mhz":  round(freq.current, 0) if freq else 0,
            "per_core":  [round(c, 1) for c in per_core],
        }
    except Exception as e:
        log.debug("CPU error: %s", e)
        return {"percent": 0, "free": 100, "cores_logical": 1, "cores_physical": 1,
                "freq_mhz": 0, "per_core": []}


def get_ram() -> dict:
    """Реальное использование RAM."""
    try:
        mem  = psutil.virtual_memory()
        swap = psutil.swap_memory()
        return {
            "percent":     round(mem.percent, 1),
            "free":        round(100.0 - mem.percent, 1),
            "total_mb":    mem.total // (1024 * 1024),
            "used_mb":     mem.used  // (1024 * 1024),
            "available_mb": mem.available // (1024 * 1024),
            "swap_percent": round(swap.percent, 1),
            "swap_total_mb": swap.total // (1024 * 1024),
        }
    except Exception as e:
        log.debug("RAM error: %s", e)
        return {"percent": 0, "free": 100, "total_mb": 0, "used_mb": 0,
                "available_mb": 0, "swap_percent": 0, "swap_total_mb": 0}


def get_disks() -> list[dict]:
    """Все смонтированные разделы."""
    result = []
    try:
        for part in psutil.disk_partitions(all=False):
            try:
                usage = psutil.disk_usage(part.mountpoint)
                result.append({
                    "device":     part.device,
                    "mountpoint": part.mountpoint,
                    "fstype":     part.fstype,
                    "total_gb":   round(usage.total / (2**30), 1),
                    "free_gb":    round(usage.free  / (2**30), 1),
                    "percent":    usage.percent,
                })
            except PermissionError:
                pass
    except Exception as e:
        log.debug("Disk error: %s", e)
    return result


def get_network() -> dict:
    """Сетевые интерфейсы и трафик."""
    try:
        addrs   = psutil.net_if_addrs()
        stats   = psutil.net_if_stats()
        io      = psutil.net_io_counters(pernic=True)
        conns   = len(psutil.net_connections(kind="inet"))

        interfaces = []
        for name, addr_list in addrs.items():
            ips = [a.address for a in addr_list
                   if a.family == socket.AF_INET and not a.address.startswith("127.")]
            if not ips:
                continue
            st  = stats.get(name)
            ioc = io.get(name)
            interfaces.append({
                "name":     name,
                "ip":       ips[0] if ips else "",
                "up":       st.isup if st else False,
                "speed_mb": st.speed if st else 0,
                "sent_mb":  round(ioc.bytes_sent / (1024*1024), 1) if ioc else 0,
                "recv_mb":  round(ioc.bytes_recv / (1024*1024), 1) if ioc else 0,
            })
        return {"interfaces": interfaces, "connections": conns}
    except Exception as e:
        log.debug("Network error: %s", e)
        return {"interfaces": [], "connections": 0}


def get_temperature() -> dict:
    """Температура CPU/GPU/диска (через psutil + lm-sensors fallback)."""
    temps = {}
    try:
        sensors = psutil.sensors_temperatures()
        for chip, entries in sensors.items():
            for e in entries:
                key = f"{chip}_{e.label or 'temp'}"
                temps[key] = round(e.current, 1)
    except (AttributeError, Exception):
        pass

    # Fallback: /sys/class/thermal (ARM boards: Orange Pi, RPi)
    if not temps:
        for zone in Path("/sys/class/thermal").glob("thermal_zone*"):
            try:
                t_raw  = (zone / "temp").read_text().strip()
                t_type = (zone / "type").read_text().strip()
                temps[t_type] = round(int(t_raw) / 1000, 1)
            except Exception:
                pass

    return temps


def get_battery() -> Optional[dict]:
    """Заряд батареи (None если стационарный ПК)."""
    try:
        bat = psutil.sensors_battery()
        if bat is None:
            return None
        return {
            "percent": round(bat.percent, 1),
            "charging": bat.power_plugged,
            "time_left_min": round(bat.secsleft / 60) if bat.secsleft > 0 else -1,
        }
    except Exception:
        return None


def get_gpu() -> list[dict]:
    """GPU информация: NVIDIA (nvidia-smi) и AMD (rocm-smi)."""
    gpus = []

    # NVIDIA
    nvidia = shutil.which("nvidia-smi")
    if nvidia:
        try:
            r = subprocess.run(
                [nvidia, "--query-gpu=name,utilization.gpu,memory.used,memory.total,temperature.gpu",
                 "--format=csv,noheader,nounits"],
                capture_output=True, text=True, timeout=5
            )
            for line in r.stdout.strip().splitlines():
                parts = [p.strip() for p in line.split(",")]
                if len(parts) >= 5:
                    gpus.append({
                        "vendor": "NVIDIA",
                        "name":   parts[0],
                        "util":   int(parts[1]) if parts[1].isdigit() else 0,
                        "vram_used_mb":  int(parts[2]) if parts[2].isdigit() else 0,
                        "vram_total_mb": int(parts[3]) if parts[3].isdigit() else 0,
                        "temp_c": int(parts[4]) if parts[4].isdigit() else 0,
                    })
        except Exception:
            pass

    # AMD ROCm
    rocm = shutil.which("rocm-smi")
    if rocm:
        try:
            r = subprocess.run([rocm, "--showallinfo"], capture_output=True, text=True, timeout=5)
            if r.returncode == 0 and "GPU" in r.stdout:
                gpus.append({"vendor": "AMD ROCm", "raw": r.stdout[:200]})
        except Exception:
            pass

    # Fallback: /sys/class/drm
    if not gpus and Path("/sys/class/drm").exists():
        cards = list(Path("/sys/class/drm").glob("card[0-9]"))
        for c in cards[:2]:
            vendor_path = c / "device" / "vendor"
            name_path   = c / "device" / "product_name"
            try:
                vendor = vendor_path.read_text().strip() if vendor_path.exists() else "Unknown"
                name   = name_path.read_text().strip() if name_path.exists() else c.name
                gpus.append({"vendor": vendor, "name": name, "card": c.name})
            except Exception:
                pass

    return gpus


def get_io_devices() -> dict:
    """Ввод/вывод: Serial, GPIO, I2C, SPI, USB, Audio."""
    devices = {
        "serial": [],
        "i2c":    [],
        "spi":    [],
        "gpio":   False,
        "usb":    [],
        "audio":  [],
    }

    # Serial / UART
    try:
        import serial.tools.list_ports
        devices["serial"] = [
            {"port": p.device, "desc": p.description[:50], "hwid": p.hwid[:40]}
            for p in serial.tools.list_ports.comports()
        ]
    except ImportError:
        # Fallback: /dev/tty*
        for tty in sorted(Path("/dev").glob("tty[SUA][0-9]*"))[:8]:
            devices["serial"].append({"port": str(tty), "desc": "serial", "hwid": ""})

    # I2C
    for i2c in sorted(Path("/dev").glob("i2c-*"))[:4]:
        devices["i2c"].append(str(i2c))

    # SPI
    for spi in sorted(Path("/dev").glob("spidev*"))[:4]:
        devices["spi"].append(str(spi))

    # GPIO
    devices["gpio"] = any([
        Path("/sys/class/gpio").exists(),
        Path("/dev/gpiochip0").exists(),
        bool(shutil.which("gpio")),
    ])

    # USB (через lsusb)
    usb_cmd = shutil.which("lsusb")
    if usb_cmd:
        try:
            r = subprocess.run([usb_cmd], capture_output=True, text=True, timeout=5)
            devices["usb"] = [
                line.strip()
                for line in r.stdout.splitlines()
                if line.strip() and "Hub" not in line
            ][:10]
        except Exception:
            pass

    # Audio
    try:
        r = subprocess.run(
            ["aplay", "-l"], capture_output=True, text=True, timeout=3
        )
        devices["audio"] = [
            line.strip() for line in r.stdout.splitlines()
            if line.startswith("card")
        ][:4]
    except Exception:
        pass

    return devices


def get_p2p_power_index() -> int:
    """
    Честный индекс мощности узла для P2P авторитета.
    0–100. Учитывает свободный CPU, RAM и ядра.
    """
    try:
        cpu_free = 100.0 - psutil.cpu_percent(interval=0.2)
        mem      = psutil.virtual_memory()
        ram_free_pct = (mem.available / mem.total * 100) if mem.total else 0
        cores    = min(psutil.cpu_count(logical=True) or 1, 16)
        # Взвешенный индекс: 40% CPU свободен + 40% RAM свободна + 20% ядра
        idx = int(0.4 * cpu_free + 0.4 * ram_free_pct + 0.2 * (cores / 16 * 100))
        return max(0, min(100, idx))
    except Exception:
        return 50  # разумный дефолт


# ── ФОРМАТИРОВАННЫЕ ОТЧЁТЫ ────────────────────────────────────────────────────

def format_full_report() -> str:
    """Полный отчёт о состоянии системы — реальные данные."""
    cpu   = get_cpu()
    ram   = get_ram()
    disks = get_disks()
    net   = get_network()
    temps = get_temperature()
    bat   = get_battery()
    gpus  = get_gpu()

    lines = ["📊 СОСТОЯНИЕ СИСТЕМЫ:"]

    # CPU
    lines.append(
        f"  💻 CPU:    {cpu['percent']}% нагрузка"
        f" | свободно: {cpu['free']}%"
        f" | {cpu['cores_physical']}p/{cpu['cores_logical']}l ядер"
        f" | {cpu['freq_mhz']:.0f} МГц"
    )

    # RAM
    lines.append(
        f"  🧠 RAM:    {ram['percent']}% занято"
        f" | {ram['used_mb']:,} / {ram['total_mb']:,} МБ"
        f" | своп: {ram['swap_percent']}%"
    )

    # Диски
    for d in disks[:3]:
        lines.append(
            f"  💾 {d['mountpoint']:8} {d['percent']:5.1f}%"
            f" | своб: {d['free_gb']:.1f} ГБ / {d['total_gb']:.1f} ГБ"
        )

    # Сеть
    for iface in net["interfaces"][:3]:
        state = "🟢" if iface["up"] else "🔴"
        lines.append(
            f"  {state} {iface['name']:8} {iface['ip']:15}"
            f" ↑{iface['sent_mb']:.0f}МБ ↓{iface['recv_mb']:.0f}МБ"
        )
    lines.append(f"  🌐 Активных соединений: {net['connections']}")

    # Температуры
    if temps:
        t_str = "  | ".join(
            f"{k.split('_')[-1]}: {v}°C"
            for k, v in list(temps.items())[:4]
        )
        lines.append(f"  🌡️  Темп: {t_str}")

    # GPU
    for g in gpus[:2]:
        if "util" in g:
            lines.append(
                f"  🎮 GPU {g.get('vendor','')} {g.get('name','')[:30]}"
                f" | {g.get('util',0)}%"
                f" | VRAM {g.get('vram_used_mb',0)}/{g.get('vram_total_mb',0)} МБ"
                f" | {g.get('temp_c',0)}°C"
            )
        else:
            lines.append(f"  🎮 GPU: {g.get('vendor','')} {g.get('name', g.get('raw',''))[:40]}")

    # Батарея
    if bat:
        charge_str = "🔌 заряжается" if bat["charging"] else f"⏳ ~{bat['time_left_min']}мин"
        lines.append(f"  🔋 Батарея: {bat['percent']}% {charge_str}")

    return "\n".join(lines)


def format_io_report() -> str:
    """Отчёт об устройствах ввода/вывода."""
    io = get_io_devices()

    lines = ["🔌 УСТРОЙСТВА ВВОДА/ВЫВОДА:"]

    # Serial
    if io["serial"]:
        lines.append("  📡 Serial/UART:")
        for d in io["serial"]:
            lines.append(f"    {d['port']} — {d['desc']}")
    else:
        lines.append("  📡 Serial/UART: не обнаружены")

    # I2C
    lines.append(f"  🔗 I2C: {', '.join(io['i2c']) if io['i2c'] else 'нет'}")

    # SPI
    lines.append(f"  🔗 SPI: {', '.join(io['spi']) if io['spi'] else 'нет'}")

    # GPIO
    lines.append(f"  📌 GPIO: {'✅ доступен' if io['gpio'] else '❌ нет'}")

    # USB
    if io["usb"]:
        lines.append("  🔌 USB устройства:")
        for u in io["usb"][:6]:
            lines.append(f"    {u}")

    # Audio
    if io["audio"]:
        lines.append("  🔊 Аудио:")
        for a in io["audio"]:
            lines.append(f"    {a}")

    return "\n".join(lines)


def format_p2p_node_info() -> str:
    """Информация о текущей P2P ноде."""
    cpu   = get_cpu()
    ram   = get_ram()
    power = get_p2p_power_index()
    hostname = platform.node()
    arch     = platform.machine()
    system   = platform.system()

    return (
        f"🌐 P2P NODE INFO:\n"
        f"  Хост:    {hostname} ({system}/{arch})\n"
        f"  CPU:     {cpu['percent']}% нагр | {cpu['cores_logical']} потоков\n"
        f"  RAM:     {ram['percent']}% занято | {ram['available_mb']:,} МБ свободно\n"
        f"  Мощность (power index): {power}/100\n"
        f"  IP:      {_get_local_ip()}"
    )


def _get_local_ip() -> str:
    """Определяет локальный IP через UDP-трик (без подключения)."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"


# ── ПАТЧ ArgosSensorBridge ────────────────────────────────────────────────────

class PatchedSensorBridge:
    """
    Замена ArgosSensorBridge с реальными данными.
    Используй в core.py вместо ArgosSensorBridge если оригинал возвращает 0%.
    """

    def get_full_report(self) -> str:
        return format_full_report()

    def get_io_report(self) -> str:
        return format_io_report()

    def optimize_vram_distribution(self) -> str:
        gpus = get_gpu()
        if not gpus:
            return "🎮 GPU не обнаружен. Убедись что nvidia-smi или rocm-smi установлены."
        lines = ["🎮 VRAM РАСПРЕДЕЛЕНИЕ:"]
        for i, g in enumerate(gpus):
            if "vram_total_mb" in g:
                used  = g["vram_used_mb"]
                total = g["vram_total_mb"]
                free  = total - used
                pct   = round(used / total * 100) if total else 0
                lines.append(
                    f"  GPU {i}: {g['name'][:30]}\n"
                    f"    Использовано: {used} МБ / {total} МБ ({pct}%)\n"
                    f"    Свободно: {free} МБ"
                )
            else:
                lines.append(f"  GPU {i}: {g.get('vendor','')} {g.get('name','')}")
        return "\n".join(lines)

    def get_p2p_power(self) -> int:
        return get_p2p_power_index()
