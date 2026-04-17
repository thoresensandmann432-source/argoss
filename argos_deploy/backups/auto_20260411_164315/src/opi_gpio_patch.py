"""
opi_gpio_patch.py — Совместимость GPIO для Orange Pi One (H3/Allwinner)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Orange Pi One отличия от Raspberry Pi:
  • SoC: Allwinner H3 (Cortex-A7 quad-core, 512MB RAM)
  • GPIO: 40-pin совместимость, но НЕ RPi.GPIO — нужен OPi.GPIO или gpiod
  • I2C : /dev/i2c-0 (PA11=SDA, PA12=SCL)  — активируется через armbian-config
  • SPI : /dev/spidev0.0  (PA0..PA3)
  • UART: /dev/ttyS0 (PA4/PA5), /dev/ttyS1 (PA14/PA13) - LoRa/Modbus
  • Нет встроенного WiFi/BT — нужен USB донгл

Этот модуль:
  1. Подменяет RPi.GPIO → OPi.GPIO в sys.modules (прозрачно для остального кода)
  2. Публикует константы: OPI_I2C_BUS, OPI_UART_PORT, GPIO_AVAILABLE
  3. Безопасен на не-OPi платформах (ничего не ломает)
"""

from __future__ import annotations
import sys
import os
import logging

log = logging.getLogger("argos.opi_gpio")

# ── Определяем платформу ──────────────────────────────────────────────────
def _is_orange_pi() -> bool:
    """Определяем что мы на Orange Pi (по /proc/cpuinfo или env)."""
    if os.getenv("OPI_GPIO_MODE"):
        return True
    try:
        cpuinfo = open("/proc/cpuinfo").read().lower()
        return "allwinner" in cpuinfo or "sun8i" in cpuinfo or "h3" in cpuinfo
    except Exception:
        return False

IS_ORANGE_PI = _is_orange_pi()
IS_LINUX_ARM = sys.platform == "linux" and os.uname().machine in ("aarch64", "armv7l")

# ── I2C ───────────────────────────────────────────────────────────────────
# Orange Pi One: /dev/i2c-0
OPI_I2C_BUS   = int(os.getenv("OPI_I2C_BUS", "0"))
OPI_I2C_AVAIL = os.path.exists(f"/dev/i2c-{OPI_I2C_BUS}")

# ── UART ──────────────────────────────────────────────────────────────────
# Предпочтительный порт для LoRa/Modbus на OPi One
_uart_candidates = ["/dev/ttyS1", "/dev/ttyUSB0", "/dev/ttyACM0", "/dev/ttyS0"]
OPI_UART_PORT = os.getenv("LORA_PORT") or os.getenv("MODBUS_PORT") or next(
    (p for p in _uart_candidates if os.path.exists(p)), "/dev/ttyS1"
)

# ── GPIO подмена ──────────────────────────────────────────────────────────
GPIO_AVAILABLE = False

def _install_gpio_shim():
    """Устанавливает совместимый GPIO shim в sys.modules."""
    global GPIO_AVAILABLE

    # Попытка 1: OPi.GPIO (официальная библиотека для Orange Pi)
    try:
        import OPi.GPIO as _gpio  # type: ignore
        mode = os.getenv("OPI_GPIO_MODE", "SUNXI")
        _gpio.setmode(getattr(_gpio, mode, _gpio.SUNXI))
        _ensure_rpi_module(_gpio)
        GPIO_AVAILABLE = True
        log.info("OPi.GPIO загружен (режим %s)", mode)
        return _gpio
    except ImportError:
        pass

    # Попытка 2: gpiod (новый Linux GPIO API)
    try:
        import gpiod as _gpiod  # type: ignore

        class _GpiodShim:
            """Минимальный shim RPi.GPIO поверх gpiod."""
            BCM = BOARD = SUNXI = OUT = IN = HIGH = LOW = 1
            PUD_UP = PUD_DOWN = 0

            def __init__(self):
                self._chip = None
                try:
                    self._chip = _gpiod.Chip("gpiochip0")
                except Exception:
                    pass

            def setmode(self, m): pass
            def setwarnings(self, w): pass

            def setup(self, pin, direction, initial=0, pull_up_down=0):
                if not self._chip: return
                try:
                    line = self._chip.get_line(pin)
                    if direction == self.OUT:
                        line.request(consumer="argos", type=_gpiod.LINE_REQ_DIR_OUT, default_vals=[initial])
                    else:
                        line.request(consumer="argos", type=_gpiod.LINE_REQ_DIR_IN)
                except Exception as e:
                    log.debug("GPIO setup pin %s: %s", pin, e)

            def output(self, pin, value):
                if not self._chip: return
                try:
                    self._chip.get_line(pin).set_value(int(value))
                except Exception:
                    pass

            def input(self, pin):
                if not self._chip: return 0
                try:
                    return self._chip.get_line(pin).get_value()
                except Exception:
                    return 0

            def cleanup(self, *a):
                if self._chip:
                    try: self._chip.close()
                    except: pass

        shim = _GpiodShim()
        _ensure_rpi_module(shim)
        GPIO_AVAILABLE = True
        log.info("GPIO shim: gpiod backend")
        return shim
    except ImportError:
        pass

    # Fallback: тихий no-op shim (не роняет ARGOS на десктопе/x86)
    class _NoopGPIO:
        BCM = BOARD = SUNXI = OUT = IN = HIGH = LOW = 1
        PUD_UP = PUD_DOWN = 0
        def setmode(self, m): pass
        def setwarnings(self, w): pass
        def setup(self, *a, **k): pass
        def output(self, *a): pass
        def input(self, pin): return 0
        def cleanup(self, *a): pass
        def PWM(self, pin, freq): return type("PWM",(),{"start":lambda*a:None,"stop":lambda*a:None,"ChangeDutyCycle":lambda*a:None})()

    noop = _NoopGPIO()
    _ensure_rpi_module(noop)
    log.debug("GPIO: no-op shim (OPi.GPIO и gpiod не найдены)")
    return noop


def _ensure_rpi_module(gpio_obj):
    """Создаёт RPi.GPIO в sys.modules если не существует."""
    if "RPi" not in sys.modules:
        rpi_mod = type(sys)("RPi")
        rpi_mod.GPIO = gpio_obj
        sys.modules["RPi"]     = rpi_mod
        sys.modules["RPi.GPIO"] = gpio_obj


# ── Устанавливаем shim при импорте ────────────────────────────────────────
_gpio_instance = _install_gpio_shim()


# ── Публичный API ─────────────────────────────────────────────────────────
def get_gpio():
    """Возвращает GPIO объект (OPi.GPIO, gpiod-shim или no-op)."""
    return _gpio_instance


def i2c_scan() -> list[int]:
    """Сканирует I2C шину и возвращает адреса найденных устройств."""
    found = []
    try:
        import smbus2
        bus = smbus2.SMBus(OPI_I2C_BUS)
        for addr in range(0x08, 0x78):
            try:
                bus.read_byte(addr)
                found.append(addr)
            except Exception:
                pass
        bus.close()
    except ImportError:
        log.warning("smbus2 не установлен: pip install smbus2 --break-system-packages")
    except Exception as e:
        log.warning("I2C scan: %s", e)
    return found


def status_report() -> str:
    """Статус аппаратных интерфейсов Orange Pi One."""
    lines = ["🍊 ORANGE PI ONE — АППАРАТНЫЙ СТАТУС"]
    lines.append(f"  GPIO   : {'✅ ' + type(_gpio_instance).__name__ if GPIO_AVAILABLE else '○  нет библиотеки'}")
    lines.append(f"  I2C    : {'✅ /dev/i2c-' + str(OPI_I2C_BUS) if OPI_I2C_AVAIL else '○  /dev/i2c-' + str(OPI_I2C_BUS) + ' не найден'}")

    spi_avail = os.path.exists("/dev/spidev0.0")
    lines.append(f"  SPI    : {'✅ /dev/spidev0.0' if spi_avail else '○  /dev/spidev0.0 не найден'}")
    lines.append(f"  UART   : {'✅ ' + OPI_UART_PORT if os.path.exists(OPI_UART_PORT) else '○  ' + OPI_UART_PORT + ' не найден'}")

    # I2C устройства
    if OPI_I2C_AVAIL:
        devs = i2c_scan()
        if devs:
            hex_addrs = ", ".join(f"0x{a:02X}" for a in devs)
            lines.append(f"  I2C девайсы: {hex_addrs}")
        else:
            lines.append("  I2C девайсы: нет (или шина не активирована)")

    # USB устройства
    try:
        usb_devs = os.listdir("/dev/")
        usb_tty = [d for d in usb_devs if "ttyUSB" in d or "ttyACM" in d]
        if usb_tty:
            lines.append(f"  USB Serial : ✅ {', '.join('/dev/' + d for d in usb_tty)}")
    except Exception:
        pass

    lines.append("")
    lines.append("  Для активации: sudo armbian-config → System → Hardware")
    lines.append("  Включи: i2c0, spi-spidev, uart1")
    return "\n".join(lines)
