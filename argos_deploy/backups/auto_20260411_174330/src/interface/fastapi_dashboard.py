"""
src/interface/fastapi_dashboard.py
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
FastAPI веб-панель + Remote Control API Аргоса.

Эндпоинты:
  GET  /api/health           — статус (без авторизации)
  GET  /api/status           — CPU/RAM/диск/состояние
  POST /api/command          — выполнить команду (Bearer token)
  GET  /api/events?limit=N   — последние события EventBus
  POST /webhook/command      — IPC webhook (Bearer token)
  GET  /                     — HTML веб-панель

pip install fastapi uvicorn[standard]
"""

from __future__ import annotations

import asyncio
import os
import time
import threading
import datetime
from typing import Any

try:
    from fastapi import FastAPI, Request, HTTPException, Depends  # type: ignore
    from fastapi.responses import HTMLResponse, JSONResponse  # type: ignore
    from fastapi.middleware.cors import CORSMiddleware  # type: ignore
    import uvicorn  # type: ignore

    _FASTAPI_OK = True
except ImportError:
    _FASTAPI_OK = False

_START_TIME = time.time()


class FastAPIDashboard:
    """FastAPI веб-панель + REST API + IPC webhook Аргоса."""

    VERSION = "2.1.3"

    def __init__(
        self,
        core=None,
        admin=None,
        flasher=None,
        port: int = 8080,
        host: str = "0.0.0.0",
    ):
        self.core = core
        self.admin = admin
        self.flasher = flasher
        self.port = port
        self.host = host
        self.token = os.getenv("ARGOS_REMOTE_TOKEN", "")
        self._app: Any = None
        self._thread: threading.Thread | None = None

    # ── Auth ─────────────────────────────────────────────────────────────────

    def _check_auth(self, request: Request):
        if not self.token:
            return True
        auth = request.headers.get("Authorization", "")
        if not auth.startswith("Bearer ") or auth[7:] != self.token:
            raise HTTPException(status_code=401, detail="Unauthorized")
        return True

    # ── App factory ───────────────────────────────────────────────────────────

    def _build_app(self) -> Any:
        if not _FASTAPI_OK:
            raise ImportError("FastAPI не установлен: pip install fastapi uvicorn")

        app = FastAPI(title="Argos Universal OS", version=self.VERSION)

        app.add_middleware(
            CORSMiddleware,
            allow_origins=["*"],
            allow_methods=["*"],
            allow_headers=["*"],
        )

        dashboard = self  # ссылка для замыканий

        # ── /api/health ──────────────────────────────────────────────────────

        @app.get("/api/health")
        async def health():
            return {
                "ok": True,
                "status": "ok",
                "version": self.VERSION,
                "uptime_seconds": round(time.time() - _START_TIME),
                "node": os.getenv("HOSTNAME", "argos"),
            }

        # ── /api/status ───────────────────────────────────────────────────────

        @app.get("/api/status")
        async def status():
            info: dict[str, Any] = {"version": self.VERSION}
            try:
                import psutil
                import sys as _sys

                info["cpu_pct"] = psutil.cpu_percent(interval=0.1)
                mem = psutil.virtual_memory()
                info["ram_pct"] = mem.percent
                info["ram_mb"] = mem.total // 1024 // 1024
                _disk_path = "C:/" if _sys.platform == "win32" else "/"
                disk = psutil.disk_usage(_disk_path)
                info["disk_pct"] = disk.percent
            except Exception:
                pass
            if dashboard.core:
                try:
                    q = dashboard.core.quantum.generate_state()
                    info["quantum_state"] = q.get("name", "?")
                    info["ai_mode"] = dashboard.core.ai_mode_label()
                except Exception:
                    pass
            return info

        # ── /api/command ──────────────────────────────────────────────────────

        @app.post("/api/command")
        async def command(request: Request):
            dashboard._check_auth(request)
            data = await request.json()
            cmd = data.get("cmd", "").strip()
            if not cmd:
                raise HTTPException(status_code=400, detail="cmd is required")
            if not dashboard.core:
                return JSONResponse({"ok": False, "error": "Ядро не инициализировано"})
            try:
                result = dashboard.core.process(cmd)
                answer = result.get("answer", "") if isinstance(result, dict) else str(result)
                return {"ok": True, "answer": answer, "cmd": cmd}
            except Exception as exc:
                return JSONResponse({"ok": False, "error": str(exc)}, status_code=500)

        # ── /api/events ───────────────────────────────────────────────────────

        @app.get("/api/events")
        async def events(request: Request, limit: int = 20):
            dashboard._check_auth(request)
            evt_list = []
            if dashboard.core:
                try:
                    from src.event_bus import get_bus

                    bus = get_bus()
                    for ev in list(bus._history)[-limit:]:
                        evt_list.append(
                            {
                                "topic": getattr(ev, "topic", str(ev)),
                                "data": getattr(ev, "data", {}),
                                "ts": getattr(ev, "ts", 0),
                            }
                        )
                except Exception:
                    pass
            return {"ok": True, "events": evt_list, "count": len(evt_list)}

        # ── /api/log ──────────────────────────────────────────────────────────

        @app.get("/api/log")
        async def log_endpoint(request: Request, lines: int = 50):
            dashboard._check_auth(request)
            text = ""
            _log_candidates = [
                "logs/argos.log",
                "logs/argos_stdout.log",
                "logs/argo_live.out.log",
                "logs/argos_server.out",
            ]
            for candidate in _log_candidates:
                if os.path.exists(candidate):
                    try:
                        with open(candidate, encoding="utf-8", errors="replace") as _f:
                            _all = _f.readlines()
                        text = "".join(_all[-lines:])
                        break
                    except Exception:
                        continue
            return {"ok": True, "lines": text, "source": candidate if text else "none"}

        # ── /webhook/command (IPC) ────────────────────────────────────────────

        @app.post("/webhook/command")
        async def webhook_command(request: Request):
            data = await request.json()
            if dashboard.token and data.get("token") != dashboard.token:
                raise HTTPException(status_code=401, detail="Unauthorized")
            cmd = data.get("cmd", "").strip()
            if not cmd:
                raise HTTPException(status_code=400, detail="cmd is required")
            if not dashboard.core:
                return {"ok": False, "error": "Ядро не инициализировано"}
            result = dashboard.core.process(cmd)
            answer = result.get("answer", "") if isinstance(result, dict) else str(result)
            return {"ok": True, "reply": answer}

        # ── / HTML панель ─────────────────────────────────────────────────────

        @app.get("/", response_class=HTMLResponse)
        async def root():
            return HTMLResponse(_html_panel(self.VERSION, self.port))

        return app

    # ── Start ─────────────────────────────────────────────────────────────────

    def start(self) -> str:
        if not _FASTAPI_OK:
            return "❌ FastAPI не установлен: pip install fastapi uvicorn"
        self._app = self._build_app()

        def _run():
            uvicorn.run(self._app, host=self.host, port=self.port, log_level="warning")

        self._thread = threading.Thread(target=_run, daemon=True, name="ArgosAPI")
        self._thread.start()
        return f"✅ FastAPI Dashboard: http://{self.host}:{self.port}"


def _html_panel(version: str, port: int) -> str:
    return f"""<!DOCTYPE html>
<html lang="ru">
<head>
  <meta charset="UTF-8">
  <title>ARGOS v{version}</title>
  <style>
    body {{ background:#0a0a0a; color:#00ff88; font-family:monospace; padding:2rem; }}
    h1 {{ color:#00f2ff; }}
    .btn {{ background:#003; border:1px solid #00ff88; color:#00ff88;
            font-family:monospace; padding:0.5rem 1rem; cursor:pointer; margin:0.3rem; }}
    .btn:hover {{ background:#006; }}
    #out {{ border:1px solid #00ff88; padding:1rem; min-height:4rem;
            white-space:pre-wrap; margin-top:1rem; }}
    #logbox {{ border:1px solid #1a4a2a; padding:0.5rem; height:160px;
               overflow-y:auto; white-space:pre; font-size:0.75em;
               color:#5af; margin-top:0.5rem; background:#000; }}
    input {{ background:#001; border:1px solid #00ff88; color:#00ff88;
             font-family:monospace; padding:0.4rem; width:60%; }}
    .metrics {{ font-size:0.85em; color:#0af; margin-top:0.5rem; }}
  </style>
</head>
<body>
  <h1>&#x1f531; ARGOS Universal OS v{version}</h1>
  <div class="metrics" id="metrics">Загрузка...</div>
  <div style="margin-top:1rem">
    <input id="cmd" placeholder="Введите команду..." onkeydown="if(event.key==='Enter')send()">
    <button class="btn" onclick="send()">&#x25b6; RUN</button>
  </div>
  <div>
    <button class="btn" onclick="run('статус системы')">&#x1f4ca; Статус</button>
    <button class="btn" onclick="run('помощь')">&#x2753; Помощь</button>
    <button class="btn" onclick="run('крипто')">&#x1f4b0; Крипто</button>
    <button class="btn" onclick="run('git статус')">&#x1f500; Git</button>
  </div>
  <div id="out">Готов к работе...</div>
  <div style="margin-top:1rem;color:#0af;font-size:0.8em">&#x1f4cb; СИСТЕМНЫЙ ЛОГ</div>
  <div id="logbox">Загружаю лог...</div>
  <script>
    // Токен: из URL-параметра ?token=XXX или пустой
    const token = new URLSearchParams(location.search).get('token') || '';
    const hdrs = {{'Content-Type':'application/json',
                   'Authorization': token ? 'Bearer '+token : ''}};

    async function run(cmd) {{
      document.getElementById('out').textContent = '&#x23f3; ' + cmd + '...';
      try {{
        const r = await fetch('/api/command', {{
          method:'POST', headers: hdrs,
          body: JSON.stringify({{cmd}})
        }});
        const d = await r.json();
        document.getElementById('out').textContent = d.answer || d.error || JSON.stringify(d);
      }} catch(e) {{
        document.getElementById('out').textContent = '&#x274c; ' + e;
      }}
    }}
    function send() {{
      const v = document.getElementById('cmd').value.trim();
      if(v) {{ run(v); document.getElementById('cmd').value=''; }}
    }}

    async function fetchStatus() {{
      try {{
        const r = await fetch('/api/health');
        const d = await r.json();
        const s = await fetch('/api/status');
        const sd = await s.json();
        document.getElementById('metrics').textContent =
          'up ' + d.uptime_seconds + 's | ' +
          'cpu ' + (sd.cpu_pct||'?') + '% | ' +
          'ram ' + (sd.ram_pct||'?') + '% | ' +
          'disk ' + (sd.disk_pct||'?') + '% | ' +
          'ai=' + (sd.ai_mode||'?');
        document.title = 'ARGOS v{version} | up ' + d.uptime_seconds + 's';
      }} catch(e) {{}}
    }}

    async function fetchLog() {{
      try {{
        const r = await fetch('/api/log' + (token?'?token='+token:''));
        const d = await r.json();
        const el = document.getElementById('logbox');
        if(d.lines) {{ el.textContent = d.lines; el.scrollTop = el.scrollHeight; }}
      }} catch(e) {{}}
    }}

    fetchStatus();
    fetchLog();
    setInterval(fetchStatus, 10000);
    setInterval(fetchLog, 8000);
  </script>
</body>
</html>"""
