import serial
import json
import threading
import time
from src.argos_logger import get_logger

log = get_logger("argos.esp32")

class ESP32Terminal:
    def __init__(self, core, port="COM3", baud=921600):
        self.core = core
        self.port = port
        self.baud = baud
        self.ser = None
        self.running = False

    def connect(self):
        try:
            self.ser = serial.Serial(self.port, self.baud, timeout=1)
            self.running = True
            threading.Thread(target=self._listen, daemon=True).start()
            threading.Thread(target=self._push_stats, daemon=True).start()
            log.info(f"📟 Терминал ESP32 подключен на {self.port}")
        except Exception as e:
            log.error(f"❌ Ошибка подключения ESP32: {e}")

    def _listen(self):
        """Слушает команды с тачскрина ESP32"""
        while self.running:
            if self.ser.in_waiting:
                try:
                    line = self.ser.readline().decode('utf-8').strip()
                    data = json.loads(line)
                    if data.get("type") == "user_cmd":
                        cmd = data.get("cmd")
                        log.info(f"📥 Команда с тачскрина: {cmd}")
                        # Выполняем команду в ядре Аргоса
                        self.core.process_logic(cmd, None, None)
                except: pass
            time.sleep(0.1)

    def _push_stats(self):
        """Отправляет метрики ПК на экран ESP32 каждые 2 сек"""
        while self.running:
            try:
                import psutil
                stats = {
                    "type": "status",
                    "cpu": str(psutil.cpu_percent()),
                    "ram": str(psutil.virtual_memory().percent),
                    "disk": f"{psutil.disk_usage('/').free // (2**30)}G",
                    "os": "Windows",
                    "quantum": self.core.quantum.generate_state()["name"]
                }
                self.ser.write((json.dumps(stats) + "\n").encode())
            except: pass
            time.sleep(2)

    def send_reply(self, text):
        """Отправляет текстовый ответ Аргоса на экран ESP32"""
        if self.ser and self.ser.is_open:
            msg = {"type": "reply", "text": text}
            self.ser.write((json.dumps(msg) + "\n").encode())