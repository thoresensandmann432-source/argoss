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

import random
from pathlib import Path
from typing import Optional, Any
from src.argos_logger import get_logger

log = get_logger("argos.arc3")

# ── Константы ─────────────────────────────────────────────────────────────────
# Локальная папка для кэша датасетов (JSON-файлы задач)
_ARC_DATA_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "arc_agi"

# Маппинг: ключ датасета → (класс arc_agi, подпапка в _ARC_DATA_DIR)
_DS_MAP = {
    "arc1_train": ("ARC1Training",   "arc1_train"),
    "arc1_eval":  ("ARC1Evaluation", "arc1_eval"),
    "arc2_train": ("ARC2Training",   "arc2_train"),
    "arc2_eval":  ("ARC2Evaluation", "arc2_eval"),
}
_DS_LABELS = {
    "arc1_train": "ARC1 Training",
    "arc1_eval":  "ARC1 Evaluation",
    "arc2_train": "ARC2 Training",
    "arc2_eval":  "ARC2 Evaluation",
}

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


def _get_arc_cls(cls_name: str):
    """Возвращает класс датасета из arc_agi по имени."""
    import arc_agi
    return getattr(arc_agi, cls_name)


def _load_dataset(ds_name: str = "arc1_train"):
    """
    Загружает датасет из локального кэша (_ARC_DATA_DIR/<subdir>).
    Возвращает Dataset или None если данных нет (нужно запустить download).
    НЕ скачивает автоматически — только читает уже загруженные файлы.
    """
    entry = _DS_MAP.get(ds_name)
    if entry is None:
        log.warning("[ARC] Неизвестный датасет: %s", ds_name)
        return None
    cls_name, subdir = entry
    path = _ARC_DATA_DIR / subdir
    if not path.exists() or not any(path.glob("*.json")):
        return None  # нет локальных данных — нужен 'arc загрузить'
    try:
        cls = _get_arc_cls(cls_name)
        return cls.load_directory(path)
    except Exception as e:
        log.warning("[ARC] Ошибка чтения датасета %s из %s: %s", ds_name, path, e)
        return None


class ARC3Agent:
    """Агент для решения задач ARC-AGI из датасета."""

    def __init__(self, core=None):
        self.core = core
        self._last_task = None
        self._last_task_idx: int = -1
        self._last_result: dict = {}
        self._ds_name: str = "arc1_train"

    def status(self) -> str:
        lines = ["🎮 ARC-AGI Датасет:"]
        try:
            import arc_agi  # noqa: F401
            lines.append("  ✅ arc-agi пакет установлен")
        except ImportError:
            lines.append("  ❌ arc-agi не установлен → pip install arc-agi")
            return "\n".join(lines)

        # Проверяем локальный кэш для каждого датасета
        any_missing = False
        for ds_key, label in _DS_LABELS.items():
            _, subdir = _DS_MAP[ds_key]
            path = _ARC_DATA_DIR / subdir
            json_files = list(path.glob("*.json")) if path.exists() else []
            if json_files:
                lines.append(f"  ✅ {label}: {len(json_files)} задач (кэш: {path})")
            else:
                lines.append(f"  ⚠️ {label}: нет данных → запусти 'arc загрузить'")
                any_missing = True

        if any_missing:
            lines.append("  💡 Данные скачиваются с GitHub (публичные репо, без ключей)")

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
            train_pairs = task.train   # List[Pair] — обучающие пары
            test_pairs  = task.test    # List[Pair] — тестовые пары
            lines = [f"🧩 Задача #{idx} / {n} ({ds_name}):"]
            lines.append(f"  Обучающих пар: {len(train_pairs)} | Тестовых: {len(test_pairs)}")
            for i, pair in enumerate(train_pairs[:2]):  # показываем первые 2
                inp = getattr(pair, 'input', None)
                out = getattr(pair, 'output', None)
                lines.append(f"\n  [Пара {i+1}]")
                lines.append(f"  Вход: {_grid_to_text(inp)}")
                lines.append(f"  Выход: {_grid_to_text(out)}")
            if len(train_pairs) > 2:
                lines.append(f"\n  ... и ещё {len(train_pairs)-2} пар")
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
        """
        Скачивает датасеты ARC-AGI с GitHub в локальный кэш.
        Использует cls.download(path) — скачивает ZIP-архив репо и извлекает JSON.
        Не требует API-ключей (данные публичные).
        """
        try:
            lines = ["📥 Загрузка датасетов ARC-AGI с GitHub..."]
            _ARC_DATA_DIR.mkdir(parents=True, exist_ok=True)
            for ds_key, label in _DS_LABELS.items():
                cls_name, subdir = _DS_MAP[ds_key]
                path = _ARC_DATA_DIR / subdir
                # Пропускаем уже загруженные
                existing = list(path.glob("*.json")) if path.exists() else []
                if existing:
                    lines.append(f"  ✅ {label}: уже есть {len(existing)} задач, пропускаем")
                    continue
                try:
                    cls = _get_arc_cls(cls_name)
                    ds = cls.download(path)   # скачивает ZIP с GitHub → извлекает JSON
                    n = len(ds)
                    lines.append(f"  {'✅' if n > 0 else '⚠️'} {label}: {n} задач → {path}")
                except Exception as e:
                    lines.append(f"  ❌ {label}: {e}")
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
            train_pairs = task.train   # List[Pair]
            test_pairs  = task.test    # List[Pair]
            if not train_pairs:
                return f"❌ Задача #{idx} не имеет обучающих пар."

            # Формируем промпт для LLM
            prompt_lines = [
                f"Задача ARC-AGI #{idx}. Найди паттерн трансформации входного грида в выходной.",
                "Обучающие примеры:",
            ]
            for i, pair in enumerate(train_pairs):
                inp = getattr(pair, 'input', None)
                out = getattr(pair, 'output', None)
                prompt_lines.append(f"Пример {i+1}:")
                prompt_lines.append(f"  Вход: {_grid_to_text(inp)}")
                prompt_lines.append(f"  Выход: {_grid_to_text(out)}")

            # Тестовый вход (без ответа)
            if test_pairs:
                prompt_lines.append("\nТестовый вход (дай ответный грид):")
                prompt_lines.append(_grid_to_text(getattr(test_pairs[0], 'input', None)))
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
