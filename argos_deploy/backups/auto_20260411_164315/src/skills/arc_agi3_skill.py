"""
arc_agi3_skill.py — ARGOS ↔ ARC-AGI датасет + решатель

arc-agi v0.0.7 — пакет для работы с датасетами ARC-AGI-1 и ARC-AGI-2:
  • arc_agi.ARC1Training / ARC1Evaluation — задачи ARC-1
  • arc_agi.ARC2Training / ARC2Evaluation — задачи ARC-2
  • arc_agi.RemoteDataset               — загрузка с arcprize.org

Каждая задача (Task):
  • task.challenge  — список пар обучения [{input: Grid, output: Grid}, ...]
  • task.solution   — правильный выходной Grid для тестовой пары
  • task.inputs()   — тестовые входы (без ответа)

Команды:
  arc статус          — статус пакета и датасетов
  arc задача <N>      — показать N-ю задачу ARC1 Training
  arc случайная       — случайная задача
  arc загрузить       — скачать датасет (RemoteDataset)
  arc решай <N>       — попытка LLM решить задачу N
"""

from __future__ import annotations

SKILL_DESCRIPTION = "Работа с датасетами ARC-AGI-1/2 и решение задач"

import os
import json
import random
from typing import Optional, Any
from src.argos_logger import get_logger

log = get_logger("argos.arc3")

# ── Константы ─────────────────────────────────────────────────────────────────
ARC3_API_KEY_ENV  = "ARC_API_KEY"
_ARC3_API_KEY_ALT = "ARC3_API_KEY"
ARC3_API_BASE     = "https://three.arcprize.org"

# 10 цветов ARC-AGI (индекс → имя для LLM-промпта)
ARC_COLOR_NAMES = [
    "black", "blue", "red", "green", "yellow",
    "grey", "magenta", "orange", "azure", "maroon",
]


def _grid_to_text(grid_data) -> str:
    """Конвертирует грид ARC в читаемый текст."""
    try:
        if hasattr(grid_data, 'to_list'):
            rows = grid_data.to_list()
        elif isinstance(grid_data, list):
            rows = grid_data
        else:
            return str(grid_data)[:200]

        lines = []
        for row in rows:
            cells = []
            for val in row:
                name = ARC_COLOR_NAMES[val] if isinstance(val, int) and val < len(ARC_COLOR_NAMES) else str(val)
                cells.append(name[0])  # первая буква цвета
            lines.append(" ".join(cells))
        h = len(rows)
        w = len(rows[0]) if rows else 0
        return f"[{h}×{w}]\n" + "\n".join(lines)
    except Exception as e:
        return f"(ошибка рендера: {e})"


def _load_dataset(ds_name: str = "arc1_train"):
    """Загружает датасет. Возвращает объект датасета или None."""
    try:
        import arc_agi
        mapping = {
            "arc1_train": arc_agi.ARC1Training,
            "arc1_eval":  arc_agi.ARC1Evaluation,
            "arc2_train": arc_agi.ARC2Training,
            "arc2_eval":  arc_agi.ARC2Evaluation,
        }
        cls = mapping.get(ds_name, arc_agi.ARC1Training)
        return cls()
    except Exception as e:
        log.warning("[ARC] Ошибка загрузки датасета %s: %s", ds_name, e)
        return None


class ARC3Agent:
    """Агент для решения задач ARC-AGI из датасета."""

    def __init__(self, core=None):
        self.core = core
        self._last_task = None
        self._last_task_idx: int = -1
        self._last_result: dict = {}
        self._ds_name: str = "arc1_train"

    def _get_api_key(self) -> str:
        return (os.getenv(ARC3_API_KEY_ENV, "")
                or os.getenv(_ARC3_API_KEY_ALT, "")).strip()

    def status(self) -> str:
        lines = ["🎮 ARC-AGI Датасет:"]
        try:
            import arc_agi
            lines.append(f"  ✅ arc-agi пакет установлен")
            # Проверяем каждый датасет
            for name, cls in [
                ("ARC1 Training",   arc_agi.ARC1Training),
                ("ARC1 Evaluation", arc_agi.ARC1Evaluation),
                ("ARC2 Training",   arc_agi.ARC2Training),
                ("ARC2 Evaluation", arc_agi.ARC2Evaluation),
            ]:
                try:
                    ds = cls()
                    n = len(ds)
                    if n > 0:
                        lines.append(f"  ✅ {name}: {n} задач")
                    else:
                        lines.append(f"  ⚠️ {name}: пустой (нужна загрузка)")
                except Exception as e:
                    lines.append(f"  ❌ {name}: {e}")
        except ImportError:
            lines.append("  ❌ arc-agi не установлен → pip install arc-agi")

        key = self._get_api_key()
        if key:
            lines.append(f"  🔑 API-ключ задан ({ARC3_API_KEY_ENV})")
        else:
            lines.append(f"  ℹ️ API-ключ не задан ({ARC3_API_KEY_ENV} в .env)")

        if self._last_result:
            r = self._last_result
            lines.append(
                f"  📊 Последняя задача #{r.get('idx','?')}: "
                f"{'✅ решена' if r.get('correct') else '❌ не решена'}"
            )
        return "\n".join(lines)

    def show_task(self, idx: int, ds_name: str = "arc1_train") -> str:
        """Показывает задачу N из датасета."""
        ds = _load_dataset(ds_name)
        if ds is None:
            return "❌ Датасет недоступен."
        n = len(ds)
        if n == 0:
            return (
                "⚠️ Датасет пуст — задачи не загружены.\n"
                "Используй команду 'arc загрузить' или скачай датасет вручную:\n"
                "  https://arcprize.org/play\n"
                "  pip install arc-agi && python -c \"import arc_agi; arc_agi.ARC1Training().cache_all()\""
            )
        idx = idx % n
        try:
            task = ds[idx]
            self._last_task = task
            self._last_task_idx = idx
            pairs = task.challenge if hasattr(task, 'challenge') else []
            lines = [f"🧩 Задача #{idx} / {n} ({ds_name}):"]
            lines.append(f"  Обучающих пар: {len(pairs)}")
            for i, pair in enumerate(pairs[:2]):  # показываем первые 2
                inp = getattr(pair, 'input', None) or (pair.get('input') if isinstance(pair, dict) else None)
                out = getattr(pair, 'output', None) or (pair.get('output') if isinstance(pair, dict) else None)
                lines.append(f"\n  [Пара {i+1}]")
                lines.append(f"  Вход: {_grid_to_text(inp)}")
                lines.append(f"  Выход: {_grid_to_text(out)}")
            if len(pairs) > 2:
                lines.append(f"\n  ... и ещё {len(pairs)-2} пар")
            test_inputs = task.inputs() if hasattr(task, 'inputs') else []
            lines.append(f"\n  Тестовых входов: {len(list(test_inputs)) if test_inputs else 0}")
            return "\n".join(lines)
        except Exception as e:
            return f"❌ Ошибка загрузки задачи #{idx}: {e}"

    def random_task(self, ds_name: str = "arc1_train") -> str:
        """Показывает случайную задачу."""
        ds = _load_dataset(ds_name)
        if ds is None:
            return "❌ Датасет недоступен."
        n = len(ds)
        if n == 0:
            return "⚠️ Датасет пуст."
        idx = random.randint(0, n - 1)
        return self.show_task(idx, ds_name)

    def download(self) -> str:
        """Попытка скачать датасет через RemoteDataset."""
        try:
            import arc_agi
            lines = ["📥 Попытка загрузки датасетов ARC-AGI..."]
            for name, cls in [
                ("ARC1 Training",   arc_agi.ARC1Training),
                ("ARC1 Evaluation", arc_agi.ARC1Evaluation),
            ]:
                try:
                    ds = cls()
                    if len(ds) == 0 and hasattr(ds, 'cache_all'):
                        ds.cache_all()
                    lines.append(f"  ✅ {name}: {len(ds)} задач")
                except Exception as e:
                    lines.append(f"  ❌ {name}: {e}")
            return "\n".join(lines)
        except Exception as e:
            return f"❌ Ошибка загрузки: {e}"

    def solve_task(self, idx: int, ds_name: str = "arc1_train") -> str:
        """LLM пытается решить задачу N."""
        ds = _load_dataset(ds_name)
        if ds is None:
            return "❌ Датасет недоступен."
        n = len(ds)
        if n == 0:
            return "⚠️ Датасет пуст — сначала загрузи: 'arc загрузить'"
        idx = idx % n
        try:
            task = ds[idx]
            pairs = task.challenge if hasattr(task, 'challenge') else []
            if not pairs:
                return f"❌ Задача #{idx} не имеет обучающих пар."

            # Формируем промпт для LLM
            prompt_lines = [
                f"Задача ARC-AGI #{idx}. Найди паттерн трансформации входного грида в выходной.",
                "Обучающие примеры:",
            ]
            for i, pair in enumerate(pairs):
                inp = getattr(pair, 'input', None) or (pair.get('input') if isinstance(pair, dict) else None)
                out = getattr(pair, 'output', None) or (pair.get('output') if isinstance(pair, dict) else None)
                prompt_lines.append(f"Пример {i+1}:")
                prompt_lines.append(f"  Вход: {_grid_to_text(inp)}")
                prompt_lines.append(f"  Выход: {_grid_to_text(out)}")

            # Тестовый вход
            test_inputs = list(task.inputs()) if hasattr(task, 'inputs') else []
            if test_inputs:
                prompt_lines.append("\nТестовый вход (дай ответный грид):")
                prompt_lines.append(_grid_to_text(test_inputs[0]))
            prompt_lines.append("\nОпиши паттерн и дай ответ для тестового входа.")

            prompt = "\n".join(prompt_lines)

            if self.core:
                try:
                    result = self.core.ask_ai(prompt)
                    self._last_result = {"idx": idx, "correct": None, "answer": result}
                    return f"🤖 ARC #{idx} — ответ LLM:\n{result[:600]}"
                except Exception as e:
                    return f"❌ LLM недоступен: {e}"
            else:
                return f"❌ Core не подключён — LLM недоступен.\n\nПромпт для ручного решения:\n{prompt[:400]}"
        except Exception as e:
            return f"❌ Ошибка: {e}"

    def list_envs(self) -> str:
        """Информация о доступных датасетах."""
        lines = ["🎮 Датасеты ARC-AGI:"]
        try:
            import arc_agi
            for name, cls, key in [
                ("ARC1 Training",   arc_agi.ARC1Training,   "arc1_train"),
                ("ARC1 Evaluation", arc_agi.ARC1Evaluation, "arc1_eval"),
                ("ARC2 Training",   arc_agi.ARC2Training,   "arc2_train"),
                ("ARC2 Evaluation", arc_agi.ARC2Evaluation, "arc2_eval"),
            ]:
                try:
                    ds = cls()
                    n = len(ds)
                    status = f"{n} задач" if n > 0 else "пустой"
                    lines.append(f"  • {name} ({key}): {status}")
                except Exception as e:
                    lines.append(f"  • {name}: ❌ {e}")
        except ImportError:
            lines.append("  ❌ arc-agi не установлен")
        lines.append("\nКоманды:")
        lines.append("  'arc задача 0'     — задача #0 из ARC1 Training")
        lines.append("  'arc случайная'    — случайная задача")
        lines.append("  'arc решай 5'      — LLM решает задачу #5")
        lines.append("  'arc загрузить'    — скачать датасеты")
        return "\n".join(lines)


# ── Синглтон и handle() ───────────────────────────────────────────────────────
_agent: ARC3Agent | None = None


def handle(text: str, core=None) -> str | None:
    global _agent
    t = text.lower().strip()

    if not any(k in t for k in ["arc", "arc-agi", "arcagi"]):
        return None

    if _agent is None:
        _agent = ARC3Agent(core=core)
    elif core is not None and _agent.core is None:
        _agent.core = core

    if any(k in t for k in ["arc статус", "arc status", "arc3 статус"]):
        return _agent.status()

    if any(k in t for k in ["arc среды", "arc список", "arc envs", "arc датасеты", "arc datasets"]):
        return _agent.list_envs()

    if any(k in t for k in ["arc загрузить", "arc скачать", "arc download"]):
        return _agent.download()

    if "arc случайная" in t or "arc random" in t:
        ds = "arc2_train" if "arc2" in t else "arc1_train"
        return _agent.random_task(ds)

    import re

    # arc задача <N>
    m_task = re.search(r'arc\s+задач[ауи]?\s*(\d+)', t)
    if m_task:
        ds = "arc2_train" if "arc2" in t else "arc1_train"
        return _agent.show_task(int(m_task.group(1)), ds)

    # arc решай <N>
    m_solve = re.search(r'arc\s+(?:решай|решить|solve|run)\s+(\d+)', t)
    if m_solve:
        ds = "arc2_train" if "arc2" in t else "arc1_train"
        return _agent.solve_task(int(m_solve.group(1)), ds)

    # arc <N> напрямую
    m_direct = re.search(r'^arc\s+(\d+)$', t)
    if m_direct:
        return _agent.show_task(int(m_direct.group(1)))

    # Общий запрос про arc без конкретной команды
    if any(k in t for k in ["arc-agi", "arcagi", "arc agi"]):
        return _agent.status()

    return None


TRIGGERS = [
    "arc", "arc-agi", "arcagi", "arc status", "arc статус",
    "arc среды", "arc датасеты", "arc загрузить", "arc случайная",
    "arc задача", "arc решай", "arc решить",
]


def setup(core=None):
    pass
