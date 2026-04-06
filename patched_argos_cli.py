import sys
import os
import requests
import argparse
import json

# ПРАВИЛЬНЫЙ BASE_URL для нашего сервера
BASE_URL = "http://localhost:5051"

def make_request(method: str, endpoint: str, data=None, stream=False):
    """Универсальная функция для API запросов с правильным URL."""
    url = f"{BASE_URL}{endpoint}"
    headers = {"Content-Type": "application/json"}
    
    try:
        if method.upper() == "GET":
            response = requests.get(url, headers=headers, timeout=30)
        elif method.upper() == "POST":
            response = requests.post(url, headers=headers, json=data, timeout=30, stream=stream)
        else:
            raise ValueError(f"Неподдерживаемый метод: {method}")
            
        if response.status_code == 200:
            if stream:
                return response
            else:
                try:
                    return response.json()
                except:
                    return {"text": response.text}
        else:
            print(f"❌ HTTP ошибка: {response.status_code} для {url}")
            print(f"   Ответ: {response.text}")
            return None
            
    except requests.exceptions.ConnectionError:
        print(f"❌ Ошибка: не удалось подключиться к {BASE_URL}")
        print("   Убедитесь, что ARGOS запущен (python main.py)")
        sys.exit(1)
    except Exception as e:
        print(f"❌ Ошибка запроса: {e}")
        return None

def cmd_chat(args):
    """Отправить сообщение в ARGOS."""
    data = {
        "message": args.message,
        "stream": getattr(args, 'stream', False)
    }
    
    if getattr(args, 'system', None):
        data["system_prompt"] = args.system
        
    if getattr(args, 'temperature', None) is not None:
        data["temperature"] = args.temperature
    
    result = make_request("POST", "/api/chat", data)
    if result:
        if isinstance(result, dict) and "response" in result:
            print(result["response"])
        elif isinstance(result, dict) and "text" in result:
            print(result["text"])
        else:
            print(json.dumps(result, indent=2, ensure_ascii=False))

def cmd_status(args):
    """Проверка статуса."""
    result = make_request("GET", "/api/status")
    if result:
        print(json.dumps(result, indent=2, ensure_ascii=False))

def main():
    parser = argparse.ArgumentParser(
        description="ARGOS CLI Client (PATCHED VERSION)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Примеры:
  patched_argos_cli.py chat "Привет, Аргос!"
  patched_argos_cli.py status
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
    
    args = parser.parse_args()
    
    if hasattr(args, 'func'):
        args.func(args)
    else:
        parser.print_help()

if __name__ == "__main__":
    main()
