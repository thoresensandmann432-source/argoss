import subprocess
import shlex
from fastapi import FastAPI, HTTPException, Header
import uvicorn
import os

app = FastAPI()

# Тот самый токен из твоего .env для безопасности
ARGOS_BRIDGE_TOKEN = "your_secret_token_here" 

# БЕЛЫЙ СПИСОК: Только эти команды разрешены Аргосу
ALLOWED_COMMANDS = {
    "Get-Process", "Get-Service", "dir", "ls", "Get-Content", 
    "Get-ChildItem", "nvidia-smi", "Get-WmiObject", "systeminfo", "df"
}

@app.post("/exec")
async def run_powershell(data: dict, authorization: str = Header(None)):
    # 1. Проверка авторизации
    if authorization != f"Bearer {ARGOS_BRIDGE_TOKEN}":
        raise HTTPException(status_code=403, detail="Доступ запрещен: Неверный токен")

    cmd_raw = data.get("cmd", "").strip()
    
    # 2. Проверка по белому списку (защита от RCE)
    is_safe = any(cmd_raw.startswith(allowed) for allowed in ALLOWED_COMMANDS)
    
    if not is_safe:
        return {"status": "denied", "message": f"Команда '{cmd_raw}' не входит в белый список безопасности."}

    try:
        # 3. Безопасный запуск без профиля пользователя
        result = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", cmd_raw],
            capture_output=True, 
            text=True, 
            timeout=30,
            encoding='cp866' # Для корректного русского языка в Windows
        )
        
        return {
            "status": "ok",
            "stdout": result.stdout,
            "stderr": result.stderr,
            "code": result.returncode
        }
    except subprocess.TimeoutExpired:
        return {"status": "error", "message": "Превышено время ожидания (30с)"}
    except Exception as e:
        return {"status": "error", "message": str(e)}

if __name__ == "__main__":
    print(f"🚀 ЗАЩИЩЕННЫЙ МОСТ ARGOS v2.2 запущен на порту 5000")
    print(f"🔒 Разрешенные команды: {', '.join(ALLOWED_COMMANDS)}")
    uvicorn.run(app, host="0.0.0.0", port=5000)
