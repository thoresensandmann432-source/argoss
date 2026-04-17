import requests
import argparse
import json

# ПРАВИЛЬНЫЙ ПОРТ - 5051 (TCP)
BASE_URL = "http://localhost:5051"

def make_request(method: str, endpoint: str, data=None):
    """Универсальная функция для API запросов."""
    url = f"{BASE_URL}{endpoint}"
    headers = {"Content-Type": "application/json"}
    
    try:
        if method.upper() == "GET":
            response = requests.get(url, headers=headers, timeout=15)
        elif method.upper() == "POST":
            response = requests.post(url, headers=headers, json=data, timeout=15)
        else:
            raise ValueError(f"Неподдерживаемый метод: {method}")
        
        if response.status_code == 200:
            try:
                return response.json()
            except:
                return {"text": response.text}
        else:
            print(f"❌ HTTP ошибка: {response.status_code} для {url}")
            print(f"   Ответ: {response.text}")
            return None
            
    except Exception as e:
        print(f"❌ Ошибка запроса: {e}")
        return None

def cmd_chat(args):
    """Отправка сообщения в Argos"""
    data = {"message": args.message}
    result = make_request("POST", "/api/chat", data)
    
    if result:
        if "response" in result:
            print(f"💬 {result['response']}")
        elif "text" in result:
            print(result["text"])
        else:
            print(json.dumps(result, indent=2, ensure_ascii=False))

def cmd_status(args):
    """Получение статуса системы"""
    result = make_request("GET", "/api/status")
    if result:
        print(json.dumps(result, indent=2, ensure_ascii=False))

def cmd_skills(args):
    """Получение списка навыков"""
    # Проверяем возможные endpoints
    endpoints = [
        "/api/skills", 
        "/skills",
        "/api/v1/skills",
        "/api/nodes"
    ]
    
    for endpoint in endpoints:
        result = make_request("GET", endpoint)
        if result:
            print(json.dumps(result, indent=2, ensure_ascii=False))
            return
    
    # Если API не отвечает, пробуем через chat
    chat_result = make_request("POST", "/api/chat", {"message": "list all skills"})
    if chat_result:
        print(json.dumps(chat_result, indent=2, ensure_ascii=False))

def main():
    parser = argparse.ArgumentParser(description="Argos CLI (Working on Port 5051)")
    subparsers = parser.add_subparsers(dest="command", required=True)
    
    chat = subparsers.add_parser("chat", help="Отправить сообщение")
    chat.add_argument("message", help="Сообщение для отправки")
    chat.set_defaults(func=cmd_chat)
    
    status = subparsers.add_parser("status", help="Получить статус системы")
    status.set_defaults(func=cmd_status)
    
    skills = subparsers.add_parser("skills", help="Получить список навыков")
    skills.set_defaults(func=cmd_skills)
    
    args = parser.parse_args()
    args.func(args)

if __name__ == "__main__":
    main()
