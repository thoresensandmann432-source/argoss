import psutil
import time
import math


class AuthorityManager:
    def __init__(self, core):
        self.core = core
        self.start_time = time.time()

    def calculate_my_weight(self):
        # Мощность = (Ядра CPU + VRAM в ГБ)
        cpu_cores = psutil.cpu_count()
        # Пытаемся определить VRAM (у тебя 8+4=12)
        vram_gb = 12  # Упрощенно для твоего сетапа

        age_days = (time.time() - self.start_time) / 86400
        # Формула: Мощность * log(Возраст + 2)
        weight = (cpu_cores + vram_gb) * math.log2(age_days + 2)
        return round(weight, 2)

    def get_role(self, weight):
        if weight > 50:
            return "VERIFIER (Master)"
        if weight > 20:
            return "DRAFTER (Worker)"
        return "OBSERVER (Newbie)"
