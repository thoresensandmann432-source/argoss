"""
src/startup_validator.py — Валидация окружения при запуске ARGOS
================================================================
Проверяет:
  - версию Python (>=3.10)
  - наличие .env и загрузку переменных
  - обязательные Python-пакеты
  - создание нужных директорий
  - предупреждения о безопасности (ARGOS_REMOTE_TOKEN)
"""

from __future__ import annotations

import importlib
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

__all__ = ["StartupValidator", "ValidationReport", "ValidationResult", "_REQUIRED_PACKAGES"]


# ── Обязательные пакеты ───────────────────────────────────────────────────────
_REQUIRED_PACKAGES: list[tuple[str, str]] = [
    ("psutil", "pip install psutil"),
    ("requests", "pip install requests"),
    ("dotenv", "pip install python-dotenv"),
    ("cryptography", "pip install cryptography"),
    ("packaging", "pip install packaging"),
    ("fastapi", "pip install fastapi"),
    ("sklearn", "pip install scikit-learn"),
    ("numpy", "pip install numpy"),
]

# ── Директории, которые должны существовать ───────────────────────────────────
_REQUIRED_DIRS = ["src", "config", "data", "logs", "tests"]


@dataclass
class ValidationResult:
    """Результат одной проверки."""

    level: str  # "ok" | "warn" | "error"
    message: str
    detail: str = ""

    @property
    def is_error(self) -> bool:
        return self.level == "error"

    @property
    def is_warning(self) -> bool:
        return self.level == "warn"


@dataclass
class ValidationReport:
    """Итоговый отчёт по всем проверкам."""

    results: list[ValidationResult] = field(default_factory=list)

    def add(self, level: str, message: str, detail: str = "") -> None:
        self.results.append(ValidationResult(level, message, detail))

    @property
    def ok(self) -> bool:
        return not any(r.is_error for r in self.results)

    @property
    def errors(self) -> list[ValidationResult]:
        return [r for r in self.results if r.is_error]

    @property
    def warnings(self) -> list[ValidationResult]:
        return [r for r in self.results if r.is_warning]

    def print(self) -> None:
        """Выводит отчёт в stdout."""
        print(f"\n{'═' * 55}")
        print("  🔱 ARGOS StartupValidator")
        print(f"{'═' * 55}")
        for r in self.results:
            if r.level == "ok":
                icon = "  ✅"
            elif r.level == "warn":
                icon = "  ⚠️ "
            else:
                icon = "  ❌"
            line = f"{icon}  {r.message}"
            if r.detail:
                line += f" — {r.detail[:60]}"
            print(line)
        status = "PASS" if self.ok else "FAIL"
        print(f"{'═' * 55}")
        print(
            f"  Статус: {status} | Ошибок: {len(self.errors)} | Предупреждений: {len(self.warnings)}"
        )
        print(f"{'═' * 55}\n")


class StartupValidator:
    """
    Валидатор окружения ARGOS.

    Запускается до инициализации ядра и проверяет
    что всё необходимое для работы присутствует.
    """

    def __init__(self, root: str | Path | None = None) -> None:
        self.root = Path(root) if root else Path(".").resolve()
        self._report = ValidationReport()

    def validate(self) -> ValidationReport:
        """Выполняет все проверки и возвращает отчёт."""
        self._report = ValidationReport()
        self._check_python_version()
        self._load_env()
        self._create_dirs()
        self._check_packages()
        self._check_security()
        return self._report

    # ── Проверки ──────────────────────────────────────────────────────────────

    def _check_python_version(self) -> None:
        vi = sys.version_info
        ver = f"{vi.major}.{vi.minor}.{vi.micro}"
        if vi >= (3, 10):
            self._report.add("ok", f"Python {ver} ✓")
        else:
            self._report.add("error", f"Python {ver} — требуется 3.10+", "Обновите Python")

    def _load_env(self) -> None:
        env_path = self.root / ".env"
        if env_path.exists():
            try:
                _load_dotenv(env_path)
                self._report.add("ok", ".env загружен")
            except Exception as e:
                self._report.add("warn", ".env — ошибка загрузки", str(e))
        else:
            self._report.add("warn", ".env не найден", "Скопируй .env.example → .env")

    def _create_dirs(self) -> None:
        for dir_name in _REQUIRED_DIRS:
            dir_path = self.root / dir_name
            dir_path.mkdir(parents=True, exist_ok=True)
        self._report.add("ok", f"Директории созданы ({', '.join(_REQUIRED_DIRS)})")

    def _check_packages(self) -> None:
        for import_name, install_cmd in _REQUIRED_PACKAGES:
            try:
                importlib.import_module(import_name)
                self._report.add("ok", f"Пакет: {import_name}")
            except ImportError:
                self._report.add("error", f"Пакет отсутствует: {import_name}", install_cmd)

    def _check_security(self) -> None:
        token = os.environ.get("ARGOS_REMOTE_TOKEN", "")
        if not token:
            self._report.add(
                "warn",
                "ARGOS_REMOTE_TOKEN не задан",
                "Remote API доступен без авторизации",
            )
        else:
            self._report.add("ok", "ARGOS_REMOTE_TOKEN задан")


# ── Вспомогательные функции ───────────────────────────────────────────────────


def _load_dotenv(path: Path) -> None:
    """Простая загрузка .env без зависимостей от python-dotenv."""
    try:
        from dotenv import load_dotenv

        load_dotenv(str(path), override=False)
        return
    except ImportError:
        pass

    # Fallback — ручной парсинг
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            if key and key not in os.environ:
                os.environ[key] = value
