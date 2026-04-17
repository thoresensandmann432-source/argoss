"""
ai_coder.py — AI Coder ARGOS
═══════════════════════════════════════════════════════
Генерация и доработка кода через локальный Ollama:
  • Генерация кода по описанию
  • Объяснение существующего кода
  • Исправление ошибок (fix)
  • Рефакторинг
  • Генерация тестов
  • Создание скила по описанию → автоматическая интеграция
═══════════════════════════════════════════════════════
"""

from __future__ import annotations

SKILL_DESCRIPTION = "Генерация и доработка кода через Ollama"

import os
import ast
import json
import time
import re
from typing import Optional

try:
    import requests
    _REQ = True
except ImportError:
    _REQ = False

from src.argos_logger import get_logger

log = get_logger("argos.ai_coder")

GENERATED_DIR = "src/skills/generated"
HISTORY_FILE  = "data/ai_coder_history.json"
os.makedirs(GENERATED_DIR, exist_ok=True)
os.makedirs("data", exist_ok=True)


class AICoder:
    """
    AI-помощник для генерации кода через Ollama.
    Умеет генерировать, объяснять, фиксить и создавать скилы.
    """

    def __init__(self, core=None):
        self.core       = core
        self._ollama    = os.getenv("OLLAMA_HOST", "http://localhost:11434")
        self._model     = os.getenv("OLLAMA_MODEL", "qwen2.5-coder:7b")
        self._fallback  = os.getenv("OLLAMA_MODEL", "llama3.2:3b")
        self._history: list = self._load_history()

    def _load_history(self) -> list:
        if os.path.exists(HISTORY_FILE):
            try:
                return json.load(open(HISTORY_FILE, encoding="utf-8"))
            except Exception:
                pass
        return []

    def _save_history(self):
        try:
            json.dump(self._history[-100:], open(HISTORY_FILE, "w", encoding="utf-8"),
                      indent=2, ensure_ascii=False)
        except Exception:
            pass

    # ── Ollama запрос ─────────────────────────────────────────────────────────

    def _ask_ollama(self, prompt: str, system: str = "", model: str = "") -> str:
        """Отправляет запрос в Ollama, возвращает текст ответа."""
        if not _REQ:
            return "❌ requests не установлен"

        m = model or self._model
        payload = {
            "model": m,
            "prompt": prompt,
            "stream": False,
            "options": {"temperature": 0.2, "num_predict": 2048},
        }
        if system:
            payload["system"] = system

        try:
            r = requests.post(
                f"{self._ollama}/api/generate",
                json=payload, timeout=120,
            )
            if r.ok:
                return r.json().get("response", "").strip()
            # Если модель не найдена — пробуем fallback
            if r.status_code == 404 and m != self._fallback:
                log.warning("Модель %s не найдена, пробуем %s", m, self._fallback)
                payload["model"] = self._fallback
                r2 = requests.post(f"{self._ollama}/api/generate", json=payload, timeout=120)
                if r2.ok:
                    return r2.json().get("response", "").strip()
            return f"❌ Ollama {r.status_code}: {r.text[:200]}"
        except requests.exceptions.ConnectionError:
            return "❌ Ollama недоступен. Запусти: ollama serve"
        except Exception as e:
            return f"❌ {e}"

    # ── Извлечение кода из ответа ─────────────────────────────────────────────

    @staticmethod
    def _extract_code(text: str, lang: str = "python") -> str:
        """Извлекает блок кода из ``` ... ``` обёртки."""
        pattern = rf"```{lang}?\s*([\s\S]+?)```"
        match = re.search(pattern, text)
        if match:
            return match.group(1).strip()
        # Если нет блока — возвращаем весь текст как код
        return text.strip()

    # ── Основные операции ─────────────────────────────────────────────────────

    def generate(self, description: str, lang: str = "python") -> str:
        """Генерирует код по текстовому описанию."""
        system = (
            f"Ты — опытный {lang}-разработчик. Пишешь чистый, рабочий код.\n"
            "Всегда оборачивай код в ```python ... ```.\n"
            "Добавляй docstring и комментарии на русском.\n"
            "Не добавляй лишних объяснений — только код."
        )
        prompt = f"Напиши {lang}-код:\n{description}"

        log.info("AICoder: generate — %s", description[:60])
        answer = self._ask_ollama(prompt, system)
        code = self._extract_code(answer, lang)

        self._history.append({
            "ts": time.strftime("%Y-%m-%d %H:%M"), "op": "generate",
            "desc": description[:80], "lines": code.count("\n") + 1,
        })
        self._save_history()
        return code

    def explain(self, code: str) -> str:
        """Объясняет код на русском."""
        prompt = (
            f"Объясни этот код подробно на русском:\n\n```python\n{code}\n```\n\n"
            "Опиши: что делает, как работает, какие риски."
        )
        return self._ask_ollama(prompt)

    def fix(self, code: str, error: str = "") -> str:
        """Исправляет ошибки в коде."""
        err_section = f"\nОшибка:\n{error}" if error else ""
        system = "Ты — Python-отладчик. Исправь код. Верни ТОЛЬКО исправленный код в ```python```."
        prompt = f"Исправь код:{err_section}\n\n```python\n{code}\n```"
        answer = self._ask_ollama(prompt, system)
        return self._extract_code(answer)

    def refactor(self, code: str, goal: str = "") -> str:
        """Рефакторинг кода."""
        goal_str = goal or "улучши читаемость, добавь типы, оптимизируй"
        system = "Ты — Python-архитектор. Верни ТОЛЬКО улучшенный код в ```python```."
        prompt = f"Рефактори этот код ({goal_str}):\n\n```python\n{code}\n```"
        answer = self._ask_ollama(prompt, system)
        return self._extract_code(answer)

    def gen_tests(self, code: str) -> str:
        """Генерирует unit-тесты для кода."""
        system = "Пиши pytest-тесты. Верни ТОЛЬКО тесты в ```python```."
        prompt = f"Напиши unit-тесты для:\n\n```python\n{code}\n```"
        answer = self._ask_ollama(prompt, system)
        return self._extract_code(answer)

    # ── Создание скила ────────────────────────────────────────────────────────

    def create_skill(self, description: str, skill_name: str = "") -> str:
        """
        Генерирует полноценный ARGOS-скил по описанию и сохраняет его.
        """
        if not skill_name:
            # Авто-имя из описания
            skill_name = re.sub(r"[^\w]", "_", description.split()[0].lower())[:20]
        if not skill_name.endswith(".py"):
            skill_name += ".py"

        system = """Ты — разработчик ARGOS (автономная AI-система Python).
Создай скил по следующим правилам:
1. Класс с говорящим именем (CamelCase)
2. __init__(self, core=None) — принимает ядро ARGOS
3. execute(self) -> str — основное действие, возвращает текст
4. report(self) -> str — краткий статус
5. Импорты через try/except с флагом
6. Логгер: from src.argos_logger import get_logger
7. Комментарии на русском
Верни ТОЛЬКО код в ```python```."""

        prompt = f"Создай ARGOS-скил:\n{description}"

        log.info("AICoder: create_skill '%s' — %s", skill_name, description[:60])
        answer = self._ask_ollama(prompt, system)
        code = self._extract_code(answer)

        # Проверка синтаксиса
        try:
            ast.parse(code)
        except SyntaxError as e:
            # Пробуем автофикс
            log.warning("SyntaxError в сгенерированном скиле: %s", e)
            code = self.fix(code, str(e))
            try:
                ast.parse(code)
            except SyntaxError:
                return f"❌ AI сгенерировал код с синтаксической ошибкой. Попробуй снова."

        # Сохраняем
        filepath = os.path.join(GENERATED_DIR, skill_name)
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(f"# ARGOS AI-Generated Skill\n# Описание: {description}\n# Создан: {time.strftime('%Y-%m-%d %H:%M')}\n\n")
            f.write(code)

        # Опционально — инжектим в ядро
        inject_result = ""
        if self.core and hasattr(self.core, "skill_loader") and self.core.skill_loader:
            try:
                self.core.skill_loader.load_file(filepath, core=self.core)
                inject_result = "\n✅ Загружен в ядро ARGOS"
            except Exception as e:
                inject_result = f"\n⚠️ Загрузка: {e}"

        self._history.append({
            "ts": time.strftime("%Y-%m-%d %H:%M"), "op": "create_skill",
            "name": skill_name, "desc": description[:80],
        })
        self._save_history()

        return (
            f"✅ Скил создан: {skill_name}\n"
            f"   Строк кода: {code.count(chr(10)) + 1}\n"
            f"   Путь: {filepath}"
            f"{inject_result}"
        )

    # ── Команды из ARGOS ──────────────────────────────────────────────────────

    def handle_command(self, text: str) -> Optional[str]:
        """Обрабатывает команды из чата ARGOS."""
        t = text.lower().strip()

        # напиши код / сгенерируй код
        if any(k in t for k in ["напиши код", "сгенерируй код", "создай код", "write code"]):
            desc = re.sub(r"(напиши|сгенерируй|создай)\s+код\s*", "", t).strip()
            if not desc:
                return "Формат: напиши код [описание]"
            return f"```python\n{self.generate(desc)}\n```"

        # создай скил
        if any(k in t for k in ["создай скил", "новый скил", "сделай скил"]):
            desc = re.sub(r"(создай|новый|сделай)\s+скил\s*", "", t).strip()
            if not desc:
                return "Формат: создай скил [описание]"
            return self.create_skill(desc)

        # объясни код
        if "объясни код" in t:
            code_match = re.search(r"```(?:python)?\s*([\s\S]+?)```", text)
            if code_match:
                return self.explain(code_match.group(1))
            return "Формат: объясни код ```python\n# код\n```"

        # исправь код
        if any(k in t for k in ["исправь код", "fix код", "fix code"]):
            code_match = re.search(r"```(?:python)?\s*([\s\S]+?)```", text)
            if code_match:
                fixed = self.fix(code_match.group(1))
                return f"✅ Исправленный код:\n```python\n{fixed}\n```"

        # рефакторинг
        if "рефакторинг" in t or "refactor" in t:
            code_match = re.search(r"```(?:python)?\s*([\s\S]+?)```", text)
            if code_match:
                result = self.refactor(code_match.group(1))
                return f"✅ Рефакторинг:\n```python\n{result}\n```"

        # тесты
        if any(k in t for k in ["напиши тесты", "создай тесты", "gen tests"]):
            code_match = re.search(r"```(?:python)?\s*([\s\S]+?)```", text)
            if code_match:
                tests = self.gen_tests(code_match.group(1))
                return f"✅ Тесты:\n```python\n{tests}\n```"

        return None

    def report(self) -> str:
        ops = len(self._history)
        last = self._history[-1] if self._history else {}
        return (
            f"🤖 AI Coder\n"
            f"  Модель: {self._model}\n"
            f"  Ollama: {self._ollama}\n"
            f"  Операций: {ops}\n"
            f"  Последняя: {last.get('ts','—')} {last.get('op','')}\n"
            f"  Скилов создано: {len([e for e in self._history if e.get('op')=='create_skill'])}"
        )

    def execute(self) -> str:
        return self.report()
