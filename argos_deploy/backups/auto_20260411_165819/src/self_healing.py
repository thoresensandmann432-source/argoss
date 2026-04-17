"""
src/self_healing.py — Движок автоисправления Python-кода ARGOS
==============================================================
Обнаруживает и исправляет типичные ошибки файлов:
  - BOM-метка UTF-8 (\ufeff)
  - Смешанные отступы (tabs vs spaces)
  - Управляющие символы
При наличии ядра — сложные исправления через LLM с backup и hot-reload.
"""

from __future__ import annotations

import ast
import importlib
import importlib.util
import os
import re
import shutil
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

__all__ = ["SelfHealingEngine", "_path_to_module"]

_BACKUP_DIR = "data/.self_healing_backups"
_MAX_HISTORY = 50


def _path_to_module(path: str | Path) -> Optional[str]:
    """Конвертирует путь к файлу в имя модуля Python или None."""
    p = Path(path)
    if p.suffix != ".py":
        return None
    parts = p.with_suffix("").parts
    return ".".join(parts)


@dataclass
class _HealRecord:
    timestamp: float
    file: str
    error: str
    method: str
    success: bool


class SelfHealingEngine:
    """
    Движок автоисправления Python-кода.

    Умеет:
    - Валидировать синтаксис через ast.parse (без выполнения)
    - Применять локальные патчи (BOM, tabs, управляющие символы)
    - Запрашивать LLM-исправление через ядро
    - Создавать резервные копии и восстанавливать их
    - Горячо перезагружать модули после исправления
    """

    def __init__(self, core=None) -> None:
        self._core = core
        self._history: list[_HealRecord] = []
        self._healed_count = 0
        self._failed_count = 0

    # ── Валидация ─────────────────────────────────────────────────────────────

    def validate_code(self, code: str) -> tuple[bool, str]:
        """Проверяет синтаксис кода. Возвращает (ok, сообщение)."""
        if not code.strip():
            return True, "OK (пусто)"
        try:
            ast.parse(code)
            return True, "✅ Синтаксис OK"
        except SyntaxError as e:
            return False, f"SyntaxError: {e.msg} (строка {e.lineno})"
        except Exception as e:
            return False, f"Ошибка: {e}"

    def validate_file(self, path: str | Path) -> tuple[bool, str]:
        """Проверяет синтаксис файла. Возвращает (ok, сообщение)."""
        p = Path(path)
        if not p.exists():
            return False, f"❌ Файл не найден: {path}"
        try:
            src = p.read_text(encoding="utf-8", errors="replace")
            return self.validate_code(src)
        except Exception as e:
            return False, f"❌ Ошибка чтения: {e}"

    def validate_all_src(self, src_dir: str | Path = "src") -> str:
        """Проверяет все .py файлы в директории. Возвращает отчёт."""
        src_path = Path(src_dir)
        if not src_path.exists():
            return f"❌ Директория не найдена: {src_dir}"

        ok_count = 0
        err_count = 0
        errors: list[str] = []

        for py_file in sorted(src_path.rglob("*.py")):
            is_ok, msg = self.validate_file(py_file)
            if is_ok:
                ok_count += 1
            else:
                err_count += 1
                errors.append(f"  {py_file}: {msg}")

        report = [f"📊 Валидация {src_dir}/: {ok_count} ✅  {err_count} ❌"]
        report.extend(errors[:10])
        if len(errors) > 10:
            report.append(f"  ... и ещё {len(errors) - 10}")
        return "\n".join(report)

    # ── Резервное копирование ─────────────────────────────────────────────────

    def backup_file(self, path: str | Path) -> Optional[str]:
        """Создаёт резервную копию файла. Возвращает путь или None."""
        p = Path(path)
        if not p.exists():
            return None
        try:
            backup_dir = Path(_BACKUP_DIR)
            backup_dir.mkdir(parents=True, exist_ok=True)
            stamp = int(time.time() * 1000)
            backup_path = backup_dir / f"{p.name}.{stamp}.bak"
            shutil.copy2(p, backup_path)
            return str(backup_path)
        except Exception:
            return None

    def restore_file(self, path: str | Path, backup: str | Path) -> bool:
        """Восстанавливает файл из резервной копии."""
        try:
            shutil.copy2(backup, path)
            return True
        except Exception:
            return False

    # ── Автоисправление ───────────────────────────────────────────────────────

    def _local_fix(self, code: str, error_msg: str) -> Optional[str]:
        """Применяет локальные патчи без LLM. Возвращает исправленный код или None."""
        changed = False

        # 1. Удаляем BOM
        if code.startswith("\ufeff"):
            code = code[1:]
            changed = True

        # 2. Исправляем смешанные отступы (tabs → 4 пробела)
        if "tab" in error_msg.lower() or "\t" in code:
            new_lines = []
            for line in code.splitlines(keepends=True):
                if line.startswith("\t"):
                    line = line.expandtabs(4)
                    changed = True
                new_lines.append(line)
            code = "".join(new_lines)

        # 3. Убираем Windows CRLF → LF
        if "\r\n" in code:
            code = code.replace("\r\n", "\n")
            changed = True

        # 4. Убираем управляющие символы (кроме \n \t)
        cleaned = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", code)
        if cleaned != code:
            code = cleaned
            changed = True

        return code if changed else None

    def heal_code(self, code: str, error_msg: str) -> Optional[str]:
        """Пытается исправить код через LLM-ядро. Возвращает исправленный код или None."""
        if not self._core:
            return None
        try:
            ask = getattr(self._core, "_ask_gemini", None) or getattr(
                self._core, "_ask_ollama", None
            )
            if not ask:
                return None
            prompt = (
                f"Исправь следующий Python-код. Ошибка: {error_msg}\n\n"
                f"```python\n{code[:3000]}\n```\n\n"
                f"Верни ТОЛЬКО исправленный код без объяснений."
            )
            result = ask("Ты Python-эксперт.", prompt)
            if result:
                cleaned = re.sub(
                    r"^```python\n?|^```\n?|```$", "", result, flags=re.MULTILINE
                ).strip()
                ok, _ = self.validate_code(cleaned)
                if ok:
                    return cleaned
        except Exception:
            pass
        return None

    def auto_heal_file(self, path: str | Path, error_msg: str = "") -> str:
        """
        Полный цикл автоисправления файла:
        backup → local fix → LLM fix → validate → hot-reload.
        """
        p = Path(path)
        if not p.exists():
            return f"❌ Файл не найден: {path}"

        # Резервная копия
        backup = self.backup_file(p)
        if not backup:
            return f"❌ Не удалось создать резервную копию: {path}"

        try:
            code = p.read_text(encoding="utf-8", errors="replace")
        except Exception as e:
            return f"❌ Ошибка чтения: {e}"

        # Попытка 1: локальный патч
        fixed = self._local_fix(code, error_msg)
        method = "local"

        # Попытка 2: LLM если локальный патч не помог
        if fixed is None or not self.validate_code(fixed)[0]:
            lm_fixed = self.heal_code(code, error_msg)
            if lm_fixed:
                fixed = lm_fixed
                method = "llm"

        if fixed is None:
            self._failed_count += 1
            self._history.append(
                _HealRecord(
                    timestamp=time.time(),
                    file=str(p),
                    error=error_msg,
                    method="none",
                    success=False,
                )
            )
            if len(self._history) > _MAX_HISTORY:
                self._history = self._history[-_MAX_HISTORY:]
            return f"⚠️ Не удалось исправить автоматически: {path}"

        # Валидируем результат
        ok, msg = self.validate_code(fixed)
        if not ok:
            self.restore_file(p, backup)
            self._failed_count += 1
            self._history.append(
                _HealRecord(
                    timestamp=time.time(),
                    file=str(p),
                    error=error_msg,
                    method=method,
                    success=False,
                )
            )
            if len(self._history) > _MAX_HISTORY:
                self._history = self._history[-_MAX_HISTORY:]
            return f"❌ Исправление не прошло валидацию: {msg}"

        # Сохраняем
        try:
            p.write_text(fixed, encoding="utf-8")
        except Exception as e:
            self.restore_file(p, backup)
            return f"❌ Ошибка записи: {e}"

        # Hot-reload
        self._try_hot_reload(p)

        self._healed_count += 1
        self._history.append(
            _HealRecord(
                timestamp=time.time(),
                file=str(p),
                error=error_msg,
                method=method,
                success=True,
            )
        )
        if len(self._history) > _MAX_HISTORY:
            self._history = self._history[-_MAX_HISTORY:]

        return f"✅ Исправлен ({method}): {p.name}"

    def _try_hot_reload(self, path: Path) -> None:
        """Горячо перезагружает модуль если он уже импортирован."""
        mod_name = _path_to_module(path)
        if mod_name and mod_name in sys.modules:
            try:
                importlib.reload(sys.modules[mod_name])
            except Exception:
                pass

    # ── Отчёты ────────────────────────────────────────────────────────────────

    def history(self) -> str:
        """Возвращает историю исправлений."""
        if not self._history:
            return "📭 История исправлений пуста."
        lines = [f"📋 История Self-Healing ({len(self._history)} записей):"]
        for r in reversed(self._history[-10:]):
            icon = "✅" if r.success else "❌"
            ts = time.strftime("%H:%M:%S", time.localtime(r.timestamp))
            lines.append(f"  {icon} {ts} | {Path(r.file).name} | {r.method}")
        return "\n".join(lines)

    def status(self) -> str:
        """Возвращает статус движка."""
        return (
            f"🔧 Self-Healing Engine\n"
            f"  Успешно: {self._healed_count}\n"
            f"  Неудачно: {self._failed_count}\n"
            f"  Резервные копии: {_BACKUP_DIR}\n"
            f"  Ядро: {'подключено' if self._core else 'не подключено'}"
        )
