"""
arc_planner.py — ARC-AGI-3 Action Selector with LLM Reasoning

Планировщик действий для ARC-AGI-3 агента.
Использует WorldModel для принятия обоснованных решений:

  Стратегии:
    EXPLORE   — систематическое исследование действий
    EXPLOIT   — использование известных паттернов с наивысшей наградой
    LLM       — LLM-рассуждение на основе гипотезы + текущего состояния
    RANDOM    — случайное действие (escape из циклов)

Логика выбора стратегии:
  1. Если < MIN_EXPLORE_STEPS шагов — EXPLORE (нужен охват действий)
  2. Если цикл обнаружен — RANDOM (escape)
  3. Если есть паттерн с положительной наградой — EXPLOIT
  4. Если есть уверенная гипотеза (≥0.65) — LLM
  5. Иначе — EXPLORE / LLM смешанно
"""

from __future__ import annotations

import os
import random
import time
from typing import Any, Optional

from src.argos_logger import get_logger
from src.mind.world_model import WorldModel, ARC3_COLORS

log = get_logger("argos.arc3.planner")

# ── Константы ─────────────────────────────────────────────────────────────────
MIN_EXPLORE_STEPS = int(os.getenv("ARC3_MIN_EXPLORE", "30"))
LLM_CONFIDENCE_THRESHOLD = float(os.getenv("ARC3_LLM_CONF", "0.55"))
MAX_LLM_CALLS_PER_EPISODE = int(os.getenv("ARC3_MAX_LLM_CALLS", "80"))
CYCLE_ESCAPE_WINDOW = int(os.getenv("ARC3_CYCLE_ESCAPE", "5"))


# ── Стратегии ─────────────────────────────────────────────────────────────────
class Strategy:
    EXPLORE = "explore"
    EXPLOIT = "exploit"
    LLM     = "llm"
    RANDOM  = "random"


# ── ArcPlanner ────────────────────────────────────────────────────────────────

class ArcPlanner:
    """
    Планировщик действий для ARC-AGI-3.

    Использование:
        planner = ArcPlanner(available_actions=[0,1,...,15], core=argos_core)
        action = planner.next_action(world_model)
    """

    def __init__(
        self,
        available_actions: list[Any] | None = None,
        core=None,
    ):
        self.available_actions: list[Any] = available_actions or list(range(16))
        self.core = core

        self._llm_calls = 0
        self._explore_idx = 0             # указатель для систематического EXPLORE
        self._escape_counter = 0          # счётчик RANDOM шагов при цикле
        self._last_strategy = Strategy.EXPLORE

        # Кэш наиболее эффективных действий (обновляется из WorldModel)
        self._effective_actions: list[Any] = []

    # ── Публичный API ─────────────────────────────────────────────────────────

    def update_actions(self, available_actions: list[Any]):
        """Обновляет список доступных действий (может прийти из info['actions'])."""
        if available_actions:
            self.available_actions = available_actions

    def next_action(self, wm: WorldModel) -> Any:
        """
        Выбирает следующее действие на основе WorldModel.
        Возвращает выбранное действие.
        """
        step = len(wm.frames)
        strategy = self._choose_strategy(wm, step)
        self._last_strategy = strategy

        action = self._execute_strategy(strategy, wm)
        log.debug("[Planner] Шаг %d: стратегия=%s, action=%s", step, strategy, action)
        return action

    def explain_last(self) -> str:
        """Объясняет, почему была выбрана последняя стратегия."""
        return f"Последняя стратегия: {self._last_strategy}"

    # ── Выбор стратегии ───────────────────────────────────────────────────────

    def _choose_strategy(self, wm: WorldModel, step: int) -> str:
        actions = len(wm.action_effects)  # кол-во уже испытанных действий

        # 1. Escape из цикла
        if wm.is_loop(threshold=2):
            if self._escape_counter <= 0:
                self._escape_counter = CYCLE_ESCAPE_WINDOW
                log.info("[Planner] Цикл! Переключаюсь на RANDOM для выхода.")
            self._escape_counter -= 1
            return Strategy.RANDOM

        # 2. Минимальная разведка
        if step < MIN_EXPLORE_STEPS or actions < len(self.available_actions) // 2:
            return Strategy.EXPLORE

        # 3. Паттерн с наградой → EXPLOIT
        rewarded_patterns = [
            p for p in wm.patterns
            if p["action"] in wm.positive_reward_steps  # хотя бы раз давал +
        ]
        if rewarded_patterns:
            return Strategy.EXPLOIT

        # 4. Уверенная гипотеза + остаток LLM-бюджета → LLM
        best = wm.best_hypothesis()
        if (best and best.confidence >= LLM_CONFIDENCE_THRESHOLD
                and self._llm_calls < MAX_LLM_CALLS_PER_EPISODE):
            return Strategy.LLM

        # 5. Смешанный режим: 2/3 EXPLORE, 1/3 LLM
        if (self._llm_calls < MAX_LLM_CALLS_PER_EPISODE
                and step % 3 == 0 and best):
            return Strategy.LLM

        return Strategy.EXPLORE

    # ── Исполнение стратегий ──────────────────────────────────────────────────

    def _execute_strategy(self, strategy: str, wm: WorldModel) -> Any:
        if strategy == Strategy.RANDOM:
            return random.choice(self.available_actions)

        if strategy == Strategy.EXPLORE:
            return self._explore(wm)

        if strategy == Strategy.EXPLOIT:
            return self._exploit(wm)

        if strategy == Strategy.LLM:
            result = self._llm(wm)
            if result is not None:
                return result
            # Fallback если LLM не ответил
            return self._explore(wm)

        return random.choice(self.available_actions)

    def _explore(self, wm: WorldModel) -> Any:
        """
        Систематический обход: сначала каждое действие по разу,
        потом — наиболее эффективные по результатам.
        """
        # Приоритет: ещё не испытанные действия
        tried = set(wm.action_effects.keys())
        untried = [a for a in self.available_actions if a not in tried]
        if untried:
            return untried[0]

        # Все попробованы — переходим к наиболее результативным
        effective = wm.most_effective_actions(top_n=5)
        if effective:
            # Циклически перебираем топ-5
            self._explore_idx = (self._explore_idx + 1) % len(effective)
            return effective[self._explore_idx % len(effective)]

        # Полный fallback
        self._explore_idx = (self._explore_idx + 1) % len(self.available_actions)
        return self.available_actions[self._explore_idx]

    def _exploit(self, wm: WorldModel) -> Any:
        """
        Использует паттерны с наибольшей суммарной наградой.
        """
        # Ищем действие, после которого получали положительную награду
        best_action = None
        best_score = -1.0
        for step_idx, rec in enumerate(wm.frames):
            if rec.reward > 0 and rec.action is not None:
                # Проверяем, есть ли паттерн для этого действия
                effects = wm.action_effects.get(rec.action, [])
                if effects:
                    score = rec.reward * len(effects)
                    if score > best_score:
                        best_score = score
                        best_action = rec.action

        if best_action is not None:
            return best_action

        # Fallback: паттерны с наибольшим количеством изменений
        effective = wm.most_effective_actions(top_n=3)
        return effective[0] if effective else self.available_actions[0]

    def _llm(self, wm: WorldModel) -> Optional[Any]:
        """
        Запрашивает LLM для выбора следующего действия.
        Строит промпт из WorldModel, парсит ответ.
        """
        if not self.core:
            return None

        curr = wm.current_frame()
        if curr is None:
            return None

        best = wm.best_hypothesis()
        hypothesis_text = best.text if best else "Гипотеза ещё не сформирована."

        state_text = curr.as_text(max_cells=60)
        patterns_text = wm.patterns_summary()
        coverage = wm.action_coverage()
        coverage_text = ", ".join(
            f"{a}:{n}" for a, n in sorted(coverage.items())
        )[:200]

        prompt = (
            "Ты управляешь агентом в среде ARC-AGI-3.\n"
            f"Гипотеза о правилах: {hypothesis_text}\n\n"
            f"Текущее состояние (шаг {curr.step}):\n{state_text}\n\n"
            f"Паттерны: {patterns_text}\n"
            f"Покрытие действий: {coverage_text}\n\n"
            f"Доступные действия: {self.available_actions[:20]}\n\n"
            "Выбери ОДНО следующее действие для максимизации награды.\n"
            "Ответь ТОЛЬКО числом или строкой из списка доступных действий. "
            "Без объяснений."
        )

        try:
            result = None
            for _m, _s in [
                ("_ask_gemini",    ""),
                ("_ask_gigachat",  ""),
                ("_ask_yandexgpt", ""),
                ("_ask_grok",      ""),
                ("_ask_openai",    ""),
                ("_ask_ollama",    ""),
            ]:
                if result:
                    break
                if not hasattr(self.core, _m):
                    continue
                try:
                    result = getattr(self.core, _m)(_s, prompt)
                except Exception:
                    pass
            self._llm_calls += 1
            if not result:
                return None
            parsed = self._parse_action(result.strip())
            if parsed is not None:
                log.debug("[Planner] LLM выбрал action=%s (вызов №%d)", parsed, self._llm_calls)
                return parsed
        except Exception as e:
            log.warning("[Planner] LLM ошибка: %s", e)

        return None

    def _parse_action(self, text: str) -> Optional[Any]:
        """Пытается извлечь действие из строки ответа LLM."""
        text = text.strip().split("\n")[0].strip()

        # Сначала — прямое совпадение с доступными действиями
        for act in self.available_actions:
            if str(act) == text:
                return act

        # Первое число в строке
        import re
        m = re.search(r"\b(\d+)\b", text)
        if m:
            num = int(m.group(1))
            if num in self.available_actions:
                return num
            # Ближайшее допустимое действие
            closest = min(self.available_actions,
                          key=lambda a: abs(int(a) - num) if isinstance(a, int) else 999)
            return closest

        return None

    # ── Сводка ────────────────────────────────────────────────────────────────

    def stats(self) -> str:
        return (
            f"ArcPlanner: стратегия={self._last_strategy}, "
            f"LLM-вызовов={self._llm_calls}/{MAX_LLM_CALLS_PER_EPISODE}, "
            f"explore_idx={self._explore_idx}"
        )
