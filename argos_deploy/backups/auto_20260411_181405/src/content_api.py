from __future__ import annotations

import threading
from typing import Literal

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel


def create_app():
    from src.connectivity import telegram_bot as tg
    import arc_play

    app = FastAPI(title="Argos Content Control", version="1.0")

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/content-mode")
    def get_mode():
        return {"mode": "free" if tg.CONTENT_ALLOW_ALL else "safe"}

    @app.post("/content-mode")
    def set_mode(mode: Literal["free", "safe"]):
        if mode == "free":
            tg.CONTENT_ALLOW_ALL = True
        else:
            tg.CONTENT_ALLOW_ALL = False
        return {"mode": "free" if tg.CONTENT_ALLOW_ALL else "safe"}

    @app.get("/domains")
    def get_domains():
        return {"domains": tg.get_allowed_domains()}

    @app.post("/domains")
    def update_domains(add: list[str] | None = None, remove: list[str] | None = None):
        domains = tg.update_allowed_domains(add=add or [], remove=remove or [])
        return {"domains": domains}

    class ArcPlayRequest(BaseModel):
        env_id: str = "ls20"
        steps: int = 10
        render: bool = False
        action_name: str | None = None

    @app.get("/arc/status")
    def arc_status():
        return arc_play.get_status()

    @app.get("/arc/stats")
    def arc_stats():
        return arc_play.get_learning_stats()

    @app.post("/arc/play")
    def arc_play_start(req: ArcPlayRequest):
        return arc_play.start_game_async(
            env_id=req.env_id,
            steps=req.steps,
            render=req.render,
            action_name=req.action_name,
        )

    return app


def start_content_api(host: str = "127.0.0.1", port: int = 5050):
    app = create_app()

    config = uvicorn.Config(app, host=host, port=port, log_level="warning")
    server = uvicorn.Server(config)

    thread = threading.Thread(target=server.run, daemon=True, name="ContentAPI")
    thread.start()
    return thread
