#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ARGOS Flash Tool — универсальный инструмент прошивки ESP8266
Вызывается из АРГОС или вручную:
  python argos_flash_tool.py --port COM5 --file C:/ARGOS/firmware/argos_display/argos_display.ino
  python argos_flash_tool.py --port COM5 --bin C:/ARGOS/firmware/argos_display.bin
  python argos_flash_tool.py --auto   # авто-поиск порта и компиляция
"""

import sys
import os
import subprocess
import argparse
import json
import datetime
import serial.tools.list_ports

LOG_FILE = "C:/ARGOS/logs/flash_log.txt"
ARDUINO_CLI = "arduino-cli"       # должен быть в PATH или укажи полный путь
BOARD = "esp8266:esp8266:nodemcuv2"  # NodeMCU v3 (ESP8266)
BAUD = 115200

def log(msg, level="INFO"):
    ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] [{level}] {msg}"
    print(line)
    try:
        os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass

def find_esp_port():
    """Авто-поиск порта с ESP8266 / CH340 / CP2102"""
    ESP_KEYWORDS = ["CH340", "CH341", "CP210", "USB-SERIAL", "USB Serial", "NodeMCU"]
    ports = list(serial.tools.list_ports.comports())
    for p in ports:
        desc = (p.description or "") + (p.manufacturer or "")
        if any(k.lower() in desc.lower() for k in ESP_KEYWORDS):
            log(f"Авто-обнаружен порт: {p.device} ({p.description})")
            return p.device
    if ports:
        log(f"ESP не определён, использую первый порт: {ports[0].device}", "WARN")
        return ports[0].device
    return None

def list_ports():
    ports = list(serial.tools.list_ports.comports())
    if not ports:
        log("Нет доступных COM-портов!", "ERROR")
        return []
    result = []
    for p in ports:
        result.append({"port": p.device, "desc": p.description})
        log(f"Порт: {p.device} — {p.description}")
    return result

def compile_sketch(sketch_path, output_dir=None):
    """Компиляция .ino через arduino-cli"""
    if not output_dir:
        output_dir = os.path.join(os.path.dirname(sketch_path), "build")
    os.makedirs(output_dir, exist_ok=True)

    log(f"Компиляция: {sketch_path}")
    cmd = [
        ARDUINO_CLI, "compile",
        "--fqbn", BOARD,
        "--output-dir", output_dir,
        sketch_path
    ]
    log(f"Команда: {' '.join(cmd)}")
    result = subprocess.run(cmd, capture_output=True, text=True)

    if result.returncode != 0:
        log(f"Ошибка компиляции:\n{result.stderr}", "ERROR")
        return None

    log("Компиляция успешна ✓")

    # Ищем .bin файл в output_dir
    for f in os.listdir(output_dir):
        if f.endswith(".bin"):
            bin_path = os.path.join(output_dir, f)
            log(f"Бинарник: {bin_path}")
            return bin_path

    log("Бинарный файл не найден после компиляции!", "ERROR")
    return None

def flash_bin(port, bin_path):
    """Прошивка .bin через esptool.py"""
    if not os.path.exists(bin_path):
        log(f"Файл не найден: {bin_path}", "ERROR")
        return False

    log(f"Прошивка {bin_path} → {port} (baud={BAUD})")
    cmd = [
        sys.executable, "-m", "esptool",
        "--port", port,
        "--baud", str(BAUD),
        "--chip", "esp8266",
        "write_flash",
        "--flash_mode", "dio",
        "--flash_size", "detect",
        "0x0",
        bin_path
    ]
    log(f"Команда: {' '.join(cmd)}")
    result = subprocess.run(cmd, capture_output=True, text=True)

    if result.returncode != 0:
        log(f"Ошибка прошивки:\n{result.stderr}", "ERROR")
        log(result.stdout)
        return False

    log("✅ Прошивка завершена успешно!")
    log(result.stdout)
    return True

def main():
    parser = argparse.ArgumentParser(description="ARGOS Flash Tool для ESP8266")
    parser.add_argument("--port", help="COM-порт (например COM5). Если не указан — авто-поиск")
    parser.add_argument("--file", help="Путь к .ino файлу (будет скомпилирован)")
    parser.add_argument("--bin", help="Путь к готовому .bin файлу")
    parser.add_argument("--list-ports", action="store_true", help="Показать доступные COM-порты")
    parser.add_argument("--auto", action="store_true", help="Авто-режим: найти ESP и прошить")
    parser.add_argument("--json", action="store_true", dest="json_out", help="Вывод в JSON (для АРГОС)")
    args = parser.parse_args()

    result = {"success": False, "message": "", "port": None}

    if args.list_ports:
        ports = list_ports()
        if args.json_out:
            print(json.dumps({"ports": ports}))
        return

    # Определяем порт
    port = args.port
    if not port:
        port = find_esp_port()
        if not port:
            msg = "ESP8266 не найден. Подключи устройство к USB."
            log(msg, "ERROR")
            result["message"] = msg
            if args.json_out:
                print(json.dumps(result))
            return

    result["port"] = port

    # Компиляция .ino если указан
    bin_path = args.bin
    if args.file:
        bin_path = compile_sketch(args.file)
        if not bin_path:
            result["message"] = "Ошибка компиляции"
            if args.json_out:
                print(json.dumps(result))
            return

    if not bin_path:
        # Авто-режим: ищем последний .bin в стандартной папке АРГОС
        default_bin = "C:/ARGOS/firmware/argos_display/build"
        if os.path.exists(default_bin):
            for f in os.listdir(default_bin):
                if f.endswith(".bin"):
                    bin_path = os.path.join(default_bin, f)
                    break
        if not bin_path:
            msg = "Не указан .ino или .bin файл"
            log(msg, "ERROR")
            result["message"] = msg
            if args.json_out:
                print(json.dumps(result))
            return

    # Прошивка
    success = flash_bin(port, bin_path)
    result["success"] = success
    result["message"] = "Прошивка успешна ✅" if success else "Ошибка прошивки ❌"
    result["bin"] = bin_path

    if args.json_out:
        print(json.dumps(result))

if __name__ == "__main__":
    main()
