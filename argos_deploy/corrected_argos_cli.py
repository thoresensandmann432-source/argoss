import requests
import sys
import json

# ПРАВИЛЬНЫЙ ПОРТ ARGOS
ARGOS_PORT = 5051
BASE_URL = f"http://localhost:{ARGOS_PORT}"

class ArgosClient:
    def __init__(self, base_url=BASE_URL):
        self.base_url = base_url
        self.session = requests.Session()
        
    def send_chat(self, message):
        """Отправка сообщения в Argos chat"""
        try:
            # Пробуем разные возможные endpoints
            endpoints = [
                "/api/chat", 
                "/chat", 
                "/message",
                "/api/v1/chat"
            ]
            
            payload = {"message": message, "text": message}
            
            for endpoint in endpoints:
                try:
                    url = f"{self.base_url}{endpoint}"
                    response = self.session.post(
                        url,
                        json=payload,
                        headers={"Content-Type": "application/json"},
                        timeout=15
                    )
                    
                    if response.status_code == 200:
                        try:
                            return response.json()
                        except:
                            return {"text": response.text, "status": "success"}
                    elif response.status_code == 404:
                        continue
                    else:
                        print(f"⚠️  Endpoint {endpoint}: {response.status_code}")
                        
                except Exception as e:
                    if "404" not in str(e):
                        print(f"⚠️  Ошибка endpoint {endpoint}: {e}")
            
            # Если ни один endpoint не сработал, пробуем универсальный
            print("❌ Не найдены рабочие chat endpoints")
            return None
            
        except Exception as e:
            print(f"❌ Ошибка отправки сообщения: {e}")
            return None
    
    def get_status(self):
        """Получение статуса системы"""
        try:
            endpoints = ["/api/status", "/status", "/health", "/api/v1/status"]
            
            for endpoint in endpoints:
                try:
                    url = f"{self.base_url}{endpoint}"
                    response = self.session.get(url, timeout=10)
                    
                    if response.status_code == 200:
                        try:
                            return response.json()
                        except:
                            return {"text": response.text, "status": "success"}
                    elif response.status_code != 404:
                        print(f"⚠️  Status endpoint {endpoint}: {response.status_code}")
                        
                except Exception as e:
                    if "404" not in str(e):
                        print(f"⚠️  Ошибка status endpoint {endpoint}: {e}")
            
            return None
        except Exception as e:
            print(f"❌ Ошибка получения статуса: {e}")
            return None

def main():
    if len(sys.argv) < 2:
        print("Использование: python corrected_argos_cli.py [chat <message>|status]")
        return
    
    client = ArgosClient()
    command = sys.argv[1].lower()
    
    if command == "status":
        print("📊 Получение статуса системы...")
        result = client.get_status()
        if result:
            print(json.dumps(result, indent=2, ensure_ascii=False))
        else:
            print("❌ Не удалось получить статус")
            
    elif command == "chat" and len(sys.argv) > 2:
        message = " ".join(sys.argv[2:])
        print(f"💬 Отправка: {message}")
        result = client.send_chat(message)
        if result:
            print(json.dumps(result, indent=2, ensure_ascii=False))
        else:
            print("❌ Не удалось отправить сообщение")
    else:
        print("Неизвестная команда")

if __name__ == "__main__":
    main()
