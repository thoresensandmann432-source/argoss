"""
pip_manager_ext.py — Расширенный Pip Manager для ARGOS

Управление пакетами Python через программный интерфейс.

Использование:
    from src.pip_manager_ext import PipManager
    
    pm = PipManager()
    pm.install("requests")
    pm.uninstall("old_package")
    pm.list_outdated()
"""

import subprocess
import sys
import json
import re
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass
from pathlib import Path

from src.argos_logger import get_logger

log = get_logger("argos.pip")


@dataclass
class PackageInfo:
    """Информация о пакете."""
    name: str
    version: str
    latest: Optional[str] = None
    summary: Optional[str] = None
    installed: bool = True


class PipManager:
    """
    Менеджер пакетов Python для ARGOS.
    
    Безопасная обёртка над pip с проверками и логированием.
    """
    
    def __init__(self, python_path: Optional[str] = None):
        """
        Инициализация менеджера.
        
        Args:
            python_path: Путь к Python (по умолчанию sys.executable)
        """
        self.python_path = python_path or sys.executable
        self._pip_cmd = [self.python_path, "-m", "pip"]
    
    def _run_command(self, args: List[str], timeout: int = 60) -> Tuple[int, str, str]:
        """
        Выполнение команды pip.
        
        Returns:
            (returncode, stdout, stderr)
        """
        cmd = self._pip_cmd + args
        log.debug(f"pip: {' '.join(cmd)}")
        
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout,
                encoding='utf-8',
                errors='replace'
            )
            return result.returncode, result.stdout, result.stderr
        except subprocess.TimeoutExpired:
            log.error(f"pip timeout after {timeout}s")
            return -1, "", f"timeout after {timeout}s"
        except Exception as e:
            log.error(f"pip error: {e}")
            return -1, "", str(e)
    
    def install(self, package: str, version: Optional[str] = None, 
                upgrade: bool = False, user: bool = False) -> bool:
        """
        Установка пакета.
        
        Args:
            package: Имя пакета
            version: Версия (опционально)
            upgrade: Обновить если уже установлен
            user: Установить в user-site
            
        Returns:
            True если успешно
        """
        pkg_spec = f"{package}=={version}" if version else package
        
        args = ["install"]
        if upgrade:
            args.append("--upgrade")
        if user:
            args.append("--user")
        args.append(pkg_spec)
        
        log.info(f"Installing {pkg_spec}...")
        code, stdout, stderr = self._run_command(args)
        
        if code == 0:
            log.info(f"✅ {pkg_spec} installed successfully")
            return True
        else:
            log.error(f"❌ Failed to install {pkg_spec}: {stderr[:200]}")
            return False
    
    def uninstall(self, package: str, auto_confirm: bool = True) -> bool:
        """
        Удаление пакета.
        
        Args:
            package: Имя пакета
            auto_confirm: Автоматически подтверждать удаление
            
        Returns:
            True если успешно
        """
        args = ["uninstall"]
        if auto_confirm:
            args.append("-y")
        args.append(package)
        
        log.info(f"Uninstalling {package}...")
        code, stdout, stderr = self._run_command(args)
        
        if code == 0:
            log.info(f"✅ {package} uninstalled")
            return True
        else:
            log.error(f"❌ Failed to uninstall {package}: {stderr[:200]}")
            return False
    
    def list_installed(self) -> List[PackageInfo]:
        """
        Список установленных пакетов.
        
        Returns:
            Список PackageInfo
        """
        code, stdout, _ = self._run_command(["list", "--format=json"])
        
        if code != 0:
            return []
        
        try:
            data = json.loads(stdout)
            return [
                PackageInfo(
                    name=item["name"],
                    version=item["version"],
                    installed=True
                )
                for item in data
            ]
        except json.JSONDecodeError:
            log.error("Failed to parse pip list output")
            return []
    
    def list_outdated(self) -> List[PackageInfo]:
        """
        Список устаревших пакетов.
        
        Returns:
            Список PackageInfo с latest версией
        """
        code, stdout, _ = self._run_command(
            ["list", "--outdated", "--format=json"]
        )
        
        if code != 0:
            return []
        
        try:
            data = json.loads(stdout)
            return [
                PackageInfo(
                    name=item["name"],
                    version=item["version"],
                    latest=item.get("latest_version"),
                    installed=True
                )
                for item in data
            ]
        except json.JSONDecodeError:
            log.error("Failed to parse pip outdated output")
            return []
    
    def search(self, query: str) -> List[Dict]:
        """
        Поиск пакетов (устарело в pip 21+).
        
        Использует PyPI JSON API.
        
        Args:
            query: Поисковый запрос
            
        Returns:
            Результаты поиска
        """
        import urllib.request
        import urllib.parse
        
        try:
            url = f"https://pypi.org/pypi/{query}/json"
            with urllib.request.urlopen(url, timeout=10) as resp:
                data = json.loads(resp.read())
                return [{
                    "name": data["info"]["name"],
                    "version": data["info"]["version"],
                    "summary": data["info"]["summary"],
                    "url": data["info"]["package_url"]
                }]
        except urllib.error.HTTPError as e:
            if e.code == 404:
                log.warning(f"Package {query} not found on PyPI")
            return []
        except Exception as e:
            log.error(f"Search failed: {e}")
            return []
    
    def show(self, package: str) -> Optional[Dict]:
        """
        Информация о пакете.
        
        Args:
            package: Имя пакета
            
        Returns:
            Словарь с информацией или None
        """
        code, stdout, _ = self._run_command(["show", package])
        
        if code != 0:
            return None
        
        info = {}
        for line in stdout.strip().split("\n"):
            if ":" in line:
                key, value = line.split(":", 1)
                info[key.strip().lower().replace("-", "_")] = value.strip()
        
        return info
    
    def is_installed(self, package: str) -> bool:
        """Проверка установлен ли пакет."""
        return self.show(package) is not None
    
    def get_version(self, package: str) -> Optional[str]:
        """Получить версию установленного пакета."""
        info = self.show(package)
        return info.get("version") if info else None
    
    def requirements_save(self, path: str = "requirements.txt"):
        """Сохранить зависимости в файл."""
        code, stdout, _ = self._run_command(["freeze"])
        
        if code == 0:
            with open(path, 'w', encoding='utf-8') as f:
                f.write(stdout)
            log.info(f"✅ Requirements saved to {path}")
            return True
        return False
    
    def requirements_load(self, path: str = "requirements.txt", upgrade: bool = False) -> bool:
        """Установить пакеты из requirements.txt."""
        if not Path(path).exists():
            log.error(f"❌ File not found: {path}")
            return False
        
        args = ["install", "-r", path]
        if upgrade:
            args.append("--upgrade")
        
        log.info(f"Installing from {path}...")
        code, stdout, stderr = self._run_command(args, timeout=300)
        
        if code == 0:
            log.info(f"✅ Requirements from {path} installed")
            return True
        else:
            log.error(f"❌ Failed: {stderr[:200]}")
            return False
    
    def check_argos_dependencies(self) -> Dict[str, bool]:
        """
        Проверка зависимостей ARGOS.
        
        Returns:
            Словарь {пакет: установлен}
        """
        critical = [
            "requests", "customtkinter", "ollama", "python-dotenv",
            "cryptography", "pynput", "pillow", "numpy"
        ]
        
        optional = [
            "kivy", "torch", "transformers", "sentence-transformers",
            "beautifulsoup4", "pymongo", "psycopg2-binary"
        ]
        
        result = {
            "critical": {},
            "optional": {}
        }
        
        for pkg in critical:
            result["critical"][pkg] = self.is_installed(pkg)
        
        for pkg in optional:
            result["optional"][pkg] = self.is_installed(pkg)
        
        return result


# ══════════════════════════════════════════════════════════════════════════════
# Интеграция с ARGOS Core
# ══════════════════════════════════════════════════════════════════════════════

class PipSkillAdapter:
    """Адаптер для работы как навык ARGOS."""
    
    def __init__(self, core=None):
        self.core = core
        self._manager = PipManager()
    
    def handle(self, text: str, core=None) -> Optional[str]:
        """Обработчик команд pip."""
        t = text.lower()
        
        # Установка
        if any(x in t for x in ["установи пакет", "pip install", "pip install"]):
            match = re.search(r"(?:установи|install)\s+(?:пакет\s+)?(\S+)", t)
            if match:
                pkg = match.group(1)
                success = self._manager.install(pkg)
                return f"{'✅' if success else '❌'} {pkg}"
        
        # Обновление
        if "обнови пакет" in t or "pip upgrade" in t:
            match = re.search(r"(?:обнови|upgrade)\s+(?:пакет\s+)?(\S+)", t)
            if match:
                pkg = match.group(1)
                success = self._manager.install(pkg, upgrade=True)
                return f"{'✅' if success else '❌'} {pkg} updated"
        
        # Список устаревших
        if "устаревшие пакеты" in t or "pip outdated" in t:
            outdated = self._manager.list_outdated()
            if outdated:
                lines = [f"📦 {p.name}: {p.version} → {p.latest}" for p in outdated[:10]]
                return "\n".join(lines)
            return "✅ Все пакеты актуальны"
        
        # Проверка зависимостей
        if "проверь зависимости" in t or "check dependencies" in t:
            deps = self._manager.check_argos_dependencies()
            
            lines = ["📦 Зависимости ARGOS:"]
            
            missing_critical = [p for p, ok in deps["critical"].items() if not ok]
            if missing_critical:
                lines.append(f"❌ Критические: {', '.join(missing_critical)}")
            else:
                lines.append("✅ Все критические зависимости установлены")
            
            missing_optional = [p for p, ok in deps["optional"].items() if not ok]
            if missing_optional:
                lines.append(f"⚠️ Опциональные: {', '.join(missing_optional)}")
            
            return "\n".join(lines)
        
        return None
    
    @property
    def name(self) -> str:
        return "pip_manager"
    
    @property
    def version(self) -> str:
        return "2.0.0"


# ══════════════════════════════════════════════════════════════════════════════
# CLI
# ══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="ARGOS Pip Manager")
    parser.add_argument("command", choices=["install", "uninstall", "list", "outdated", "check"])
    parser.add_argument("package", nargs="?", help="Package name")
    parser.add_argument("--upgrade", action="store_true", help="Upgrade if installed")
    
    args = parser.parse_args()
    
    pm = PipManager()
    
    if args.command == "install":
        if not args.package:
            print("❌ Укажите пакет: python pip_manager_ext.py install requests")
            sys.exit(1)
        success = pm.install(args.package, upgrade=args.upgrade)
        sys.exit(0 if success else 1)
    
    elif args.command == "uninstall":
        if not args.package:
            print("❌ Укажите пакет")
            sys.exit(1)
        success = pm.uninstall(args.package)
        sys.exit(0 if success else 1)
    
    elif args.command == "list":
        packages = pm.list_installed()
        for pkg in packages:
            print(f"{pkg.name}=={pkg.version}")
    
    elif args.command == "outdated":
        packages = pm.list_outdated()
        for pkg in packages:
            print(f"{pkg.name}: {pkg.version} → {pkg.latest}")
    
    elif args.command == "check":
        deps = pm.check_argos_dependencies()
        
        print("Критические зависимости:")
        for pkg, ok in deps["critical"].items():
            status = "✅" if ok else "❌"
            print(f"  {status} {pkg}")
        
        print("\nОпциональные зависимости:")
        for pkg, ok in deps["optional"].items():
            status = "✅" if ok else "⚠️"
            print(f"  {status} {pkg}")
