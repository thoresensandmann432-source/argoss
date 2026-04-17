"""
autonomy_fileops.py — автономный агент + анализ/мониторинг файлов.
"""

from __future__ import annotations

SKILL_DESCRIPTION = "Автономный агент мониторинга и операций с файлами"

import json
import os
import threading
import time
from collections import Counter
from pathlib import Path
from typing import Optional


EVENTS_FILE = Path("data/file_monitor_events.json")
EVENTS_FILE.parent.mkdir(parents=True, exist_ok=True)


class _FileMonitor:
    def __init__(self):
        self._running = False
        self._thread: threading.Thread | None = None
        self._root = Path(".")
        self._interval = 8
        self._state: dict[str, tuple[int, float]] = {}
        self._events: list[dict] = []

    def _snapshot(self, root: Path) -> dict[str, tuple[int, float]]:
        snap: dict[str, tuple[int, float]] = {}
        for p in root.rglob("*"):
            if not p.is_file():
                continue
            try:
                st = p.stat()
                snap[str(p.resolve())] = (int(st.st_size), float(st.st_mtime))
            except Exception:
                continue
        return snap

    def _loop(self):
        while self._running:
            now = time.time()
            cur = self._snapshot(self._root)
            for path, meta in cur.items():
                if path not in self._state:
                    self._events.append({"ts": now, "type": "created", "path": path})
                elif self._state[path] != meta:
                    self._events.append({"ts": now, "type": "modified", "path": path})
            for path in list(self._state.keys()):
                if path not in cur:
                    self._events.append({"ts": now, "type": "deleted", "path": path})
            self._state = cur
            self._events = self._events[-500:]
            try:
                EVENTS_FILE.write_text(json.dumps(self._events, ensure_ascii=False, indent=2), encoding="utf-8")
            except Exception:
                pass
            time.sleep(self._interval)

    def start(self, root: str, interval: int = 8) -> str:
        if self._running:
            return "⚠️ Файл-монитор уже запущен"
        self._root = Path(root or ".").resolve()
        if not self._root.exists():
            return f"❌ Путь не найден: {self._root}"
        self._interval = max(3, min(int(interval), 120))
        self._state = self._snapshot(self._root)
        self._running = True
        self._thread = threading.Thread(target=self._loop, name="argos-file-monitor", daemon=True)
        self._thread.start()
        return f"✅ Файл-монитор запущен: {self._root} (интервал {self._interval}s)"

    def stop(self) -> str:
        if not self._running:
            return "⚠️ Файл-монитор уже остановлен"
        self._running = False
        return "⏹ Файл-монитор остановлен"

    def status(self) -> str:
        return (
            f"📂 FileMonitor: {'🟢 ON' if self._running else '🔴 OFF'}\n"
            f"  root: {self._root}\n"
            f"  interval: {self._interval}s\n"
            f"  events: {len(self._events)}"
        )


_MON = _FileMonitor()


class AutonomyFileOps:
    def __init__(self, core=None):
        self.core = core

    def _agent_toggle(self, on: bool) -> str:
        if not self.core:
            return "❌ core недоступен"
        setattr(self.core, "_agent_enabled", bool(on))
        return "🤖 Автоагент включен" if on else "🛑 Автоагент выключен"

    def _agent_status(self) -> str:
        if not self.core:
            return "❌ core недоступен"
        enabled = bool(getattr(self.core, "_agent_enabled", False))
        q_status = ""
        tq = getattr(self.core, "task_queue", None)
        if tq and hasattr(tq, "status"):
            try:
                q_status = "\n" + tq.status()
            except Exception:
                q_status = ""
        return f"🤖 Автоагент: {'ON' if enabled else 'OFF'}{q_status}"

    def _analyze_files(self, root: str = ".", limit: int = 6) -> str:
        p = Path(root or ".").resolve()
        if not p.exists():
            return f"❌ Путь не найден: {p}"
        files = []
        for f in p.rglob("*"):
            if f.is_file():
                try:
                    st = f.stat()
                    files.append((f, st.st_size))
                except Exception:
                    continue
        if not files:
            return f"📂 Файлы не найдены: {p}"
        total = sum(sz for _, sz in files)
        ext = Counter((f.suffix.lower() or "<noext>") for f, _ in files)
        top = sorted(files, key=lambda x: x[1], reverse=True)[: max(1, limit)]
        lines = [
            f"📊 Анализ файлов: {p}",
            f"  файлов: {len(files)}",
            f"  размер: {total/1024/1024:.1f} MB",
            "  топ расширений: " + ", ".join(f"{k}:{v}" for k, v in ext.most_common(6)),
            "  большие файлы:",
        ]
        for f, sz in top:
            lines.append(f"   - {f} ({sz/1024/1024:.2f} MB)")
        return "\n".join(lines)

    def handle_command(self, text: str) -> Optional[str]:
        t = (text or "").lower().strip()
        if t in ("автоагент вкл", "агент авто вкл", "agent auto on"):
            return self._agent_toggle(True)
        if t in ("автоагент выкл", "агент авто выкл", "agent auto off"):
            return self._agent_toggle(False)
        if t in ("автоагент статус", "agent auto status"):
            return self._agent_status()

        if t.startswith("анализ файлов"):
            path = text.split("анализ файлов", 1)[-1].strip() if "анализ файлов" in t else ""
            return self._analyze_files(path or ".")

        if t.startswith("файлмонитор старт") or t.startswith("file monitor start"):
            tail = text.split(" ", 2)
            path = tail[2].strip() if len(tail) >= 3 else "."
            return _MON.start(path)
        if t in ("файлмонитор стоп", "file monitor stop"):
            return _MON.stop()
        if t in ("файлмонитор статус", "file monitor status"):
            return _MON.status()
        return None


def handle(text: str, core=None) -> Optional[str]:
    lt = (text or "").lower()
    triggers = (
        "автоагент", "agent auto",
        "анализ файлов", "файлмонитор", "file monitor",
    )
    if not any(k in lt for k in triggers):
        return None
    return AutonomyFileOps(core=core).handle_command(text)

