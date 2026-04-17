"""
smart_firmware_researcher.py — Умный исследователь прошивок ARGOS

Когда шаблон не найден — ищет информацию об устройстве в интернете
(GitHub, Arduino Hub, ESP-IDF docs, datasheet sites) и автоматически
генерирует прошивку/конфиг.

Схема работы:
  1. parse_device_query() — разбирает запрос пользователя
  2. search_device_info()  — ищет в интернете (RSS, GitHub API, ESP/Arduino портали)
  3. build_template()      — строит шаблон из найденных данных
  4. generate_firmware()   — генерирует .ino / .py / конфиг файл
"""

from __future__ import annotations

import json
import os
import re
import time
from typing import Optional

try:
    import requests
    _REQ = True
except ImportError:
    _REQ = False

try:
    import xml.etree.ElementTree as ET
    _ET = True
except ImportError:
    _ET = False

from src.argos_logger import get_logger

log = get_logger("argos.smart_fw")

# ── Базы знаний известных чипов / модулей ────────────────────────────────────
CHIP_DB = {
    # WiFi/BT SoC
    "esp8266":  {"family": "esp8266", "protocol": "wifi",    "framework": "arduino", "flash_tool": "esptool", "baud": 115200},
    "esp32":    {"family": "esp32",   "protocol": "wifi+bt", "framework": "arduino", "flash_tool": "esptool", "baud": 921600},
    "esp32s2":  {"family": "esp32",   "protocol": "wifi",    "framework": "arduino", "flash_tool": "esptool", "baud": 921600},
    "esp32s3":  {"family": "esp32",   "protocol": "wifi+bt", "framework": "arduino", "flash_tool": "esptool", "baud": 921600},
    "esp32c3":  {"family": "esp32",   "protocol": "wifi+bt", "framework": "arduino", "flash_tool": "esptool", "baud": 921600},
    # LoRa
    "sx1276":   {"family": "lora",    "protocol": "lora",    "framework": "arduino", "lib": "LoRa",           "freq": 433},
    "sx1278":   {"family": "lora",    "protocol": "lora",    "framework": "arduino", "lib": "LoRa",           "freq": 433},
    "sx1262":   {"family": "lora",    "protocol": "lora",    "framework": "arduino", "lib": "LoRa",           "freq": 868},
    "sx1272":   {"family": "lora",    "protocol": "lora",    "framework": "arduino", "lib": "LoRa",           "freq": 868},
    "ra-02":    {"family": "lora",    "protocol": "lora",    "framework": "arduino", "lib": "LoRa",           "freq": 433},
    # Zigbee
    "cc2530":   {"family": "zigbee",  "protocol": "zigbee",  "framework": "znp",     "flash_tool": "cc-tool"},
    "cc2652":   {"family": "zigbee",  "protocol": "zigbee",  "framework": "znp",     "flash_tool": "cc-tool"},
    "efr32":    {"family": "zigbee",  "protocol": "zigbee",  "framework": "silabs",  "flash_tool": "commander"},
    # Arduino
    "atmega328": {"family": "avr",   "protocol": "serial",  "framework": "arduino", "flash_tool": "avrdude", "baud": 115200},
    "atmega2560":{"family": "avr",   "protocol": "serial",  "framework": "arduino", "flash_tool": "avrdude", "baud": 115200},
    "arduino":   {"family": "avr",   "protocol": "serial",  "framework": "arduino", "flash_tool": "avrdude", "baud": 9600},
    # Raspberry Pi
    "raspberry": {"family": "rpi",   "protocol": "linux",   "framework": "python",  "flash_tool": "rpi-imager"},
    "rpi":       {"family": "rpi",   "protocol": "linux",   "framework": "python",  "flash_tool": "rpi-imager"},
    # STM32
    "stm32":    {"family": "stm32",  "protocol": "serial",  "framework": "arduino", "flash_tool": "st-flash", "baud": 115200},
    "bluepill": {"family": "stm32",  "protocol": "serial",  "framework": "arduino", "flash_tool": "st-flash", "baud": 115200},
    # Sensors
    "dht11":    {"family": "sensor", "protocol": "1wire",   "lib": "DHT"},
    "dht22":    {"family": "sensor", "protocol": "1wire",   "lib": "DHT"},
    "ds18b20":  {"family": "sensor", "protocol": "1wire",   "lib": "OneWire,DallasTemperature"},
    "bme280":   {"family": "sensor", "protocol": "i2c",     "lib": "Adafruit BME280"},
    "hc-sr04":  {"family": "sensor", "protocol": "gpio",    "lib": "ultrasonic"},
    "pir":      {"family": "sensor", "protocol": "gpio",    "lib": ""},
    "relay":    {"family": "actuator","protocol": "gpio",   "lib": ""},
    # Modbus
    "rs485":    {"family": "modbus", "protocol": "modbus",  "framework": "python",  "lib": "pymodbus"},
    "modbus":   {"family": "modbus", "protocol": "modbus",  "framework": "python",  "lib": "pymodbus"},
}

# ── Паттерны протоколов для авто-определения ────────────────────────────────
PROTOCOL_KEYWORDS = {
    "lora":    ["lora", "sx127", "sx126", "ra-02", "rfm95", "lorawan"],
    "zigbee":  ["zigbee", "z-stack", "cc253", "cc265", "efr32", "ieee 802.15.4"],
    "wifi":    ["wifi", "wi-fi", "wlan", "esp8266", "esp32", "802.11"],
    "bt":      ["bluetooth", "ble", "bt", "нрф", "nrf52"],
    "modbus":  ["modbus", "rs485", "rs-485", "rtu", "tcp/ip modbus"],
    "mqtt":    ["mqtt", "mosquitto", "broker"],
    "i2c":     ["i2c", "i²c", "sda", "scl", "bme", "bmp", "mpu"],
    "1wire":   ["1-wire", "1wire", "onewire", "ds18", "dht"],
    "can":     ["can bus", "canbus", "mcp2515"],
}


class DeviceInfo:
    """Информация об устройстве, собранная из разных источников."""

    def __init__(self, query: str):
        self.query = query
        self.device_name = ""
        self.chip = ""
        self.family = ""
        self.protocol = ""
        self.framework = "arduino"
        self.flash_tool = "esptool"
        self.libs: list[str] = []
        self.baud = 115200
        self.freq = None
        self.github_repo = ""
        self.description = ""
        self.pinout: dict = {}
        self.code_snippet = ""
        self.source = "local_db"

    def to_template(self) -> dict:
        return {
            "description": self.description or f"Auto-generated: {self.device_name}",
            "hardware": self.device_name,
            "protocol": self.protocol or "custom",
            "firmware": self.framework or "arduino",
            "flash_tool": self.flash_tool,
            "config": {
                "chip": self.chip,
                "family": self.family,
                "libs": self.libs,
                "baud": self.baud,
                "freq_mhz": self.freq,
                "github_ref": self.github_repo,
                "pinout": self.pinout,
                "source": self.source,
            },
        }


class SmartFirmwareResearcher:
    """
    Ищет информацию об устройстве онлайн и генерирует прошивку.

    Источники:
      1. Локальная база чипов (CHIP_DB) — мгновенно
      2. GitHub Search API — репозитории с примерами кода
      3. PlatformIO Registry API — платформы и библиотеки
      4. Arduino Library Index RSS — библиотеки Arduino
    """

    GITHUB_API = "https://api.github.com/search/repositories"
    PLATFORMIO_API = "https://api.registry.platformio.org/v3/packages"
    ARDUINO_LIB_INDEX = "https://downloads.arduino.cc/libraries/library_index.json.gz"

    HEADERS = {
        "User-Agent": "ArgosBot/2.1 IoT Firmware Researcher",
        "Accept": "application/json",
    }

    def __init__(self, cache_dir: str = "data/fw_cache"):
        os.makedirs(cache_dir, exist_ok=True)
        self._cache_dir = cache_dir
        self._timeout = 8

    # ── 1. Разбор запроса ───────────────────────────────────────────────────

    def parse_device_query(self, query: str) -> DeviceInfo:
        """Разбирает текст запроса — находит чип, протокол, имя устройства."""
        info = DeviceInfo(query)
        q = query.lower().strip()

        # Убираем команды
        for cmd in ["создай прошивку", "собери прошивку", "прошивка для", "прошивка",
                    "с нуля", "from scratch", "создай", "сделай", "для"]:
            q = q.replace(cmd, " ").strip()
        info.device_name = q.strip() or query.strip()

        # Поиск чипа в базе
        for chip_key, chip_data in CHIP_DB.items():
            if chip_key in q:
                info.chip = chip_key
                info.family = chip_data.get("family", "")
                info.protocol = chip_data.get("protocol", "")
                info.framework = chip_data.get("framework", "arduino")
                info.flash_tool = chip_data.get("flash_tool", "esptool")
                if chip_data.get("lib"):
                    info.libs = [l.strip() for l in chip_data["lib"].split(",")]
                info.baud = chip_data.get("baud", 115200)
                info.freq = chip_data.get("freq")
                info.source = "local_db"
                break

        # Авто-определение протокола по ключевым словам
        if not info.protocol:
            for proto, keywords in PROTOCOL_KEYWORDS.items():
                if any(kw in q for kw in keywords):
                    info.protocol = proto
                    break

        return info

    # ── 2. Поиск в интернете ────────────────────────────────────────────────

    def search_device_info(self, info: DeviceInfo) -> DeviceInfo:
        """Дополняет DeviceInfo данными из интернета."""
        if not _REQ:
            log.warning("requests не установлен — поиск онлайн недоступен")
            return info

        search_query = info.device_name
        log.info("SmartFW: поиск '%s'...", search_query)

        # Параллельный поиск в разных источниках
        info = self._search_github(info, search_query)
        if not info.libs:
            info = self._search_platformio(info, search_query)

        return info

    def _cache_path(self, key: str) -> str:
        safe = re.sub(r"[^\w]", "_", key)[:50]
        return os.path.join(self._cache_dir, f"{safe}.json")

    def _load_cache(self, key: str) -> Optional[dict]:
        path = self._cache_path(key)
        if not os.path.exists(path):
            return None
        try:
            data = json.load(open(path, encoding="utf-8"))
            if time.time() - data.get("_ts", 0) < 86400:  # 24ч кэш
                return data
        except Exception:
            pass
        return None

    def _save_cache(self, key: str, data: dict):
        data["_ts"] = time.time()
        try:
            json.dump(data, open(self._cache_path(key), "w", encoding="utf-8"),
                      ensure_ascii=False, indent=2)
        except Exception:
            pass

    def _search_github(self, info: DeviceInfo, query: str) -> DeviceInfo:
        """Ищет репозитории на GitHub — берёт топ результат."""
        cache_key = f"gh_{query}"
        cached = self._load_cache(cache_key)
        if cached:
            return self._apply_github_result(info, cached)

        try:
            params = {
                "q": f"{query} arduino firmware esp32 iot language:c++",
                "sort": "stars",
                "order": "desc",
                "per_page": 5,
            }
            r = requests.get(self.GITHUB_API, params=params,
                             headers=self.HEADERS, timeout=self._timeout)
            if r.status_code == 200:
                data = r.json()
                items = data.get("items", [])
                if items:
                    top = items[0]
                    result = {
                        "repo": top.get("full_name", ""),
                        "url": top.get("html_url", ""),
                        "description": top.get("description", ""),
                        "stars": top.get("stargazers_count", 0),
                        "language": top.get("language", ""),
                        "topics": top.get("topics", []),
                    }
                    self._save_cache(cache_key, result)
                    return self._apply_github_result(info, result)
            elif r.status_code == 403:
                log.warning("GitHub API rate limit — используем кэш")
        except Exception as e:
            log.warning("GitHub search error: %s", e)

        return info

    def _apply_github_result(self, info: DeviceInfo, gh: dict) -> DeviceInfo:
        if gh.get("repo"):
            info.github_repo = gh["repo"]
            info.source = "github"
            if gh.get("description") and not info.description:
                info.description = gh["description"]
            topics = gh.get("topics", [])
            for topic in topics:
                t = topic.lower()
                for proto, keywords in PROTOCOL_KEYWORDS.items():
                    if any(kw in t for kw in keywords):
                        if not info.protocol:
                            info.protocol = proto
            log.info("SmartFW: GitHub топ-репо %s ★%s", gh["repo"], gh.get("stars", 0))
        return info

    def _search_platformio(self, info: DeviceInfo, query: str) -> DeviceInfo:
        """Ищет библиотеку в реестре PlatformIO."""
        cache_key = f"pio_{query}"
        cached = self._load_cache(cache_key)
        if cached:
            return self._apply_pio_result(info, cached)

        try:
            params = {"query": query, "type": "library", "limit": 3}
            r = requests.get(self.PLATFORMIO_API, params=params,
                             headers=self.HEADERS, timeout=self._timeout)
            if r.status_code == 200:
                data = r.json()
                items = data.get("items", [])
                if items:
                    lib = items[0]
                    result = {
                        "name": lib.get("name", ""),
                        "description": lib.get("description", ""),
                        "frameworks": lib.get("frameworks", []),
                        "platforms": lib.get("platforms", []),
                    }
                    self._save_cache(cache_key, result)
                    return self._apply_pio_result(info, result)
        except Exception as e:
            log.warning("PlatformIO search error: %s", e)

        return info

    def _apply_pio_result(self, info: DeviceInfo, pio: dict) -> DeviceInfo:
        if pio.get("name"):
            info.libs.append(pio["name"])
            if pio.get("description") and not info.description:
                info.description = pio["description"]
            log.info("SmartFW: PlatformIO lib '%s'", pio["name"])
        return info

    # ── 3. Генерация прошивки ───────────────────────────────────────────────

    def generate_firmware(self, info: DeviceInfo, output_dir: str = "assets/firmware") -> str:
        """Генерирует файл прошивки на основе DeviceInfo. Возвращает путь к файлу."""
        os.makedirs(output_dir, exist_ok=True)

        family = info.family or self._guess_family(info)

        if family in ("esp8266", "esp32"):
            return self._gen_esp_sketch(info, output_dir)
        elif family == "avr":
            return self._gen_arduino_sketch(info, output_dir)
        elif family == "rpi":
            return self._gen_rpi_script(info, output_dir)
        elif family == "lora":
            return self._gen_lora_sketch(info, output_dir)
        elif family == "modbus":
            return self._gen_modbus_script(info, output_dir)
        elif family == "sensor":
            return self._gen_sensor_sketch(info, output_dir)
        else:
            return self._gen_generic_sketch(info, output_dir)

    def _guess_family(self, info: DeviceInfo) -> str:
        q = info.device_name.lower()
        if any(x in q for x in ["esp32", "esp8266"]):
            return "esp32" if "esp32" in q else "esp8266"
        if any(x in q for x in ["arduino", "atmega", "uno", "nano", "mega"]):
            return "avr"
        if any(x in q for x in ["raspberry", "rpi"]):
            return "rpi"
        if any(x in q for x in ["lora", "sx127", "ra-02"]):
            return "lora"
        if any(x in q for x in ["modbus", "rs485"]):
            return "modbus"
        return "generic"

    def _safe_name(self, name: str) -> str:
        return re.sub(r"[^\w]", "_", name.strip())[:30]

    def _libs_include(self, libs: list[str]) -> str:
        if not libs:
            return "// No external libraries detected"
        return "\n".join(f'#include <{lib}.h>' for lib in libs)

    def _gen_esp_sketch(self, info: DeviceInfo, out: str) -> str:
        name = self._safe_name(info.device_name)
        chip = info.chip.upper() or "ESP32"
        libs = self._libs_include(info.libs or ["WiFi", "PubSubClient"])
        gh_ref = f"\n// Reference: https://github.com/{info.github_repo}" if info.github_repo else ""
        code = f"""// ═══════════════════════════════════════════════════════
// ARGOS Auto-Generated Firmware — {info.device_name}
// Chip: {chip} | Protocol: {info.protocol or 'WiFi+MQTT'}
// Generated: {time.strftime('%Y-%m-%d %H:%M')}
// Source: {info.source}{gh_ref}
// ═══════════════════════════════════════════════════════
// cython: language_level=3

{libs}

// ── Настройки ────────────────────────────────────────────
const char* WIFI_SSID     = "YOUR_SSID";
const char* WIFI_PASS     = "YOUR_PASSWORD";
const char* MQTT_BROKER   = "192.168.1.1";
const int   MQTT_PORT     = 1883;
const char* DEVICE_ID     = "argos_{name.lower()}";
const char* TOPIC_STATUS  = "argos/{name.lower()}/status";
const char* TOPIC_COMMAND = "argos/{name.lower()}/cmd";

// ── Переменные ───────────────────────────────────────────
WiFiClient   espClient;
// PubSubClient mqtt(espClient);
unsigned long lastMsg = 0;

void setup() {{
  Serial.begin({info.baud or 115200});
  Serial.println("[ARGOS] {info.device_name} — starting...");

  // WiFi
  WiFi.begin(WIFI_SSID, WIFI_PASS);
  while (WiFi.status() != WL_CONNECTED) {{
    delay(500);
    Serial.print(".");
  }}
  Serial.println("\\n[ARGOS] WiFi OK: " + WiFi.localIP().toString());

  // TODO: MQTT connect
  // mqtt.setServer(MQTT_BROKER, MQTT_PORT);

  Serial.println("[ARGOS] Ready ✓");
}}

void loop() {{
  // mqtt.loop();

  unsigned long now = millis();
  if (now - lastMsg > 5000) {{
    lastMsg = now;
    // TODO: read sensor / send data
    Serial.println("[ARGOS] tick");
  }}
}}
"""
        path = os.path.join(out, f"argos_{name}.ino")
        with open(path, "w", encoding="utf-8") as f:
            f.write(code)
        return path

    def _gen_arduino_sketch(self, info: DeviceInfo, out: str) -> str:
        name = self._safe_name(info.device_name)
        libs = self._libs_include(info.libs)
        code = f"""// ═══════════════════════════════════════════════════════
// ARGOS Auto-Generated Firmware — {info.device_name}
// Platform: Arduino AVR | Generated: {time.strftime('%Y-%m-%d %H:%M')}
// ═══════════════════════════════════════════════════════

{libs}

void setup() {{
  Serial.begin({info.baud or 9600});
  Serial.println("[ARGOS] {info.device_name} started");
  // TODO: init pins / sensors
}}

void loop() {{
  // TODO: main logic
  delay(1000);
}}
"""
        path = os.path.join(out, f"argos_{name}.ino")
        with open(path, "w", encoding="utf-8") as f:
            f.write(code)
        return path

    def _gen_rpi_script(self, info: DeviceInfo, out: str) -> str:
        name = self._safe_name(info.device_name)
        code = f"""#!/usr/bin/env python3
# ═══════════════════════════════════════════════════════
# ARGOS Auto-Generated Script — {info.device_name}
# Platform: Raspberry Pi | Generated: {time.strftime('%Y-%m-%d %H:%M')}
# ═══════════════════════════════════════════════════════

import time
import logging

logging.basicConfig(level=logging.INFO, format="%(asctime)s [ARGOS] %(message)s")
log = logging.getLogger("{name}")


def setup():
    log.info("{info.device_name} — setup")
    # TODO: import RPi.GPIO, configure pins
    # import RPi.GPIO as GPIO
    # GPIO.setmode(GPIO.BCM)


def loop():
    log.info("tick")
    # TODO: sensor read / MQTT publish
    time.sleep(5)


if __name__ == "__main__":
    setup()
    while True:
        loop()
"""
        path = os.path.join(out, f"argos_{name}.py")
        with open(path, "w", encoding="utf-8") as f:
            f.write(code)
        return path

    def _gen_lora_sketch(self, info: DeviceInfo, out: str) -> str:
        name = self._safe_name(info.device_name)
        freq = int((info.freq or 433) * 1e6)
        code = f"""// ═══════════════════════════════════════════════════════
// ARGOS Auto-Generated LoRa Firmware — {info.device_name}
// Frequency: {info.freq or 433} MHz | Generated: {time.strftime('%Y-%m-%d %H:%M')}
// ═══════════════════════════════════════════════════════

#include <SPI.h>
#include <LoRa.h>

#define LORA_FREQ    {freq}
#define LORA_SS      5
#define LORA_RST     14
#define LORA_DIO0    2
#define DEVICE_ID    "argos_{name.lower()}"

int msgCount = 0;

void setup() {{
  Serial.begin(115200);
  LoRa.setPins(LORA_SS, LORA_RST, LORA_DIO0);
  if (!LoRa.begin(LORA_FREQ)) {{
    Serial.println("[ARGOS] LoRa init FAILED!");
    while (true);
  }}
  LoRa.setSpreadingFactor(7);
  LoRa.setSignalBandwidth(125E3);
  LoRa.setCodingRate4(5);
  Serial.println("[ARGOS] LoRa ready @ {info.freq or 433} MHz ✓");
}}

void loop() {{
  // RX
  int pktSize = LoRa.parsePacket();
  if (pktSize) {{
    String data = "";
    while (LoRa.available()) data += (char)LoRa.read();
    int rssi = LoRa.packetRssi();
    Serial.println("[RX] " + data + " RSSI=" + rssi);
  }}

  // TX каждые 10 сек
  static unsigned long last = 0;
  if (millis() - last > 10000) {{
    last = millis();
    LoRa.beginPacket();
    LoRa.print(DEVICE_ID);
    LoRa.print(":msg#");
    LoRa.print(msgCount++);
    LoRa.endPacket();
    Serial.println("[TX] sent #" + String(msgCount));
  }}
}}
"""
        path = os.path.join(out, f"argos_{name}_lora.ino")
        with open(path, "w", encoding="utf-8") as f:
            f.write(code)
        return path

    def _gen_modbus_script(self, info: DeviceInfo, out: str) -> str:
        name = self._safe_name(info.device_name)
        code = f"""#!/usr/bin/env python3
# ═══════════════════════════════════════════════════════
# ARGOS Auto-Generated Modbus Script — {info.device_name}
# Generated: {time.strftime('%Y-%m-%d %H:%M')}
# pip install pymodbus
# ═══════════════════════════════════════════════════════

import time, logging
from pymodbus.client import ModbusSerialClient

logging.basicConfig(level=logging.INFO, format="%(asctime)s [ARGOS] %(message)s")
log = logging.getLogger("modbus")

PORT    = "/dev/ttyUSB0"   # COM3 на Windows
BAUD    = 9600
UNIT_ID = 1               # Slave ID устройства

def read_device(client, unit):
    result = client.read_holding_registers(0, count=4, unit=unit)
    if not result.isError():
        log.info("Регистры 0-3: %s", result.registers)
    else:
        log.warning("Ошибка чтения: %s", result)

def main():
    client = ModbusSerialClient(method="rtu", port=PORT, baudrate=BAUD,
                                 stopbits=1, bytesize=8, parity="N", timeout=1)
    if not client.connect():
        log.error("Нет соединения с %s", PORT)
        return

    log.info("{info.device_name} Modbus RTU: подключено к %s", PORT)
    try:
        while True:
            read_device(client, UNIT_ID)
            time.sleep(5)
    finally:
        client.close()

if __name__ == "__main__":
    main()
"""
        path = os.path.join(out, f"argos_{name}_modbus.py")
        with open(path, "w", encoding="utf-8") as f:
            f.write(code)
        return path

    def _gen_sensor_sketch(self, info: DeviceInfo, out: str) -> str:
        name = self._safe_name(info.device_name)
        lib_name = (info.libs[0] if info.libs else info.device_name.upper())
        code = f"""// ═══════════════════════════════════════════════════════
// ARGOS Auto-Generated Sensor Firmware — {info.device_name}
// Protocol: {info.protocol or 'GPIO'} | Generated: {time.strftime('%Y-%m-%d %H:%M')}
// ═══════════════════════════════════════════════════════

{self._libs_include(info.libs)}

#define SENSOR_PIN  4    // DATA pin — измени при необходимости

void setup() {{
  Serial.begin(9600);
  Serial.println("[ARGOS] {info.device_name} sensor ready");
  // TODO: sensor.begin()
}}

void loop() {{
  // TODO: float val = sensor.read();
  // Serial.println("[ARGOS] value: " + String(val));
  delay(2000);
}}
"""
        path = os.path.join(out, f"argos_{name}_sensor.ino")
        with open(path, "w", encoding="utf-8") as f:
            f.write(code)
        return path

    def _gen_generic_sketch(self, info: DeviceInfo, out: str) -> str:
        name = self._safe_name(info.device_name)
        gh_comment = f"// Похожие проекты: https://github.com/{info.github_repo}" if info.github_repo else ""
        code = f"""// ═══════════════════════════════════════════════════════
// ARGOS Auto-Generated Firmware — {info.device_name}
// Protocol: {info.protocol or 'Unknown'} | Generated: {time.strftime('%Y-%m-%d %H:%M')}
// Source: {info.source}
{gh_comment}
// ═══════════════════════════════════════════════════════

// TODO: добавь нужные библиотеки для {info.device_name}
// #include <YourLibrary.h>

void setup() {{
  Serial.begin(115200);
  Serial.println("[ARGOS] {info.device_name} — init");
  // TODO: инициализация устройства
}}

void loop() {{
  // TODO: основная логика
  delay(1000);
}}
"""
        path = os.path.join(out, f"argos_{name}_fw.ino")
        with open(path, "w", encoding="utf-8") as f:
            f.write(code)
        return path

    # ── 4. Полный пайплайн ─────────────────────────────────────────────────

    def research_and_build(self, query: str) -> dict:
        """
        Главный метод: разбирает запрос → ищет онлайн → генерирует файл.

        Возвращает:
          {
            "status": "ok" | "partial" | "offline",
            "message": str,      # ответ для пользователя
            "fw_path": str,      # путь к сгенерированному файлу
            "template": dict,    # шаблон для gateway_manager
            "info": DeviceInfo,
          }
        """
        # 1. Парсинг
        info = self.parse_device_query(query)
        log.info("SmartFW: запрос='%s' чип=%s протокол=%s", query, info.chip, info.protocol)

        # 2. Онлайн-поиск (если не нашли в локальной базе)
        status = "ok"
        if info.source == "local_db":
            status = "ok"
        else:
            try:
                info = self.search_device_info(info)
                status = "ok" if info.github_repo or info.libs else "partial"
            except Exception as e:
                log.warning("SmartFW: онлайн поиск недоступен: %s", e)
                status = "offline"

        # 3. Генерация файла
        fw_path = self.generate_firmware(info)

        # 4. Формирование ответа
        lines = [f"🔧 УМНАЯ ПРОШИВКА: {info.device_name}",
                 "─" * 40]
        if info.chip:
            lines.append(f"📦 Чип: {info.chip.upper()}")
        if info.family:
            lines.append(f"🏗  Семейство: {info.family}")
        if info.protocol:
            lines.append(f"📡 Протокол: {info.protocol}")
        if info.libs:
            lines.append(f"📚 Библиотеки: {', '.join(info.libs)}")
        if info.github_repo:
            lines.append(f"🐙 GitHub ref: github.com/{info.github_repo}")
        if info.description:
            lines.append(f"📝 {info.description[:80]}")
        lines.append(f"💾 Файл: {fw_path}")

        if status == "offline":
            lines.append("⚠️  Поиск онлайн недоступен — использована локальная база")
        elif status == "partial":
            lines.append("ℹ️  Частичная информация — онлайн-поиск дал ограниченный результат")

        lines.append("─" * 40)
        lines.append("✅ Прошивка сгенерирована. Отредактируй TODO-секции под своё устройство.")

        return {
            "status": status,
            "message": "\n".join(lines),
            "fw_path": fw_path,
            "template": info.to_template(),
            "info": info,
        }
