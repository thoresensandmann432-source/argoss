import sys
import requests
import argparse
import json
import os

# ИСПРАВЛЕННЫЙ BASE_URL
BASE_URL = "http://localhost:5051"

def make_request(method: str, endpoint: str, data=None, stream=False):
    """Универсальная функция для API запросов."""
    url = f"{BASE_URL}{endpoint}"
    headers = {"Content-Type": "application/json"}
    
    try:
        if method.upper() == "GET":
            response = requests.get(url, headers=headers, timeout=30)
        elif method.upper() == "POST":
            response = requests.post(url, headers=headers, json=data, timeout=30, stream=stream)
        else:
            raise ValueError(f"Неподдерживаемый метод: {method}")
            
        return response
            
    except requests.exceptions.ConnectionError:
        print(f"❌ Ошибка: не удалось подключиться к {BASE_URL}")
        print("   Убедитесь, что ARGOS запущен (python main.py)")
        sys.exit(1)
    except Exception as e:
        print(f"❌ Ошибка запроса: {e}")
        return None

def cmd_chat(args):
    """Отправить сообщение в ARGOS."""
    print(f"💬 Отправка: {args.message}")
    
    data = {
        "message": args.message,
        "stream": getattr(args, 'stream', False)
    }
    
    if getattr(args, 'system', None):
        data["system_prompt"] = args.system
        
    if getattr(args, 'temperature', None) is not None:
        data["temperature"] = args.temperature
    
    response = make_request("POST", "/api/chat", data)
    if response:
        if response.status_code == 200:
            try:
                result = response.json()
                if isinstance(result, dict) and "response" in result:
                    print(result["response"])
                else:
                    print(json.dumps(result, indent=2, ensure_ascii=False))
            except:
                print(response.text)
        else:
            print(f"❌ HTTP ошибка: {response.status_code}")
            try:
                print(f"   Ответ: {response.json()}")
            except:
                print(f"   Ответ: {response.text}")

def cmd_status(args):
    """Проверка статуса."""
    print("📊 Получение статуса...")
    
    response = make_request("GET", "/api/status")
    if response:
        if response.status_code == 200:
            try:
                result = response.json()
                print(json.dumps(result, indent=2, ensure_ascii=False))
            except:
                print(response.text)
        else:
            print(f"❌ HTTP ошибка: {response.status_code}")
            try:
                print(f"   Ответ: {response.json()}")
            except:
                print(f"   Ответ: {response.text}")

def cmd_skills(args):
    """Получение списка навыков."""
    print("🧩 Получение списка навыков...")
    
    # Пробуем разные endpoints для получения навыков
    endpoints = ["/api/skills", "/skills", "/api/v1/skills"]
    
    for endpoint in endpoints:
        response = make_request("GET", endpoint)
        if response and response.status_code == 200:
            try:
                result = response.json()
                print(json.dumps(result, indent=2, ensure_ascii=False))
                return
            except:
                print(response.text)
                return
        elif response and response.status_code != 404:
            print(f"⚠️  Endpoint {endpoint}: {response.status_code}")
    
    # Если стандартные endpoints не работают, пробуем через chat
    print("🔄 Пробуем получить навыки через chat...")
    chat_response = make_request("POST", "/api/chat", {"message": "list all skills"})
    if chat_response and chat_response.status_code == 200:
        try:
            print(chat_response.json())
        except:
            print(chat_response.text)

def main():
    parser = argparse.ArgumentParser(
        description="ARGOS CLI Client (FIXED PORT 5051)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Примеры:
  fixed_argos_cli.py chat "Привет, Аргос!"
  fixed_argos_cli.py status
  fixed_argos_cli.py skills
        """
    )
    
    subparsers = parser.add_subparsers(dest='command', help='Команды')
    
    # Chat команда
    chat_p = subparsers.add_parser('chat', help='Отправить сообщение в ARGOS')
    chat_p.add_argument('message', help='Сообщение')
    chat_p.add_argument("--system", help="Системный промпт")
    chat_p.add_argument("--temperature", type=float, default=0.7)
    chat_p.add_argument("--stream", action="store_true", help="Потоковый вывод")
    chat_p.set_defaults(func=cmd_chat)
    
    # Status команда
    status_p = subparsers.add_parser('status', help='Состояние системы')
    status_p.set_defaults(func=cmd_status)
    
    # Skills команда
    skills_p = subparsers.add_parser('skills', help='Список навыков')
    skills_p.set_defaults(func=cmd_skills)
    
    args = parser.parse_args()
    
    if hasattr(args, 'func'):
        args.func(args)
    else:
        parser.print_help()

if __name__ == "__main__":
    main()
