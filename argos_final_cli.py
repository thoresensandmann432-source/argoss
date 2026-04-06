import requests
import argparse
import json
import sys

# ПРАВИЛЬНЫЙ ПОРТ И БАЗОВЫЙ URL
BASE_URL = "http://localhost:5051"
TIMEOUT = 15

def make_request(method: str, endpoint: str, data=None):
    """Универсальная функция для API запросов с правильными путями."""
    url = f"{BASE_URL}{endpoint}"
    headers = {"Content-Type": "application/json"}
    
    try:
        if method.upper() == "GET":
            response = requests.get(url, headers=headers, timeout=TIMEOUT)
        elif method.upper() == "POST":
            response = requests.post(url, headers=headers, json=data, timeout=TIMEOUT)
        else:
            raise ValueError(f"Неподдерживаемый метод: {method}")
        
        return response
            
    except Exception as e:
        print(f"❌ Ошибка запроса: {e}")
        return None

def cmd_chat(args):
    """Отправка сообщения через правильный endpoint"""
    # Проверяем несколько возможных путей
    endpoints = [
        "/api/chat",
        "/chat",
        "/message",
        "/api/v1/chat"
    ]
    
    for endpoint in endpoints:
        print(f"🔍 Проверка {endpoint}...")
        response = make_request("POST", endpoint, {"message": args.message})
        
        if response and response.status_code == 200:
            try:
                result = response.json()
                if isinstance(result, dict) and "response" in result:
                    print(f"💬 {result['response']}")
                    return
                else:
                    print(json.dumps(result, indent=2, ensure_ascii=False))
                    return
            except:
                print(response.text)
                return
        elif response:
            print(f"⚠️ {endpoint}: {response.status_code} - {response.text[:100]}")
    
    print("❌ Не удалось найти рабочий endpoint для чата")

def cmd_status(args):
    """Получение статуса через правильный endpoint"""
    endpoints = [
        "/api/status",
        "/status",
        "/health",
        "/api/v1/status"
    ]
    
    for endpoint in endpoints:
        print(f"🔍 Проверка {endpoint}...")
        response = make_request("GET", endpoint)
        
        if response and response.status_code == 200:
            try:
                result = response.json()
                print(json.dumps(result, indent=2, ensure_ascii=False))
                return
            except:
                print(response.text)
                return
        elif response:
            print(f"⚠️ {endpoint}: {response.status_code} - {response.text[:100]}")
    
    print("❌ Не удалось получить статус")

def cmd_skills(args):
    """Получение списка навыков через разные методы"""
    # Метод 1: Попробуем получить через chat
    print("🔄 Пытаемся получить навыки через chat...")
    response = make_request("POST", "/api/chat", {"message": "list all skills"})
    if response and response.status_code == 200:
        try:
            result = response.json()
            print(json.dumps(result, indent=2, ensure_ascii=False))
            return
        except:
            print(response.text)
            return
    
    # Метод 2: Проверим специальные endpoints
    endpoints = [
        "/api/skills",
        "/skills",
        "/api/v1/skills",
        "/api/nodes"
    ]
    
    for endpoint in endpoints:
        print(f"🔍 Проверка {endpoint}...")
        response = make_request("GET", endpoint)
        
        if response and response.status_code == 200:
            try:
                result = response.json()
                print(json.dumps(result, indent=2, ensure_ascii=False))
                return
            except:
                print(response.text)
                return
        elif response:
            print(f"⚠️ {endpoint}: {response.status_code} - {response.text[:100]}")
    
    print("❌ Не удалось получить список навыков")

def main():
    parser = argparse.ArgumentParser(description="Argos CLI - Умный поиск правильных endpoints")
    subparsers = parser.add_subparsers(dest="command", required=True)
    
    chat = subparsers.add_parser("chat", help="Отправить сообщение в Argos")
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
