from fastapi import FastAPI
import uvicorn
from pydantic import BaseModel

app = FastAPI(title="Argos Test Server", version="1.0.0")

class ChatRequest(BaseModel):
    message: str

@app.get("/")
async def root():
    return {"message": "Argos Test Server Running", "status": "ok"}

@app.get("/api/status")
async def status():
    return {"status": "running", "service": "argos", "port": 5001}

@app.post("/api/chat")
async def chat(request: ChatRequest):
    return {"response": f"Argos получил: {request.message}", "status": "ok"}

@app.post("/api/kimi/chat")
async def kimi_chat(request: ChatRequest):
    return {"response": f"Kimi получил: {request.message}", "status": "ok"}

if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=5001)  # Порт 5001 вместо 5000
