"""
MarketEngine - Финансовая Автономия v2.5
Зарабатывает деньги на аренду серверов в простое
"""
import subprocess
import os
import psutil

class MarketEngine:
    def __init__(self, core):
        self.core = core
        self.is_active = False
        self.miner_process = None
        self.wallet = os.getenv("ARGOS_WALLET", "")
        self.idle_threshold = 30  # % CPU usage

    def check_idle(self):
        """Проверяет простой системы"""
        cpu = psutil.cpu_percent(interval=1)
        return cpu < self.idle_threshold

    def toggle(self, state=None):
        """Включает/выключает майнинг"""
        if state is None:
            state = not self.is_active
            
        if state and not self.is_active:
            if not self.check_idle():
                print("⚠️ [MARKET] Система не в простое, отложено")
                return False
                
            if not self.wallet:
                print("❌ [MARKET] ARGOS_WALLET не задан")
                return False
                
            # Запуск XMRig на CPU
            try:
                self.miner_process = subprocess.Popen(
                    ["xmrig", "-o", "pool.supportxmr.com:443", 
                     "-u", self.wallet, "--donate-level=1"],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL
                )
                self.is_active = True
                print(f"💰 [MARKET] Майнинг активирован: {self.wallet[:10]}...")
                return True
            except FileNotFoundError:
                print("❌ [MARKET] xmrig не найден. Установи: https://xmrig.com/")
                return False
                
        elif not state and self.is_active:
            if self.miner_process:
                self.miner_process.terminate()
            os.system("taskkill /f /im xmrig.exe 2>nul")
            self.is_active = False
            print("⏸️ [MARKET] Майнинг остановлен")
            return True
            
        return self.is_active

    def get_stats(self):
        """Возвращает статистику дохода"""
        if not self.is_active:
            return {"status": "inactive"}
        return {
            "status": "active",
            "wallet": self.wallet[:10] + "...",
            "pid": self.miner_process.pid if self.miner_process else None
        }
