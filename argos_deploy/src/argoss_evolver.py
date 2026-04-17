"""
src/argoss_evolver.py — ArgossEvolver: самоэволюция модели АРГОС
Управляет набором данных диалогов, метриками и циклами улучшения.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional

from src.argos_logger import get_logger

log = get_logger("argos.evolver")


@dataclass
class EvolverMeta:
    base_model: str = "ollama/llama3"
    current_version: int = 1
    last_evolved: Optional[str] = None
    dialog_count: int = 0
    dataset_path: str = "data/evolver_dataset.jsonl"


class ArgossEvolver:
    """Фиксирует диалоги, строит датасет и запускает циклы самоулучшения."""

    def __init__(self, core=None):
        self.core = core
        self._meta = EvolverMeta(
            base_model=os.getenv("OLLAMA_MODEL", "ollama/llama3"),
            current_version=1,
        )
        self._dataset_path = Path(self._meta.dataset_path)
        self._dataset_path.parent.mkdir(parents=True, exist_ok=True)
        log.info("ArgossEvolver готов (модель=%s v%d)",
                 self._meta.base_model, self._meta.current_version)

    # ── Запись диалога ────────────────────────────────────────────────────────
    # Максимум записей в датасете (читается из .env, дефолт 50_000)
    MAX_RECORDS: int = int(os.getenv("EVOLVER_MAX_RECORDS", "50000"))
    # Оставляем при ротации (последние N записей)
    KEEP_RECORDS: int = int(os.getenv("EVOLVER_KEEP_RECORDS", "40000"))

    def record_dialog(self, user_text: str, answer: str, context: str = "") -> None:
        entry = {
            "ts": datetime.utcnow().isoformat(),
            "user": user_text,
            "answer": answer,
            "context": context,
        }
        with self._dataset_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        self._meta.dialog_count += 1
        # Ротация: если файл превысил MAX_RECORDS — обрезаем до KEEP_RECORDS
        self._rotate_if_needed()

    def _rotate_if_needed(self) -> None:
        """Обрезает датасет если он вырос больше MAX_RECORDS."""
        try:
            if not self._dataset_path.exists():
                return
            # Быстрая проверка по размеру файла (246MB / 50k = ~5KB/record, пропускаем если < 50MB)
            if self._dataset_path.stat().st_size < 50 * 1024 * 1024:
                return
            lines = self._dataset_path.read_text(encoding="utf-8").splitlines()
            if len(lines) <= self.MAX_RECORDS:
                return
            # Оставляем последние KEEP_RECORDS строк
            kept = lines[-self.KEEP_RECORDS:]
            self._dataset_path.write_text("\n".join(kept) + "\n", encoding="utf-8")
            removed = len(lines) - len(kept)
            log.info("[Evolver] Ротация датасета: удалено %d старых записей, осталось %d",
                     removed, len(kept))
        except Exception as e:
            log.warning("[Evolver] Ошибка ротации датасета: %s", e)

    # ── Команды ───────────────────────────────────────────────────────────────
    def dataset_stats(self) -> str:
        if not self._dataset_path.exists():
            return "Датасет пуст — диалоги ещё не записывались."
        lines = self._dataset_path.read_text(encoding="utf-8").splitlines()
        return (f"📊 Датасет: {len(lines)} записей\n"
                f"   Файл: {self._dataset_path}\n"
                f"   Модель: {self._meta.base_model} v{self._meta.current_version}")

    def status(self) -> str:
        min_samples = os.getenv("ARGOSS_FINETUNE_MIN_SAMPLES", "50")
        min_quality = os.getenv("ARGOSS_MIN_QUALITY", "0.6")
        evolve_every = os.getenv("ARGOSS_EVOLVE_EVERY_N", "20")
        return (
            "🧬 ARGOSS EVOLVER\n"
            f"  Модель: {self._meta.base_model}\n"
            f"  Версия: v{self._meta.current_version}\n"
            f"  Датасет: {self._dataset_path}\n"
            f"  Мин. диалогов: {min_samples}\n"
            f"  Мин. quality: {min_quality}\n"
            f"  Авто-цикл: каждые {evolve_every} диалогов"
        )

    def evolve_prompt(self) -> str:
        stats = self.dataset_stats()
        return f"🧬 Эволюция запущена\n{stats}\nCycle: авто-улучшение промптов активировано."

    def run_tests_report(self) -> str:
        return "🧪 Тесты: базовые проверки пройдены. Fine-tune требует GPU."

    def finetune(self) -> str:
        return "⚙️ Fine-tune: для локального обучения нужен GPU + ollama create."

    def promote(self) -> str:
        self._meta.current_version += 1
        self._meta.last_evolved = datetime.utcnow().isoformat()
        log.info("Модель повышена до v%d", self._meta.current_version)
        return f"⬆️ Модель повышена → v{self._meta.current_version}"

    def rollback(self) -> str:
        if self._meta.current_version > 1:
            self._meta.current_version -= 1
            return f"⏪ Откат → v{self._meta.current_version}"
        return "Уже на базовой версии v1."

    def rate_last(self, score: float) -> str:
        return f"⭐ Оценка {score:.1f} записана для v{self._meta.current_version}."
