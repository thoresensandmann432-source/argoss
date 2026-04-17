"""
WinBridge - Гипервизор Windows v2.5
Управление Windows изнутри Docker/контейнера
"""
import requests
import os

class WinBridge:
    def __init__(self, core):
        self.core = core
        self.url = os.getenv("ARGOS_WIN_BRIDGE_URL", "http://host.docker.internal:5000/exec")
        self.token = os.getenv("ARGOS_BRIDGE_TOKEN", "")

    def run(self, cmd):
        """Выполняет команду на хосте Windows"""
        if not self.token:
            return {"status": "error", "msg": "ARGOS_BRIDGE_TOKEN not set"}
            
        headers = {"Authorization": f"Bearer {self.token}"}
        try:
            r = requests.post(
                self.url,
                json={"cmd": cmd},
                headers=headers,
                timeout=30
            )
            return r.json()
        except requests.exceptions.ConnectionError:
            return {"status": "error", "msg": "Windows Host Offline"}
        except Exception as e:
            return {"status": "error", "msg": str(e)}

    def is_available(self):
        """Проверяет доступность хоста"""
        result = self.run("echo test")
        return result.get("status") == "ok"

    def restart_service(self, service_name):
        """Перезапускает службу Windows"""
        return self.run(f"Restart-Service -Name {service_name}")

    def kill_process(self, process_name):
        """Убивает процесс на хосте"""
        return self.run(f"taskkill /F /IM {process_name}")
