import requests
import json

def test_argos_api():
    base_url = "http://localhost:5000"
    
    print("🔍 Проверяем Argos API на порту 5000...")
    
    # Проверим корневой путь
    try:
        response = requests.get(base_url, timeout=10)
        print(f"🏠 Root (/): Status {response.status_code}")
        if response.status_code == 200:
            print(f"   Content type: {response.headers.get('content-type')}")
            if 'text/html' in response.headers.get('content-type', ''):
                print("   📄 Это HTML страница (возможно веб-интерфейс)")
            else:
                print(f"   📄 Response preview: {response.text[:100]}")
    except Exception as e:
        print(f"❌ Root error: {e}")
    
    # Попробуем API эндпоинты
    api_endpoints = [
        "/api/status",
        "/api/chat", 
        "/api/kimi/chat",
        "/status",
        "/chat"
    ]
    
    for endpoint in api_endpoints:
        try:
            if endpoint in ["/api/chat", "/chat"]:
                # POST запросы
                response = requests.post(
                    f"{base_url}{endpoint}", 
                    json={"message": "test"}, 
                    timeout=10
                )
            else:
                # GET запросы
                response = requests.get(f"{base_url}{endpoint}", timeout=10)
            
            print(f"🔗 {endpoint}: Status {response.status_code}")
            if response.status_code == 200:
                try:
                    data = response.json()
                    print(f"   📦 {data}")
                except:
                    print(f"   📄 Plain text: {response.text[:100]}")
        except Exception as e:
            print(f"❌ {endpoint}: Error - {e}")

if __name__ == "__main__":
    test_argos_api()
