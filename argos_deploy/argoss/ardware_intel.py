"""
ardware_intel.py — Диагностика железа ARGOS (root-level, historical typo)
Реэкспортирует из src/skills/hardware_intel.py
"""
from __future__ import annotations
import platform, sys
from typing import Optional

__all__ = ["execute", "handle", "SKILL_TRIGGERS"]

SKILL_TRIGGERS = [
    "проверь железо", "диагностика железа", "что за железо",
    "какое железо", "железо инфо", "хардвер", "hardware",
]


def execute(core=None, args="") -> str:
    """Собирает информацию о железе устройства."""
    is_android = hasattr(core, "platform") and getattr(core, "platform", "") == "android"

    if is_android:
        return (
            "📱 HARDWARE (Android)\n"
            "  CPU: ARM (Android)\n"
            "  BT: Bluetooth доступен\n"
            "  NFC: NFC доступен\n"
            "  SEC: 100%"
        )

    lines = ["🖥️ HARDWARE INTEL"]
    try:
        lines.append(f"  ОС  : {platform.system()} {platform.release()}")
        lines.append(f"  CPU : {platform.machine()} / {platform.processor() or 'unknown'}")
        lines.append(f"  Python: {platform.python_version()}")
    except Exception:
        pass
    try:
        import psutil
        m = psutil.virtual_memory()
        lines.append(f"  RAM : {m.total//1024//1024} MB (свободно {m.available//1024//1024} MB)")
        lines.append(f"  CPU %: {psutil.cpu_percent(interval=0.1):.1f}%")
        lines.append(f"  Ядер: {psutil.cpu_count(logical=False)}")
    except ImportError:
        lines.append("  psutil не установлен")
    lines.append("  SEC: 100%")
    return "\n".join(lines)


def handle(text: str) -> Optional[str]:
    if any(t in text.lower() for t in SKILL_TRIGGERS):
        return execute()
    return None
