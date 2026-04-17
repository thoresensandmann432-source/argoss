"""
skill_loader_patch.py — Патч для SkillLoader
Загружает ВСЕ навыки из src/skills/ — и папки-пакеты, и плоские .py файлы.
Положить в src/ рядом со skill_loader.py, либо применить через telegram_bot.

Применение:
  1. Отправить этот файл в Telegram боту как патч
  2. Или запустить: python skill_loader_patch.py
"""

from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path
from src.argos_logger import get_logger

log = get_logger("argos.skill_loader")


# ── Метаданные для flat-файлов которые SkillLoader не знает ──────────────────
_FLAT_SKILL_META = {
    "browser_conduit": {
        "name": "browserconduit",
        "version": "1.0.0",
        "group": "WEB",
        "description": "Управление браузером и внешними AI",
        "triggers": ["браузер", "browser", "открой браузер"],
        "class": "BrowserConduit",
    },
    "firmware_examples": {
        "name": "firmwareexamples",
        "version": "1.0.0",
        "group": "HARDWARE",
        "description": "Примеры прошивок для ESP32/Arduino",
        "triggers": ["прошивка", "firmware", "примеры прошивок"],
        "class": None,
    },
    "hardware_intel": {
        "name": "hardwareintel",
        "version": "1.1.0",
        "group": "SYSTEM",
        "description": "Диагностика железа: CPU, RAM, GPU, диски",
        "triggers": ["проверь железо", "hardware", "железо", "характеристики"],
        "class": "HardwareIntelSkill",
    },
    "huggingface_ai": {
        "name": "huggingfaceai",
        "version": "1.0.0",
        "group": "AI",
        "description": "Интеграция с HuggingFace Inference API",
        "triggers": [
            "huggingface", "hf модель", "hugging face",
            "hf semantic", "semantic search", "scifact",
            "hf index", "hf search", "hf dataset",
            "hf space", "hf sentiment", "hf finance", "hf voiceclone",
            "hf joycaption", "hf datasetgen", "hf echoenv", "hf netgoat",
        ],
        "class": "HuggingFaceAI",
    },
    "net_scanner": {
        "name": "netscanner_flat",
        "version": "1.0.0",
        "group": "NETWORK",
        "description": "Сканирование сети (flat version)",
        "triggers": ["скан порт", "сканировать хост"],
        "class": "NetGhost",
    },
    "network_shadow": {
        "name": "networkshadow",
        "version": "1.0.0",
        "group": "NETWORK",
        "description": "Теневой сетевой мониторинг",
        "triggers": ["сетевой призрак", "network shadow", "тень сети"],
        "class": "NetworkShadow",
    },
    "shodan_scanner": {
        "name": "shodanscanner",
        "version": "1.0.0",
        "group": "SECURITY",
        "description": "Сканирование через Shodan API",
        "triggers": ["shodan", "сканируй shodan", "shodan скан"],
        "class": "ShodanScanner",
    },
    "smart_environments": {
        "name": "smartenvironments",
        "version": "1.0.0",
        "group": "IOT",
        "description": "Управление умными средами (теплица, аквариум и др.)",
        "triggers": ["умная среда", "теплица", "аквариум", "smart env"],
        "class": "SmartEnvironmentManager",
    },
    "tasmota_updater": {
        "name": "tasmotaupdater",
        "version": "1.0.0",
        "group": "IOT",
        "description": "Обновление прошивки Tasmota устройств",
        "triggers": ["обнови тасмота", "tasmota update", "tasmota", "тасмота", "tasmota ", "тасмота "],
        "class": "TasmotaUpdater",
    },
    "web_explorer": {
        "name": "webexplorer",
        "version": "1.0.0",
        "group": "WEB",
        "description": "Поиск в интернете (DuckDuckGo + Wikipedia)",
        "triggers": ["изучи", "найди в интернете", "поиск в сети", "research"],
        "class": "ArgosWebExplorer",
    },
    "system_monitor": {
        "name": "systemmonitor",
        "version": "1.0.0",
        "group": "SYSTEM",
        "description": "Мониторинг CPU/RAM/диска с Telegram-алертами",
        "triggers": ["мониторинг", "системный мониторинг", "порог cpu", "порог памяти", "system monitor"],
        "class": "SystemMonitor",
    },
    "auto_backup": {
        "name": "autobackup",
        "version": "1.0.0",
        "group": "SYSTEM",
        "description": "Автоматическое резервное копирование проекта",
        "triggers": ["бэкап", "backup", "резервная копия", "архивировать"],
        "class": "AutoBackup",
    },
    "iot_watchdog": {
        "name": "iotwatchdog",
        "version": "1.0.0",
        "group": "IOT",
        "description": "Мониторинг IoT устройств с авто-рестартом",
        "triggers": ["watchdog", "добавь в watchdog", "iot мониторинг", "следи за устройством"],
        "class": "IoTWatchdog",
    },
    "ai_coder": {
        "name": "aicoder",
        "version": "1.0.0",
        "group": "AI",
        "description": "Генерация, объяснение и фикс кода через Ollama",
        "triggers": [
            "напиши код", "объясни код", "исправь код", "ai coder", "ai_coder",
            "aicoder", "рефакторинг", "запусти aicoder", "включи aicoder",
            "запусти ai coder", "запусти ai_coder",
        ],
        "class": "AICoder",
    },
    "tg_code_injector": {
        "name": "tgcodeinjector",
        "version": "1.0.0",
        "group": "SYSTEM",
        "description": "Приём кода от админа через Telegram + горячая загрузка",
        "triggers": ["запусти инжектор", "code injector", "tg injector", "инжектор кода"],
        "class": "TGCodeInjector",
    },
    "serp_search": {
        "name": "serpsearch",
        "version": "1.0.0",
        "group": "WEB",
        "description": "Поиск через SerpAPI (Google) или DuckDuckGo",
        "triggers": ["поищи", "найди в google", "serp", "серп", "serpapi", "поиск google"],
        "class": "SerpSearch",
    },
    "web_scrapper": {
        "name": "webscrapper",
        "version": "1.0.0",
        "group": "WEB",
        "description": "Парсинг веб-страниц",
        "triggers": ["парсинг", "web scrapper", "скачай страницу"],
        "class": None,
    },
    "usb_access_point": {
        "name": "usbaccesspoint",
        "version": "1.0.0",
        "group": "NETWORK",
        "description": "USB-гаджет + WiFi AP + веб-морда ARGOS",
        "triggers": ["запусти точку доступа", "usb гаджет", "веб морда", "wifi ap",
                     "точка доступа", "webui", "web interface", "ap статус"],
        "class": None,
    },
    # [FIX] Добавлены отсутствующие навыки
    "arc_agi3_skill": {
        "name": "arcagi3",
        "version": "1.0.0",
        "group": "AI",
        "description": "ARC-AGI3 solving skill via AI",
        "triggers": ["arc agi", "arcagi", "абстрактные диаграммы"],
        "class": None,
    },
    "esp32_usb_bridge": {
        "name": "esp32usbbridge",
        "version": "1.0.0",
        "group": "HARDWARE",
        "description": "USB мост для ESP32 прошивки",
        "triggers": ["esp32", "esptool", "прошей esp32", "esp32 usb"],
        "class": None,
    },
    "pip_manager": {
        "name": "pipmanager",
        "version": "1.0.0",
        "group": "SYSTEM",
        "description": "Управление пакетами pip",
        "triggers": ["pip", "установи пакет", "pip install", "зависимости"],
        "class": None,
    },
    "smtp_mailer": {
        "name": "smtp_mailer",
        "version": "1.0.0",
        "group": "NOTIFICATION",
        "description": "Отправка email через SMTP",
        "triggers": ["smtp", "email", "отправь письмо", "mail"],
        "class": None,
    },
    "ton_blockchain": {
        "name": "tonblockchain",
        "version": "1.0.0",
        "group": "BLOCKCHAIN",
        "description": "Интеграция с TON блокчейн",
        "triggers": ["ton", "the open network", "токен", "ton wallet"],
        "class": None,
    },
    "ga4_analytics": {
        "name": "ga4analytics",
        "version": "1.0.0",
        "group": "ANALYTICS",
        "description": "Google Analytics 4 отчёты",
        "triggers": ["ga4", "google analytics", "аналитика", "отчёт га4"],
        "class": None,
    },
    "crypto_utils": {
        "name": "cryptoutils",
        "version": "1.0.0",
        "group": "CRYPTO",
        "description": "Утилиты для криптографии и шифрования",
        "triggers": ["crypto", "шифрование", "cryptoutils", "encrypt"],
        "class": None,
    },
    "ebay_parser": {
        "name": "ebayparser",
        "version": "1.0.0",
        "group": "PARSING",
        "description": "Парсинг и поиск на eBay",
        "triggers": ["ebay", "найди на ebay", "поиск ebay"],
        "class": None,
    },
    "fastapi_skill": {
        "name": "fastapiskill",
        "version": "1.0.0",
        "group": "WEB",
        "description": "FastAPI сервер и эндпоинты",
        "triggers": ["fastapi", "api", "фастапи", "запусти сервер"],
        "class": None,
    },
    "test_injected": {
        "name": "testinjected",
        "version": "1.0.0",
        "group": "TESTING",
        "description": "Тестирование инжекции кода",
        "triggers": ["тест инжекции", "test injected", "тест инжектор"],
        "class": None,
    },
    "ton_blockchain": {
        "name": "tonblockchain",
        "version": "1.0.0",
        "group": "FINANCE",
        "description": "TON: баланс, транзакции, генерация кошельков",
        "triggers": [
            "ton", "ton wallet", "ton баланс", "ton транзакции", "ton статус", "ton цена",
            "тон", "тон кошелек", "тон кошелёк", "тон баланс", "тон транзакции",
        ],
        "class": "TonBlockchain",
    },
    "multi_provider_chat": {
        "name": "multiproviderchat",
        "version": "1.0.0",
        "group": "AI",
        "description": "Единый вызов xAI/OpenAI через OpenAI SDK",
        "triggers": [
            "ai спроси", "ai grok", "ai openai",
            "ask grok", "ask openai", "xai api", "openai api",
        ],
        "class": "MultiProviderChat",
    },
    "autonomy_fileops": {
        "name": "autonomyfileops",
        "version": "1.0.0",
        "group": "SYSTEM",
        "description": "Автоагент + анализ и мониторинг файлов",
        "triggers": [
            "автоагент", "agent auto",
            "анализ файлов", "файлмонитор", "file monitor",
        ],
        "class": "AutonomyFileOps",
    },
    "desktop_actions": {
        "name": "desktopactions",
        "version": "1.0.0",
        "group": "DESKTOP",
        "description": "Управление мышью, клавиатурой и скриншоты через Telegram",
        "triggers": [
            "мышь", "mouse",
            "клавиша", "нажми", "key ",
            "печатай", "type ",
            "скриншот", "screenshot",
            "горячие клавиши",
            "экран статус", "desktop status",
        ],
        "class": "DesktopActionsSkill",
    },
    # Пакетные навыки (с манифестами) - пропускаются загрузчиком
    # "content_gen" - пакет с manifest.yaml
    # "crypto_monitor" - пакет с manifest.yaml
    # "evolution" - пакет с manifest.yaml
    # "scheduler" - пакет с manifest.yaml
    # "net_scanner" - пакет с manifest.yaml
    # "web_scrapper" - пакет с manifest.yaml
}


class FlatSkillWrapper:
    """Обёртка для плоских .py навыков — делает их совместимыми с SkillLoader."""

    def __init__(self, skill_name: str, skill_path: Path, meta: dict):
        self.skill_name = skill_name
        self.skill_path = skill_path
        self.meta = meta
        self._module = None
        self._instance = None

    def _load(self):
        if self._module is not None:
            return True
        try:
            spec = importlib.util.spec_from_file_location(
                f"flat_skill_{self.skill_name}", str(self.skill_path)
            )
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            self._module = mod

            # Создаём экземпляр класса если указан
            cls_name = self.meta.get("class")
            if cls_name:
                cls = getattr(mod, cls_name, None)
                if cls:
                    try:
                        self._instance = cls()
                    except Exception:
                        pass
            return True
        except Exception as e:
            log.warning("FlatSkillWrapper: не удалось загрузить %s: %s", self.skill_name, e)
            return False

    def handle(self, text: str) -> str | None:
        """Попытка выполнить навык через handle() или автовыбор метода."""
        if not self._load():
            return None

        # 1. handle(text) на модуле
        if hasattr(self._module, "handle"):
            try:
                result = self._module.handle(text)
                if result is not None:
                    return str(result)
            except Exception:
                pass

        # 2. Методы экземпляра
        if self._instance:
            for method in ("handle", "handle_command", "report", "scan", "execute", "run", "get"):
                fn = getattr(self._instance, method, None)
                if callable(fn):
                    try:
                        if method in ("handle", "handle_command"):
                            result = fn(text)
                        else:
                            result = fn()
                        if result is not None:
                            return str(result)
                    except Exception:
                        pass

        # 3. execute() на модуле
        if hasattr(self._module, "execute"):
            try:
                return str(self._module.execute())
            except Exception:
                pass

        return None

    @property
    def name(self) -> str:
        return self.meta.get("name", self.skill_name)

    @property
    def version(self) -> str:
        return self.meta.get("version", "1.0.0")

    @property
    def description(self) -> str:
        return self.meta.get("description", f"Навык {self.skill_name}")

    @property
    def group(self) -> str:
        return self.meta.get("group", "GENERAL")

    @property
    def triggers(self) -> list[str]:
        return self.meta.get("triggers", [])


class PatchedSkillLoader:
    """
    Расширенный SkillLoader — загружает ВСЕ навыки из src/skills/.
    Поддерживает как пакеты (папки с __init__.py), так и плоские .py файлы.
    """

    def __init__(self, original_loader=None):
        self._original = original_loader
        self._flat_skills: list[FlatSkillWrapper] = []
        self._skills_dir: Path | None = None

    def load_all(self, core=None) -> str:
        """Загружает все навыки и возвращает отчёт."""
        report_lines = []

        # Загружаем оригинальные пакеты
        if self._original:
            try:
                orig_report = self._original.load_all(core=core)
                report_lines.append(orig_report)
            except Exception as e:
                report_lines.append(f"⚠️ OriginalLoader: {e}")

        # Находим src/skills/
        self._skills_dir = self._find_skills_dir()
        if not self._skills_dir:
            return "\n".join(report_lines) + "\n❌ src/skills не найден"

        # Загружаем flat .py файлы
        loaded = 0
        for py_file in sorted(self._skills_dir.glob("*.py")):
            if py_file.stem.startswith("_"):
                continue
            # Пропускаем если уже есть папка-пакет с таким именем
            if (self._skills_dir / py_file.stem).is_dir():
                continue
            meta = _FLAT_SKILL_META.get(
                py_file.stem,
                {
                    "name": py_file.stem.replace("_", ""),
                    "version": "1.0.0",
                    "group": "GENERAL",
                    "description": f"Навык {py_file.stem}",
                    "triggers": [],
                    "class": None,
                },
            )
            wrapper = FlatSkillWrapper(py_file.stem, py_file, meta)
            self._flat_skills.append(wrapper)
            loaded += 1
            log.info("FlatSkill загружен: %s", py_file.stem)

        report_lines.append(f"✅ Flat-навыков зарегистрировано: {loaded}")
        return "\n".join(report_lines)

    def dispatch(self, text: str, core=None) -> str | None:
        """Диспетчер: сначала оригинальный loader, потом flat навыки."""
        t = (text or "").lower().strip()
        if any(t.startswith(prefix) for prefix in ("запусти навык ", "выполни навык ", "используй навык ")):
            skill_name = ""
            for prefix in ("запусти навык ", "выполни навык ", "используй навык "):
                if t.startswith(prefix):
                    skill_name = t[len(prefix):].strip()
                    break
            if skill_name:
                direct = self.dispatch_by_name(skill_name, text=text, core=core)
                if direct is not None:
                    return direct

        # Оригинальный loader
        if self._original:
            try:
                result = self._original.dispatch(text, core=core)
                if result is not None:
                    return result
            except Exception:
                pass

        # Flat навыки
        for skill in self._flat_skills:
            if any(trigger in t for trigger in skill.triggers):
                result = skill.handle(text)
                if result is not None:
                    return result

        return None

    def dispatch_by_name(self, skill_name: str, text: str = "", core=None) -> str | None:
        """Принудительный запуск навыка по имени/алиасу."""
        name = (skill_name or "").strip().lower()
        if not name:
            return None
        normalized = {name, name.replace(" ", "_"), name.replace("_", ""), name.replace("_", " ")}

        if self._original:
            for cand in sorted(normalized, key=len, reverse=True):
                try:
                    result = self._original.dispatch(f"запусти навык {cand}", core=core)
                    if result is not None:
                        return result
                except Exception:
                    pass

        for skill in self._flat_skills:
            aliases = {
                skill.skill_name.lower(),
                skill.name.lower(),
                skill.skill_name.lower().replace("_", ""),
                skill.name.lower().replace("_", ""),
                skill.skill_name.lower().replace("_", " "),
                skill.name.lower().replace("_", " "),
            }
            if normalized & aliases:
                result = skill.handle(text or f"запусти навык {skill.skill_name}")
                if result is not None:
                    return result
        return None

    def list_skills(self) -> str:
        """Список всех навыков — пакеты + flat."""
        lines = []

        # Оригинальные
        if self._original:
            try:
                orig = self._original.list_skills()
                lines.append(orig)
            except Exception:
                pass

        # Flat навыки
        if self._flat_skills:
            lines.append("\n  [FLAT FILES]")
            for sk in self._flat_skills:
                lines.append(f"    📄 {sk.name} v{sk.version} — {sk.description}")

        return "\n".join(lines) if lines else "❌ Навыки не загружены"

    def _find_skills_dir(self) -> Path | None:
        for base in [Path(__file__).parent, Path.cwd()]:
            for candidate in [base / "src" / "skills", base / "skills"]:
                if candidate.exists():
                    return candidate
        return None

    def save_all(self, output_path: str = "skills_snapshot.json") -> str:
        """Сохраняет список всех навыков в JSON файл."""
        import json
        from datetime import datetime

        skills_data = {
            "timestamp": datetime.now().isoformat(),
            "skills_dir": str(self._skills_dir or "unknown"),
            "packages": [],
            "flat_files": [],
        }

        if self._original and hasattr(self._original, "_skills"):
            for sk in self._original._skills:
                try:
                    skills_data["packages"].append(
                        {
                            "name": sk.name if hasattr(sk, "name") else str(sk),
                            "version": getattr(sk, "version", "?"),
                            "description": getattr(sk, "description", ""),
                        }
                    )
                except Exception:
                    pass

        for sk in self._flat_skills:
            skills_data["flat_files"].append(
                {
                    "name": sk.name,
                    "version": sk.version,
                    "description": sk.description,
                    "group": sk.group,
                    "triggers": sk.triggers,
                    "file": sk.skill_path.name,
                }
            )

        path = Path(output_path)
        path.write_text(json.dumps(skills_data, ensure_ascii=False, indent=2), encoding="utf-8")
        total = len(skills_data["packages"]) + len(skills_data["flat_files"])
        return (
            f"✅ Навыки сохранены в `{path.resolve()}`\n"
            f"  Пакеты:  {len(skills_data['packages'])}\n"
            f"  Flat:    {len(skills_data['flat_files'])}\n"
            f"  Итого:   {total}"
        )


def patch_core(core):
    """
    Заменяет skill_loader в экземпляре ArgosCore на PatchedSkillLoader.
    Вызвать один раз: patch_core(core)
    """
    if core is None:
        return "❌ core is None"
    original = getattr(core, "skill_loader", None)
    patched = PatchedSkillLoader(original_loader=original)
    report = patched.load_all(core=core)
    core.skill_loader = patched
    log.info("PatchedSkillLoader установлен: %s", report)
    return f"✅ SkillLoader обновлён\n{report}"


# ── Запуск напрямую ───────────────────────────────────────────────────────────
if __name__ == "__main__":
    print("skill_loader_patch.py — проверка")
    loader = PatchedSkillLoader()
    report = loader.load_all()
    print(report)
    print()
    print(loader.list_skills())
