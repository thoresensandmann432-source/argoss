#!/usr/bin/env python3
"""
argos_service.py — Установка Аргоса как Windows-сервиса

Требует: pip install pywin32
Запуск от администратора:
  python argos_service.py install   — установить сервис
  python argos_service.py start     — запустить
  python argos_service.py stop      — остановить
  python argos_service.py remove    — удалить
"""
import sys
import os
from pathlib import Path

SERVICE_NAME = "ArgosUniversalOS"
SERVICE_DISPLAY = "Argos Universal OS"
SERVICE_DESC = "Автономный ИИ-ассистент Аргос"

def install_via_nssm():
    """Установка через NSSM (Non-Sucking Service Manager) — проще всего."""
    nssm = Path("nssm.exe")
    if not nssm.exists():
        print("NSSM не найден. Скачай: https://nssm.cc/download")
        print("Или используй: python argos_service.py bat")
        return False
    
    python_exe = sys.executable
    main_py    = str(Path.cwd() / "main.py")
    
    os.system(f'nssm install {SERVICE_NAME} "{python_exe}" "{main_py} --no-gui"')
    os.system(f'nssm set {SERVICE_NAME} DisplayName "{SERVICE_DISPLAY}"')
    os.system(f'nssm set {SERVICE_NAME} Description "{SERVICE_DESC}"')
    os.system(f'nssm set {SERVICE_NAME} AppDirectory "{Path.cwd()}"')
    os.system(f'nssm set {SERVICE_NAME} Start SERVICE_AUTO_START')
    print(f"✅ Сервис {SERVICE_NAME} установлен. Запуск: nssm start {SERVICE_NAME}")
    return True

def install_via_bat():
    """Создаёт .bat файл для Startup папки."""
    startup = Path(os.environ.get("APPDATA", ".")) / "Microsoft/Windows/Start Menu/Programs/Startup"
    bat_src = Path("argos_autostart.bat")
    if bat_src.exists():
        import shutil
        dst = startup / "argos.bat"
        shutil.copy2(str(bat_src), str(dst))
        print(f"✅ Автозапуск установлен: {dst}")
        print("Аргос будет запускаться при входе в систему.")
    else:
        print("❌ argos_autostart.bat не найден рядом со скриптом")

if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "help"
    
    if cmd == "install":
        if not install_via_nssm():
            print("Пробуем через bat...")
            install_via_bat()
    elif cmd == "bat":
        install_via_bat()
    elif cmd == "start":
        os.system(f"sc start {SERVICE_NAME}")
    elif cmd == "stop":
        os.system(f"sc stop {SERVICE_NAME}")
    elif cmd == "remove":
        os.system(f"sc delete {SERVICE_NAME}")
    else:
        print(__doc__)
