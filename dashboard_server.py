#!/usr/bin/env python3
"""
ARGOS Unified Dashboard Server — http://localhost:8080/
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Что делает:
  • Раздаёт все HTML-дашборды с патчингом API URL
  • Проксирует /health /brain/nodes /brain/command → ARGOS :8000
  • Опрашивает Azure-ноды кластера в реальном времени
  • Отдаёт /api/logs из logs/argos_main.log
"""

import json, os, time, threading, socket
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse
import urllib.request, urllib.error

# ── Конфиг ────────────────────────────────────────────────────
BASE_DIR  = os.path.dirname(os.path.abspath(__file__))
ARGOS_API = "http://localhost:5010"   # ARGOS Brain API
PORT      = 8081                       # 8080 занят ARGOS web_server.py

# Ноды кластера: id → {ip, label, color}
NODES = {
    "LOCAL": {"ip": "127.0.0.1",       "label": "LOCAL", "color": "#58a6ff"},
    "AU":    {"ip": "20.53.240.36",    "label": "AU",    "color": "#f85149"},
    "JP1":   {"ip": "40.81.208.101",   "label": "JP1",   "color": "#3fb950"},
    "JP2":   {"ip": "172.207.209.134", "label": "JP2",   "color": "#d29922"},
    "SE":    {"ip": "20.240.192.35",   "label": "SE",    "color": "#bc8cff"},
    "EXT":   {"ip": "47.237.24.124",   "label": "EXT",   "color": "#ff9500"},
}

MIME = {
    "html": "text/html; charset=utf-8",
    "css":  "text/css",
    "js":   "application/javascript",
    "json": "application/json",
    "svg":  "image/svg+xml",
    "png":  "image/png",
    "ico":  "image/x-icon",
    "woff2":"font/woff2",
}

# ── HTTP helpers ───────────────────────────────────────────────
def http_get(url, timeout=5):
    try:
        req = urllib.request.Request(url, headers={"Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode("utf-8", errors="replace"))
    except Exception as e:
        return {"error": str(e)}

def http_post(url, data, timeout=10):
    try:
        body = json.dumps(data, ensure_ascii=False).encode()
        req  = urllib.request.Request(url, data=body, method="POST")
        req.add_header("Content-Type", "application/json")
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode("utf-8", errors="replace"))
    except Exception as e:
        return {"error": str(e)}

def argos(path, timeout=6):
    return http_get(ARGOS_API + path, timeout)

def get_local_metrics() -> dict:
    """Реальные метрики локальной машины через psutil."""
    try:
        import psutil, time as _t
        try:
            t1 = psutil.cpu_times(); _t.sleep(0.3); t2 = psutil.cpu_times()
            busy  = (t2.user - t1.user) + (t2.system - t1.system)
            total = sum(t2) - sum(t1)
            cpu   = round(100 * busy / max(total, 0.001), 1)
        except Exception:
            cpu = 0
        ram  = psutil.virtual_memory()
        disk = psutil.disk_usage(BASE_DIR)
        return {
            "ok": True,
            "cpu_pct":  cpu,
            "ram_pct":  round(ram.percent, 1),
            "disk_pct": round(disk.percent, 1),
            "ram_used_mb":  ram.used  // 1024 // 1024,
            "ram_total_mb": ram.total // 1024 // 1024,
            "disk_free_gb": disk.free  // 1024 ** 3,
        }
    except ImportError:
        return {"ok": False, "error": "psutil not available"}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def argos_post(path, data, timeout=15):
    return http_post(ARGOS_API + path, data, timeout)

# ── Nodes scanner ──────────────────────────────────────────────
def probe_node(nid: str, ip: str) -> dict:
    """Пробует /health на ноде, возвращает её статус."""
    port = 8000
    t0   = time.time()
    url  = f"http://{ip}:{port}/health"
    d    = http_get(url, timeout=3)
    ms   = int((time.time() - t0) * 1000)

    if "error" in d:
        return {
            "status": "offline", "ping": "—",
            "cpu": 0, "ram": 0, "disk": 0, "gpu": 0,
            "uptime": "—", "provider": "—",
            "p2p": False, "wg_active": False, "peers": 0,
        }
    up_s = d.get("uptime_seconds", 0)
    return {
        "status":   "online",
        "ping":     f"{ms}ms",
        "cpu":      round(d.get("cpu_pct",  0), 1),
        "ram":      round(d.get("ram_pct",  0), 1),
        "disk":     round(d.get("disk_pct", 0), 1),
        "gpu":      0,
        "uptime":   f"{up_s//3600}h {(up_s%3600)//60}m",
        "provider": d.get("ai_mode", "Auto"),
        "p2p":      True,
        "wg_active":True,
        "peers":    d.get("peers", 0),
    }

_nodes_cache = {}
_nodes_lock  = threading.Lock()
_nodes_ts    = 0

def get_nodes(force=False) -> dict:
    global _nodes_cache, _nodes_ts
    with _nodes_lock:
        if not force and time.time() - _nodes_ts < 10:
            return _nodes_cache
    # Параллельный опрос
    results = {}
    threads = []
    def probe(nid, ip):
        results[nid] = probe_node(nid, ip)
    for nid, info in NODES.items():
        t = threading.Thread(target=probe, args=(nid, info["ip"]), daemon=True)
        t.start()
        threads.append(t)
    for t in threads:
        t.join(timeout=4)
    with _nodes_lock:
        _nodes_cache = results
        _nodes_ts    = time.time()
    return results

# ── Log reader ─────────────────────────────────────────────────
def read_logs(n=200) -> list:
    """Читает последние n строк из лога ARGOS. Работает с бинарными файлами."""
    log_candidates = [
        os.path.join(BASE_DIR, "logs", "argos_main.log"),
        os.path.join(BASE_DIR, "argos.log"),
        os.path.join(BASE_DIR, "logs", "argos.log"),
    ]
    log_path = next((p for p in log_candidates if os.path.exists(p)), None)
    if not log_path:
        return [{"level": "WARN", "message": "Лог-файл не найден", "time": ""}]
    try:
        # Read last 50KB to avoid loading huge files
        with open(log_path, "rb") as f:
            f.seek(0, 2)
            size = f.tell()
            f.seek(max(0, size - 50 * 1024))
            raw = f.read()
        text = raw.decode("utf-8", errors="replace")
        raw_lines = text.splitlines()[-n:]
        lines = []
        for line in raw_lines:
            line = line.rstrip()
            if not line or len(line) < 4:
                continue
            # Skip binary garbage
            if line.count('\x00') > 2 or line.count('\ufffd') > 10:
                continue
            lvl = "INFO"
            lu = line.upper()
            for l in ("ERROR", "CRITICAL", "WARNING", "WARN", "DEBUG"):
                if l in lu:
                    lvl = l.replace("WARNING", "WARN").replace("CRITICAL", "ERROR")
                    break
            ts = ""
            if len(line) > 19 and line[4] in ("-", "/"):
                ts = line[:19]
                line = line[20:].strip()
            lines.append({"level": lvl, "message": line[:300], "time": ts})
        return lines or [{"level": "INFO", "message": "Лог пустой", "time": ""}]
    except Exception as e:
        return [{"level": "ERROR", "message": f"Ошибка чтения лога: {e}", "time": ""}]

# ── HTTP Handler ───────────────────────────────────────────────
class Handler(BaseHTTPRequestHandler):

    def log_message(self, fmt, *args):
        pass  # тихий режим

    def _cors(self):
        self.send_header("Access-Control-Allow-Origin",  "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")

    def _json(self, data, code=200):
        body = json.dumps(data, ensure_ascii=False, default=str).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", len(body))
        self._cors()
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):
        self.send_response(204)
        self._cors()
        self.end_headers()

    # ── GET ─────────────────────────────────────────────────────
    def do_GET(self):
        path = urlparse(self.path).path.rstrip("/") or "/"

        # Root
        if path == "/":
            return self._serve_file("unified_dashboard.html")

        # WireGuard Manager
        if path in ("/wg", "/wg_manager", "/wireguard"):
            return self._serve_file("wg_manager.html")

        # Health
        if path == "/health":
            h = argos("/health")
            # enrich with system/status data
            try:
                ss = argos("/system/status", timeout=3)
                h.update({k: v for k, v in ss.items() if k not in h})
            except Exception:
                pass
            return self._json(h)

        # Status
        if path in ("/status", "/brain/status"):
            return self._json(argos("/brain/status"))

        # System status
        if path == "/system/status":
            return self._json(argos("/system/status"))

        # Skills — generate from system_status
        if path == "/skills":
            ss = argos("/system/status")
            return self._json({"skills_count": ss.get("skills_count", 0), "data": ss})

        # Brain nodes — реальный опрос кластера
        if path == "/brain/nodes":
            return self._json(get_nodes())

        # Logs
        if path in ("/api/logs", "/logs"):
            return self._json(read_logs())

        # P2P status (low timeout — brain may be slow)
        if path == "/p2p/status":
            d = argos("/p2p/status", timeout=3)
            if "error" in d:
                # Fallback from /brain/nodes p2p data
                nodes = _nodes_cache or {}
                d = {
                    "p2p_active": any(v.get("p2p") for v in nodes.values()),
                    "nodes_online": sum(1 for v in nodes.values() if v.get("status") == "online"),
                }
            return self._json(d)

        # Local system metrics (psutil)
        if path == "/metrics":
            return self._json(get_local_metrics())

        # ARGOS proxy /api/argos/...
        if path.startswith("/api/argos"):
            sub = path[len("/api/argos"):] or "/health"
            return self._json(argos(sub))

        # Telegram webhook proxy (ngrok → dashboard → ARGOS webhook port)
        if path == "/telegram":
            return self._proxy_raw("http://localhost:8001/telegram", "GET", body=b"")

        # Static file
        self._serve_file(path.lstrip("/"))

    # ── POST ────────────────────────────────────────────────────
    def do_POST(self):
        path   = urlparse(self.path).path
        clen   = int(self.headers.get("Content-Length", 0) or 0)
        body   = self.rfile.read(clen)
        try:
            payload = json.loads(body) if body else {}
        except Exception:
            payload = {}

        # Brain command / terminal
        if path in ("/brain/command", "/command"):
            action = payload.get("action", "")
            cmd    = payload.get("text") or payload.get("command") or payload.get("skill") or payload.get("query") or action
            if not cmd:
                return self._json({"error": "no command"}, 400)
            # Try brain /think endpoint (ArgosCore integration)
            result = argos_post("/think", {"query": cmd}, timeout=20)
            if "error" not in result:
                return self._json({"status": "ok", "response": result.get("response", result)})
            # Fallback: return info about available endpoints
            return self._json({
                "status": "ok",
                "response": f"[Brain] Команда получена: {cmd}\n"
                           f"Brain API: {ARGOS_API}\n"
                           f"ArgosCore: не подключён к brain API\n"
                           f"Для выполнения команд используй MCP инструменты.",
                "source": "dashboard_server",
            })

        # Telegram webhook proxy (POST from Telegram → ARGOS webhook)
        if path == "/telegram":
            return self._proxy_raw("http://localhost:8001/telegram", "POST", body=body)

        # ARGOS proxy POST
        if path.startswith("/api/argos"):
            sub = path[len("/api/argos"):] or "/command"
            return self._json(argos_post(sub, payload))

        self.send_error(404)

    # ── Raw proxy ───────────────────────────────────────────────
    def _proxy_raw(self, url: str, method: str = "POST", body: bytes = b""):
        """Проксирует запрос к указанному URL без JSON-парсинга."""
        try:
            req = urllib.request.Request(url, data=body if body else None, method=method)
            req.add_header("Content-Type", self.headers.get("Content-Type", "application/json"))
            with urllib.request.urlopen(req, timeout=10) as r:
                resp_body = r.read()
                self.send_response(r.status)
                self.send_header("Content-Type", r.headers.get("Content-Type", "application/json"))
                self.send_header("Content-Length", len(resp_body))
                self._cors()
                self.end_headers()
                self.wfile.write(resp_body)
        except Exception as e:
            self._json({"error": str(e)}, 502)

    # ── Static file server ──────────────────────────────────────
    def _serve_file(self, filename: str):
        # Защита от path traversal
        filename = os.path.normpath(filename.replace("..", "")).lstrip("/\\")
        if not filename:
            filename = "unified_dashboard.html"

        filepath = os.path.join(BASE_DIR, filename)
        if not os.path.isfile(filepath):
            self.send_error(404, f"Not found: {filename}")
            return

        ext   = filename.rsplit(".", 1)[-1].lower() if "." in filename else "html"
        ctype = MIME.get(ext, "application/octet-stream")

        with open(filepath, "rb") as f:
            data = f.read()

        # Патчим API URL в HTML: old ports → наш порт
        if ext == "html":
            for old_url in [
                b"http://localhost:5010",
                b"http://localhost:5001",
                b"'http://localhost:5010'",
                b'"http://localhost:5010"',
                b"'http://localhost:5001'",
                b'"http://localhost:5001"',
            ]:
                new_url = old_url.replace(b"5010", b"8081").replace(b"5001", b"8081")
                data = data.replace(old_url, new_url)

        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", len(data))
        self._cors()
        self.end_headers()
        self.wfile.write(data)


# ── Entry point ────────────────────────────────────────────────
if __name__ == "__main__":
    import sys, io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    print("=" * 56)
    print("  ARGOS Unified Dashboard Server")
    print(f"  http://localhost:{PORT}/")
    print("=" * 56)
    print("  Tabs:")
    print(f"    /                           -> LIVE")
    print(f"    /dashboard.html             -> Classic v1")
    print(f"    /dashboard_v3.html          -> Cluster v3")
    print(f"    /argos_brain_dashboard.html -> P2P Nodes")
    print(f"    /argos_free_apis.html       -> Free APIs")
    print(f"  ARGOS proxy -> {ARGOS_API}")
    print("=" * 56)

    # Прогрев кеша нод в фоне
    threading.Thread(target=lambda: get_nodes(force=True), daemon=True).start()

    server = HTTPServer(("0.0.0.0", PORT), Handler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n⏹  Сервер остановлен.")
