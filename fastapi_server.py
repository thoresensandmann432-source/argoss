# В fastapi_server.py заменить эндпоинт:
@app.post("/exec")
async def run_powershell(command: dict):
    cmd = command.get("cmd", "")
    # Валидация — только разрешённые команды
    allowed = {"Get-Process", "Get-Service", "dir", "ls", "type"}
    if not any(cmd.strip().startswith(a) for a in allowed):
        return {"status": "error", "message": "Команда не разрешена"}
    
    result = subprocess.run(
        ["powershell", "-NoProfile", "-Command", cmd],
        capture_output=True, text=True, timeout=30
    )
    return {"status": "ok", "output": result.stdout, "error": result.stderr}
