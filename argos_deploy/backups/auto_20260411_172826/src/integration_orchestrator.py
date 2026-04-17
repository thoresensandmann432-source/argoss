from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
TON_REPO = ROOT / "integrations" / "ton-wallet-generation"
TON_REPO_URL = "https://github.com/flaming-chameleon/ton-wallet-generation.git"


def _run(cmd: list[str], cwd: Path | None = None, timeout: int = 180) -> tuple[bool, str]:
    try:
        p = subprocess.run(
            cmd,
            cwd=str(cwd) if cwd else None,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        if p.returncode == 0:
            return True, (p.stdout or "").strip()
        err = (p.stderr or p.stdout or "").strip()
        return False, err[:500]
    except Exception as e:
        return False, str(e)


def run_full_integration() -> str:
    lines: list[str] = ["🔧 Полная интеграция: старт"]

    # 1) TON repo + deps
    try:
        TON_REPO.parent.mkdir(parents=True, exist_ok=True)
        if TON_REPO.exists():
            ok, out = _run(["git", "pull"], cwd=TON_REPO, timeout=120)
            lines.append("✅ TON repo обновлен" if ok else f"⚠️ TON pull: {out}")
        else:
            ok, out = _run(["git", "clone", TON_REPO_URL, str(TON_REPO)], timeout=120)
            lines.append("✅ TON repo клонирован" if ok else f"⚠️ TON clone: {out}")
    except Exception as e:
        lines.append(f"⚠️ TON repo: {e}")

    req = TON_REPO / "requirements.txt"
    if req.exists():
        ok, out = _run([sys.executable, "-m", "pip", "install", "-r", str(req)], timeout=240)
        lines.append("✅ TON зависимости установлены" if ok else f"⚠️ TON pip: {out}")

    # 2) base deps for providers
    ok, out = _run([sys.executable, "-m", "pip", "install", "openai", "python-dotenv"], timeout=180)
    lines.append("✅ OpenAI SDK зависимости установлены" if ok else f"⚠️ openai pip: {out}")

    # 3) quick checks
    docker_ok, _ = _run(["docker", "--version"], timeout=20)
    lines.append("✅ Docker доступен" if docker_ok else "⚠️ Docker не найден в PATH")

    # 4) env hints
    env_path = ROOT / ".env"
    if env_path.exists():
        txt = env_path.read_text(encoding="utf-8", errors="ignore")
        def has(name: str) -> bool:
            return f"{name}=" in txt
        hints = []
        for k in ("OPENAI_API_KEY", "XAI_API_KEY", "GROK_API_KEY", "HF_TOKEN", "TELEGRAM_BOT_TOKEN"):
            hints.append(f"{k}:{'ok' if has(k) else 'missing'}")
        lines.append("🔐 ENV: " + "  ".join(hints))
    else:
        lines.append("⚠️ .env не найден")

    lines.append("✅ Полная интеграция: завершена")
    return "\n".join(lines)
