import requests
import json

def debug_server_connection(port=5001):
    base_url = f"http://localhost:{port}"
    
    print(f"Проверяем подключение к {base_url}")
    
    # Проверим корневой путь
    try:
        response = requests.get(base_url, timeout=5)
        print(f"Root response status: {response.status_code}")
        print(f"Root response text: {response.text[:200]}")  # Первые 200 символов
    except Exception as e:
        print(f"Root connection error: {e}")
    
    # Проверим API пути
    try:
        response = requests.get(f"{base_url}/api/status", timeout=5)
        print(f"API status code: {response.status_code}")
        print(f"API response: {response.text}")
    except Exception as e:
        print(f"API connection error: {e}")

if __name__ == "__main__":
    debug_server_connection()
