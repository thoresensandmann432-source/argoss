import requests
import sys
import json

# Настройки сервера Argos
ARGOS_BASE_URL = "http://localhost:5051"
TIMEOUT = 15

def test_server_connection():
    """Проверка базового подключения к серверу"""
    try:
        response = requests.get(ARGOS_BASE_URL, timeout=TIMEOUT)
        print(f"✅ Сервер доступен: {response.status_code}")
        if response.status_code == 200:
            print(f"📄 Ответ: {response.text[:200]}...")
        return response.status_code == 200
    except Exception as e:
        print(f"❌ Ошибка подключения к серверу: {e}")
        return False

def discover_api_endpoints():
    """Поиск доступных API endpoints"""
    common_endpoints = [
        "/", "/api", "/api/v1", "/health", "/status", 
        "/openapi.json", "/docs", "/redoc"
    ]
    
    print("🔍 Поиск доступных endpoints...")
    found_endpoints = []
    
    for endpoint in common_endpoints:
        try:
            url = f"{ARGOS_BASE_URL}{endpoint}"
            response = requests.get(url, timeout=5)
            if response.status_code == 200:
                found_endpoints.append(endpoint)
                print(f"✅ Найден: {endpoint} ({response.status_code})")
        except:
            pass
    
    return found_endpoints

def send_chat_message(message):
    """Отправка сообщения в чат Argos"""
    try:
        # Пробуем разные возможные endpoints
        endpoints = ["/api/chat", "/chat", "/message", "/api/message"]
        
        for endpoint in endpoints:
            try:
                url = f"{ARGOS_BASE_URL}{endpoint}"
                response = requests.post(
                    url, 
                    json={"message": message, "text": message},
                    headers={"Content-Type": "application/json"},
                    timeout=TIMEOUT
                )
                
                if response.status_code == 200:
                    try:
                        data = response.json()
                        print(f"💬 Ответ от {endpoint}: {data}")
                        return True
                    except:
                        print(f"📄 Текстовый ответ от {endpoint}: {response.text}")
                        return True
                elif response.status_code != 404:
                    print(f"⚠️  {endpoint}: {response.status_code} - {response.text[:100]}")
            except Exception as e:
                if "404" not in str(e):
                    print(f"⚠️  Ошибка при обращении к {endpoint}: {e}")
        
        print("❌ Не удалось найти рабочий endpoint для чата")
        return False
        
    except Exception as e:
        print(f"❌ Ошибка отправки сообщения: {e}")
        return False

def main():
    print(f"🚀 Тестирование Argos сервера на {ARGOS_BASE_URL}")
    print("=" * 50)
    
    # Проверка подключения
    if not test_server_connection():
        return
    
    # Поиск endpoints
    endpoints = discover_api_endpoints()
    
    # Если передан аргумент - отправляем сообщение
    if len(sys.argv) > 1:
        message = " ".join(sys.argv[1:])
        print(f"\n📤 Отправка сообщения: '{message}'")
        send_chat_message(message)
    else:
        print("\nℹ️  Использование: python argos_test_cli.py <сообщение>")
        print("ℹ️  Пример: python argos_test_cli.py \"привет мир\"")

if __name__ == "__main__":
    main()
