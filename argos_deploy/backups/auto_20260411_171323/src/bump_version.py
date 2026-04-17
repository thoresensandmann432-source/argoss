#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
bump_version.py — Автоматический бамп версии ARGOS Universal OS
================================================================
Обновляет версию в нескольких файлах одновременно.
Поддерживает: pyproject.toml, README.md, manifest.json, manifest.yaml, build.py

Использование:
    python bump_version.py              # применить изменения
    python bump_version.py --dry-run    # показать без записи
    python bump_version.py --minor      # minor bump
    python bump_version.py --major      # major bump

Константы OLD/NEW/TARGETS/REMOVE/RENAME используются в тестах.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).parent.resolve()

# ── Текущая и следующая версии (обновляются при каждом запуске) ──────────────
OLD = "2.1.3"
NEW = "2.2.0"

# ── Целевые файлы: (путь, regex-паттерн, шаблон замены) ─────────────────────
TARGETS: list[tuple[str, str, str]] = [
    ("pyproject.toml", r'(version\s*=\s*")[^"]+(")', r"\g<1>{NEW}\g<2>"),
    ("README.md", r"(v)(\d+\.\d+\.\d+)", r"\g<1>{NEW}"),
    ("build.py", r'(version\s*=\s*")[^"]+(")', r"\g<1>{NEW}\g<2>"),
    ("config/manifest.json", r'"version":\s*"[^"]+"', '"version": "{NEW}"'),
    ("config/manifest.yaml", r"version:\s*[\w.]+", "version: {NEW}"),
]

# ── Файлы для удаления (устаревшие) ─────────────────────────────────────────
REMOVE: list[str] = [
    "life_support_patch.py",
    "life_v2_patch.py",
    "consciousness_patch_cell.py",
    "kivy_1gui.py",
    "kivy_ma.py",
]

# ── Файлы для переименования: (старое_имя, новое_имя) ───────────────────────
RENAME: list[tuple[str, str]] = [
    ("ardware_intel.py", "hardware_intel.py"),
    ("ARGOS_EMERGENCY_RESTORE.py", "scripts/ARGOS_EMERGENCY_RESTORE.py"),
]


def _parse_version(version: str) -> tuple[int, int, int]:
    parts = version.split(".")
    if len(parts) != 3:
        raise ValueError(f"Неверный формат версии: {version!r}")
    return int(parts[0]), int(parts[1]), int(parts[2])


def _bump_version(old: str, part: str) -> str:
    major, minor, patch = _parse_version(old)
    if part == "major":
        major, minor, patch = major + 1, 0, 0
    elif part == "minor":
        minor, patch = minor + 1, 0
    else:
        patch += 1
    return f"{major}.{minor}.{patch}"


def _update_file(
    path: Path,
    pattern: str,
    replacement: str,
    old_ver: str,
    new_ver: str,
    dry_run: bool,
) -> bool:
    """Применяет замену версии в файле. Возвращает True если файл изменился."""
    if not path.exists():
        print(f"  ⚠️  {path.name} — не найден, пропускаю")
        return False

    text = path.read_text(encoding="utf-8")

    # Подставляем новую версию в шаблон замены
    repl = replacement.replace("{NEW}", new_ver).replace("{OLD}", old_ver)

    new_text, count = re.subn(pattern, repl, text)

    if count == 0:
        print(f"  ⚠️  {path.name} — паттерн не найден")
        return False

    if new_text == text:
        print(f"  ✓  {path.name} — уже актуален")
        return False

    print(f"  ✅  {path.name}: {old_ver} → {new_ver}  ({count} замен)")
    if not dry_run:
        path.write_text(new_text, encoding="utf-8")
    return True


def bump(dry_run: bool = False, part: str = "patch") -> None:
    """Основная функция — бамп версии во всех целевых файлах."""
    global OLD, NEW

    # Читаем текущую версию из pyproject.toml
    pyproject = ROOT / "pyproject.toml"
    if pyproject.exists():
        text = pyproject.read_text(encoding="utf-8")
        m = re.search(r'version\s*=\s*"([^"]+)"', text)
        if m:
            OLD = m.group(1)

    NEW = _bump_version(OLD, part)

    print(f"\n📦  Текущая версия : {OLD}")
    print(f"🚀  Новая версия   : {NEW}")
    if dry_run:
        print(f"🔍  Режим dry-run  : изменения не записываются\n")
    else:
        print()

    changed = 0
    for rel_path, pattern, repl_tmpl in TARGETS:
        path = ROOT / rel_path
        if _update_file(path, pattern, repl_tmpl, OLD, NEW, dry_run):
            changed += 1

    print(f"\n  Обновлено файлов: {changed}")
    if dry_run:
        print("  (dry-run: файлы не записаны)")


def main() -> None:
    parser = argparse.ArgumentParser(description="Bump ARGOS version")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--major", action="store_true")
    group.add_argument("--minor", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    part = "major" if args.major else "minor" if args.minor else "patch"
    bump(dry_run=args.dry_run, part=part)


if __name__ == "__main__":
    main()
