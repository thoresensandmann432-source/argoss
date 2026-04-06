"""
arc_agi3_skill.py — ARGOS ↔ ARC-AGI-3 Competition Interface

ARC-AGI-3 — интерактивный бенчмарк для агентов:
  • Агент наблюдает 64×64 сетку (16 цветов), выбирает действия
  • Нет явных инструкций — агент сам обнаруживает цель и правила среды
  • Оценка RHAE = (шагов_человека / шагов_агента)² ← нужна эффективность
  • API: arc.make(env_id) → reset() → step(action) → (state, reward, done, info)

Интеграция с Аргосом:
  • execute_intent: "arc старт", "arc решай <env>", "arc статус", "arc стоп"
  • LLM-рассуждение через _ask_ollama (RX 580 для анализа, RX 560 для быстрых решений)
  • WorldModel сохраняет гипотезы о правилах среды в памяти Аргоса

Команды:
  arc статус          — статус подключения и последний результат
  arc среды           — список доступных окружений
  arc решай <env_id>  — запустить агента на среде
  arc шаг <действие>  — ручной шаг (для тестирования)
  arc стоп            — остановить текущий эпизод
"""

from __future__ import annotations

import os
import json
import time
import threading
from typing import Any, Optional
from src.argos_logger import get_logger
from src.mind.world_model import WorldModel
from src.mind.arc_planner import ArcPlanner

log = get_logger("argos.arc3")

# ── Константы ─────────────────────────────────────────────────────────────────
ARC3_API_KEY_ENV   = "ARC3_API_KEY"
ARC3_API_BASE      = "https://three.arcprize.org"
ARC3_LOCAL_PKG     = "arc-agi"          # pip install arc-agi
ARC3_MAX_STEPS     = 500               # лимит шагов за эпизод
ARC3_EXPLORE_STEPS = 30               # фаза разведки перед планированием

# 16 цветов ARC-AGI-3 (индекс → имя для LLM-промпта)
ARC3_COLOR_NAMES = [
    "black", "blue", "red", "green", "yellow",
    "grey", "magenta", "orange", "azure", "maroon",
    "cyan", "lime", "brown", "white", "pink", "purple"
]


class ARC3Agent:
    """
    Агент для решения задач ARC-AGI-3.

    Фазы работы:
      1. EXPLORE  — случайные/систематические действия, наблюдение эффектов
      2. MODEL     — LLM анализирует изменения и строит гипотезу о правилах
      3. PLAN      — LLM строит план действий к цели
      4. EXECUTE   — выполнение плана, адаптация при расхождении
    """

    def __init__(self, core=None):
        self.core = core
        self._game = None
        self._env_id: str = ""
        self._step_count = 0
        self._episode_start = 0.0
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._last_result: dict = {}
        self._wm: Optional[WorldModel] = None    # структурированная модель мира
        self._planner: Optional[ArcPlanner] = None
        # Legacy поддержка — заполняется из _wm при необходимости
        self._history: list[dict] = []

    # ── Подключение к ARC-AGI-3 ───────────────────────────────────────────────

    def _load_arc(self):
        """Пытается импортировать arc-agi. Возвращает модуль или None."""
        try:
            import arc  # pip install arc-agi
            return arc
        except ImportError:
            return None

    def _connect_api(self) -> bool:
        """Проверяет API-ключ и соединение с three.arcprize.org."""
        key = os.getenv(ARC3_API_KEY_ENV, "").strip()
        if not key:
            return False
        try:
            import requests
            r = requests.get(
                f"{ARC3_API_BASE}/api/envs",
                headers={"Authorization": f"Bearer {key}"},
                timeout=5
            )
            return r.ok
        except Exception:
            return False

    def status(self) -> str:
        arc = self._load_arc()
        api_ok = self._connect_api()
        lines = ["🎮 ARC-AGI-3 Agent:"]

        if arc:
            lines.append("  ✅ arc-agi пакет установлен")
        else:
            lines.append("  ❌ arc-agi не найден → pip install arc-agi")

        if api_ok:
            lines.append("  ✅ API-ключ действителен (three.arcprize.org)")
        elif os.getenv(ARC3_API_KEY_ENV):
            lines.append("  ⚠️ API-ключ задан, но соединение не проверено (офлайн?)")
        else:
            lines.append(f"  ❌ API-ключ не задан → .env: {ARC3_API_KEY_ENV}=ваш_ключ")

        if self._running:
            elapsed = int(time.time() - self._episode_start)
            lines.append(f"  🔄 Эпизод: {self._env_id} | шаг {self._step_count} | {elapsed}с")
            if self._wm:
                lines.append(f"  {self._wm.full_summary()}")
            if self._planner:
                lines.append(f"  {self._planner.stats()}")
        elif self._last_result:
            r = self._last_result
            lines.append(
                f"  📊 Последний: {r.get('env_id','?')} | "
                f"RHAE {r.get('rhae', 0):.4f} | "
                f"{r.get('steps', 0)} шагов | {r.get('status','?')} | "
                f"паттернов: {r.get('patterns', 0)}"
            )
            hyp = r.get('hypothesis', '')
            if hyp and hyp != '—':
                lines.append(f"  💡 {hyp[:120]}")
        return "\n".join(lines)

    # ── Наблюдение ─────────────────────────────────────────────────────────────

    def _frame_to_text(self, frame) -> str:
        """
        Конвертирует 64×64 фрейм в компактное текстовое представление для LLM.
        Возвращает только непустые (non-black) клетки: (row,col,color).
        """
        if frame is None:
            return "(пустой фрейм)"
        try:
            lines = []
            if hasattr(frame, 'tolist'):
                grid = frame.tolist()
            elif isinstance(frame, list):
                grid = frame
            else:
                return str(frame)[:200]

            non_black = []
            for r, row in enumerate(grid):
                for c, val in enumerate(row):
                    if val != 0:  # 0 = black / background
                        name = ARC3_COLOR_NAMES[val] if val < len(ARC3_COLOR_NAMES) else str(val)
                        non_black.append(f"({r},{c})={name}")

            if not non_black:
                return "Сетка пуста (только чёрный фон)"
            # Группируем для читаемости
            return f"Непустых клеток: {len(non_black)}\n" + ", ".join(non_black[:80])
        except Exception as e:
            return f"Ошибка разбора фрейма: {e}"

    def _diff_frames(self, f1, f2) -> str:
        """Возвращает список изменённых клеток между двумя фреймами."""
        try:
            g1 = f1.tolist() if hasattr(f1, 'tolist') else f1
            g2 = f2.tolist() if hasattr(f2, 'tolist') else f2
            changes = []
            for r in range(min(len(g1), len(g2))):
                for c in range(min(len(g1[r]), len(g2[r]))):
                    if g1[r][c] != g2[r][c]:
                        old = ARC3_COLOR_NAMES[g1[r][c]] if g1[r][c] < 16 else str(g1[r][c])
                        new = ARC3_COLOR_NAMES[g2[r][c]] if g2[r][c] < 16 else str(g2[r][c])
                        changes.append(f"({r},{c}): {old}→{new}")
            if not changes:
                return "Изменений нет"
            return f"{len(changes)} изменений: " + ", ".join(changes[:30])
        except Exception:
            return "Не удалось сравнить фреймы"

    # ── Рассуждение через LLM ─────────────────────────────────────────────────

    def _llm_infer_rules(self, history_summary: str) -> str:
        """LLM анализирует историю эпизода и строит гипотезу о правилах среды."""
        if not self.core:
            return "LLM недоступен"
        prompt = (
            f"Ты анализируешь интерактивную среду ARC-AGI-3.\n"
            f"Наблюдения за {len(self._history)} шагов:\n"
            f"{history_summary}\n\n"
            f"Задача: вывести гипотезу о правилах среды.\n"
            f"Что является целью? Как действия влияют на состояние?\n"
            f"Ответь кратко (3-5 предложений)."
        )
        try:
            result = self.core._ask_ollama("", prompt)
            return result or "Нет ответа"
        except Exception as e:
            return f"Ошибка LLM: {e}"

    def _llm_plan_action(self, state_text: str, hypothesis: str, available_actions: list) -> Any:
        """LLM выбирает следующее действие исходя из гипотезы и текущего состояния."""
        if not self.core:
            return available_actions[0] if available_actions else 0
        actions_str = str(available_actions[:20])
        prompt = (
            f"Среда ARC-AGI-3. Гипотеза о правилах: {hypothesis}\n"
            f"Текущее состояние:\n{state_text}\n"
            f"Доступные действия: {actions_str}\n"
            f"Выбери ОДНО следующее действие (только число/строку из списка).\n"
            f"Ответь только значением действия, без объяснений."
        )
        try:
            result = self.core._ask_ollama("", prompt)
            if result:
                result = result.strip()
                # Попытка привести к типу из available_actions
                for act in available_actions:
                    if str(act) == result:
                        return act
                # Fallback: первое доступное
                return available_actions[0]
        except Exception:
            pass
        return available_actions[0] if available_actions else 0

    # ── Главный цикл агента ───────────────────────────────────────────────────

    def solve(self, env_id: str, mode: str = "auto") -> str:
        """
        Запускает агент на среде env_id.
        mode: "auto" — полный автономный цикл (explore→model→plan→execute)
              "explore" — только фаза разведки
        """
        arc = self._load_arc()
        if not arc:
            return ("❌ arc-agi не установлен.\n"
                    "Установи: pip install arc-agi\n"
                    "Ключ API: зарегистрируйся на https://three.arcprize.org")

        if self._running:
            return f"⚠️ Уже запущен эпизод: {self._env_id}. Остановить: 'arc стоп'"

        self._thread = threading.Thread(
            target=self._solve_loop,
            args=(arc, env_id, mode),
            daemon=True, name=f"arc3-{env_id}"
        )
        self._thread.start()
        return f"🎮 Запускаю ARC-AGI-3 агента на среде `{env_id}` (режим: {mode})..."

    def _solve_loop(self, arc, env_id: str, mode: str):
        """Основной цикл решения (выполняется в фоне)."""
        self._running = True
        self._env_id = env_id
        self._step_count = 0
        self._episode_start = time.time()
        self._history = []

        # ── Инициализация WorldModel + ArcPlanner ─────────────────────────
        wm = WorldModel(env_id=env_id)
        self._wm = wm
        available_actions = list(range(16))
        planner = ArcPlanner(available_actions=available_actions, core=self.core)
        self._planner = planner

        done = False
        info: Any = {}

        try:
            game = arc.make(env_id)
            state = game.reset()
            self._game = game
            log.info("[ARC3] Среда %s запущена.", env_id)

            # Записываем начальное состояние (action=None, step=0)
            wm.observe(step=0, action=None, state=state, reward=0.0, done=False)

            # ── Главный цикл ──────────────────────────────────────────────
            while not done and self._step_count < ARC3_MAX_STEPS and self._running:
                # Выбор действия через ArcPlanner
                action = planner.next_action(wm)

                state, reward, done, info = game.step(action)
                self._step_count += 1

                # Обновляем список действий если API предоставил новый
                if isinstance(info, dict) and 'actions' in info:
                    planner.update_actions(info['actions'])

                # Записываем в WorldModel
                rec = wm.observe(
                    step=self._step_count,
                    action=action,
                    state=state,
                    reward=reward,
                    done=done,
                )

                # Обновляем гипотезу по знаку вознаграждения
                wm.update_hypothesis_from_reward(reward, self._step_count)

                if reward > 0:
                    log.info("[ARC3] +Награда %.2f на шаге %d (action=%s)", reward, self._step_count, action)

                # ── Моделирование: строим гипотезу после EXPLORE-фазы ────
                if (mode == "auto"
                        and self._step_count == ARC3_EXPLORE_STEPS
                        and not wm.hypotheses):
                    history_text = wm.history_summary(last_n=ARC3_EXPLORE_STEPS)
                    patterns_text = wm.patterns_summary()
                    hypothesis_text = self._llm_infer_rules(
                        f"{history_text}\n\n{patterns_text}"
                    )
                    h = wm.add_hypothesis(hypothesis_text, confidence=0.5, source="llm")
                    log.info("[ARC3] Гипотеза сформирована (conf=%.2f): %s", h.confidence, h.text[:80])

                    # Сохраняем в память Аргоса
                    if self.core and hasattr(self.core, 'memory') and self.core.memory:
                        self.core.memory.store_fact(
                            category="arc3",
                            key=f"hypothesis_{env_id}",
                            value=hypothesis_text,
                        )

                if done:
                    log.info("[ARC3] Среда завершена на шаге %d.", self._step_count)
                    break

            # ── Результат ─────────────────────────────────────────────────
            elapsed = time.time() - self._episode_start
            human_steps = 10  # заглушка — реальное значение из API
            if isinstance(info, dict):
                human_steps = info.get('human_steps', info.get('optimal_steps', 10))
            rhae = (human_steps / max(self._step_count, 1)) ** 2

            best_h = wm.best_hypothesis()
            self._last_result = {
                "env_id":      env_id,
                "steps":       self._step_count,
                "human_steps": human_steps,
                "rhae":        round(rhae, 4),
                "status":      "solved" if done else "timeout",
                "elapsed_s":   round(elapsed, 1),
                "hypothesis":  best_h.text if best_h else "—",
                "patterns":    len(wm.patterns),
                "world_model": wm.to_dict(),
            }
            log.info("[ARC3] Эпизод завершён: %s", self._last_result)

        except Exception as e:
            log.error("[ARC3] Ошибка в эпизоде %s: %s", env_id, e)
            self._last_result = {"env_id": env_id, "status": "error", "error": str(e)}
        finally:
            self._running = False
            self._game = None

    def stop(self) -> str:
        if not self._running:
            return "ℹ️ Нет активного эпизода."
        self._running = False
        return f"⛔ Эпизод {self._env_id} остановлен на шаге {self._step_count}."

    def step_manual(self, action_str: str) -> str:
        """Ручной шаг для отладки."""
        if not self._game or not self._running:
            return "❌ Нет активного эпизода. Запусти: arc решай <env_id>"
        try:
            action = int(action_str)
        except ValueError:
            action = action_str

        state, reward, done, info = self._game.step(action)
        self._step_count += 1
        frame = state.get('frame') if isinstance(state, dict) else state
        frame_text = self._frame_to_text(frame)
        return (f"Шаг {self._step_count}: action={action}\n"
                f"Reward: {reward} | Done: {done}\n"
                f"Состояние:\n{frame_text[:300]}")

    def list_envs(self) -> str:
        """Список доступных сред."""
        arc = self._load_arc()
        if not arc:
            return "❌ arc-agi не установлен"
        try:
            envs = arc.list_envs() if hasattr(arc, 'list_envs') else []
            if not envs:
                return ("🎮 Среды ARC-AGI-3:\n"
                        "  Установи arc-agi и получи ключ на https://three.arcprize.org\n"
                        "  Затем: arc среды — покажет список")
            return "🎮 Доступные среды:\n" + "\n".join(f"  • {e}" for e in envs[:20])
        except Exception as e:
            return f"❌ Ошибка получения сред: {e}"


# ── Синглтон и handle() ───────────────────────────────────────────────────────
_agent: ARC3Agent | None = None


def handle(text: str, core=None) -> str | None:
    global _agent
    t = text.lower().strip()

    if not any(k in t for k in ["arc", "arc-agi", "arcagi"]):
        return None

    if _agent is None:
        _agent = ARC3Agent(core=core)

    if any(k in t for k in ["arc статус", "arc status", "arc3 статус"]):
        return _agent.status()

    if any(k in t for k in ["arc среды", "arc список", "arc envs", "arc environments"]):
        return _agent.list_envs()

    if any(k in t for k in ["arc стоп", "arc stop", "arc3 стоп"]):
        return _agent.stop()

    import re
    # arc шаг <действие>
    m_step = re.search(r'arc\s+шаг\s+(\S+)', t)
    if m_step:
        return _agent.step_manual(m_step.group(1))

    # arc решай <env_id>
    m_solve = re.search(r'arc\s+(?:решай|решить|solve|run|запусти)\s+(\S+)', t)
    if m_solve:
        return _agent.solve(m_solve.group(1))

    # arc <env_id> напрямую
    m_direct = re.search(r'^arc\s+(\w{2,}[\d]+)', t)
    if m_direct:
        return _agent.solve(m_direct.group(1))

    return None


TRIGGERS = [
    "arc", "arc-agi", "arcagi", "arc status", "arc статус",
    "arc среды", "arc envs", "arc environments", "arc стоп", "arc stop",
    "arc шаг", "arc решай", "arc решить", "arc solve", "arc run",
]


def setup(core=None):
    pass
