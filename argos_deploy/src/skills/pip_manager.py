"""
src/skills/pip_manager.py — Менеджер пакетов pip и поиск по PyPI для Аргоса.

Команды:
  pip установи <пакет>           — установить пакет
  pip удали <пакет>             — удалить пакет
  pip обнови <пакет>            — обновить пакет
  pip список                    — список установленных пакетов
  pip поиск <запрос>            — поиск пакетов на PyPI
  pip инфо <пакет>              — информация о пакете на PyPI
  pip проверь                   — проверить устаревшие пакеты
"""

from __future__ import annotations

SKILL_DESCRIPTION = "Управление pip-пакетами и поиск по PyPI"

import subprocess
import json
import sys
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.core import ArgosCore

SKILL_NAME = "pip_manager"
SKILL_TRIGGERS = ["pip установи", "pip удали", "pip обнови", "pip список",
                  "pip поиск", "pip инфо", "pip проверь", "pypi"]


class PipManager:
    """Менеджер пакетов pip с поиском PyPI."""

    PYPI_BASE = "https://pypi.org/pypi"
    PYPI_SEARCH = "https://pypi.org/search/?q={}&format=json"

    def __init__(self, core: "ArgosCore | None" = None):
        self.core = core
        self._pip = [sys.executable, "-m", "pip"]

    # ─── Публичный API ───────────────────────────────────────────────────

    def handle_command(self, text: str) -> str | None:
        t = text.lower().strip()
        if "pip установи " in t:
            pkg = text.split("pip установи ", 1)[-1].strip().split()[0]
            return self.install(pkg)
        if "pip удали " in t:
            pkg = text.split("pip удали ", 1)[-1].strip().split()[0]
            return self.uninstall(pkg)
        if "pip обнови " in t:
            pkg = text.split("pip обнови ", 1)[-1].strip().split()[0]
            return self.upgrade(pkg)
        if "pip список" in t:
            return self.list_installed()
        if "pip поиск " in t:
            query = text.split("pip поиск ", 1)[-1].strip()
            return self.search_pypi(query)
        if "pip инфо " in t:
            pkg = text.split("pip инфо ", 1)[-1].strip().split()[0]
            return self.package_info(pkg)
        if "pip проверь" in t:
            return self.check_outdated()
        return None

    def install(self, package: str) -> str:
        """Установить пакет через pip."""
        try:
            result = subprocess.run(
                self._pip + ["install", "--quiet", package],
                capture_output=True, text=True, timeout=120
            )
            if result.returncode == 0:
                return f"✅ pip: пакет '{package}' успешно установлен."
            err = result.stderr.strip()[-300:] if result.stderr else "неизвестная ошибка"
            return f"❌ pip install {package}: {err}"
        except subprocess.TimeoutExpired:
            return f"⏱️ pip: установка '{package}' превысила таймаут."
        except Exception as e:
            return f"❌ pip install: {e}"

    def uninstall(self, package: str) -> str:
        """Удалить пакет."""
        try:
            result = subprocess.run(
                self._pip + ["uninstall", "-y", package],
                capture_output=True, text=True, timeout=60
            )
            if result.returncode == 0:
                return f"✅ pip: пакет '{package}' удалён."
            return f"❌ pip uninstall {package}: {result.stderr.strip()[-200:]}"
        except Exception as e:
            return f"❌ pip uninstall: {e}"

    def upgrade(self, package: str) -> str:
        """Обновить пакет до последней версии."""
        try:
            result = subprocess.run(
                self._pip + ["install", "--upgrade", "--quiet", package],
                capture_output=True, text=True, timeout=120
            )
            if result.returncode == 0:
                return f"✅ pip: пакет '{package}' обновлён до последней версии."
            return f"❌ pip upgrade {package}: {result.stderr.strip()[-200:]}"
        except Exception as e:
            return f"❌ pip upgrade: {e}"

    def list_installed(self, limit: int = 20) -> str:
        """Список установленных пакетов."""
        try:
            result = subprocess.run(
                self._pip + ["list", "--format=json"],
                capture_output=True, text=True, timeout=30
            )
            packages = json.loads(result.stdout)
            lines = [f"📦 УСТАНОВЛЕННЫЕ ПАКЕТЫ ({len(packages)} шт.):"]
            for p in packages[:limit]:
                lines.append(f"  • {p['name']} v{p['version']}")
            if len(packages) > limit:
                lines.append(f"  ... и ещё {len(packages) - limit} пакетов")
            return "\n".join(lines)
        except Exception as e:
            return f"❌ pip list: {e}"

    def search_pypi(self, query: str, limit: int = 5) -> str:
        """Поиск пакетов на PyPI через JSON API."""
        try:
            import urllib.request
            url = f"https://pypi.org/search/?q={urllib.parse.quote(query)}"
            # PyPI не имеет JSON search API — парсим через requests
            try:
                import requests
                resp = requests.get(
                    f"https://pypi.org/search/?q={query}&format=json",
                    headers={"Accept": "application/json"},
                    timeout=10
                )
                # PyPI отдаёт HTML, ищем через простой scrape
                from bs4 import BeautifulSoup
                soup = BeautifulSoup(resp.text, "html.parser")
                results = soup.select('a[class*="package-snippet"]')
                if not results:
                    results = soup.select(".package-snippet")
                lines = [f"🔍 PyPI поиск: '{query}'"]
                for r in results[:limit]:
                    name_el = r.select_one("span.package-snippet__name")
                    ver_el = r.select_one("span.package-snippet__version")
                    desc_el = r.select_one("p.package-snippet__description")
                    name = name_el.text.strip() if name_el else "?"
                    ver = ver_el.text.strip() if ver_el else ""
                    desc = desc_el.text.strip()[:60] if desc_el else ""
                    lines.append(f"  • {name} {ver} — {desc}")
                if len(lines) == 1:
                    lines.append("  Результаты не найдены. Попробуйте pip инфо <пакет>")
                return "\n".join(lines)
            except ImportError:
                return self._search_pypi_fallback(query, limit)
        except Exception as e:
            return f"❌ PyPI поиск: {e}"

    def _search_pypi_fallback(self, query: str, limit: int) -> str:
        """Fallback поиска через pip search (может не работать в новых версиях)."""
        try:
            result = subprocess.run(
                self._pip + ["index", "versions", query],
                capture_output=True, text=True, timeout=15
            )
            if result.returncode == 0:
                return f"📦 PyPI: {result.stdout.strip()[:300]}"
            return f"🔍 Используйте: pip инфо {query}"
        except Exception:
            return f"🔍 Поиск PyPI: откройте https://pypi.org/search/?q={query}"

    def package_info(self, package: str) -> str:
        """Информация о пакете с PyPI JSON API."""
        try:
            import urllib.request
            import urllib.error
            url = f"{self.PYPI_BASE}/{package}/json"
            req = urllib.request.Request(url, headers={"User-Agent": "ArgosOS/2.1"})
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read())
            info = data.get("info", {})
            name = info.get("name", package)
            version = info.get("version", "?")
            summary = info.get("summary", "Нет описания")
            author = info.get("author", "?")
            home = info.get("home_page") or info.get("project_url") or ""
            license_ = info.get("license", "?")
            requires = ", ".join((info.get("requires_dist") or [])[:5]) or "нет"
            lines = [
                f"📦 {name} v{version}",
                f"  Описание: {summary}",
                f"  Автор: {author}",
                f"  Лицензия: {license_}",
                f"  Зависимости: {requires}",
            ]
            if home:
                lines.append(f"  Сайт: {home}")
            return "\n".join(lines)
        except Exception as e:
            return f"❌ pip инфо {package}: {e}"

    def check_outdated(self) -> str:
        """Проверить устаревшие пакеты."""
        try:
            result = subprocess.run(
                self._pip + ["list", "--outdated", "--format=json"],
                capture_output=True, text=True, timeout=60
            )
            packages = json.loads(result.stdout) if result.stdout.strip() else []
            if not packages:
                return "✅ Все пакеты актуальны."
            lines = [f"⬆️ УСТАРЕВШИЕ ПАКЕТЫ ({len(packages)} шт.):"]
            for p in packages[:15]:
                lines.append(f"  • {p['name']} {p['version']} → {p['latest_version']}")
            if len(packages) > 15:
                lines.append(f"  ... и ещё {len(packages) - 15}")
            lines.append("\nДля обновления: pip обнови <имя_пакета>")
            return "\n".join(lines)
        except Exception as e:
            return f"❌ pip проверь: {e}"

    def run(self) -> str:
        """Краткая справка."""
        return (
            "📦 PIP MANAGER:\n"
            "  pip установи <пакет>  — установить\n"
            "  pip удали <пакет>     — удалить\n"
            "  pip обнови <пакет>    — обновить\n"
            "  pip список            — список установленных\n"
            "  pip поиск <запрос>   — поиск на PyPI\n"
            "  pip инфо <пакет>     — инфо о пакете\n"
            "  pip проверь           — устаревшие пакеты"
        )


def handle(text: str, core=None) -> str | None:
    t = text.lower()
    triggers = ["pip установи", "pip удали", "pip обнови", "pip список",
                "pip поиск", "pip инфо", "pip проверь", "pypi поиск"]
    if not any(kw in t for kw in triggers):
        return None
    return PipManager(core).handle_command(text)
