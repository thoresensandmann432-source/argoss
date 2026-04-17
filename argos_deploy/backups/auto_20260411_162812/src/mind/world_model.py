"""
world_model.py — ARC-AGI-3 Grid State Tracker & Hypothesis Engine

Хранит историю состояний сетки, обнаруживает паттерны трансформаций,
поддерживает гипотезы о правилах среды и эволюционирует их по мере наблюдений.

Используется arc_agi3_skill.py (ARC3Agent) для накопления структурированных знаний
о конкретной среде и передачи их в arc_planner.py для принятия решений.
"""

from __future__ import annotations

import json
import time
import hashlib
import re
from collections import Counter, defaultdict
from typing import Any, Optional

from src.argos_logger import get_logger

log = get_logger("argos.arc3.world")

# Имена 16 цветов ARC-AGI-3
ARC3_COLORS = [
    "black", "blue", "red", "green", "yellow",
    "grey", "magenta", "orange", "azure", "maroon",
    "cyan", "lime", "brown", "white", "pink", "purple"
]

GRID_SIZE = 64  # ARC-AGI-3 использует сетку 64×64


# ── Вспомогательные функции ────────────────────────────────────────────────────

def _grid_to_list(frame) -> list[list[int]]:
    """Приводит фрейм (numpy / list) к list[list[int]]."""
    if frame is None:
        return []
    if hasattr(frame, "tolist"):
        return frame.tolist()
    if isinstance(frame, list):
        return frame
    return []


def _frame_hash(grid: list[list[int]]) -> str:
    """SHA-1 хэш состояния сетки для быстрой дедупликации."""
    s = json.dumps(grid, separators=(",", ":"))
    return hashlib.sha1(s.encode()).hexdigest()[:12]


def _sparse(grid: list[list[int]]) -> dict[tuple[int, int], int]:
    """Конвертирует сетку в разреженный словарь {(r,c): color} (без чёрных клеток)."""
    result = {}
    for r, row in enumerate(grid):
        for c, val in enumerate(row):
            if val != 0:
                result[(r, c)] = val
    return result


def _diff_sparse(a: dict, b: dict) -> list[tuple]:
    """
    Список изменений между двумя разреженными состояниями.
    Возвращает [(r, c, old_color, new_color), ...]
    """
    keys = set(a) | set(b)
    changes = []
    for k in keys:
        old = a.get(k, 0)
        new = b.get(k, 0)
        if old != new:
            changes.append((k[0], k[1], old, new))
    return changes


def _color_name(idx: int) -> str:
    if 0 <= idx < len(ARC3_COLORS):
        return ARC3_COLORS[idx]
    return str(idx)


# ── FrameRecord ────────────────────────────────────────────────────────────────

class FrameRecord:
    """Снимок одного шага: состояние + контекст."""
    __slots__ = ("step", "action", "grid", "sparse", "hash",
                 "reward", "done", "timestamp")

    def __init__(
        self,
        step: int,
        action: Any,
        grid: list[list[int]],
        reward: float = 0.0,
        done: bool = False,
    ):
        self.step = step
        self.action = action
        self.grid = grid
        self.sparse = _sparse(grid)
        self.hash = _frame_hash(grid)
        self.reward = reward
        self.done = done
        self.timestamp = time.time()

    @property
    def non_black_count(self) -> int:
        return len(self.sparse)

    def as_text(self, max_cells: int = 80) -> str:
        """Текстовое представление для LLM-промпта."""
        if not self.sparse:
            return "Сетка пуста (фон чёрный)"
        cells = [
            f"({r},{c})={_color_name(v)}"
            for (r, c), v in sorted(self.sparse.items())
        ]
        header = f"Непустых клеток: {len(cells)}"
        body = ", ".join(cells[:max_cells])
        suffix = f" …+{len(cells)-max_cells} ещё" if len(cells) > max_cells else ""
        return f"{header}\n{body}{suffix}"


# ── Hypothesis ────────────────────────────────────────────────────────────────

class Hypothesis:
    """Одна гипотеза о правилах среды с весом доверия."""

    def __init__(self, text: str, confidence: float = 0.5, source: str = "llm"):
        self.text = text
        self.confidence = confidence   # [0, 1]
        self.source = source           # "llm" | "pattern" | "manual"
        self.created_at = time.time()
        self.confirmations = 0
        self.refutations = 0

    def confirm(self, delta: float = 0.05):
        self.confirmations += 1
        self.confidence = min(1.0, self.confidence + delta)

    def refute(self, delta: float = 0.1):
        self.refutations += 1
        self.confidence = max(0.0, self.confidence - delta)

    def __repr__(self):
        return (f"Hypothesis(conf={self.confidence:.2f}, "
                f"+{self.confirmations}/-{self.refutations}): {self.text[:60]}")


# ── WorldModel ────────────────────────────────────────────────────────────────

class WorldModel:
    """
    Трекер состояния мира для одного ARC-AGI-3 эпизода.

    Хранит:
      • историю фреймов (FrameRecord)
      • карту действий → эффектов (action_effects)
      • набор гипотез о правилах (hypotheses)
      • выявленные паттерны (patterns)
      • сводку для LLM (summary_for_llm)
    """

    def __init__(self, env_id: str = ""):
        self.env_id = env_id
        self.created_at = time.time()
        self.frames: list[FrameRecord] = []

        # action → список изменений (для выявления паттернов)
        self.action_effects: defaultdict[Any, list[list[tuple]]] = defaultdict(list)

        # Гипотезы (индексируем по тексту для дедупликации)
        self.hypotheses: list[Hypothesis] = []

        # Выявленные повторяющиеся паттерны
        self.patterns: list[dict] = []

        # Посещённые хэши состояний (для обнаружения циклов)
        self._visited_hashes: Counter = Counter()

        # Статистика вознаграждений
        self.total_reward: float = 0.0
        self.positive_reward_steps: list[int] = []

    # ── Обновление ────────────────────────────────────────────────────────────

    def observe(
        self,
        step: int,
        action: Any,
        state: Any,
        reward: float = 0.0,
        done: bool = False,
    ) -> FrameRecord:
        """
        Добавляет новый фрейм в историю.
        Автоматически анализирует изменения и обновляет паттерны.
        """
        # Извлекаем сетку из разных форматов состояния
        grid_raw = state
        if isinstance(state, dict):
            grid_raw = state.get("frame", state.get("grid", state.get("observation", None)))
        grid = _grid_to_list(grid_raw)

        rec = FrameRecord(step=step, action=action, grid=grid,
                          reward=reward, done=done)
        self.frames.append(rec)
        self._visited_hashes[rec.hash] += 1
        self.total_reward += reward

        if reward > 0:
            self.positive_reward_steps.append(step)

        # Анализируем разницу с предыдущим кадром
        if len(self.frames) >= 2:
            prev = self.frames[-2]
            changes = _diff_sparse(prev.sparse, rec.sparse)
            if changes:
                self.action_effects[action].append(changes)
                self._detect_patterns(action, changes)
            else:
                log.debug("[WorldModel] Шаг %d: действие %s — изменений нет", step, action)

        return rec

    def _detect_patterns(self, action: Any, changes: list[tuple]):
        """
        Ищет повторяющиеся трансформации для данного действия.
        Если одни и те же изменения цвета встречаются ≥3 раз — фиксируем паттерн.
        """
        # Подпись трансформации: набор (old→new) без координат
        sig = tuple(sorted(set((c[2], c[3]) for c in changes)))
        pattern_key = (action, sig)

        # Считаем сколько раз встречался этот тип трансформации
        count = sum(
            1 for c_list in self.action_effects[action]
            if tuple(sorted(set((c[2], c[3]) for c in c_list))) == sig
        )

        if count >= 3:
            # Проверяем, не добавили ли уже этот паттерн
            existing = next(
                (p for p in self.patterns
                 if p.get("action") == action and p.get("sig") == sig),
                None
            )
            if existing:
                existing["count"] = count
            else:
                transitions = [
                    f"{_color_name(old)}→{_color_name(new)}" for old, new in sig
                ]
                self.patterns.append({
                    "action": action,
                    "sig": sig,
                    "transitions": transitions,
                    "count": count,
                })
                log.info(
                    "[WorldModel] Паттерн обнаружен: action=%s, %s (×%d)",
                    action, transitions, count
                )

    # ── Гипотезы ──────────────────────────────────────────────────────────────

    def add_hypothesis(self, text: str, confidence: float = 0.5,
                       source: str = "llm") -> Hypothesis:
        """Добавляет новую гипотезу (дедупликация по тексту)."""
        text = text.strip()
        existing = next((h for h in self.hypotheses
                         if h.text[:80] == text[:80]), None)
        if existing:
            existing.confirm(0.03)
            return existing
        h = Hypothesis(text, confidence=confidence, source=source)
        self.hypotheses.append(h)
        return h

    def best_hypothesis(self) -> Optional[Hypothesis]:
        """Гипотеза с наивысшим доверием."""
        if not self.hypotheses:
            return None
        return max(self.hypotheses, key=lambda h: h.confidence)

    def update_hypothesis_from_reward(self, reward: float, step: int):
        """Подтверждает / опровергает ведущую гипотезу по знаку вознаграждения."""
        h = self.best_hypothesis()
        if h is None:
            return
        if reward > 0:
            h.confirm()
            log.debug("[WorldModel] Гипотеза подтверждена (reward=%s, шаг=%d)", reward, step)
        elif reward < 0:
            h.refute()
            log.debug("[WorldModel] Гипотеза опровергнута (reward=%s, шаг=%d)", reward, step)

    # ── Запросы ───────────────────────────────────────────────────────────────

    def is_loop(self, threshold: int = 3) -> bool:
        """True, если текущее состояние уже встречалось ≥threshold раз."""
        if not self.frames:
            return False
        return self._visited_hashes[self.frames[-1].hash] >= threshold

    def current_frame(self) -> Optional[FrameRecord]:
        return self.frames[-1] if self.frames else None

    def action_coverage(self) -> dict[Any, int]:
        """Сколько раз каждое действие было выполнено."""
        return {a: len(eff) for a, eff in self.action_effects.items()}

    def most_effective_actions(self, top_n: int = 5) -> list[Any]:
        """
        Действия, чаще всего вызывающие ненулевые изменения.
        (Простая эвристика: больше изменений = интереснее.)
        """
        scored = []
        for action, effects in self.action_effects.items():
            # Средний размер изменений
            avg = sum(len(e) for e in effects) / max(len(effects), 1)
            scored.append((avg, action))
        scored.sort(reverse=True)
        return [a for _, a in scored[:top_n]]

    def reward_trend(self) -> str:
        """Текстовое описание тренда вознаграждений."""
        n = len(self.frames)
        if n == 0:
            return "нет данных"
        positive = len(self.positive_reward_steps)
        if positive == 0:
            return "нет положительных вознаграждений"
        last_pos = self.positive_reward_steps[-1]
        steps_since = n - last_pos
        return (f"{positive} положительных вознаграждений из {n} шагов; "
                f"последнее на шаге {last_pos} ({steps_since} шагов назад)")

    # ── Текстовые сводки для LLM ──────────────────────────────────────────────

    def history_summary(self, last_n: int = 20) -> str:
        """Компактная история последних N шагов для LLM-промпта."""
        records = self.frames[-last_n:]
        if not records:
            return "История пуста."
        lines = []
        for rec in records:
            action_effects = self.action_effects.get(rec.action, [])
            n_changes = len(action_effects[-1]) if action_effects else 0
            lines.append(
                f"  Шаг {rec.step}: action={rec.action} "
                f"→ изменений {n_changes}, reward={rec.reward:.2f}"
                + (" [DONE]" if rec.done else "")
            )
        return "\n".join(lines)

    def patterns_summary(self) -> str:
        """Текстовое описание обнаруженных паттернов."""
        if not self.patterns:
            return "Повторяющихся паттернов не обнаружено."
        lines = ["Обнаруженные паттерны трансформаций:"]
        for p in self.patterns[:10]:
            lines.append(
                f"  action={p['action']} → {', '.join(p['transitions'])} (×{p['count']})"
            )
        return "\n".join(lines)

    def full_summary(self) -> str:
        """Полная сводка для LLM: паттерны + гипотеза + тренд наград."""
        parts = [
            f"Среда: {self.env_id}",
            f"Шагов пройдено: {len(self.frames)}",
            f"Награды: {self.reward_trend()}",
            "",
            self.patterns_summary(),
        ]
        best = self.best_hypothesis()
        if best:
            parts += [
                "",
                f"Ведущая гипотеза (доверие {best.confidence:.0%}):",
                f"  {best.text}",
            ]
        if self.is_loop():
            parts.append("\n⚠️ Цикл обнаружен — текущее состояние уже встречалось.")
        return "\n".join(parts)

    # ── Сериализация ──────────────────────────────────────────────────────────

    def to_dict(self) -> dict:
        """Сериализация модели для сохранения в памяти Аргоса."""
        best = self.best_hypothesis()
        return {
            "env_id":         self.env_id,
            "steps":          len(self.frames),
            "total_reward":   round(self.total_reward, 3),
            "positive_steps": self.positive_reward_steps,
            "patterns":       [
                {"action": p["action"], "transitions": p["transitions"], "count": p["count"]}
                for p in self.patterns
            ],
            "best_hypothesis": best.text if best else None,
            "best_confidence": round(best.confidence, 3) if best else 0,
            "hypotheses_count": len(self.hypotheses),
        }

    def __repr__(self):
        return (
            f"WorldModel(env={self.env_id!r}, frames={len(self.frames)}, "
            f"hypotheses={len(self.hypotheses)}, patterns={len(self.patterns)})"
        )
