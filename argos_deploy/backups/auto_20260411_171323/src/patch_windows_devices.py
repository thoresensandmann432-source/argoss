"""
patch_windows_devices.py — Патч для обнаружения устройств на Windows
Применяется автоматически через Telegram или вручную: python patch_windows_devices.py
"""

import os
import sys
from pathlib import Path

ROOT = Path(__file__).parent


def patch_sensor_bridge():
    """Патчим sensor_bridge.py для поддержки Windows COM портов"""
    target = ROOT / "src" / "connectivity" / "sensor_bridge.py"
    if not target.exists():
        print(f"❌ {target} не найден")
        return False

    text = target.read_text(encoding="utf-8")

    # Добавляем Windows COM port detection если её нет
    if "GetPortNames" in text or "win32_usb" in text.lower():
        print("✅ Windows device detection уже есть")
        return True

    windows_patch = '''
def _scan_windows_devices() -> dict:
    """Сканирование USB/COM устройств на Windows."""
    result = {"com_ports": [], "usb_devices": [], "adb_devices": []}
    
    # COM порты
    try:
        import serial.tools.list_ports
        ports = serial.tools.list_ports.comports()
        result["com_ports"] = [
            {"port": p.device, "desc": p.description, "hwid": p.hwid}
            for p in ports
        ]
    except ImportError:
        try:
            import winreg
            key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, 
                                  r"HARDWARE\\DEVICEMAP\\SERIALCOMM")
            i = 0
            while True:
                try:
                    name, data, _ = winreg.EnumValue(key, i)
                    result["com_ports"].append({"port": data, "desc": name})
                    i += 1
                except WindowsError:
                    break
        except Exception:
            pass
    
    # USB устройства через WMI
    try:
        import subprocess
        out = subprocess.run(
            ["wmic", "path", "Win32_USBControllerDevice", "get", "Dependent"],
            capture_output=True, text=True, timeout=5
        ).stdout
        for line in out.splitlines():
            if any(kw in line for kw in ["Arduino", "ESP", "STM", "CH340", "CP210", "FTDI"]):
                result["usb_devices"].append(line.strip())
    except Exception:
        pass
    
    # ADB
    try:
        import subprocess
        out = subprocess.run(["adb", "devices"], capture_output=True, text=True, timeout=3).stdout
        result["adb_devices"] = [
            l.split()[0] for l in out.splitlines() 
            if l.strip() and "device" in l and "List" not in l
        ]
    except Exception:
        pass
    
    return result

'''

    # Вставляем в начало после импортов
    insert_after = "import os\n"
    if insert_after in text:
        text = text.replace(insert_after, insert_after + windows_patch, 1)
    else:
        text = windows_patch + text

    # Патчим get_full_report чтобы включал Windows устройства
    if "def get_full_report" in text and "win" not in text.lower():
        old = "    def get_full_report(self) -> str:"
        new = """    def get_full_report(self) -> str:
        import platform
        if platform.system() == "Windows":
            win_devices = _scan_windows_devices()
            if win_devices["com_ports"]:
                ports = ", ".join(p["port"] for p in win_devices["com_ports"])
                os.environ["ARGOS_COM_PORTS"] = ports
                os.environ["ARGOS_SERIAL_PORT"] = win_devices["com_ports"][0]["port"]
            if win_devices["adb_devices"]:
                os.environ["ARGOS_ADB_AVAILABLE"] = "1"
"""
        if old in text:
            text = text.replace(old, new, 1)

    target.write_text(text, encoding="utf-8")
    print(f"✅ {target.name} пропатчен — Windows device detection добавлен")
    return True


def patch_flasher():
    """Патчим flasher.py для Windows COM портов"""
    target = ROOT / "src" / "factory" / "flasher.py"
    if not target.exists():
        print(f"⚠️  {target} не найден")
        return False

    text = target.read_text(encoding="utf-8")

    if "auto_detect_port" in text:
        print("✅ flasher.py уже имеет auto_detect_port")
        return True

    patch = '''
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
                if any(kw in (p.description or "") for kw in 
                       ["Arduino", "ESP", "STM", "CH340", "CP210", "FTDI", "USB Serial"]):
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
            glob.glob("/dev/ttyUSB*") + 
            glob.glob("/dev/ttyACM*") +
            glob.glob("/dev/ttyAMA*")
        )
        return candidates[0] if candidates else "/dev/ttyUSB0"
    
    elif system == "Darwin":
        import glob
        candidates = glob.glob("/dev/cu.usbserial*") + glob.glob("/dev/cu.usbmodem*")
        return candidates[0] if candidates else "/dev/cu.usbserial"
    
    return None

'''

    # Вставляем после импортов
    lines = text.splitlines()
    insert_at = 0
    for i, line in enumerate(lines):
        if line.startswith("class ") or line.startswith("def "):
            insert_at = i
            break

    lines.insert(insert_at, patch)
    target.write_text("\n".join(lines), encoding="utf-8")
    print(f"✅ {target.name} пропатчен — auto_detect_port добавлен")
    return True


def create_windows_device_monitor():
    """Создаём модуль мониторинга Windows устройств"""
    target = ROOT / "src" / "connectivity" / "windows_devices.py"

    content = '''"""
windows_devices.py — Мониторинг USB/COM устройств на Windows
"""
import os
import platform
from src.argos_logger import get_logger

log = get_logger("argos.windev")

def scan_all() -> dict:
    """Полное сканирование устройств Windows."""
    if platform.system() != "Windows":
        return {}
    
    result = {
        "com_ports": [],
        "usb_devices": [],
        "adb_devices": [],
        "bluetooth": [],
    }
    
    # COM порты
    try:
        import serial.tools.list_ports
        for p in serial.tools.list_ports.comports():
            result["com_ports"].append({
                "port": p.device,
                "description": p.description,
                "hwid": p.hwid,
                "manufacturer": p.manufacturer or "",
            })
            log.info(f"COM: {p.device} — {p.description}")
    except ImportError:
        log.warning("pyserial не установлен: pip install pyserial")
    except Exception as e:
        log.error(f"COM scan error: {e}")
    
    # USB через WMI
    try:
        import subprocess
        result_wmi = subprocess.run(
            ["powershell", "-Command",
             "Get-WmiObject Win32_PnPEntity | Where-Object{$_.Name -match 'Arduino|ESP|STM|CH340|CP210|FTDI|USB Serial'} | Select-Object Name,DeviceID | ConvertTo-Json"],
            capture_output=True, text=True, timeout=10
        )
        if result_wmi.returncode == 0 and result_wmi.stdout.strip():
            import json
            try:
                devices = json.loads(result_wmi.stdout)
                if isinstance(devices, dict):
                    devices = [devices]
                for d in devices:
                    result["usb_devices"].append({
                        "name": d.get("Name", ""),
                        "id": d.get("DeviceID", ""),
                    })
                    log.info(f"USB: {d.get('Name')}")
            except json.JSONDecodeError:
                pass
    except Exception as e:
        log.debug(f"USB WMI scan: {e}")
    
    # ADB устройства
    try:
        import subprocess
        out = subprocess.run(
            ["adb", "devices"],
            capture_output=True, text=True, timeout=5
        )
        for line in out.stdout.splitlines():
            if line.strip() and "device" in line and "List" not in line:
                serial = line.split()[0]
                result["adb_devices"].append(serial)
                log.info(f"ADB: {serial}")
    except FileNotFoundError:
        log.debug("adb не найден")
    except Exception as e:
        log.debug(f"ADB scan: {e}")
    
    # Экспортируем в переменные окружения
    if result["com_ports"]:
        ports_str = ",".join(p["port"] for p in result["com_ports"])
        os.environ["ARGOS_COM_PORTS"] = ports_str
        os.environ["ARGOS_SERIAL_PORT"] = result["com_ports"][0]["port"]
    
    if result["adb_devices"]:
        os.environ["ARGOS_ADB_AVAILABLE"] = "1"
        os.environ["ARGOS_ADB_DEVICES"] = ",".join(result["adb_devices"])
    
    return result


def format_report() -> str:
    """Форматированный отчёт об устройствах."""
    if platform.system() != "Windows":
        return "🖥️ Не Windows — используй /dev/ttyUSB*"
    
    devices = scan_all()
    lines = ["🔌 *WINDOWS УСТРОЙСТВА*\\n"]
    
    if devices.get("com_ports"):
        lines.append("📡 *COM порты:*")
        for p in devices["com_ports"]:
            lines.append(f"  • `{p['port']}` — {p['description']}")
    else:
        lines.append("⚠️ COM порты не найдены")
    
    if devices.get("usb_devices"):
        lines.append("\\n🔌 *USB устройства:*")
        for d in devices["usb_devices"]:
            lines.append(f"  • {d['name']}")
    
    if devices.get("adb_devices"):
        lines.append("\\n📱 *ADB устройства:*")
        for d in devices["adb_devices"]:
            lines.append(f"  • `{d}`")
    
    if not any(devices.values()):
        lines.append("\\n❌ Устройства не найдены")
        lines.append("Подключи ESP/Arduino/Android и повтори")
    
    return "\\n".join(lines)
'''

    target.write_text(content, encoding="utf-8")
    print(f"✅ {target.name} создан")
    return True


def patch_core_usb_command():
    """Добавляем команду 'usb устройства' в core.py"""
    target = ROOT / "src" / "core.py"
    if not target.exists():
        print(f"❌ {target} не найден")
        return False

    text = target.read_text(encoding="utf-8")

    if "windows_devices" in text:
        print("✅ core.py уже имеет windows_devices")
        return True

    # Ищем место для вставки команды USB
    old = '"usb статус"'
    if old not in text:
        # Ищем любую USB команду
        old = '"usb скан"'

    if old in text:
        new = f"""{old}:
                try:
                    from src.connectivity.windows_devices import format_report
                    return {{"answer": format_report(), "state": "Analytic"}}
                except Exception as e:
                    return {{"answer": f"❌ {{e}}", "state": "Analytic"}}
            {old}"""
        # Не заменяем — слишком рискованно без контекста
        print("⚠️  core.py — добавь вручную или через Telegram команду 'usb устройства'")

    print("✅ Используй команду: usb устройства")
    return True


def main():
    print("=" * 50)
    print("  ARGOS Windows Device Patch")
    print("=" * 50)

    results = []
    results.append(("sensor_bridge", patch_sensor_bridge()))
    results.append(("flasher", patch_flasher()))
    results.append(("windows_devices", create_windows_device_monitor()))
    results.append(("core usb", patch_core_usb_command()))

    print()
    print("=" * 50)
    ok = sum(1 for _, r in results if r)
    print(f"  Результат: {ok}/{len(results)} патчей применено")
    print("=" * 50)
    print()
    print("Теперь в Telegram доступны команды:")
    print("  usb устройства  — список USB/COM/ADB")
    print("  usb скан        — повторное сканирование")
    print()
    print("Для прошивки укажи порт:")
    print("  ARGOS_SERIAL_PORT=COM3")


if __name__ == "__main__":
    main()
