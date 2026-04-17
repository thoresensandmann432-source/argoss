"""
argos_rp2350_geek.py — ARGOS firmware для Waveshare RP2350-GEEK
═══════════════════════════════════════════════════════════════
MicroPython firmware: дисплей 1.14" ST7789 135×240, USB Serial JSON

Установка:
  1. Загрузи MicroPython для RP2350 (ARM): https://micropython.org/download/RPI_PICO2/
  2. Скопируй этот файл как main.py через Thonny или rshell
  3. Также скопируй st7789.py (драйвер дисплея) — см. ниже

Дисплей (SPI0):
  LCD_CS   = GP9
  LCD_CLK  = GP10
  LCD_MOSI = GP11
  LCD_DC   = GP8
  LCD_RST  = GP12
  LCD_BL   = GP13    (подсветка PWM)

Кнопки:
  BTN_A    = GP15
  BTN_B    = GP17

USB Serial: CDC 115200 baud, JSON протокол
  Отправляет: {"type":"hello",...} | {"type":"pong"} | {"type":"user_cmd","cmd":"..."}
  Принимает:  {"type":"status","cpu":7.2,"ram":42.1,"disk":"120GB","os":"Windows"}
              {"type":"reply","text":"..."}
              {"type":"ping"}

Температура: внутренний датчик RP2350 ADC (канал 4)
"""

import sys
import json
import time
import machine
import utime

# ── Пины ─────────────────────────────────────────────────────────────────────
LCD_CS   = 9
LCD_CLK  = 10
LCD_MOSI = 11
LCD_DC   = 8
LCD_RST  = 12
LCD_BL   = 13

BTN_A_PIN = 15
BTN_B_PIN = 17

# ── Цвета (RGB565) ────────────────────────────────────────────────────────────
BLACK   = 0x0000
WHITE   = 0xFFFF
GRAY    = 0x8410
DKGRAY  = 0x3186
RED     = 0xF800
GREEN   = 0x07E0
DKGREEN = 0x03E0
BLUE    = 0x001F
CYAN    = 0x07FF
YELLOW  = 0xFFE0
ORANGE  = 0xFD20
PURPLE  = 0x8010
ARGOS_C = 0x04FF   # фирменный ARGOS синий-зелёный

# ── Дисплей ───────────────────────────────────────────────────────────────────
WIDTH  = 135
HEIGHT = 240

# ── Внутренний ADC (температура) ─────────────────────────────────────────────
_adc_temp = machine.ADC(4)   # канал 4 = внутренний датчик RP2350

def read_chip_temp() -> float:
    """Читает температуру чипа RP2350 в °C."""
    raw = _adc_temp.read_u16()
    voltage = raw * 3.3 / 65535
    # Формула RP2040/RP2350: T = 27 - (V - 0.706) / 0.001721
    return round(27.0 - (voltage - 0.706) / 0.001721, 1)


# ── ST7789 mini-driver ────────────────────────────────────────────────────────
# Встроенный минимальный драйвер — работает без внешних библиотек
class ST7789:
    def __init__(self, spi, dc, cs, rst, bl, width=135, height=240):
        self.spi = spi
        self.dc  = machine.Pin(dc,  machine.Pin.OUT)
        self.cs  = machine.Pin(cs,  machine.Pin.OUT)
        self.rst = machine.Pin(rst, machine.Pin.OUT)
        self.bl  = machine.PWM(machine.Pin(bl))
        self.bl.freq(1000)
        self.bl.duty_u16(65535)
        self.w   = width
        self.h   = height
        self._init()

    def _cmd(self, c, data=None):
        self.cs(0); self.dc(0)
        self.spi.write(bytes([c]))
        if data:
            self.dc(1)
            self.spi.write(bytes(data))
        self.cs(1)

    def _init(self):
        self.rst(0); utime.sleep_ms(10)
        self.rst(1); utime.sleep_ms(120)
        cmds = [
            (0x11, None),          # Sleep out
            (0x3A, [0x05]),        # Color mode: 16bit RGB565
            (0x36, [0x70]),        # MadCtl: BGR swap, row/col order for 135×240
            (0xB2, [0x0C,0x0C,0x00,0x33,0x33]),  # Porch
            (0xB7, [0x35]),        # Gate ctrl
            (0xBB, [0x19]),        # VCOMS
            (0xC0, [0x2C]),        # LCM ctrl
            (0xC2, [0x01]),        # VDV/VRH en
            (0xC3, [0x12]),        # VRH
            (0xC4, [0x20]),        # VDV
            (0xC6, [0x0F]),        # FR ctrl
            (0xD0, [0xA4,0xA1]),   # Power ctrl
            (0xE0, [0xD0,0x04,0x0D,0x11,0x13,0x2B,0x3F,0x54,0x4C,0x18,0x0D,0x0B,0x1F,0x23]),
            (0xE1, [0xD0,0x04,0x0C,0x11,0x13,0x2C,0x3F,0x44,0x51,0x2F,0x1F,0x1F,0x20,0x23]),
            (0x21, None),          # Display inversion ON
            (0x29, None),          # Display ON
        ]
        utime.sleep_ms(5)
        for cmd, data in cmds:
            self._cmd(cmd, data)
            if cmd == 0x11:
                utime.sleep_ms(120)

    def set_window(self, x0, y0, x1, y1):
        # ST7789 135×240 offset: col+52, row+40
        x0 += 52; x1 += 52
        y0 += 40; y1 += 40
        self._cmd(0x2A, [x0>>8, x0&0xFF, x1>>8, x1&0xFF])
        self._cmd(0x2B, [y0>>8, y0&0xFF, y1>>8, y1&0xFF])
        self._cmd(0x2C)

    def fill_rect(self, x, y, w, h, color):
        self.set_window(x, y, x+w-1, y+h-1)
        hi = color >> 8; lo = color & 0xFF
        chunk = bytes([hi, lo] * 64)
        total = w * h
        self.cs(0); self.dc(1)
        while total > 0:
            n = min(total, 64)
            self.spi.write(chunk[:n*2])
            total -= n
        self.cs(1)

    def fill(self, color):
        self.fill_rect(0, 0, self.w, self.h, color)

    def pixel(self, x, y, color):
        self.set_window(x, y, x, y)
        self.cs(0); self.dc(1)
        self.spi.write(bytes([color>>8, color&0xFF]))
        self.cs(1)

    def hline(self, x, y, w, color):
        self.fill_rect(x, y, w, 1, color)

    def vline(self, x, y, h, color):
        self.fill_rect(x, y, 1, h, color)

    def rect(self, x, y, w, h, color):
        self.hline(x, y, w, color)
        self.hline(x, y+h-1, w, color)
        self.vline(x, y, h, color)
        self.vline(x+w-1, y, h, color)

    # ── Шрифт 5×8 (встроенный, ASCII 32-127) ────────────────────────────
    _FONT = (
        b'\x00\x00\x00\x00\x00'  # ' '
        b'\x00\x00\x5f\x00\x00'  # '!'
        b'\x00\x07\x00\x07\x00'  # '"'
        b'\x14\x7f\x14\x7f\x14'  # '#'
        b'\x24\x2a\x7f\x2a\x12'  # '$'
        b'\x23\x13\x08\x64\x62'  # '%'
        b'\x36\x49\x55\x22\x50'  # '&'
        b'\x00\x05\x03\x00\x00'  # "'"
        b'\x00\x1c\x22\x41\x00'  # '('
        b'\x00\x41\x22\x1c\x00'  # ')'
        b'\x14\x08\x3e\x08\x14'  # '*'
        b'\x08\x08\x3e\x08\x08'  # '+'
        b'\x00\x50\x30\x00\x00'  # ','
        b'\x08\x08\x08\x08\x08'  # '-'
        b'\x00\x60\x60\x00\x00'  # '.'
        b'\x20\x10\x08\x04\x02'  # '/'
        b'\x3e\x51\x49\x45\x3e'  # '0'
        b'\x00\x42\x7f\x40\x00'  # '1'
        b'\x42\x61\x51\x49\x46'  # '2'
        b'\x21\x41\x45\x4b\x31'  # '3'
        b'\x18\x14\x12\x7f\x10'  # '4'
        b'\x27\x45\x45\x45\x39'  # '5'
        b'\x3c\x4a\x49\x49\x30'  # '6'
        b'\x01\x71\x09\x05\x03'  # '7'
        b'\x36\x49\x49\x49\x36'  # '8'
        b'\x06\x49\x49\x29\x1e'  # '9'
        b'\x00\x36\x36\x00\x00'  # ':'
        b'\x00\x56\x36\x00\x00'  # ';'
        b'\x08\x14\x22\x41\x00'  # '<'
        b'\x14\x14\x14\x14\x14'  # '='
        b'\x00\x41\x22\x14\x08'  # '>'
        b'\x02\x01\x51\x09\x06'  # '?'
        b'\x32\x49\x79\x41\x3e'  # '@'
        b'\x7e\x11\x11\x11\x7e'  # 'A'
        b'\x7f\x49\x49\x49\x36'  # 'B'
        b'\x3e\x41\x41\x41\x22'  # 'C'
        b'\x7f\x41\x41\x22\x1c'  # 'D'
        b'\x7f\x49\x49\x49\x41'  # 'E'
        b'\x7f\x09\x09\x09\x01'  # 'F'
        b'\x3e\x41\x49\x49\x7a'  # 'G'
        b'\x7f\x08\x08\x08\x7f'  # 'H'
        b'\x00\x41\x7f\x41\x00'  # 'I'
        b'\x20\x40\x41\x3f\x01'  # 'J'
        b'\x7f\x08\x14\x22\x41'  # 'K'
        b'\x7f\x40\x40\x40\x40'  # 'L'
        b'\x7f\x02\x0c\x02\x7f'  # 'M'
        b'\x7f\x04\x08\x10\x7f'  # 'N'
        b'\x3e\x41\x41\x41\x3e'  # 'O'
        b'\x7f\x09\x09\x09\x06'  # 'P'
        b'\x3e\x41\x51\x21\x5e'  # 'Q'
        b'\x7f\x09\x19\x29\x46'  # 'R'
        b'\x46\x49\x49\x49\x31'  # 'S'
        b'\x01\x01\x7f\x01\x01'  # 'T'
        b'\x3f\x40\x40\x40\x3f'  # 'U'
        b'\x1f\x20\x40\x20\x1f'  # 'V'
        b'\x3f\x40\x38\x40\x3f'  # 'W'
        b'\x63\x14\x08\x14\x63'  # 'X'
        b'\x07\x08\x70\x08\x07'  # 'Y'
        b'\x61\x51\x49\x45\x43'  # 'Z'
        b'\x00\x7f\x41\x41\x00'  # '['
        b'\x02\x04\x08\x10\x20'  # '\'
        b'\x00\x41\x41\x7f\x00'  # ']'
        b'\x04\x02\x01\x02\x04'  # '^'
        b'\x40\x40\x40\x40\x40'  # '_'
        b'\x00\x01\x02\x04\x00'  # '`'
        b'\x20\x54\x54\x54\x78'  # 'a'
        b'\x7f\x48\x44\x44\x38'  # 'b'
        b'\x38\x44\x44\x44\x20'  # 'c'
        b'\x38\x44\x44\x48\x7f'  # 'd'
        b'\x38\x54\x54\x54\x18'  # 'e'
        b'\x08\x7e\x09\x01\x02'  # 'f'
        b'\x0c\x52\x52\x52\x3e'  # 'g'
        b'\x7f\x08\x04\x04\x78'  # 'h'
        b'\x00\x44\x7d\x40\x00'  # 'i'
        b'\x20\x40\x44\x3d\x00'  # 'j'
        b'\x7f\x10\x28\x44\x00'  # 'k'
        b'\x00\x41\x7f\x40\x00'  # 'l'
        b'\x7c\x04\x18\x04\x78'  # 'm'
        b'\x7c\x08\x04\x04\x78'  # 'n'
        b'\x38\x44\x44\x44\x38'  # 'o'
        b'\x7c\x14\x14\x14\x08'  # 'p'
        b'\x08\x14\x14\x18\x7c'  # 'q'
        b'\x7c\x08\x04\x04\x08'  # 'r'
        b'\x48\x54\x54\x54\x20'  # 's'
        b'\x04\x3f\x44\x40\x20'  # 't'
        b'\x3c\x40\x40\x20\x7c'  # 'u'
        b'\x1c\x20\x40\x20\x1c'  # 'v'
        b'\x3c\x40\x30\x40\x3c'  # 'w'
        b'\x44\x28\x10\x28\x44'  # 'x'
        b'\x0c\x50\x50\x50\x3c'  # 'y'
        b'\x44\x64\x54\x4c\x44'  # 'z'
    )

    def char(self, x, y, c, fg, bg, scale=1):
        """Рисует символ ASCII."""
        idx = ord(c) - 32
        if idx < 0 or idx >= len(self._FONT) // 5:
            idx = 0
        for col in range(5):
            byte = self._FONT[idx*5 + col]
            for row in range(8):
                if byte & (1 << row):
                    if scale == 1:
                        self.pixel(x+col, y+row, fg)
                    else:
                        self.fill_rect(x+col*scale, y+row*scale, scale, scale, fg)
                elif bg != -1:
                    if scale == 1:
                        self.pixel(x+col, y+row, bg)
                    else:
                        self.fill_rect(x+col*scale, y+row*scale, scale, scale, bg)

    def text(self, s, x, y, fg=WHITE, bg=BLACK, scale=1):
        """Выводит строку текста."""
        cx = x
        for c in s:
            self.char(cx, y, c, fg, bg, scale)
            cx += (5 + 1) * scale
        return cx

    def text_center(self, s, y, fg=WHITE, bg=BLACK, scale=1):
        w = len(s) * 6 * scale
        x = (self.w - w) // 2
        self.text(s, x, y, fg, bg, scale)

    def set_brightness(self, pct):
        """Яркость 0-100."""
        self.bl.duty_u16(int(pct / 100 * 65535))


# ── Инициализация железа ──────────────────────────────────────────────────────
spi = machine.SPI(1,
    baudrate=40_000_000,
    polarity=0, phase=0,
    sck=machine.Pin(LCD_CLK),
    mosi=machine.Pin(LCD_MOSI),
    miso=machine.Pin(12 if LCD_MOSI != 12 else 99)  # MISO не используется
)
# Фиксируем: SPI1 CLK=10, MOSI=11 — MISO не нужен для ST7789
spi = machine.SPI(1, baudrate=40_000_000, polarity=0, phase=0,
                  sck=machine.Pin(10), mosi=machine.Pin(11))

tft = ST7789(spi, dc=LCD_DC, cs=LCD_CS, rst=LCD_RST, bl=LCD_BL,
             width=WIDTH, height=HEIGHT)

btn_a = machine.Pin(BTN_A_PIN, machine.Pin.IN, machine.Pin.PULL_UP)
btn_b = machine.Pin(BTN_B_PIN, machine.Pin.IN, machine.Pin.PULL_UP)

# ── Состояние ────────────────────────────────────────────────────────────────
state = {
    "cpu":     0.0,
    "ram":     0.0,
    "disk":    "--",
    "os":      "?",
    "reply":   "ARGOS ready",
    "temp":    0.0,
    "uptime":  0,
    "connected": False,
    "last_rx":   0,
}

cpu_history = [0] * 60   # граф CPU

FW_VERSION = "1.0.0"
DEVICE_ID  = "ARGOS-RP2350-GEEK"


# ── UI ───────────────────────────────────────────────────────────────────────

def draw_bar(x, y, w, h, pct, fg, bg=DKGRAY):
    """Горизонтальная полоса заполнения."""
    filled = int(w * pct / 100)
    tft.fill_rect(x, y, filled, h, fg)
    if filled < w:
        tft.fill_rect(x + filled, y, w - filled, h, bg)


def draw_graph(x, y, w, h, data, color):
    """Мини-граф из списка значений 0-100."""
    tft.fill_rect(x, y, w, h, DKGRAY)
    n = len(data)
    step = w / n
    for i, v in enumerate(data):
        bar_h = int(h * v / 100)
        if bar_h > 0:
            px = int(x + i * step)
            tft.vline(px, y + h - bar_h, bar_h, color)


def draw_header():
    """Заголовок: лого ARGOS + статус связи."""
    tft.fill_rect(0, 0, WIDTH, 18, ARGOS_C)
    tft.text("ARGOS", 2, 5, WHITE, ARGOS_C, scale=1)
    conn_icon = "USB" if state["connected"] else "---"
    conn_color = GREEN if state["connected"] else GRAY
    tft.text(conn_icon, WIDTH - 22, 5, conn_color, ARGOS_C)
    tft.text(f"T:{state['temp']}C", 40, 5, YELLOW, ARGOS_C)


def draw_metrics():
    """CPU / RAM полосы + значения."""
    y = 22
    tft.fill_rect(0, y, WIDTH, 80, BLACK)

    # CPU
    tft.text(f"CPU {state['cpu']:4.1f}%", 2, y, CYAN, BLACK)
    draw_bar(2, y+10, WIDTH-4, 7,
             min(state['cpu'], 100),
             GREEN if state['cpu'] < 70 else (YELLOW if state['cpu'] < 90 else RED))

    # RAM
    tft.text(f"RAM {state['ram']:4.1f}%", 2, y+22, CYAN, BLACK)
    draw_bar(2, y+32, WIDTH-4, 7,
             min(state['ram'], 100),
             BLUE if state['ram'] < 70 else (ORANGE if state['ram'] < 90 else RED))

    # Disk
    disk_str = f"DSK {state['disk']}"
    tft.text(disk_str[:12], 2, y+44, GRAY, BLACK)

    # OS
    tft.text(state['os'][:10], 2, y+56, DKGRAY, BLACK)


def draw_graph_section():
    """Граф CPU последние 60 точек."""
    y = 108
    tft.fill_rect(0, y-2, WIDTH, 2, DKGRAY)
    tft.text("CPU history", 2, y+1, DKGRAY, BLACK)
    draw_graph(2, y+12, WIDTH-4, 35, cpu_history, GREEN)


def draw_reply():
    """Последний ответ ARGOS."""
    y = 168
    tft.fill_rect(0, y-2, WIDTH, 2, DKGRAY)
    tft.fill_rect(0, y, WIDTH, 70, BLACK)
    tft.text("ARGOS:", 2, y+1, ARGOS_C, BLACK)
    # Оборачиваем по 18 символов
    txt = str(state['reply'])[:72]
    line_w = 18
    lines = [txt[i:i+line_w] for i in range(0, len(txt), line_w)]
    for i, line in enumerate(lines[:4]):
        tft.text(line, 2, y+12+i*13, WHITE, BLACK)


def draw_buttons():
    """Подсказки кнопок внизу."""
    tft.fill_rect(0, HEIGHT-14, WIDTH, 14, DKGRAY)
    tft.text("[A]Status", 2, HEIGHT-12, WHITE, DKGRAY)
    tft.text("[B]Clr", WIDTH-38, HEIGHT-12, WHITE, DKGRAY)


def full_redraw():
    tft.fill(BLACK)
    draw_header()
    draw_metrics()
    draw_graph_section()
    draw_reply()
    draw_buttons()


# ── Serial JSON протокол ──────────────────────────────────────────────────────
_rx_buf = ""


def serial_send(obj: dict):
    """Отправляет JSON объект по USB CDC."""
    sys.stdout.write(json.dumps(obj) + "\n")


def serial_poll() -> dict | None:
    """Неблокирующее чтение строки из USB CDC. Возвращает dict или None."""
    global _rx_buf
    try:
        if sys.stdin in uselect_readable():
            ch = sys.stdin.read(1)
            if ch == "\n":
                line = _rx_buf.strip()
                _rx_buf = ""
                if line.startswith("{"):
                    return json.loads(line)
            else:
                _rx_buf += ch
    except Exception:
        _rx_buf = ""
    return None


def uselect_readable():
    """Проверяет наличие данных в stdin без блокировки."""
    try:
        import uselect
        return uselect.select([sys.stdin], [], [], 0)[0]
    except Exception:
        return []


def handle_message(msg: dict):
    """Обрабатывает входящее сообщение от ARGOS PC."""
    t = msg.get("type", "")

    if t == "status":
        state["cpu"]  = float(msg.get("cpu",  0))
        state["ram"]  = float(msg.get("ram",  0))
        state["disk"] = str(msg.get("disk", "--"))
        state["os"]   = str(msg.get("os",   "?"))
        state["connected"] = True
        state["last_rx"]   = utime.ticks_ms()
        # Обновляем историю CPU
        cpu_history.pop(0)
        cpu_history.append(int(state["cpu"]))

    elif t == "reply":
        state["reply"] = msg.get("text", "")
        state["connected"] = True
        state["last_rx"]   = utime.ticks_ms()

    elif t == "ping":
        serial_send({"type": "pong"})

    elif t == "cmd":
        # Прямая команда от ПК — выполняем локально
        cmd = msg.get("cmd", "")
        if cmd == "reboot":
            machine.reset()
        elif cmd == "brightness":
            pct = int(msg.get("value", 80))
            tft.set_brightness(pct)
        elif cmd == "clear":
            state["reply"] = ""
            tft.fill_rect(0, 168, WIDTH, 70, BLACK)


def send_hello():
    """Отправляет приветствие ARGOS при подключении."""
    serial_send({
        "type":    "hello",
        "device":  DEVICE_ID,
        "fw":      FW_VERSION,
        "display": "ST7789 135x240",
        "chip":    "RP2350",
        "temp":    state["temp"],
    })


def send_telemetry():
    """Периодическая телеметрия RP2350 → ПК."""
    serial_send({
        "type":   "telemetry",
        "device": DEVICE_ID,
        "temp":   state["temp"],
        "uptime": state["uptime"],
    })


# ── Загрузочный экран ─────────────────────────────────────────────────────────
def splash_screen():
    tft.fill(BLACK)
    tft.fill_rect(0, 0, WIDTH, 30, ARGOS_C)
    tft.text_center("ARGOS", 8, WHITE, ARGOS_C, scale=2)
    tft.text_center("RP2350-GEEK", 50, CYAN, BLACK)
    tft.text_center(f"FW v{FW_VERSION}", 68, GRAY, BLACK)
    tft.text_center("Waiting for", 100, WHITE, BLACK)
    tft.text_center("ARGOS PC...", 115, YELLOW, BLACK)
    tft.text_center("Connect USB", 140, GRAY, BLACK)
    tft.text_center(f"Temp: {read_chip_temp()}C", 165, ORANGE, BLACK)
    utime.sleep_ms(2000)


# ── Главный цикл ─────────────────────────────────────────────────────────────
def main():
    global _rx_buf

    splash_screen()
    full_redraw()

    # Отправляем hello сразу
    send_hello()

    last_update_ms  = 0
    last_temp_ms    = 0
    last_telem_ms   = 0
    last_hello_ms   = utime.ticks_ms()
    last_btn_a      = True
    last_btn_b      = True
    needs_redraw    = True
    redraw_sections = set()

    UPDATE_MS  = 500    # обновление дисплея
    TEMP_MS    = 3000   # чтение температуры
    TELEM_MS   = 10000  # телеметрия → ПК
    HELLO_MS   = 15000  # повторный hello если нет связи

    while True:
        now = utime.ticks_ms()

        # ── Serial приём ──────────────────────────────────────────────
        msg = serial_poll()
        if msg:
            handle_message(msg)
            needs_redraw = True
            if msg.get("type") == "status":
                redraw_sections |= {"header", "metrics", "graph"}
            elif msg.get("type") == "reply":
                redraw_sections |= {"reply"}

        # ── Проверка связи (таймаут 10 сек) ──────────────────────────
        if state["connected"] and utime.ticks_diff(now, state["last_rx"]) > 10000:
            state["connected"] = False
            redraw_sections.add("header")

        # ── Температура ───────────────────────────────────────────────
        if utime.ticks_diff(now, last_temp_ms) >= TEMP_MS:
            state["temp"] = read_chip_temp()
            state["uptime"] = utime.ticks_diff(now, 0) // 1000
            last_temp_ms = now
            redraw_sections.add("header")

        # ── Телеметрия → ПК ──────────────────────────────────────────
        if utime.ticks_diff(now, last_telem_ms) >= TELEM_MS:
            send_telemetry()
            last_telem_ms = now

        # ── Повторный hello если нет связи ────────────────────────────
        if not state["connected"] and utime.ticks_diff(now, last_hello_ms) >= HELLO_MS:
            send_hello()
            last_hello_ms = now

        # ── Кнопки ───────────────────────────────────────────────────
        btn_a_val = btn_a.value()
        btn_b_val = btn_b.value()

        if last_btn_a and not btn_a_val:
            # Кнопка A: запрос статуса
            serial_send({"type": "user_cmd", "cmd": "статус системы"})
            state["reply"] = "Requesting status..."
            redraw_sections.add("reply")

        if last_btn_b and not btn_b_val:
            # Кнопка B: очистить ответ
            state["reply"] = ""
            redraw_sections.add("reply")

        last_btn_a = btn_a_val
        last_btn_b = btn_b_val

        # ── Обновление дисплея ───────────────────────────────────────
        if utime.ticks_diff(now, last_update_ms) >= UPDATE_MS and redraw_sections:
            if "header"  in redraw_sections: draw_header()
            if "metrics" in redraw_sections: draw_metrics()
            if "graph"   in redraw_sections: draw_graph_section()
            if "reply"   in redraw_sections: draw_reply()
            redraw_sections.clear()
            last_update_ms = now

        utime.sleep_ms(20)


if __name__ == "__main__":
    main()
