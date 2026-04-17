"""
src/life_support.py — Модуль жизнеобеспечения Аргоса
=====================================================
Финансовый трекер, контракты, расходы, ROI, питчи, провайдеры.
"""
from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from typing import Optional

__all__ = ["ArgosLifeSupport"]


@dataclass
class Contract:
    name: str
    client: str
    amount: float


@dataclass
class Expense:
    category: str
    description: str
    amount: float


# ── Данные питчей ─────────────────────────────────────────────────────────────
_PITCHES = [
    "🚀 Питч 1: ARGOS — ваш автономный ИИ-помощник 24/7. Telegram-бот, умный дом, аналитика.",
    "💡 Питч 2: Замените 5 SaaS-сервисов одной системой. ARGOS экономит $200+/мес.",
    "🏠 Питч 3: Умный дом нового уровня — ARGOS управляет 7 типами систем без облаков.",
    "📊 Питч 4: ROI за 3 месяца: автоматизация рутины + аналитика = +30% продуктивности.",
    "🌐 Питч 5: P2P ИИ-сеть — ваши устройства объединяются в единый интеллект.",
]

_PROVIDERS = [
    {"name": "Gemini", "model": "gemini-2.0-flash", "price": "Free (15 RPM)", "url": "ai.google.dev"},
    {"name": "Ollama", "model": "llama3:8b", "price": "Free (local)", "url": "ollama.com"},
    {"name": "GigaChat", "model": "GigaChat-Pro", "price": "Free (1M tokens)", "url": "gigachat.ru"},
    {"name": "Watson", "model": "llama-3-70b", "price": "Free (300k/month)", "url": "ibm.com/watsonx"},
    {"name": "YandexGPT", "model": "YandexGPT Lite", "price": "Free (grant 4000₽)", "url": "ya.cloud"},
]


class ArgosLifeSupport:
    """
    Модуль жизнеобеспечения ARGOS.

    Отслеживает контракты, расходы, считает ROI,
    генерирует питчи и показывает провайдеров.
    """

    def __init__(self, core=None) -> None:
        self._core = core
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._contracts: list[Contract] = []
        self._expenses: list[Expense] = []

    # ── Управление ────────────────────────────────────────────────────────────

    def start(self) -> str:
        if self._running:
            return "⚠️ Life Support уже активен."
        self._running = True
        return "✅ Life Support активирован."

    def stop(self) -> str:
        self._running = False
        return "🛑 Life Support остановлен."

    # ── Команды ───────────────────────────────────────────────────────────────

    def handle_command(self, text: str) -> str:
        text = text.strip()

        if text in ("финансы", "finances"):
            return self._finances()

        if text.startswith("контракт "):
            return self._add_contract(text[len("контракт "):])

        if text in ("заработок", "earnings"):
            return self._earnings()

        if text.startswith("расход "):
            return self._add_expense(text[len("расход "):])

        if text in ("окупаемость", "roi"):
            return self._roi()

        if text.startswith("питч"):
            return self._pitch(text)

        if text in ("провайдеры", "providers"):
            return self._providers()

        if text in ("статус", "status"):
            return self._status()

        return self._help()

    # ── Приватные методы ──────────────────────────────────────────────────────

    def _finances(self) -> str:
        income  = sum(c.amount for c in self._contracts)
        expense = sum(e.amount for e in self._expenses)
        profit  = income - expense
        lines = [
            "💰 ФИНАНСЫ АРГОСА",
            f"  Доходы  : {income:,.0f} ₽",
            f"  Расходы : {expense:,.0f} ₽",
            f"  Прибыль : {profit:,.0f} ₽",
        ]
        return "\n".join(lines)

    def _add_contract(self, args: str) -> str:
        parts = [p.strip() for p in args.split("|")]
        if len(parts) < 3:
            return "❌ Формат: контракт Имя|Клиент|Сумма"
        try:
            amount = float(parts[2])
        except ValueError:
            return "❌ Сумма должна быть числом."
        self._contracts.append(Contract(parts[0], parts[1], amount))
        return f"✅ Контракт добавлен: {parts[0]} — {amount:,.0f} ₽"

    def _earnings(self) -> str:
        if not self._contracts:
            return "📭 Нет контрактов."
        lines = ["💼 ЗАРАБОТОК:"]
        for c in self._contracts:
            lines.append(f"  • {c.name} ({c.client}): {c.amount:,.0f} ₽")
        return "\n".join(lines)

    def _add_expense(self, args: str) -> str:
        parts = [p.strip() for p in args.split("|")]
        if len(parts) < 3:
            return "❌ Формат: расход Категория|Описание|Сумма"
        try:
            amount = float(parts[2])
        except ValueError:
            return "❌ Сумма должна быть числом."
        self._expenses.append(Expense(parts[0], parts[1], amount))
        return f"✅ Расход добавлен: {parts[1]} — {amount:,.2f} ₽"

    def _roi(self) -> str:
        income  = sum(c.amount for c in self._contracts)
        expense = sum(e.amount for e in self._expenses)
        invest  = expense if expense > 0 else 1
        roi_pct = ((income - expense) / invest) * 100
        return (
            f"📈 ROI АРГОСА\n"
            f"  Инвестиции : {expense:,.2f} ₽\n"
            f"  Доходы     : {income:,.2f} ₽\n"
            f"  ROI        : {roi_pct:.1f}%"
        )

    def _pitch(self, text: str) -> str:
        for i in range(1, 6):
            if str(i) in text:
                return _PITCHES[i - 1]
        return _PITCHES[0]

    def _providers(self) -> str:
        lines = ["🤖 AI-ПРОВАЙДЕРЫ (бесплатные):"]
        for p in _PROVIDERS:
            lines.append(f"  • {p['name']} ({p['model']}) — {p['price']}")
        return "\n".join(lines)

    def _status(self) -> str:
        return (
            f"⚙️ LIFE SUPPORT\n"
            f"  Статус    : {'активен' if self._running else 'остановлен'}\n"
            f"  Контракты : {len(self._contracts)}\n"
            f"  Расходы   : {len(self._expenses)}"
        )

    def _help(self) -> str:
        return (
            "🆘 ЖИЗНЕОБЕСПЕЧЕНИЕ — команды:\n"
            "  финансы | заработок | окупаемость\n"
            "  контракт Имя|Клиент|Сумма\n"
            "  расход Кат|Описание|Сумма\n"
            "  питч [1-5] | провайдеры | статус"
        )
