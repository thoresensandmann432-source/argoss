"""
flasher.py — Smart Flasher: авто-детект USB чипов и прошивка
Поддерживает: ESP32, RP2040, RP2350, STM32
Команды: найди usb чипы | умная прошивка [порт] | прошей gateway [порт] [цель]
"""

import os
import glob
import platform
import shutil
import subprocess
import time
from datetime import datetime
from pathlib import Path

try:
    import serial.tools.list_ports
except Exception:
    serial = None

CHIP_SIGNATURES = {
    "esp32": {
        "vid_pid": {(0x10C4, 0xEA60), (0x1A86, 0x7523), (0x0403, 0x6001)},
        "keywords": ("cp210", "ch340", "ft232", "esp32"),
    },
    "rp2040": {
        "vid_pid": {(0x2E8A, 0x0005), (0x2E8A, 0x000A)},
        "keywords": ("rp2040", "raspberry pi pico"),
    },
    "rp2350": {
        # BOOTSEL mode: 0x2E8A:0x0003 (RP2350-A/B)
        # MicroPython CDC: 0x2E8A:0x0005 (shared w/ RP2040 — кейворд выручит)
        # Waveshare RP2350-GEEK CDC: 0x2E8A:0x000B
        "vid_pid": {(0x2E8A, 0x0003), (0x2E8A, 0x000B)},
        "keywords": ("rp2350", "waveshare rp2350", "rp2350-geek", "pico 2"),
    },
    "stm32": {
        "vid_pid": {(0x0483, 0x5740), (0x0483, 0xDF11)},
        "keywords": ("stm32", "stlink", "dfu"),
    },
    # STM32H503 — PB_MCU01_H503A и аналоги (Embedsky TQ-H503A)
    # CDC VCP: 0x0483:0x5740 (уже в stm32, уточняется по keywords)
    # DFU:     0x0483:0xDF11 (уже в stm32)
    "stm32h503": {
        "vid_pid": {(0x0483, 0x5740), (0x0483, 0xDF11)},
        "keywords": ("stm32h503", "pb_mcu01", "pb mcu01", "h503a", "h503"),
    },
}

# UF2 family IDs для проверки файлов
UF2_FAMILY = {
    "rp2040": 0xE48BFF56,
    "rp2350-arm":  0xE48BFF59,
    "rp2350-riscv": 0xE48BFF5B,
    "rp2350-abs":   0xE48BFF57,
}

# Имя тома BOOTSEL для drag-and-drop UF2
BOOTSEL_VOLUME = {
    "rp2040": "RPI-RP2",
    "rp2350": "RP2350",
}

FIRMWARE_DIR = "assets/firmware"
SMART_FIRMWARES = {
    "gateway":       {"kind": "auto", "description": "Авто-заготовка под чип"},
    "air_tag":       {"kind": "auto", "description": "Авто-заготовка air_tag"},
    "rp2350_geek":   {"kind": "py",  "path": os.path.join(FIRMWARE_DIR, "argos_rp2350_geek.py"),
                      "description": "ARGOS MicroPython для Waveshare RP2350-GEEK"},
    "esp32_display": {"kind": "ino", "path": os.path.join(FIRMWARE_DIR, "argos_esp32_2432s024.ino"),
                      "description": "ARGOS дисплей ESP32-2432S024"},
    "stm32h503":     {"kind": "c",  "path": os.path.join(FIRMWARE_DIR, "argos_pb_mcu01_h503a.c"),
                      "description": "ARGOS USB CDC для PB_MCU01_H503A (STM32H503)"},
    "tasmota_relay": {"kind": "bin", "path": os.path.join(FIRMWARE_DIR, "tasmota_relay.bin")},
    "tasmota_sensor": {"kind": "bin", "path": os.path.join(FIRMWARE_DIR, "tasmota_sensor.bin")},
}

FIRMWARE_SOURCE_HINT_TEMPLATES = (
    "https://github.com/search?q={query}+firmware",
    "https://sourceforge.net/directory/?q={query}+firmware",
    "https://community.platformio.org/search?q={query}",
    "https://4pda.to/forum/index.php?act=search&source=all&query={query}",
)


def auto_detect_port() -> str | None:
    """Автоопределение COM/tty порта для прошивки."""
    import platform
    import os

    # Из переменной окружения
    env_port = os.environ.get("ARGOS_SERIAL_PORT", "")
    if env_port:
        return env_port

    system = platform.system()

    if system == "Windows":
        try:
            import serial.tools.list_ports

            ports = list(serial.tools.list_ports.comports())
            # Ищем Arduino/ESP/STM
            for p in ports:
                if any(
                    kw in (p.description or "")
                    for kw in ["Arduino", "ESP", "STM", "CH340", "CP210", "FTDI", "USB Serial"]
                ):
                    return p.device
            # Любой COM порт
            if ports:
                return ports[0].device
        except ImportError:
            pass
        return "COM3"  # дефолт Windows

    elif system == "Linux":
        import glob

        candidates = (
            glob.glob("/dev/ttyUSB*") + glob.glob("/dev/ttyACM*") + glob.glob("/dev/ttyAMA*")
        )
        return candidates[0] if candidates else "/dev/ttyUSB0"

    elif system == "Darwin":
        import glob

        candidates = glob.glob("/dev/cu.usbserial*") + glob.glob("/dev/cu.usbmodem*")
        return candidates[0] if candidates else "/dev/cu.usbserial"

    return None


class AirFlasher:

    # ── Список доступных прошивок ─────────────────────────
    def list_available_firmwares(self) -> list[str]:
        names = []
        for fw_name, meta in SMART_FIRMWARES.items():
            if meta.get("kind") == "auto":
                names.append(f"{fw_name} (auto)")
            else:
                path = meta.get("path", "")
                exists = path and os.path.exists(path)
                names.append(fw_name if exists else f"{fw_name} (ожидается {path})")
        return names

    # ── COM-порты ────────────────────────────────────────
    def _comports(self):
        if serial is None:
            return []
        try:
            return list(serial.tools.list_ports.comports())
        except Exception:
            return []

    def scan_ports(self) -> list[str]:
        ports = [p.device for p in self._comports()]
        return ports if ports else ["Устройства не обнаружены"]

    # ── Определение чипа ─────────────────────────────────
    def _guess_chip(self, port_info) -> str:
        vid = getattr(port_info, "vid", None)
        pid = getattr(port_info, "pid", None)
        desc = (getattr(port_info, "description", "") or "").lower()
        hwid = (getattr(port_info, "hwid", "") or "").lower()
        for chip, sig in CHIP_SIGNATURES.items():
            if (vid, pid) in sig["vid_pid"]:
                return chip
            if any(k in desc or k in hwid for k in sig["keywords"]):
                return chip
        return "unknown"

    def detect_usb_chips(self) -> list[dict]:
        devices = []
        for p in self._comports():
            devices.append(
                {
                    "port": p.device,
                    "chip": self._guess_chip(p),
                    "description": getattr(p, "description", "") or "Unknown",
                    "vid": getattr(p, "vid", None),
                    "pid": getattr(p, "pid", None),
                }
            )
        return devices

    def detect_usb_chips_report(self) -> str:
        devices = self.detect_usb_chips()
        if not devices:
            return "📡 USB-устройства не найдены."
        lines = ["📡 SMART FLASHER — USB ДЕТЕКТ:"]
        for d in devices:
            vp = "n/a" if d["vid"] is None else f"{d['vid']:04x}:{d['pid']:04x}"
            lines.append(f"  • {d['port']} | chip={d['chip']} | {vp} | {d['description']}")
        return "\n".join(lines)

    # ── Заготовка прошивки ───────────────────────────────
    def _build_firmware_stub(self, chip: str, target_name: str = "gateway") -> str:
        os.makedirs(FIRMWARE_DIR, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        if chip in {"esp32", "stm32"}:
            path = f"{FIRMWARE_DIR}/auto_{target_name}_{chip}_{stamp}.ino"
            code = (
                "// Auto-generated by Argos Smart Flasher\n"
                "void setup() {\n"
                "  Serial.begin(115200);\n"
                "  pinMode(LED_BUILTIN, OUTPUT);\n"
                "}\n\n"
                "void loop() {\n"
                "  digitalWrite(LED_BUILTIN, HIGH); delay(250);\n"
                "  digitalWrite(LED_BUILTIN, LOW);  delay(250);\n"
                "}\n"
            )
            with open(path, "w") as f:
                f.write(code)
            return path
        if chip in {"rp2040", "rp2350"}:
            path = f"{FIRMWARE_DIR}/auto_{target_name}_{chip}_{stamp}.py"
            code = (
                "# Auto-generated MicroPython stub by ARGOS Smart Flasher\n"
                "import machine, utime\n\n"
                "led = machine.Pin('LED', machine.Pin.OUT)\n\n"
                "while True:\n"
                "    led.toggle()\n"
                "    utime.sleep_ms(250)\n"
            )
            with open(path, "w") as f:
                f.write(code)
            return path
        path = f"{FIRMWARE_DIR}/auto_{target_name}_{stamp}.bin"
        with open(path, "wb") as f:
            f.write(b"")
        return path

    def _resolve_firmware_path(self, chip: str, target_name: str) -> tuple[str, str | None]:
        key = (target_name or "gateway").strip().lower()
        meta = SMART_FIRMWARES.get(key)
        if meta and meta.get("kind") == "bin":
            fp = str(meta.get("path", ""))
            if not os.path.exists(fp):
                return "", f"⚠️ Бинарник '{key}' не найден: {fp}"
            return fp, None
        return self._build_firmware_stub(chip, target_name=key), None

    def _tool_exists(self, name: str) -> bool:
        return shutil.which(name) is not None

    def _run(self, cmd: list[str], timeout: int = 180) -> tuple[int, str]:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        out = (proc.stdout or "") + (("\n" + proc.stderr) if proc.stderr else "")
        return proc.returncode, out.strip()

    # ── Поиск BOOTSEL тома ───────────────────────────────
    def _find_bootsel_drive(self, chip: str) -> str | None:
        """Ищет смонтированный BOOTSEL том RPI-RP2 / RP2350."""
        vol_name = BOOTSEL_VOLUME.get(chip, "RPI-RP2")
        sys_name = platform.system()
        if sys_name == "Windows":
            import string
            for letter in string.ascii_uppercase:
                drive = f"{letter}:\\"
                label_file = os.path.join(drive, "INFO_UF2.TXT")
                if os.path.exists(label_file):
                    return drive
        elif sys_name in ("Linux", "Darwin"):
            # Linux: /media/<user>/<label> или /mnt/<label>
            candidates = (
                glob.glob(f"/media/*/{vol_name}") +
                glob.glob(f"/mnt/{vol_name}") +
                glob.glob(f"/Volumes/{vol_name}")  # macOS
            )
            if candidates:
                return candidates[0]
        return None

    def _flash_uf2(self, chip: str, firmware_path: str) -> str:
        """Копирует UF2 файл на BOOTSEL том (drag-and-drop метод)."""
        fw = Path(firmware_path)
        if not fw.exists():
            return f"❌ Файл не найден: {firmware_path}"
        if not firmware_path.lower().endswith(".uf2"):
            return f"⚠️ RP2350 требует .uf2 файл (получен: {fw.suffix})"

        drive = self._find_bootsel_drive(chip)
        if not drive:
            # Попробуем picotool
            return self._flash_picotool(firmware_path)

        dest = os.path.join(drive, fw.name)
        try:
            shutil.copy2(str(fw), dest)
            return f"✅ {chip.upper()} прошит через UF2: {fw.name} → {drive}"
        except Exception as e:
            return f"❌ Ошибка копирования UF2: {e}"

    def _flash_picotool(self, firmware_path: str) -> str:
        """Прошивает через picotool (если установлен)."""
        tool = shutil.which("picotool")
        if not tool:
            return (
                "❌ BOOTSEL том не найден и picotool не установлен.\n"
                "  Удержи BOOT при подключении USB → появится RPI-RP2 / RP2350 диск\n"
                "  Или установи: https://github.com/raspberrypi/picotool"
            )
        code, out = self._run([tool, "load", "-x", firmware_path, "--force"])
        return f"✅ picotool: прошивка загружена" if code == 0 else f"❌ picotool error:\n{out[:300]}"

    def _flash_micropython_rp(self, port: str, firmware_path: str) -> str:
        """Копирует .py файл на RP2350 через rshell/mpremote как main.py."""
        fw = Path(firmware_path)
        if not fw.exists():
            return f"❌ Файл не найден: {firmware_path}"

        # Попытка через mpremote
        mpremote = shutil.which("mpremote")
        if mpremote:
            code, out = self._run(
                [mpremote, "connect", port, "cp", str(fw), ":main.py"]
            )
            if code == 0:
                return f"✅ MicroPython: {fw.name} → main.py через mpremote"
            return f"❌ mpremote ошибка:\n{out[:300]}"

        # Попытка через rshell
        rshell = shutil.which("rshell")
        if rshell:
            code, out = self._run(
                [rshell, "-p", port, "cp", str(fw), "/pyboard/main.py"]
            )
            if code == 0:
                return f"✅ MicroPython: {fw.name} → main.py через rshell"
            return f"❌ rshell ошибка:\n{out[:300]}"

        return (
            "⚠️ mpremote/rshell не найдены.\n"
            "  Установи: pip install mpremote rshell --break-system-packages\n"
            f"  Или скопируй {fw.name} как main.py через Thonny."
        )

    # ── Прошивка ─────────────────────────────────────────
    def flash_chip(self, port: str, chip: str, firmware_path: str) -> str:
        if chip == "esp32":
            tool = shutil.which("esptool.py") or shutil.which("esptool")
            if not tool:
                return "❌ esptool не найден: pip install esptool"
            if not firmware_path.lower().endswith(".bin"):
                return "⚠️ ESP32 требует .bin файл."
            code, out = self._run(
                [tool, "--port", port, "--baud", "921600", "write_flash", "0x1000", firmware_path]
            )
            return f"✅ ESP32 прошит: {port}" if code == 0 else f"❌ ESP32 error:\n{out[:400]}"

        if chip == "rp2350":
            ext = Path(firmware_path).suffix.lower()
            if ext == ".uf2":
                return self._flash_uf2(chip, firmware_path)
            elif ext == ".py":
                # MicroPython скрипт — копируем как main.py
                return self._flash_micropython_rp(port, firmware_path)
            else:
                return self._flash_picotool(firmware_path)

        if chip == "rp2040":
            ext = Path(firmware_path).suffix.lower()
            if ext == ".uf2":
                return self._flash_uf2(chip, firmware_path)
            if not self._tool_exists("platformio"):
                return "❌ PlatformIO не найден: pip install platformio"
            code, out = self._run(["platformio", "run", "-t", "upload", "--upload-port", port])
            return f"✅ RP2040 прошит" if code == 0 else f"❌ rp2040 error:\n{out[:400]}"

        if chip in {"stm32", "stm32h503"}:
            # Для .c файла (исходник) — сообщить что нужно сначала собрать
            if Path(firmware_path).suffix.lower() == ".c":
                return (
                    f"⚠️ {firmware_path} — исходный код C, не бинарник.\n"
                    "  Собери проект в STM32CubeIDE → получи .bin / .hex\n"
                    "  Потом: прошей stm32h503 argos_h503a.bin\n"
                    "  Инструкция: assets/firmware/argos_pb_mcu01_h503a_notes.md"
                )
            # DFU через dfu-util (USB, без ST-Link)
            if "(dfu)" in port.lower() or port == "":
                return self._flash_dfu(firmware_path)
            return self._flash_stm32(port, firmware_path)

        return f"⚠️ Чип '{chip}' не распознан."

    def _flash_dfu(self, firmware_path: str) -> str:
        """Прошивка через USB DFU (dfu-util). Не требует ST-Link."""
        fw = Path(firmware_path)
        if not fw.exists():
            return f"❌ Файл не найден: {firmware_path}"
        ext = fw.suffix.lower()

        # dfu-util
        dfu = shutil.which("dfu-util")
        if dfu:
            if ext == ".bin":
                cmd = [dfu, "-a", "0", "-D", str(fw),
                       "--dfuse-address", "0x08000000", "-R"]
            elif ext == ".hex":
                cmd = [dfu, "-a", "0", "-D", str(fw), "-R"]
            else:
                return f"⚠️ DFU: неподдерживаемое расширение {ext}"
            code, out = self._run(cmd, timeout=60)
            return (f"✅ STM32 прошит через DFU: {fw.name}"
                    if code == 0 else f"❌ dfu-util:\n{out[:400]}")

        # STM32CubeProgrammer через USB
        cp = shutil.which("STM32_Programmer_CLI") or shutil.which("STM32CubeProgrammer")
        if cp:
            cmd = [cp, "-c", "port=USB1", "-w", str(fw), "0x08000000", "-v", "-rst"]
            code, out = self._run(cmd, timeout=120)
            return (f"✅ STM32 DFU через CubeProgrammer: {fw.name}"
                    if code == 0 else f"❌ CubeProgrammer DFU:\n{out[:400]}")

        return (
            "❌ DFU инструменты не найдены. Установи:\n"
            "  Linux: sudo apt install dfu-util\n"
            "  Windows: STM32CubeProgrammer (st.com)\n"
            "  Шаг: удержи BOOT0 при подключении USB → устройство = STM32 BOOTLOADER"
        )

    def stm32h503_info(self) -> str:
        """Статус PB_MCU01_H503A и инструментов прошивки."""
        fw_path = os.path.join(FIRMWARE_DIR, "argos_pb_mcu01_h503a.c")
        fw_exists = "✅" if os.path.exists(fw_path) else "○"
        dfu = shutil.which("dfu-util")
        lines = [
            "🔷 PB_MCU01_H503A (STM32H503CBT6)",
            f"  Исходник: {fw_exists} {fw_path}",
            f"  dfu-util:  {'✅ ' + dfu if dfu else '○  sudo apt install dfu-util'}",
        ]
        # Проверим stlink_info тоже
        sf = shutil.which("st-flash")
        cp = shutil.which("STM32_Programmer_CLI") or shutil.which("STM32CubeProgrammer")
        lines.append(f"  st-flash:  {'✅' if sf else '○  sudo apt install stlink-tools'}")
        lines.append(f"  CubeProg:  {'✅' if cp else '○  https://st.com/stm32cubeprog'}")
        lines.append("")
        lines.append("  Команды:")
        lines.append("    прошей stm32h503        — прошить .bin через ST-Link")
        lines.append("    прошей stm32h503 (dfu)  — прошить через USB DFU")
        lines.append("    подключи stm32          — запустить USB CDC мост")
        lines.append("  Исходник → сборка в STM32CubeIDE → .bin → прошивка")
        return "\n".join(lines)

    def _flash_stm32(self, port: str, firmware_path: str) -> str:
        """Прошивает STM32 через ST-Link v2 (st-flash / STM32CubeProg / OpenOCD)."""
        fw = Path(firmware_path)
        ext = fw.suffix.lower()

        # Метод 1: st-flash (open-source stlink tools)
        st_flash = shutil.which("st-flash")
        if st_flash:
            if ext == ".bin":
                code, out = self._run([st_flash, "write", str(fw), "0x8000000"])
                return (f"✅ STM32 прошит через st-flash: {fw.name}"
                        if code == 0 else f"❌ st-flash:\n{out[:400]}")
            elif ext == ".hex":
                # st-flash не поддерживает hex напрямую — конвертируем через objcopy
                bin_path = str(fw).replace(".hex", ".bin")
                if shutil.which("arm-none-eabi-objcopy"):
                    self._run(["arm-none-eabi-objcopy", "-I", "ihex", "-O", "binary",
                               str(fw), bin_path])
                    if os.path.exists(bin_path):
                        code, out = self._run([st_flash, "write", bin_path, "0x8000000"])
                        return (f"✅ STM32 прошит (hex→bin): {fw.name}"
                                if code == 0 else f"❌ st-flash:\n{out[:400]}")
                return "⚠️ Для .hex файла нужен arm-none-eabi-objcopy или STM32CubeProgrammer"

        # Метод 2: STM32CubeProgrammer CLI
        cube_prog = shutil.which("STM32_Programmer_CLI") or shutil.which("STM32CubeProgrammer")
        if cube_prog:
            cmd = [cube_prog, "-c", "port=SWD", "-w", str(fw), "0x8000000", "-v", "-rst"]
            code, out = self._run(cmd, timeout=120)
            return (f"✅ STM32 прошит через STM32CubeProgrammer: {fw.name}"
                    if code == 0 else f"❌ STM32CubeProgrammer:\n{out[:400]}")

        # Метод 3: OpenOCD
        openocd = shutil.which("openocd")
        if openocd:
            if ext == ".bin":
                script = (
                    f"program {fw} 0x08000000 verify reset exit"
                )
            else:
                script = f"program {fw} verify reset exit"
            code, out = self._run([
                openocd, "-f", "interface/stlink.cfg",
                "-f", "target/stm32f1x.cfg",  # generic STM32 target
                "-c", script
            ], timeout=120)
            return (f"✅ STM32 прошит через OpenOCD: {fw.name}"
                    if code == 0 else f"❌ OpenOCD:\n{out[:400]}")

        # Метод 4: PlatformIO (последний резерв)
        if self._tool_exists("platformio"):
            code, out = self._run(["platformio", "run", "-t", "upload", "--upload-port", port])
            return f"✅ STM32 прошит через PlatformIO" if code == 0 else f"❌ PIO:\n{out[:400]}"

        return (
            "❌ Инструменты ST-Link не найдены. Установи один из:\n"
            "  • st-flash:  https://github.com/stlink-org/stlink\n"
            "  • STM32CubeProgrammer: https://st.com/stm32cubeprog\n"
            "  • OpenOCD:   sudo apt install openocd\n"
            "  • PlatformIO: pip install platformio --break-system-packages"
        )

    def stlink_info(self) -> str:
        """Статус ST-Link v2 инструментов и подключённых устройств."""
        lines = ["🔌 ST-Link v2 — статус инструментов:"]

        # st-flash
        sf = shutil.which("st-flash")
        lines.append(f"  st-flash:              {'✅ ' + sf if sf else '○  не найден'}")

        # st-info
        si = shutil.which("st-info")
        if si:
            try:
                code, out = self._run(["st-info", "--probe"], timeout=5)
                probe_str = out.replace("\n", " ")[:80] if code == 0 else "нет устройств"
                lines.append(f"  st-info --probe:       {probe_str}")
            except Exception:
                lines.append(f"  st-info:               ✅ {si}")
        else:
            lines.append("  st-info:               ○  не найден")

        # STM32CubeProgrammer
        cp = shutil.which("STM32_Programmer_CLI") or shutil.which("STM32CubeProgrammer")
        lines.append(f"  STM32CubeProgrammer:   {'✅ ' + cp if cp else '○  не найден'}")

        # OpenOCD
        oc = shutil.which("openocd")
        lines.append(f"  OpenOCD:               {'✅ ' + oc if oc else '○  не найден'}")

        # picotool (RP2350)
        pt = shutil.which("picotool")
        lines.append(f"  picotool (RP2350):     {'✅ ' + pt if pt else '○  не найден'}")

        # mpremote (MicroPython)
        mr = shutil.which("mpremote")
        lines.append(f"  mpremote (MicroPython):{'✅ ' + mr if mr else '○  не найден'}")

        lines.append("")
        lines.append("  Установка:")
        lines.append("    Linux:   sudo apt install stlink-tools openocd")
        lines.append("    pip:     pip install mpremote esptool --break-system-packages")
        lines.append("    RP2350:  https://github.com/raspberrypi/picotool")
        return "\n".join(lines)

    def smart_flash(self, port: str = None, target_name: str = "gateway") -> str:
        devices = self.detect_usb_chips()
        if not devices:
            return "❌ Нет USB-устройств для прошивки."
        selected = None
        if port:
            for d in devices:
                if d["port"] == port:
                    selected = d
                    break
            if not selected:
                return f"❌ Порт {port} не найден."
        else:
            selected = devices[0]

        fw, err = self._resolve_firmware_path(selected["chip"], target_name)
        available = ", ".join(self.list_available_firmwares())
        if not fw:
            return (
                f"⚡ SMART FLASHER\\n"
                f"  Порт: {selected['port']}\\n"
                f"  Чип: {selected['chip']}\\n"
                f"  Ошибка: {err}\\n"
                f"  Доступные прошивки: {available}"
            )

        result = self.flash_chip(selected["port"], selected["chip"], fw)
        return (
            f"⚡ SMART FLASHER\\n"
            f"  Порт: {selected['port']}\\n"
            f"  Чип: {selected['chip']}\\n"
            f"  Прошивка: {fw}\\n"
            f"  Доступные: {available}\\n"
            f"  Результат: {result}"
        )

    def flash_air_tag(self, port):
        return self.smart_flash(port=port, target_name="air_tag")

    def wearable_firmware_mod(
        self, device: str, port: str = "", avatar: str = "sigtrip", include_4pda: bool = False
    ) -> str:
        """
        Строит безопасный workflow модификации прошивки носимого устройства.
        Автоматически не скачивает и не прошивает неподтверждённые образы.
        """
        dev = (device or "wearable").strip()
        query = dev.replace(" ", "+")

        source_urls = []
        for tpl in FIRMWARE_SOURCE_HINT_TEMPLATES:
            if "4pda" in tpl and not include_4pda:
                continue
            source_urls.append(tpl.format(query=query))

        lines = [
            f"🧩 ARGOS Wearable Firmware Workflow (avatar: {avatar})",
            f"  Устройство: {dev}",
            "",
            "1) Поиск оригинальной прошивки в интернете (приоритет: официальные источники):",
        ]
        lines.extend(f"   • {u}" for u in source_urls)
        lines.extend(
            [
                "",
                "2) Если оригинал найден:",
                "   • Сверить хеши/подпись и сделать резервную копию текущей прошивки.",
                "   • Проанализировать бинарник и внести изменения конфигурации.",
                "",
                "3) Если оригинал не найден:",
                "   • Считать дамп с устройства (только на собственном оборудовании).",
                "   • Дизассемблировать/проанализировать локальный образ.",
                "",
                "4) Подготовка к прошивке:",
                "   • Использовать только локально проверенный модифицированный образ.",
                "   • Перед прошивкой проверить совместимость чипа и порта.",
                "",
                "5) Применение:",
            ]
        )
        if port:
            lines.append(f"   • Для порта {port}: запусти «умная прошивка {port}».")
        else:
            lines.append("   • Подключи устройство и запусти «умная прошивка [порт]».")
        lines.append("   • Важно: не обходить защиту и лицензии производителей.")
        return "\n".join(lines)

    def android_argos_os_plan(self, profile: str = "phone", preserve_features: bool = True) -> str:
        """
        План создания Argos OS на базе Android с сохранением функций устройства.
        profile: phone | tablet | tv
        """
        p = (profile or "phone").strip().lower()
        if p not in {"phone", "tablet", "tv"}:
            p = "phone"

        capability_map = {
            "phone": "телефония/SMS, камера, NFC, GPS, LTE/5G, Bluetooth, Wi‑Fi",
            "tablet": "камера, стилус/тач, Wi‑Fi/LTE, Bluetooth, GPS",
            "tv": "HDMI-CEC, DRM/MediaCodec, пульт, Wi‑Fi/Ethernet, Bluetooth Audio",
        }
        lines = [
            f"📱 Argos OS Android Plan ({p})",
            "1) База системы:",
            "   • Берём официальный Android-образ для устройства (AOSP/vendor).",
            "   • Сохраняем vendor, boot, dtbo, modem и DRM-разделы без изменений.",
            "2) Интеграция Argos:",
            "   • Добавляем Argos как системный сервис/launcher-режим, а не замену HAL.",
            "   • API интеграции: уведомления, голос, ассистент, безопасная автоматизация.",
            "3) Сохранение функций устройства:",
            f"   • Профиль {p}: {capability_map[p]}",
            "   • Обязательные smoke-тесты: звонки/сеть (phone), камера, звук, сенсоры, OTA.",
            "4) Безопасность и обновления:",
            "   • Подписываем сборки, включаем verified boot, rollback protection и OTA-канал.",
            "   • Держим fallback-прошивку для быстрого отката.",
            "5) Релизный pipeline:",
            "   • Сборка образа → эмулятор → тест на реальном устройстве → staged rollout.",
        ]
        if preserve_features:
            lines.append(
                "✅ Режим сохранения функций включён: базовые phone/tablet/tv возможности приоритетны."
            )
        return "\n".join(lines)


# Алиас для обратной совместимости
ArgosFlasher = AirFlasher
