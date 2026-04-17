#!/usr/bin/env python3
"""status_report.py — Отчёт о статусе ARGOS"""
from __future__ import annotations
import argparse, json, os, sys, time
from pathlib import Path

def build_report() -> dict:
    report = {
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "version": "2.2.0",
        "python": sys.version.split()[0],
        "platform": sys.platform,
        "checks": [],
    }
    # Check key files
    for f in ["main.py","requirements.txt","src/core.py"]:
        report["checks"].append({"name": f, "ok": Path(f).exists()})
    # Modules
    for mod in ["psutil","requests","fastapi"]:
        try: __import__(mod); report["checks"].append({"name": mod, "ok": True})
        except ImportError: report["checks"].append({"name": mod, "ok": False})
    return report

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--md",  action="store_true")
    parser.add_argument("--json",action="store_true")
    parser.add_argument("--out", default="")
    args = parser.parse_args()

    r = build_report()
    ok_count = sum(1 for c in r["checks"] if c["ok"])
    total    = len(r["checks"])

    if args.json:
        out = json.dumps(r, indent=2, ensure_ascii=False)
    else:
        lines = [
            f"# 🔱 ARGOS Status Report",
            f"**Time:** {r['timestamp']}  |  **Version:** {r['version']}",
            "",
            f"Checks: {ok_count}/{total}",
        ]
        for c in r["checks"]:
            icon = "✅" if c["ok"] else "❌"
            lines.append(f"  {icon} {c['name']}")
        out = "\n".join(lines)

    if args.out:
        Path(args.out).write_text(out, encoding="utf-8")
        print(f"Report saved: {args.out}")
    else:
        print(out)

    sys.exit(0 if ok_count == total else 1)

if __name__ == "__main__":
    main()
