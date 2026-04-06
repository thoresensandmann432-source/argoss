import requests
import sys

def test_argos_connection(port=5001):
    base_url = f"http://localhost:{port}/api"
    
    # Тест статуса
    try:
        response = requests.get(f"{base_url}/status")
        print(f"Status: {response.json()}")
    except Exception as e:
        print(f"Status error: {e}")
    
    # Тест чата
    try:
        response = requests.post(f"{base_url}/chat", json={"message": "Тестовое сообщение"})
        print(f"Chat: {response.json()}")
    except Exception as e:
        print(f"Chat error: {e}")

if __name__ == "__main__":
    test_argos_connection()
