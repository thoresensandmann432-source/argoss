import subprocess
import sys
import json

def run_argos_command(command):
    """Запуск команды через оригинальный argos_cli.py"""
    try:
        # Используем subprocess для вызова оригинального CLI
        cmd = ["python", "argos_cli.py"] + command.split()
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        
        if result.returncode == 0:
            return result.stdout
        else:
            return f"Ошибка: {result.stderr}"
    except subprocess.TimeoutExpired:
        return "Таймаут выполнения команды"
    except Exception as e:
        return f"Исключение: {e}"

def interactive_argos_session():
    """Интерактивная сессия с Argos"""
    print("🤖 Интерактивная сессия Argos")
    print("Введите команду или 'quit' для выхода")
    print("Примеры команд:")
    print("  - chat \"привет\"")
    print("  - status")
    print("  - kimi \"напиши код\"")
    print("-" * 40)
    
    while True:
        try:
            user_input = input("Argos> ").strip()
            
            if user_input.lower() in ['quit', 'exit', 'выход']:
                print("👋 До свидания!")
                break
                
            if user_input:
                print("⚙️  Выполнение...")
                result = run_argos_command(user_input)
                print(f"📋 Результат:\n{result}")
                print("-" * 40)
                
        except KeyboardInterrupt:
            print("\n👋 До свидания!")
            break
        except EOFError:
            print("\n👋 До свидания!")
            break

def test_specific_commands():
    """Тестирование специфических команд"""
    commands = [
        "chat \"help\"",
        "chat \"list skills\"", 
        "chat \"status\"",
        "chat \"mcp_connector status\"",
        "status"
    ]
    
    print("🧪 Тестирование команд Argos:")
    for cmd in commands:
        print(f"\n🔍 Команда: {cmd}")
        result = run_argos_command(cmd)
        print(f"📋 Ответ: {result}")

if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--test":
        test_specific_commands()
    else:
        interactive_argos_session()
