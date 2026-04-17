import subprocess
import json
import sys

def run_original_cli(command):
    """Запуск оригинального CLI с правильными параметрами"""
    cmd = ["python", "argos_cli.py"] + command.split()
    result = subprocess.run(cmd, capture_output=True, text=True)
    
    if result.returncode == 0:
        return result.stdout
    else:
        return f"❌ Ошибка: {result.stderr}"

def get_skills():
    """Получаем список навыков через оригинальный CLI"""
    result = run_original_cli('chat "list all skills"')
    if "❌" not in result:
        return result
    return run_original_cli('chat "show skills"')

def main():
    if len(sys.argv) < 2:
        print("Использование: python argos_proxy.py [status|skills|chat <сообщение>]")
        return
    
    command = sys.argv[1]
    
    if command == "status":
        print(run_original_cli("status"))
    
    elif command == "skills":
        print(get_skills())
    
    elif command == "chat" and len(sys.argv) > 2:
        message = " ".join(sys.argv[2:])
        print(run_original_cli(f'chat "{message}"'))
    
    else:
        print("Неизвестная команда")

if __name__ == "__main__":
    main()
