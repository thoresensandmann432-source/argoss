"""
src/skills/fastapi_skill.py — FastAPI веб-сервер для Аргоса.

Запускает встроенный REST API для удалённого управления Аргосом.
Использует fastapi + uvicorn (pip install fastapi uvicorn).
Переменные .env:
  FASTAPI_HOST  — хост (по умолчанию 0.0.0.0)
  FASTAPI_PORT  — порт (по умолчанию 8080)
  FASTAPI_TOKEN — Bearer токен для авторизации (обязательно задайте!)

Команды:
  fastapi старт           — запустить API сервер
  fastapi стоп            — остановить
  fastapi статус          — текущий статус
  fastapi маршруты        — список доступных эндпоинтов
"""

from __future__ import annotations

SKILL_DESCRIPTION = "FastAPI REST-сервер для удалённого управления"

import os
import threading
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.core import ArgosCore

SKILL_NAME = "fastapi_skill"
SKILL_TRIGGERS = ["fastapi старт", "fastapi стоп", "fastapi статус", "fastapi маршруты",
                  "api сервер", "запусти api", "web api аргос"]

# Глобальный сервер (синглтон)
_server_thread: threading.Thread | None = None
_server_running = False
_server_port = 0


class FastAPISkill:
    """FastAPI REST сервер для Аргоса."""

    def __init__(self, core: "ArgosCore | None" = None):
        self.core = core
        self.host = os.getenv("FASTAPI_HOST", "0.0.0.0")
        self.port = int(os.getenv("FASTAPI_PORT", "8080"))
        self.token = os.getenv("FASTAPI_TOKEN", "")
        try:
            self.mcp_port = int(os.getenv("ARGOS_MCP_PORT", "8000") or "8000")
        except ValueError:
            self.mcp_port = 8000

    def handle_command(self, text: str) -> str | None:
        t = text.lower().strip()
        if "fastapi стоп" in t or "стоп api" in t:
            return self.stop()
        if "fastapi статус" in t or "статус api" in t:
            return self.status()
        if "fastapi маршруты" in t:
            return self.list_routes()
        if "fastapi старт" in t or "запусти api" in t or "api сервер" in t:
            return self.start()
        return None

    def start(self) -> str:
        global _server_thread, _server_running, _server_port
        if _server_running:
            return f"⚡ FastAPI уже запущен на порту {_server_port}"
        if self.port == self.mcp_port:
            self.port = self.mcp_port + 10
        if not self.token:
            return ("⚠️ FastAPI: FASTAPI_TOKEN не задан в .env!\n"
                    "Задайте токен перед запуском для защиты API:\n"
                    "  FASTAPI_TOKEN=ваш_секретный_токен")
        try:
            import fastapi
            import uvicorn
        except ImportError:
            return "❌ FastAPI: установите зависимости: pip install fastapi uvicorn"

        app = self._build_app()
        config = uvicorn.Config(
            app, host=self.host, port=self.port,
            log_level="warning", access_log=False
        )
        server = uvicorn.Server(config)

        def _run():
            global _server_running, _server_port
            _server_running = True
            _server_port = self.port
            try:
                server.run()
            finally:
                _server_running = False

        _server_thread = threading.Thread(target=_run, daemon=True, name="ArgosAPI")
        _server_thread.start()
        import time
        time.sleep(1.5)
        return (
            f"⚡ FastAPI запущен: http://{self.host}:{self.port}\n"
            f"  MCP порт: {self.mcp_port}\n"
            f"  Документация: http://localhost:{self.port}/docs\n"
            f"  Авторизация: Bearer {self.token[:4]}...\n"
            f"  Маршруты: /ask, /status, /memory, /skills"
        )

    def stop(self) -> str:
        global _server_running
        if not _server_running:
            return "⚡ FastAPI не запущен."
        _server_running = False
        return "⚡ FastAPI: сигнал остановки отправлен."

    def status(self) -> str:
        global _server_running, _server_port
        return (
            f"⚡ FASTAPI СЕРВЕР:\n"
            f"  Статус: {'🟢 работает' if _server_running else '🔴 остановлен'}\n"
            f"  Порт: {_server_port if _server_running else self.port}\n"
            f"  Токен: {'задан ✅' if self.token else '⚠️ не задан!'}"
        )

    def list_routes(self) -> str:
        return (
            "⚡ FASTAPI МАРШРУТЫ:\n"
            "  POST /ask         — отправить запрос Аргосу\n"
            "  GET  /status      — статус системы\n"
            "  GET  /memory      — список фактов из памяти\n"
            "  GET  /skills      — список загруженных навыков\n"
            "  GET  /health      — проверка жизнеспособности"
        )

    def run(self) -> str:
        return self.status()

    def _build_app(self):
        """Строит FastAPI приложение с эндпоинтами."""
        from fastapi import FastAPI, Depends, HTTPException, Header
        from fastapi.middleware.cors import CORSMiddleware
        from pydantic import BaseModel

        app = FastAPI(
            title="Argos OS API",
            description="REST API интерфейс для управления Аргосом",
            version="2.1",
        )
        app.add_middleware(
            CORSMiddleware,
            allow_origins=["*"],
            allow_methods=["GET", "POST"],
            allow_headers=["Authorization", "Content-Type"],
        )

        token = self.token
        core = self.core

        def verify_token(authorization: str = Header(None)):
            if not authorization or authorization != f"Bearer {token}":
                raise HTTPException(status_code=401, detail="Unauthorized")
            return True

        class AskRequest(BaseModel):
            text: str

        @app.get("/health")
        async def health():
            return {"status": "ok", "service": "ArgosOS", "version": "2.1"}

        @app.get("/status", dependencies=[Depends(verify_token)])
        async def status():
            if core:
                try:
                    return {"status": "ok", "info": core.get_status() if hasattr(core, "get_status") else "running"}
                except Exception as e:
                    return {"status": "error", "detail": str(e)}
            return {"status": "ok"}

        @app.post("/ask", dependencies=[Depends(verify_token)])
        async def ask(req: AskRequest):
            if not core:
                return {"error": "Аргос не инициализирован"}
            try:
                response = core.handle(req.text)
                return {"response": response}
            except Exception as e:
                return {"error": str(e)}

        @app.get("/memory", dependencies=[Depends(verify_token)])
        async def memory(limit: int = 20):
            if not core or not hasattr(core, "memory") or not core.memory:
                return {"facts": []}
            try:
                facts = core.memory.get_all_facts()
                result = [{"category": c, "key": k, "value": v[:100], "ts": t}
                          for c, k, v, t in facts[-limit:]]
                return {"facts": result, "total": len(facts)}
            except Exception as e:
                return {"error": str(e)}

        @app.get("/skills", dependencies=[Depends(verify_token)])
        async def skills():
            from pathlib import Path
            skill_files = list(Path("src/skills").glob("*.py"))
            names = [f.stem for f in skill_files if not f.stem.startswith("_")]
            return {"skills": names, "count": len(names)}

        return app


def handle(text: str, core=None) -> str | None:
    t = text.lower()
    if not any(kw in t for kw in SKILL_TRIGGERS):
        return None
    return FastAPISkill(core).handle_command(text)
