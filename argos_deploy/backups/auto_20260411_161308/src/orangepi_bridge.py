"""
orangepi_bridge.py — Аппаратный мост Аргоса для Orange Pi One

Allwinner H3, 40-пин хедер. Поддерживает:
  • GPIO    — цифровое чтение/запись (OPi.GPIO / gpiod / sysfs fallback)
  • I2C     — датчики BMP280, AHT20, SHT31, OLED, ADS1115 (/dev/i2c-0/1)
  • UART    — серийный порт, AT-команды (/dev/ttyS1/S2/S3)
  • SPI     — устройства (/dev/spidev0.0)
  • 1-Wire  — DS18B20 температура (/sys/bus/w1/devices/)
  • RS-485  — через UART + MAX485 (pyserial + RTS как DE/RE)
  • Modbus RTU — чтение/запись holding registers (FC03/FC06, встроенный стек)

Переменные окружения:
  OPI_GPIO_BACKEND  — opi / gpiod / sysfs (default: auto)
  OPI_I2C_BUS       — 0 или 1 (default: 0)
  OPI_UART_PORT     — /dev/ttyS1 (default: /dev/ttyS1)
  OPI_UART_BAUD     — скорость UART (default: 9600)
  OPI_RS485_PORT    — /dev/ttyS2 (default: /dev/ttyS2)
  OPI_RS485_BAUD    — скорость RS-485 (default: 9600)
  OPI_1WIRE_PATH    — /sys/bus/w1/devices (default: /sys/bus/w1/devices)
"""

from __future__ import annotations

import os
import struct
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from src.argos_logger import get_logger

log = get_logger("argos.orangepi")

# ─────────────────────────────────────────────────────────────────────────────
# ПИНОВАЯ КАРТА Orange Pi One (физический номер → WiringOP / sysfs)
# ─────────────────────────────────────────────────────────────────────────────
OPI_ONE_PIN_MAP: Dict[int, Dict] = {
    3: {"wpi": 8, "sysfs": 12, "name": "SDA0", "alt": "I2C0_SDA"},
    5: {"wpi": 9, "sysfs": 11, "name": "SCL0", "alt": "I2C0_SCL"},
    7: {"wpi": 7, "sysfs": 6, "name": "PA6", "alt": "1-Wire"},
    8: {"wpi": 15, "sysfs": 198, "name": "TX1", "alt": "UART1_TX"},
    10: {"wpi": 16, "sysfs": 199, "name": "RX1", "alt": "UART1_RX"},
    11: {"wpi": 0, "sysfs": 1, "name": "PA1", "alt": "GPIO"},
    12: {"wpi": 1, "sysfs": 7, "name": "PA7", "alt": "GPIO/PWM0"},
    13: {"wpi": 2, "sysfs": 0, "name": "PA0", "alt": "GPIO"},
    15: {"wpi": 3, "sysfs": 3, "name": "PA3", "alt": "GPIO"},
    16: {"wpi": 4, "sysfs": 19, "name": "PA19", "alt": "GPIO"},
    18: {"wpi": 5, "sysfs": 18, "name": "PA18", "alt": "GPIO"},
    19: {"wpi": 12, "sysfs": 15, "name": "SPI0_MOSI", "alt": "SPI"},
    21: {"wpi": 13, "sysfs": 16, "name": "SPI0_MISO", "alt": "SPI"},
    22: {"wpi": 6, "sysfs": 2, "name": "PA2", "alt": "GPIO"},
    23: {"wpi": 14, "sysfs": 14, "name": "SPI0_CLK", "alt": "SPI"},
    24: {"wpi": 10, "sysfs": 13, "name": "SPI0_CS0", "alt": "SPI"},
    26: {"wpi": 11, "sysfs": 10, "name": "SPI0_CS1", "alt": "SPI"},
    27: {"wpi": 30, "sysfs": 19, "name": "SDA1", "alt": "I2C1_SDA"},
    28: {"wpi": 31, "sysfs": 18, "name": "SCL1", "alt": "I2C1_SCL"},
    29: {"wpi": 21, "sysfs": 5, "name": "PA5", "alt": "GPIO"},
    31: {"wpi": 22, "sysfs": 4, "name": "PA4", "alt": "GPIO"},
    32: {"wpi": 26, "sysfs": 1, "name": "PA1", "alt": "PWM1"},
    33: {"wpi": 23, "sysfs": 17, "name": "PA17", "alt": "GPIO"},
    35: {"wpi": 24, "sysfs": 20, "name": "PA20", "alt": "GPIO/PCM_FS"},
    36: {"wpi": 27, "sysfs": 21, "name": "PA21", "alt": "GPIO"},
    37: {"wpi": 25, "sysfs": 22, "name": "PA22", "alt": "GPIO"},
    38: {"wpi": 28, "sysfs": 23, "name": "PA23", "alt": "GPIO/PCM_DIN"},
    40: {"wpi": 29, "sysfs": 24, "name": "PA24", "alt": "GPIO/PCM_DOUT"},
}

# ─────────────────────────────────────────────────────────────────────────────
# GPIO БЭКЕНДЫ
# ─────────────────────────────────────────────────────────────────────────────


class _GPIOBackend:
    IN, OUT = "IN", "OUT"

    def setup(self, pin: int, mode: str): ...
    def output(self, pin: int, value: int): ...
    def input(self, pin: int) -> int:
        return 0

    def cleanup(self): ...
    def name(self) -> str:
        return "stub"


class _OpiGPIOBackend(_GPIOBackend):
    def __init__(self):
        import OPi.GPIO as GPIO

        self._g = GPIO
        GPIO.setmode(GPIO.BOARD)
        GPIO.setwarnings(False)

    def setup(self, pin, mode):
        self._g.setup(pin, self._g.IN if mode == "IN" else self._g.OUT)

    def output(self, pin, value):
        self._g.output(pin, value)

    def input(self, pin) -> int:
        return self._g.input(pin)

    def cleanup(self):
        self._g.cleanup()

    def name(self):
        return "OPi.GPIO"


class _GpiodBackend(_GPIOBackend):
    def __init__(self):
        import gpiod

        self._gpiod = gpiod
        self._chip = gpiod.Chip("gpiochip0")
        self._lines: Dict[int, Any] = {}

    def _sn(self, pin):
        return OPI_ONE_PIN_MAP.get(pin, {}).get("sysfs", pin)

    def setup(self, pin, mode):
        line = self._chip.get_line(self._sn(pin))
        t = self._gpiod.LINE_REQ_DIR_OUT if mode == "OUT" else self._gpiod.LINE_REQ_DIR_IN
        line.request(consumer="argos", type=t)
        self._lines[pin] = line

    def output(self, pin, value):
        if pin in self._lines:
            self._lines[pin].set_value(value)

    def input(self, pin) -> int:
        return self._lines[pin].get_value() if pin in self._lines else 0

    def cleanup(self):
        for l in self._lines.values():
            l.release()
        self._lines.clear()

    def name(self):
        return "gpiod"


class _SysfsBackend(_GPIOBackend):
    _BASE = Path("/sys/class/gpio")

    def _sn(self, pin):
        return OPI_ONE_PIN_MAP.get(pin, {}).get("sysfs", pin)

    def setup(self, pin, mode):
        sn = self._sn(pin)
        gdir = self._BASE / f"gpio{sn}"
        if not gdir.exists():
            try:
                (self._BASE / "export").write_text(str(sn))
                time.sleep(0.05)
            except Exception:
                pass
        try:
            (gdir / "direction").write_text("out" if mode == "OUT" else "in")
        except Exception as e:
            log.debug("sysfs setup %d: %s", pin, e)

    def output(self, pin, value):
        try:
            (self._BASE / f"gpio{self._sn(pin)}" / "value").write_text(str(value))
        except Exception as e:
            log.debug("sysfs out %d: %s", pin, e)

    def input(self, pin) -> int:
        try:
            return int((self._BASE / f"gpio{self._sn(pin)}" / "value").read_text().strip())
        except Exception:
            return 0

    def name(self):
        return "sysfs"


def _create_gpio_backend(preferred: str = "auto") -> _GPIOBackend:
    order = {"opi": ["opi", "gpiod", "sysfs"], "gpiod": ["gpiod", "opi", "sysfs"]}.get(
        preferred, ["opi", "gpiod", "sysfs"]
    )
    for b in order:
        try:
            obj = _OpiGPIOBackend() if b == "opi" else _GpiodBackend() if b == "gpiod" else None
            if obj:
                log.info("GPIO backend: %s", obj.name())
                return obj
        except Exception as e:
            log.debug("GPIO %s недоступен: %s", b, e)
    log.info("GPIO backend: sysfs")
    return _SysfsBackend()


# ─────────────────────────────────────────────────────────────────────────────
# МИНИМАЛЬНЫЙ MODBUS RTU СТЕК
# ─────────────────────────────────────────────────────────────────────────────


def _crc16(data: bytes) -> bytes:
    crc = 0xFFFF
    for b in data:
        crc ^= b
        for _ in range(8):
            crc = (crc >> 1) ^ 0xA001 if crc & 1 else crc >> 1
    return struct.pack("<H", crc)


def _mb_read(ser, slave: int, reg: int, count: int) -> Optional[List[int]]:
    req = struct.pack(">BBHH", slave, 0x03, reg, count)
    req += _crc16(req)
    ser.reset_input_buffer()
    ser.write(req)
    time.sleep(0.05)
    resp = ser.read(5 + count * 2)
    if len(resp) < 5 + count * 2 or resp[-2:] != _crc16(resp[:-2]):
        return None
    return [struct.unpack(">H", resp[3 + i : 5 + i])[0] for i in range(0, resp[2], 2)]


def _mb_write(ser, slave: int, reg: int, value: int) -> bool:
    req = struct.pack(">BBHH", slave, 0x06, reg, value)
    req += _crc16(req)
    ser.reset_input_buffer()
    ser.write(req)
    time.sleep(0.05)
    resp = ser.read(8)
    return len(resp) >= 8 and resp[6:8] == _crc16(resp[:6])


# ─────────────────────────────────────────────────────────────────────────────
# ОСНОВНОЙ КЛАСС
# ─────────────────────────────────────────────────────────────────────────────


class OrangePiBridge:
    """
    Универсальный аппаратный мост Аргоса для Orange Pi One.

    GPIO / I2C / UART / SPI / 1-Wire / RS-485 / Modbus RTU.
    Подключается к ArgosCore через _init_orangepi() и execute_intent.
    """

    def __init__(self, core=None):
        self.core = core
        self._lock = threading.Lock()

        self._gpio_backend_pref = os.getenv("OPI_GPIO_BACKEND", "auto")
        self._i2c_bus = int(os.getenv("OPI_I2C_BUS", "0"))
        self._uart_port = os.getenv("OPI_UART_PORT", "/dev/ttyS1")
        self._uart_baud = int(os.getenv("OPI_UART_BAUD", "9600"))
        self._rs485_port = os.getenv("OPI_RS485_PORT", "/dev/ttyS2")
        self._rs485_baud = int(os.getenv("OPI_RS485_BAUD", "9600"))
        self._w1_path = Path(os.getenv("OPI_1WIRE_PATH", "/sys/bus/w1/devices"))

        self._gpio: Optional[_GPIOBackend] = None
        self._i2c = None
        self._uart = None
        self._rs485 = None
        self._spi = None
        self._gpio_states: Dict[int, str] = {}

        log.info(
            "OrangePiBridge init (I2C=bus%d UART=%s RS485=%s)",
            self._i2c_bus,
            self._uart_port,
            self._rs485_port,
        )

    # ── GPIO ─────────────────────────────────────────────────────────────────

    def _gpio_ensure(self) -> _GPIOBackend:
        if self._gpio is None:
            self._gpio = _create_gpio_backend(self._gpio_backend_pref)
        return self._gpio

    def gpio_out(self, pin: int, value: int) -> str:
        try:
            g = self._gpio_ensure()
            if self._gpio_states.get(pin) != "OUT":
                g.setup(pin, "OUT")
                self._gpio_states[pin] = "OUT"
            g.output(pin, value)
            n = OPI_ONE_PIN_MAP.get(pin, {}).get("name", f"P{pin}")
            return f"✅ GPIO pin {pin} ({n}): {'HIGH' if value else 'LOW'}"
        except Exception as e:
            return f"❌ GPIO out pin {pin}: {e}"

    def gpio_in(self, pin: int) -> str:
        try:
            g = self._gpio_ensure()
            if self._gpio_states.get(pin) != "IN":
                g.setup(pin, "IN")
                self._gpio_states[pin] = "IN"
            val = g.input(pin)
            n = OPI_ONE_PIN_MAP.get(pin, {}).get("name", f"P{pin}")
            return f"📍 GPIO pin {pin} ({n}): {'HIGH' if val else 'LOW'}"
        except Exception as e:
            return f"❌ GPIO in pin {pin}: {e}"

    def gpio_status(self) -> str:
        try:
            backend = self._gpio_ensure().name()
        except Exception as e:
            return f"❌ GPIO недоступен: {e}"
        lines = [
            f"🔌 GPIO Orange Pi One — бэкенд: {backend}",
            f"  Настроено пинов: {len(self._gpio_states)}",
        ]
        for pin, mode in sorted(self._gpio_states.items()):
            info = OPI_ONE_PIN_MAP.get(pin, {})
            lines.append(f"  Pin {pin:2d} ({info.get('name','?'):8s}): {mode}")
        return "\n".join(lines)

    def pin_map(self) -> str:
        lines = [
            "📋 ORANGE PI ONE — 40-ПИН ХЕДЕР:\n",
            f"{'Физ':>4} {'WPi':>4} {'Sysfs':>6} {'Имя':<14} {'Функция'}",
            "─" * 52,
        ]
        for phys in sorted(OPI_ONE_PIN_MAP):
            p = OPI_ONE_PIN_MAP[phys]
            lines.append(f"{phys:>4} {p['wpi']:>4} {p['sysfs']:>6}  {p['name']:<14} {p['alt']}")
        lines.append("\nПитание: 1=3.3V, 2/4=5V, 6/9/14/20/25/30/34/39=GND")
        return "\n".join(lines)

    # ── I2C ──────────────────────────────────────────────────────────────────

    def _i2c_ensure(self):
        if self._i2c is None:
            import smbus2

            self._i2c = smbus2.SMBus(self._i2c_bus)
        return self._i2c

    def i2c_scan(self) -> str:
        try:
            import smbus2

            bus = smbus2.SMBus(self._i2c_bus)
        except Exception as e:
            return (
                f"❌ I2C bus {self._i2c_bus} недоступен: {e}\n"
                f"  Включить: sudo armbian-config → System → Hardware → i2c0/i2c1"
            )

        known = {
            0x3C: "SSD1306 OLED",
            0x3D: "SSD1306 OLED (alt)",
            0x40: "INA219 ток/напряж.",
            0x48: "ADS1115 АЦП",
            0x68: "MPU6050 / DS3231 RTC",
            0x69: "MPU6050 (alt)",
            0x76: "BME280/BMP280",
            0x77: "BME280/BMP280 (alt)",
            0x60: "SI1145 UV/свет",
            0x70: "PCA9548 мультиплексор",
        }
        found = []
        for addr in range(0x03, 0x78):
            try:
                bus.read_byte(addr)
                found.append(f"  0x{addr:02X} — {known.get(addr, 'неизвестное')}")
            except Exception:
                pass
        bus.close()
        if not found:
            return f"🔍 I2C bus {self._i2c_bus}: устройств не найдено. Проверь подтяжки SDA/SCL (4.7кОм)"
        return f"🔍 I2C bus {self._i2c_bus} — {len(found)} устройств:\n" + "\n".join(found)

    def i2c_read(self, addr: int, reg: int) -> str:
        try:
            val = self._i2c_ensure().read_byte_data(addr, reg)
            return f"I2C 0x{addr:02X} reg 0x{reg:02X}: 0x{val:02X} ({val})"
        except Exception as e:
            return f"❌ I2C read 0x{addr:02X}: {e}"

    def i2c_write(self, addr: int, reg: int, value: int) -> str:
        try:
            self._i2c_ensure().write_byte_data(addr, reg, value)
            return f"✅ I2C 0x{addr:02X} reg 0x{reg:02X} ← 0x{value:02X}"
        except Exception as e:
            return f"❌ I2C write 0x{addr:02X}: {e}"

    def read_bmp280(self, addr: int = 0x76) -> str:
        """Читает температуру с BMP280/BME280."""
        try:
            import smbus2

            bus = smbus2.SMBus(self._i2c_bus)
            chip_id = bus.read_byte_data(addr, 0xD0)
            if chip_id not in (0x55, 0x58, 0x60, 0x61):
                return f"❌ BMP280: неверный chip_id 0x{chip_id:02X}"
            calib = bus.read_i2c_block_data(addr, 0x88, 24)
            T1 = calib[1] << 8 | calib[0]
            T2 = calib[3] << 8 | calib[2]
            T2 = T2 - 65536 if T2 > 32767 else T2
            T3 = calib[5] << 8 | calib[4]
            T3 = T3 - 65536 if T3 > 32767 else T3
            bus.write_byte_data(addr, 0xF4, 0x25)
            time.sleep(0.1)
            raw = bus.read_i2c_block_data(addr, 0xF7, 6)
            raw_t = (raw[3] << 12) | (raw[4] << 4) | (raw[5] >> 4)
            var1 = (raw_t / 16384.0 - T1 / 1024.0) * T2
            var2 = (raw_t / 131072.0 - T1 / 8192.0) ** 2 * T3
            temp = (var1 + var2) / 5120.0
            bus.close()
            return f"🌡 BMP280 (0x{addr:02X}): {temp:.2f}°C"
        except Exception as e:
            return f"❌ BMP280: {e}"

    # ── 1-Wire ────────────────────────────────────────────────────────────────

    def read_1wire(self) -> str:
        if not self._w1_path.exists():
            return (
                "❌ 1-Wire не включён.\n"
                "  Добавь в /boot/armbianEnv.txt:\n"
                "    overlays=w1-gpio\n"
                "    param_w1_pin=PA6\n"
                "  Затем: sudo reboot"
            )
        sensors = list(self._w1_path.glob("28-*"))
        if not sensors:
            return "🌡 1-Wire: датчики DS18B20 не найдены (пин PA6, физ. 7)"
        results = [f"🌡 1-Wire DS18B20 ({len(sensors)}):"]
        for s in sensors:
            try:
                txt = (s / "w1_slave").read_text()
                if "YES" in txt:
                    temp = float(txt.split("t=")[-1].strip()) / 1000.0
                    results.append(f"  {s.name}: {temp:.3f}°C")
                else:
                    results.append(f"  {s.name}: ошибка CRC")
            except Exception as e:
                results.append(f"  {s.name}: {e}")
        return "\n".join(results)

    # ── UART ─────────────────────────────────────────────────────────────────

    def _uart_ensure(self):
        if self._uart is None or not self._uart.is_open:
            import serial

            self._uart = serial.Serial(self._uart_port, self._uart_baud, timeout=1.0)
        return self._uart

    def uart_send(self, data: str) -> str:
        try:
            ser = self._uart_ensure()
            ser.write((data + "\r\n").encode())
            time.sleep(0.1)
            resp = ser.read(ser.in_waiting or 64).decode("utf-8", errors="replace").strip()
            return (
                f"📡 UART → '{data}'\n   ← '{resp}'" if resp else f"📡 UART → '{data}' (нет ответа)"
            )
        except Exception as e:
            return f"❌ UART {self._uart_port}: {e}"

    def uart_recv(self, timeout: float = 2.0) -> str:
        try:
            ser = self._uart_ensure()
            ser.timeout = timeout
            data = ser.read(512).decode("utf-8", errors="replace").strip()
            return f"📡 UART ← '{data}'" if data else "📡 UART: нет данных"
        except Exception as e:
            return f"❌ UART recv: {e}"

    # ── RS-485 / Modbus RTU ───────────────────────────────────────────────────

    def _rs485_ensure(self):
        if self._rs485 is None or not self._rs485.is_open:
            import serial

            self._rs485 = serial.Serial(
                self._rs485_port,
                self._rs485_baud,
                bytesize=8,
                parity="N",
                stopbits=1,
                timeout=1.0,
                rtscts=False,
            )
            self._rs485.setRTS(False)
        return self._rs485

    def modbus_read(self, slave: int, reg: int, count: int = 1) -> str:
        try:
            ser = self._rs485_ensure()
            ser.setRTS(True)
            time.sleep(0.002)
            vals = _mb_read(ser, slave, reg, count)
            ser.setRTS(False)
            if vals is None:
                return f"❌ Modbus: нет ответа от slave {slave} reg {reg}"
            return f"📟 Modbus slave {slave} reg {reg}×{count}: {vals}"
        except Exception as e:
            return f"❌ Modbus read: {e}"

    def modbus_write(self, slave: int, reg: int, value: int) -> str:
        try:
            ser = self._rs485_ensure()
            ser.setRTS(True)
            time.sleep(0.002)
            ok = _mb_write(ser, slave, reg, value)
            ser.setRTS(False)
            return (
                f"✅ Modbus slave {slave} reg {reg} ← {value}"
                if ok
                else f"❌ Modbus: нет подтверждения от slave {slave}"
            )
        except Exception as e:
            return f"❌ Modbus write: {e}"

    def rs485_raw(self, data: bytes) -> str:
        try:
            ser = self._rs485_ensure()
            ser.setRTS(True)
            ser.write(data)
            ser.flush()
            time.sleep(0.005)
            ser.setRTS(False)
            time.sleep(0.05)
            resp = ser.read(64)
            return (
                f"📟 RS-485: {len(data)}B → {len(resp)}B  HEX: {resp.hex()}"
                if resp
                else f"📟 RS-485: {len(data)}B отправлено (нет ответа)"
            )
        except Exception as e:
            return f"❌ RS-485: {e}"

    # ── SPI ──────────────────────────────────────────────────────────────────

    def spi_transfer(self, data: List[int], speed: int = 500000) -> str:
        try:
            import spidev

            if self._spi is None:
                self._spi = spidev.SpiDev()
                self._spi.open(0, 0)
            self._spi.max_speed_hz = speed
            self._spi.mode = 0
            resp = self._spi.xfer2(data)
            return f"📺 SPI TX: {[hex(b) for b in data]}\n" f"       RX: {[hex(b) for b in resp]}"
        except Exception as e:
            return f"❌ SPI: {e}"

    # ── СКАНЕР ───────────────────────────────────────────────────────────────

    def scan_all(self) -> str:
        out = ["🔍 ORANGE PI ONE — ПОЛНОЕ СКАНИРОВАНИЕ\n"]
        try:
            out.append(f"✅ GPIO: {self._gpio_ensure().name()}")
        except Exception as e:
            out.append(f"❌ GPIO: {e}")
        out.append("\n" + self.i2c_scan())
        out.append("\n" + self.read_1wire())
        for port, attr, label in [
            (self._uart_port, "_uart", "UART"),
            (self._rs485_port, "_rs485", "RS-485"),
        ]:
            try:
                (self._uart_ensure if label == "UART" else self._rs485_ensure)()
                out.append(f"✅ {label}: {port}")
            except Exception as e:
                out.append(f"❌ {label} {port}: {e}")
        out.append(f"{'✅' if Path('/dev/spidev0.0').exists() else '❌'} SPI: /dev/spidev0.0")
        return "\n".join(out)

    # ── СТАТУС ────────────────────────────────────────────────────────────────

    def status(self) -> str:
        gpio_n = "не инициализирован"
        try:
            gpio_n = self._gpio_ensure().name()
        except Exception:
            pass
        w1 = len(list(self._w1_path.glob("28-*"))) if self._w1_path.exists() else 0
        return (
            f"🟠 ORANGE PI ONE BRIDGE\n"
            f"  GPIO:   {gpio_n} | пинов: {len(self._gpio_states)}\n"
            f"  I2C:    bus {self._i2c_bus} {'✅' if self._i2c else '○'}\n"
            f"  UART:   {self._uart_port} @ {self._uart_baud} {'✅' if self._uart and self._uart.is_open else '○'}\n"
            f"  RS-485: {self._rs485_port} @ {self._rs485_baud} {'✅' if self._rs485 and self._rs485.is_open else '○'}\n"
            f"  1-Wire: {w1} DS18B20\n"
            f"  SPI:    {'✅' if Path('/dev/spidev0.0').exists() else '❌'} /dev/spidev0.0"
        )

    def cleanup(self):
        if self._gpio:
            try:
                self._gpio.cleanup()
            except Exception:
                pass
        for obj in (self._uart, self._rs485):
            if obj and obj.is_open:
                try:
                    obj.close()
                except Exception:
                    pass
        if self._i2c:
            try:
                self._i2c.close()
            except Exception:
                pass
        if self._spi:
            try:
                self._spi.close()
            except Exception:
                pass
        log.info("OrangePiBridge: cleanup завершён")
