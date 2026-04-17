import requests
import sys

# Правильный порт Argos сервера
ARGOS_PORT = 5051  # Изменено с 5000 на 5051
BASE_URL = f"http://localhost:{ARGOS_PORT}"

def argos_status():
    try:
        response = requests.get(f"{BASE_URL}/api/status", timeout=10)
        if response.status_code == 200:
            data = response.json()
            print("✅ Argos Status:")
            for key, value in data.items():
                print(f"   {key}: {value}")
        else:
            print(f"❌ Status Error: {response.status_code}")
    except Exception as e:
        print(f"❌ Connection Error: {e}")

def argos_chat(message):
    try:
        response = requests.post(
            f"{BASE_URL}/api/chat",
            json={"message": message},
            timeout=10
        )
        if response.status_code == 200:
            data = response.json()
            print(f"💬 Argos Response: {data.get('response', 'No response')}")
        else:
            print(f"❌ Chat Error: {response.status_code}")
    except Exception as e:
        print(f"❌ Connection Error: {e}")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python final_argos_cli.py [status|chat <message>]")
        sys.exit(1)
    
    command = sys.argv[1]
    
    if command == "status":
        argos_status()
    elif command == "chat" and len(sys.argv) > 2:
        message = " ".join(sys.argv[2:])
        argos_chat(message)
    else:
        print("Invalid command")
