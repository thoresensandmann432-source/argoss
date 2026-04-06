import requests
import json
import logging

class ACPBridge:
    def __init__(self, delegate_url="http://127.0.0.1:5000"):
        self.url = f"{delegate_url}/write"
        self.logger = logging.getLogger("ARGOS_ACP")

    def write_task(self, task: dict) -> bool:
        """Специализированный метод для записи задач (JSON)"""
        file_path = f"tasks/{task.get('id', 'unknown')}.json"
        content = json.dumps(task, indent=4, ensure_ascii=False)
        return self.delegate_write(file_path, content)

    def delegate_write(self, file_path: str, content: str) -> dict:
        """Универсальный метод делегирования записи через ACP"""
        payload = {
            "path": file_path,
            "content": content,
            "metadata": {"source": "ARGOS_CORE", "protocol": "ACP/1.0"}
        }
        
        try:
            # Отправка на внешний Flask-приемник
            response = requests.post(self.url, json=payload, timeout=10)
            if response.status_code == 200:
                self.logger.info(f"ACP: Файл {file_path} успешно записан.")
                return {"status": "success", "path": file_path}
            
            error_msg = response.json().get("error", "Unknown error")
            return {"status": "error", "reason": error_msg}
            
        except Exception as e:
            self.logger.error(f"ACP Critical Failure: {str(e)}")
            return {"status": "fail", "reason": str(e)}

