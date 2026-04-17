#!/usr/bin/env python3
"""
format_py.py — Автоформаттер Python-файлов без внешних зависимостей.

Применяет базовые PEP-8 исправления:
  • Удаляет из pip install (строки и subprocess)
  • Нормализует отступы (tabs → spaces)
  • Убирает trailing whitespace
  • Добавляет перенос строки в конце файла
  • Нормализует импорты (убирает дубли пустых строк)

Использование:
    python3 format_py.py [файл_или_папка] [файл_или_папка] ...
    python3 format_py.py src/ main.py telegram_bot.py

При наличии black — использует его; иначе — встроенный форматтер.
"""
from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

# ── Попытка использовать black ────────────────────────────────────────────────

def _try_black(paths: list[str]) -> bool:
    """Запустить black если доступен. Вернуть True при успехе."""
    try:
        result = subprocess.run(
            [sys.executable, "-m", "black", "--line-length", "100",
             "--target-version", "py310", "--quiet"] + paths,
            capture_output=True, text=True,
        )
        if result.returncode == 0:
            print(f"✅ black отформатировал {len(paths)} файл(ов)")
            return True
        # black не установлен — returncode 1 с "No module named black"
        if "No module named black" in result.stderr:
            return False
        print(result.stderr)
        return True
    except FileNotFoundError:
        return False


# ── Встроенный мини-форматтер ─────────────────────────────────────────────────

_RE_PIP_USER = re.compile(
    r'(pip3?\s+install|python3?\s+-m\s+pip\s+install)\s+--user\b',
    re.IGNORECASE,
)
_RE_PIP_USER_MID = re.compile(r'\s+--user\b')


def _fix_pip_user(line: str) -> str:
    """Удалить из строк pip install."""
    if "--user" not in line:
        return line
    # pip install pkg  →  pip install pkg
    line = _RE_PIP_USER.sub(r'\1', line)
    # pip install pkg  →  pip install pkg
    line = _RE_PIP_USER_MID.sub('', line)
    return line


def _format_content(source: str, filepath: str) -> str:
    """Базовое форматирование без black."""
    lines = source.splitlines(keepends=True)
    result = []

    for line in lines:
        # 1. tabs → 4 пробела
        if '\t' in line:
            indent = len(line) - len(line.lstrip('\t'))
            line = '    ' * indent + line.lstrip('\t')

        # 2. trailing whitespace (кроме переноса строки)
        stripped = line.rstrip('\n\r')
        nl = line[len(stripped):]
        stripped = stripped.rstrip()
        line = stripped + nl

        # 3. Удаляем из pip install
        line = _fix_pip_user(line)

        result.append(line)

    content = ''.join(result)

    # 4. Нормализация: не более 2 пустых строк подряд
    content = re.sub(r'\n{4,}', '\n\n\n', content)

    # 5. Перенос строки в конце файла
    if content and not content.endswith('\n'):
        content += '\n'

    return content


def format_file(path: Path) -> bool:
    """Форматировать один файл. Вернуть True если файл изменился."""
    try:
        original = path.read_text(encoding="utf-8", errors="replace")
        formatted = _format_content(original, str(path))
        if formatted != original:
            path.write_text(formatted, encoding="utf-8")
            return True
        return False
    except Exception as exc:
        print(f"  ⚠️  Ошибка: {path}: {exc}")
        return False


def collect_py_files(targets: list[str]) -> list[Path]:
    """Собрать список .py файлов из аргументов."""
    files = []
    for t in targets:
        p = Path(t)
        if p.is_file() and p.suffix == ".py":
            files.append(p)
        elif p.is_dir():
            for f in sorted(p.rglob("*.py")):
                # Исключаем мусорные папки
                if any(exc in f.parts for exc in (
                    ".git", ".buildozer", "venv", ".venv",
                    "__pycache__", "node_modules",
                )):
                    continue
                files.append(f)
    return files


def main():
    targets = sys.argv[1:] or ["src", "main.py", "telegram_bot.py",
                                 "git_push.py", "build.py", "genesis.py"]
    existing = [t for t in targets if Path(t).exists()]
    if not existing:
        print("⚠️  Файлы/папки не найдены:", targets)
        sys.exit(1)

    # Сначала пробуем black
    if _try_black(existing):
        # Дополнительно чистим в .yml и .sh
        _fix_non_python(Path("."))
        return

    # Fallback: встроенный форматтер
    print("⚠️  black не найден, использую встроенный форматтер")
    files = collect_py_files(existing)
    changed = sum(1 for f in files if format_file(f))
    print(f"✅ Встроенный форматтер: {changed}/{len(files)} файлов изменено")
    _fix_non_python(Path("."))


def _fix_non_python(root: Path):
    """Удалить из .yml, .sh, .bat файлов."""
    count = 0
    patterns = ["*.yml", "*.yaml", "*.sh", "*.bat"]
    for pattern in patterns:
        for f in root.rglob(pattern):
            if any(exc in f.parts for exc in (".git", ".buildozer", "venv")):
                continue
            try:
                original = f.read_text(encoding="utf-8", errors="replace")
                fixed = _RE_PIP_USER.sub(r'\1', original)
                fixed = re.sub(r'(pip3?\s+install[^\n]*)\s+--user\b', r'\1', fixed)
                if fixed != original:
                    f.write_text(fixed, encoding="utf-8")
                    count += 1
            except Exception:
                pass
    if count:
        print(f"✅ удалён из {count} не-Python файлов")


if __name__ == "__main__":
    main()
