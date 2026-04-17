from __future__ import annotations

import os
import threading
import time
from typing import Any

import uvicorn
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware


class ArgosMCPServer:
    """Минимальный HTTP MCP endpoint для локальной интеграции."""

    def __init__(self, core=None, admin=None):
        self.core = core
        self.admin = admin
        self.started_at = time.time()
        self.app = self._create_app()

    def _providers(self) -> str:
        try:
            from src.ai_providers import providers_status

            return providers_status()
        except Exception as exc:
            return f"providers error: {exc}"

    def _skills(self) -> str:
        if self.core and getattr(self.core, "skill_loader", None):
            try:
                return self.core.skill_loader.list_skills()
            except Exception as exc:
                return f"skills error: {exc}"
        return "skill_loader not initialized"

    def _limits(self) -> str:
        try:
            from src.connectivity.telegram_bot import ArgosTelegram

            bot = ArgosTelegram(self.core, self.admin, None)
            return bot._build_limits_report()
        except Exception as exc:
            return f"limits error: {exc}"

    def _status(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "ok": True,
            "uptime_seconds": int(time.time() - self.started_at),
            "ai_mode": self.core.ai_mode_label() if self.core and hasattr(self.core, "ai_mode_label") else "unknown",
        }
        try:
            import psutil

            out["cpu_pct"] = psutil.cpu_percent(interval=0.1)
            out["ram_pct"] = psutil.virtual_memory().percent
        except Exception:
            pass
        return out

    def _image_generate(
        self,
        prompt: str,
        negative_prompt: str = "",
        steps: int = 20,
        width: int = 1024,
        height: int = 1024,
        model_name: str | None = None,
    ) -> str:
        from src.tools.image_generator import ArgosImageGenerator

        gen = ArgosImageGenerator(model_name=model_name)
        return gen.generate(
            prompt=prompt,
            negative_prompt=negative_prompt,
            steps=steps,
            width=width,
            height=height,
        )

    async def _run_command(self, text: str) -> str:
        """Async version: runs command without creating new event loop."""
        if not text.strip():
            return "empty command"
        if self.core and hasattr(self.core, "process_logic_async"):
            try:
                # Use await directly since we're already in async context
                result = await self.core.process_logic_async(text, self.admin, None)
                if isinstance(result, dict):
                    return str(result.get("answer", result))
                return str(result)
            except Exception as exc:
                return f"command error: {exc}"
        return "core not initialized"

    def _create_app(self) -> FastAPI:
        app = FastAPI(title="Argos MCP", version="1.0")
        app.add_middleware(
            CORSMiddleware,
            allow_origins=["*"],
            allow_methods=["*"],
            allow_headers=["*"],
        )

        @app.get("/health")
        def health():
            return self._status()

        @app.get("/mcp")
        def mcp_ping():
            return {
                "name": "argos",
                "ok": True,
                "transport": "http",
                "hint": "POST JSON-RPC to /mcp",
            }

        @app.post("/mcp")
        async def mcp_rpc(request: Request):
            payload = await request.json()
            if not isinstance(payload, dict):
                raise HTTPException(status_code=400, detail="JSON object expected")

            method = payload.get("method", "")
            req_id = payload.get("id")          # None для notifications
            is_notification = req_id is None    # MCP notifications не имеют id

            def _ok(result: Any):
                return {"jsonrpc": "2.0", "id": req_id, "result": result}

            def _err(code: int, message: str):
                return {"jsonrpc": "2.0", "id": req_id, "error": {"code": code, "message": message}}

            # ── Notifications (нет id) → пустой ответ 200 ────────────────────
            if is_notification:
                # notifications/initialized, notifications/cancelled, etc.
                return {}

            # ── ping ─────────────────────────────────────────────────────────
            if method == "ping":
                return _ok({})

            # ── initialize ───────────────────────────────────────────────────
            if method == "initialize":
                return _ok(
                    {
                        "protocolVersion": "2024-11-05",
                        "serverInfo": {"name": "argos", "version": "2.1.3"},
                        "capabilities": {
                            "tools": {"listChanged": False},
                        },
                        "instructions": (
                            "ARGOS Universal OS — AI-экосистема. "
                            "Используй инструмент 'command' для выполнения любых команд ARGOS. "
                            "Инструменты: providers, skills, limits, status, command, image_generate."
                        ),
                    }
                )

            # ── tools/list ───────────────────────────────────────────────────
            if method == "tools/list":
                tools = [
                    {
                        "name": "providers",
                        "description": "Показывает статус всех AI-провайдеров ARGOS (Gemini, GigaChat, Grok, OpenAI, Groq, DeepSeek, Kimi, Ollama и др.) с лимитами и квотами.",
                        "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
                    },
                    {
                        "name": "skills",
                        "description": "Список загруженных скилов (навыков) ARGOS — внешние интеграции и инструменты.",
                        "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
                    },
                    {
                        "name": "limits",
                        "description": "Отчёт о текущих лимитах и квотах провайдеров.",
                        "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
                    },
                    {
                        "name": "status",
                        "description": "Текущий статус ARGOS: uptime, CPU, RAM, режим ИИ.",
                        "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
                    },
                    {
                        "name": "image_generate",
                        "description": "Generate image from prompt and return absolute file path.",
                        "inputSchema": {
                            "type": "object",
                            "properties": {
                                "prompt": {"type": "string"},
                                "negative_prompt": {"type": "string"},
                                "steps": {"type": "integer", "minimum": 1, "maximum": 80},
                                "width": {"type": "integer", "minimum": 256, "maximum": 1536},
                                "height": {"type": "integer", "minimum": 256, "maximum": 1536},
                                "model_name": {"type": "string"},
                            },
                            "required": ["prompt"],
                            "additionalProperties": False,
                        },
                    },
                    {
                        "name": "command",
                        "description": (
                            "Выполнить команду через ядро ARGOS. "
                            "Примеры: 'статус', 'hf status', 'провайдеры', 'память', 'мысли', 'эволюция', 'режим ии grok'. "
                            "Поддерживаются все команды ARGOS."
                        ),
                        "inputSchema": {
                            "type": "object",
                            "properties": {
                                "text": {
                                    "type": "string",
                                    "description": "Команда для ARGOS на русском или английском языке",
                                }
                            },
                            "required": ["text"],
                            "additionalProperties": False,
                        },
                    },
                ]
                return _ok({"tools": tools})

            # ── tools/call ───────────────────────────────────────────────────
            if method == "tools/call":
                params = payload.get("params") or {}
                name = params.get("name")
                args = params.get("arguments") or {}
                try:
                    if name == "providers":
                        text = self._providers()
                    elif name == "skills":
                        text = self._skills()
                    elif name == "limits":
                        text = self._limits()
                    elif name == "status":
                        text = str(self._status())
                    elif name == "image_generate":
                        text = self._image_generate(
                            prompt=str(args.get("prompt", "")),
                            negative_prompt=str(args.get("negative_prompt", "")),
                            steps=int(args.get("steps", 20) or 20),
                            width=int(args.get("width", 1024) or 1024),
                            height=int(args.get("height", 1024) or 1024),
                            model_name=(str(args.get("model_name")) if args.get("model_name") else None),
                        )
                    elif name == "command":
                        text = await self._run_command(str(args.get("text", "")))
                    else:
                        return _err(-32601, f"Unknown tool: {name}")
                except Exception as exc:
                    text = f"tool error: {exc}"
                return _ok({"content": [{"type": "text", "text": text}]})

            return _err(-32601, f"Method not found: {method}")

        return app


def start_mcp_api(core=None, admin=None, host: str = "127.0.0.1", port: int = 8000):
    server = ArgosMCPServer(core=core, admin=admin)
    config = uvicorn.Config(server.app, host=host, port=port, log_level="warning")
    uv_server = uvicorn.Server(config)
    thread = threading.Thread(target=uv_server.run, daemon=True, name="ArgosMCP")
    thread.start()
    return thread


app = ArgosMCPServer(core=None, admin=None).app
