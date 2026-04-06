#!/usr/bin/env python3
"""
argos_cli.py — CLI клиент для ARGOS API

Использование:
    python argos_cli.py chat "Привет"
    python argos_cli.py kimi "Напиши код на Python"
    python argos_cli.py pip install requests
    python argos_cli.py status
"""

import argparse
import sys
import requests
import json

BASE_URL = "http://localhost:5051"


def make_request(method: str, endpoint: str, data=None, stream=False):
    """Универсальная функция для API запросов."""
    url = f"{BASE_URL}{endpoint}"
    
    try:
        if method == "GET":
            resp = requests.get(url, timeout=10)
        elif method == "POST":
            resp = requests.post(url, json=data, timeout=30, stream=stream)
        else:
            raise ValueError(f"Unknown method: {method}")
        
        resp.raise_for_status()
        
        if stream:
            return resp
        return resp.json()
        
    except requests.exceptions.ConnectionError:
        print(f"❌ Ошибка: не удалось подключиться к {BASE_URL}")
        print("   Убедитесь, что ARGOS запущен (python main.py)")
        sys.exit(1)
    except requests.exceptions.Timeout:
        print("❌ Ошибка: таймаут запроса")
        sys.exit(1)
    except requests.exceptions.HTTPError as e:
        print(f"❌ HTTP ошибка: {e}")
        try:
            print(f"   Ответ: {resp.json()}")
        except:
            pass
        sys.exit(1)


def cmd_chat(args):
    """Отправить сообщение в ARGOS."""
    print(f"💬 Отправка: {args.message}")
    
    data = make_request("POST", "/api/chat", {"message": args.message})
    
    print(f"\n🤖 ARGOS:")
    print(f"   {data.get('response', '[Нет ответа]')}")


def cmd_kimi(args):
    """Отправить сообщение через Kimi."""
    print(f"🌙 Kimi ({args.agent or 'general'}): {args.message}")
    
    if args.stream:
        print("🌙 Ответ (поток):")
        resp = make_request("POST", "/api/kimi/chat/stream", {
            "message": args.message,
            "system": args.system,
            "temperature": args.temperature
        }, stream=True)
        
        for line in resp.iter_lines():
            if line:
                line = line.decode('utf-8')
                if line.startswith('data: '):
                    try:
                        data = json.loads(line[6:])
                        if 'chunk' in data:
                            print(data['chunk'], end='', flush=True)
                        elif data.get('done'):
                            print()
                    except:
                        pass
    else:
        data = make_request("POST", "/api/kimi/chat", {
            "message": args.message,
            "system": args.system,
            "temperature": args.temperature
        })
        
        print(f"\n🌙 Kimi:")
        print(f"   {data.get('response', '[Нет ответа]')}")


def cmd_kimi_agent(args):
    """Выполнить задачу через агента Kimi."""
    print(f"🤖 Агент {args.type}: {args.task}")
    
    data = make_request("POST", "/api/kimi/agent/execute", {
        "task": args.task,
        "agent_type": args.type
    })
    
    print(f"\n📋 Результат:")
    print(f"   {data.get('response', '[Нет ответа]')}")


def cmd_pip(args):
    """Управление pip пакетами."""
    if args.pip_command == "list":
        data = make_request("GET", "/api/pip/list")
        print(f"📦 Установленные пакеты ({data.get('count', 0)}):")
        for pkg in data.get('packages', [])[:20]:
            print(f"   {pkg['name']}=={pkg['version']}")
        
    elif args.pip_command == "outdated":
        data = make_request("GET", "/api/pip/outdated")
        print(f"⚠️ Устаревшие пакеты ({data.get('count', 0)}):")
        for pkg in data.get('packages', []):
            print(f"   {pkg['name']}: {pkg['version']} → {pkg['latest']}")
            
    elif args.pip_command == "install":
        if not args.package:
            print("❌ Укажите пакет: --package requests")
            sys.exit(1)
        print(f"⬇️ Установка {args.package}...")
        data = make_request("POST", "/api/pip/install", {
            "package": args.package,
            "upgrade": args.upgrade
        })
        print(f"   {'✅' if data.get('success') else '❌'} {args.package}")
        
    elif args.pip_command == "check":
        data = make_request("GET", "/api/pip/check")
        critical = data.get('critical', {})
        optional = data.get('optional', {})
        
        print("📋 Зависимости ARGOS:")
        print(f"   ✅ Критических: {critical.get('total', 0) - critical.get('missing', 0)}/{critical.get('total', 0)}")
        print(f"   ⚠️ Опциональных: {optional.get('total', 0) - optional.get('missing', 0)}/{optional.get('total', 0)}")


def cmd_status(args):
    """Проверка статуса."""
    data = make_request("GET", "/api/status")
    
    print("📊 Статус ARGOS:")
    print(f"   Версия: {data.get('version', 'unknown')}")
    print(f"   AI режим: {data.get('ai_mode', 'unknown')}")
    print(f"   Навыков: {data.get('skills_count', 0)}")
    print(f"   Claude агентов: {data.get('claude_agents', 0)}")


def main():
    parser = argparse.ArgumentParser(
        description="ARGOS CLI Client",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Примеры:
  %(prog)s chat "Привет, Аргос!"
  %(prog)s kimi "Напиши функцию сортировки на Python" --agent programming
  %(prog)s kimi-agent "Сделай код ревью" --type programming
  %(prog)s pip list
  %(prog)s pip install requests
  %(prog)s status
        """
    )
    
    subparsers = parser.add_subparsers(dest="command", help="Команды")
    
    # chat
    chat_p = subparsers.add_parser("chat", help="Отправить сообщение в ARGOS")
    chat_p.add_argument("message", help="Текст сообщения")
    
    # kimi
    kimi_p = subparsers.add_parser("kimi", help="Отправить сообщение в Kimi")
    kimi_p.add_argument("message", help="Текст сообщения")
    kimi_p.add_argument("--system", help="Системный промпт")
    kimi_p.add_argument("--temperature", type=float, default=0.7)
    kimi_p.add_argument("--stream", action="store_true", help="Потоковый вывод")
    kimi_p.add_argument("--agent", choices=["general", "programming", "security", "devops", "data"])
    
    # kimi-agent
    kimi_agent_p = subparsers.add_parser("kimi-agent", help="Выполнить задачу агентом")
    kimi_agent_p.add_argument("task", help="Задача")
    kimi_agent_p.add_argument("--type", default="general", 
                              choices=["general", "programming", "security", "devops", "data"])
    
    # pip
    pip_p = subparsers.add_parser("pip", help="Управление pip")
    pip_p.add_argument("pip_command", choices=["list", "outdated", "install", "check"])
    pip_p.add_argument("--package", help="Имя пакета (для install)")
    pip_p.add_argument("--upgrade", action="store_true", help="Обновить пакет")
    
    # status
    subparsers.add_parser("status", help="Статус системы")
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        sys.exit(1)
    
    commands = {
        "chat": cmd_chat,
        "kimi": cmd_kimi,
        "kimi-agent": cmd_kimi_agent,
        "pip": cmd_pip,
        "status": cmd_status,
    }
    
    try:
        commands[args.command](args)
    except KeyboardInterrupt:
        print("\n⏹️ Отменено")
        sys.exit(130)


if __name__ == "__main__":
    main()