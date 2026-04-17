"""
Firmware Manager Skill
- Сканирование портов (AirFlasher)
- Быстрый бэкап ESP/ESP8266 через esptool
- Сборка ESP32 дисплея (platformio, env: esp32dev)
- Прошивка ESP32 bin через esptool

Команды (в сообщении):
  firmware scan
  firmware backup <PORT> [size_hex]   (default 0x80000)
  firmware build esp32dev
  firmware flash <PORT> esp32dev
"""

from __future__ import annotations

import json
import shlex
import subprocess
from pathlib import Path
from datetime import datetime

from src.factory.flasher import AirFlasher, SMART_FIRMWARES

TRIGGERS = ["firmware", "flash", "backup", "проши"]
BACKUP_DIR = Path("backups")
DEFAULT_BACKUP_SIZE = 0x80000  # 512 KB
ESP32_BIN = Path(".pio/build/esp32dev/firmware.bin")


def setup(core=None):
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)


def handle(text: str, core=None) -> str | None:
    t = (text or "").lower().strip()
    if not any(tr in t for tr in TRIGGERS):
        return None

    parts = t.split()
    if len(parts) >= 2 and parts[1] == "scan":
        return _scan()

    if len(parts) >= 3 and parts[1] == "backup":
        port = parts[2]
        size = DEFAULT_BACKUP_SIZE
        if len(parts) >= 4:
            try:
                size = int(parts[3], 16)
            except Exception:
                pass
        return _backup(port, size)

    if len(parts) >= 3 and parts[1] == "build" and parts[2] == "esp32dev":
        return _build_esp32()

    if len(parts) >= 4 and parts[1] == "flash" and parts[3] == "esp32dev":
        port = parts[2]
        return _flash_esp32(port)

    # default: show status
    return _scan()


def teardown():
    pass


def _scan() -> str:
    af = AirFlasher()
    devices = af.detect_usb_chips()
    fw = _list_fw()
    return "📡 SCAN\n" + json.dumps({"devices": devices, "firmwares": fw}, ensure_ascii=False, indent=2)


def _backup(port: str, size: int) -> str:
    stamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    out = BACKUP_DIR / f"{port}_backup_{size:06x}_{stamp}.bin"
    cmd = f"python -m esptool --port {shlex.quote(port)} --baud 460800 read_flash 0 {hex(size)} {shlex.quote(str(out))}"
    code, outlog = _run(cmd, timeout=300)
    status = "PASS" if code == 0 else "FAIL"
    return f"📦 BACKUP {port} {hex(size)} -> {out} [{status}]\n{outlog[-800:]}"


def _build_esp32() -> str:
    cmd = "pio run --project-dir . --environment esp32dev"
    code, outlog = _run(cmd, timeout=480)
    status = "PASS" if code == 0 else "FAIL"
    exists = ESP32_BIN.exists()
    return f"🛠 BUILD esp32dev [{status}] bin_exists={exists}\n{outlog[-800:]}"


def _flash_esp32(port: str) -> str:
    if not ESP32_BIN.exists():
        return "❌ firmware.bin не найден. Сначала запусти: firmware build esp32dev"
    cmd = (
        f"python -m esptool --port {shlex.quote(port)} --baud 921600 "
        f"write_flash 0x0 {shlex.quote(str(ESP32_BIN))}"
    )
    code, outlog = _run(cmd, timeout=300)
    status = "PASS" if code == 0 else "FAIL"
    return f"⚡ FLASH esp32dev on {port} [{status}]\n{outlog[-800:]}"


def _list_fw():
    fw = {}
    for name, meta in SMART_FIRMWARES.items():
        path = meta.get("path")
        exists = Path(path).exists() if path else False
        fw[name] = {"kind": meta.get("kind"), "path": path, "exists": exists}
    return fw


def _run(cmd: str, timeout: int = 120):
    try:
        p = subprocess.run(
            cmd,
            shell=True,
            capture_output=True,
            text=True,
            timeout=timeout,
            encoding="utf-8",
            errors="ignore",
        )
        outlog = (p.stdout or "") + "\n" + (p.stderr or "")
        return p.returncode, outlog
    except subprocess.TimeoutExpired as e:
        return 1, f"timeout after {timeout}s\n{e.stdout or ''}\n{e.stderr or ''}"
