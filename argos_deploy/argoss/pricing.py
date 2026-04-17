"""
src/pricing.py — Модуль ценообразования ARGOS
=============================================
Расходы, конкуренты, тарифы, ROI, питч, план продаж, оценка проектов.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

__all__ = ["ArgosPricing", "CostItem", "_COSTS", "_COMPETITORS", "_TIERS", "_PROJECT_TYPES"]

_USD_TO_RUB = 90.0


# ── Структуры данных ──────────────────────────────────────────────────────────

@dataclass
class CostItem:
    """Статья расходов."""
    name: str
    usd_low: float
    usd_high: float
    note: str

    @property
    def rub_low(self) -> float:
        return self.usd_low * _USD_TO_RUB

    @property
    def rub_high(self) -> float:
        return self.usd_high * _USD_TO_RUB


@dataclass
class Competitor:
    name: str
    price_usd: float
    features: str
    our_advantage: str


@dataclass
class PricingTier:
    name: str
    price_rub: float
    features: list[str]
    target: str


@dataclass
class ProjectType:
    name: str
    hours_low: int
    hours_high: int
    rate_rub: int
    description: str


# ── Данные расходов ───────────────────────────────────────────────────────────

_COSTS: list[CostItem] = [
    CostItem("Ollama (локальный LLM)",       0.0,   0.0,   "Бесплатно на своём железе"),
    CostItem("Gemini API (Flash)",           0.0,   5.0,   "15 RPM бесплатно, платно от $5"),
    CostItem("VPS Hetzner CX11",             3.29,  5.83,  "1 vCPU, 2GB RAM"),
    CostItem("Domain .ru",                   0.5,   2.0,   "Годовая стоимость"),
    CostItem("GigaChat (Сбер)",              0.0,   0.0,   "1M токенов бесплатно"),
    CostItem("IBM Watsonx (Lite)",           0.0,   0.0,   "300k токенов/мес бесплатно"),
    CostItem("Telegram Bot (размещение)",    0.0,   0.0,   "Полностью бесплатно"),
    CostItem("SQLite (хранилище)",           0.0,   0.0,   "Встроено"),
    CostItem("GitHub Actions (CI/CD)",       0.0,   0.0,   "2000 мин/мес бесплатно"),
    CostItem("Cloudflare Tunnel",            0.0,   0.0,   "Бесплатный план"),
]

_COMPETITORS: list[Competitor] = [
    Competitor("AutoGPT",       0.0,   "AI агент, GitHub",      "Локальный, интеграция IoT"),
    Competitor("Jarvis (Iron)", 0.0,   "Концепт, не продукт",   "Реальный рабочий продукт"),
    Competitor("Home Assistant",12.0,  "Умный дом, облако",     "AI + умный дом + финансы"),
    Competitor("Hetzner Cloud", 5.83,  "VPS хостинг",           "Полная автономность"),
    Competitor("ChatGPT Plus",  20.0,  "Чат + DALL-E",          "Без ограничений API, локально"),
    Competitor("Claude Pro",    20.0,  "Чат, анализ",           "Интеграция со всей системой"),
    Competitor("Copilot",       10.0,  "Код + Office",          "Универсальность платформы"),
    Competitor("Notion AI",     10.0,  "Заметки + AI",          "Полный стек возможностей"),
]

_TIERS: list[PricingTier] = [
    PricingTier(
        "Starter",
        0,
        ["Базовый AI (Ollama)", "Telegram бот", "Умный дом базовый"],
        "Частные лица / DIY",
    ),
    PricingTier(
        "Pro",
        2900,
        ["Все AI провайдеры", "P2P сеть", "IoT полный стек", "Приоритетная поддержка"],
        "Фрилансеры / малый бизнес",
    ),
    PricingTier(
        "Business",
        9900,
        ["White-label", "API доступ", "SLA 99.9%", "Обучение команды", "Telegram group"],
        "Средний бизнес",
    ),
    PricingTier(
        "Enterprise",
        49000,
        ["On-premise", "Кастомизация", "Dedicated support", "Интеграция с ERP/CRM"],
        "Крупный бизнес / интеграторы",
    ),
]

_PROJECT_TYPES: list[ProjectType] = [
    ProjectType("telegram бот",  8,  40,  2500, "Telegram боты любой сложности"),
    ProjectType("умный дом",     20, 80,  3000, "IoT и автоматизация дома"),
    ProjectType("ai система",    30, 120, 3500, "AI-решения на базе ARGOS"),
    ProjectType("аргос установка", 4, 16, 2000, "Развёртывание и настройка ARGOS"),
    ProjectType("api интеграция", 10, 30, 2800, "REST/MQTT/WebSocket интеграции"),
    ProjectType("аналитика",     15, 60, 3000, "Дашборды и аналитические системы"),
]


# ══════════════════════════════════════════════════════════════════════════════
# ArgosPricing
# ══════════════════════════════════════════════════════════════════════════════

class ArgosPricing:
    """Модуль ценообразования и рыночного анализа ARGOS."""

    def handle_command(self, text: str) -> str:  # noqa: C901
        t = text.strip().lower()

        # Алиасы
        if t in ("затраты",):
            t = "расходы"
        elif t in ("конкуренты",):
            t = "рынок"
        elif t in ("прайс-лист",):
            t = "прайс"
        elif t in ("тарифные планы",):
            t = "тарифы"

        if t in ("расходы", "expenses"):
            return self._costs()
        if t in ("рынок", "market"):
            return self._market()
        if t in ("прайс", "price"):
            return self._price()
        if t in ("тарифы", "tiers"):
            return self._tiers()
        if t.startswith("roi"):
            return self._roi(t)
        if t.startswith("питч цена") or t.startswith("pitch"):
            return self._pitch()
        if t.startswith("план продаж"):
            return self._sales_plan()
        if t.startswith("оценка"):
            return self._estimate(text[len("оценка"):].strip())

        return self._help()

    # ── Методы ────────────────────────────────────────────────────────────────

    def _costs(self) -> str:
        lines = ["💰 РАСХОДЫ АРГОСА (мес):"]
        total_low = total_high = 0.0
        for c in _COSTS:
            if c.usd_low == 0 and c.usd_high == 0:
                lines.append(f"  ✅ Бесплатно : {c.name}")
            else:
                lines.append(
                    f"  💵 {c.name}: ${c.usd_low:.2f}–${c.usd_high:.2f} "
                    f"({c.rub_low:.0f}–{c.rub_high:.0f}₽)"
                )
            total_low  += c.usd_low
            total_high += c.usd_high
        lines.append(f"\n  ИТОГО: ${total_low:.2f}–${total_high:.2f}/мес")
        return "\n".join(lines)

    def _market(self) -> str:
        lines = ["🏆 КОНКУРЕНТНЫЙ анализ:"]
        lines.append(f"  {'Решение':<20} {'Цена/мес':<12} {'Преимущество Аргоса'}")
        lines.append("  " + "─" * 60)
        lines.append(f"  {'Аргос':<20} {'Бесплатно':<12} {'— ВЫ ЗДЕСЬ —'}")
        for c in _COMPETITORS:
            price = f"${c.price_usd:.0f}" if c.price_usd > 0 else "Бесплатно"
            lines.append(f"  {c.name:<20} {price:<12} {c.our_advantage[:30]}")
        return "\n".join(lines)

    def _price(self) -> str:
        lines = ["📋 ПРАЙС-ЛИСТ ARGOS:"]
        for pt in _PROJECT_TYPES:
            low  = pt.hours_low  * pt.rate_rub
            high = pt.hours_high * pt.rate_rub
            lines.append(
                f"  • {pt.name.title()}: {low:,.0f}–{high:,.0f} ₽  "
                f"({pt.hours_low}–{pt.hours_high}ч × {pt.rate_rub}₽/ч)"
            )
        return "\n".join(lines)

    def _tiers(self) -> str:
        lines = ["💎 ТАРИФНЫЕ ПЛАНЫ:"]
        for t in _TIERS:
            price = f"{t.price_rub:,.0f} ₽/мес" if t.price_rub > 0 else "Бесплатно"
            lines.append(f"\n  🔷 {t.name} — {price}")
            lines.append(f"     Для: {t.target}")
            for f in t.features:
                lines.append(f"     ✓ {f}")
        return "\n".join(lines)

    def _roi(self, text: str) -> str:
        target = "клиент" if "клиент" in text else "общий"
        return (
            f"📈 ROI АРГОСА ({target})\n"
            f"  Инвестиция     : ~5 000 ₽ (настройка)\n"
            f"  Экономия/мес   : ~18 000 ₽ (замена SaaS)\n"
            f"  Автоматизация  : +30% продуктивности\n"
            f"  ROI за 3 мес   : 1080%\n"
            f"  Окупаемость    : < 10 дней"
        )

    def _pitch(self) -> str:
        return (
            "🚀 ПИТЧ ЦЕНЫ ARGOS\n\n"
            "  Конкуренты берут $20–$50/мес за отдельные функции.\n"
            "  ARGOS даёт ВСЁ это за $0–$6/мес:\n"
            "    ✅ AI ассистент (Gemini + Ollama)\n"
            "    ✅ Умный дом (7 типов систем)\n"
            "    ✅ P2P сеть нод\n"
            "    ✅ Telegram бот + Web панель\n"
            "    ✅ Промышленные протоколы\n\n"
            "  ROI: 1080% за первые 3 месяца."
        )

    def _sales_plan(self) -> str:
        return (
            "📊 ПЛАН ПРОДАЖ ARGOS\n\n"
            "  НЕДЕЛЯ 1: 3 демо → 1 клиент (Telegram бот, 15k₽)\n"
            "  НЕДЕЛЯ 2: 5 демо → 2 клиента (умный дом, 30k₽)\n"
            "  НЕДЕЛЯ 3: 10 демо → 3 клиента (AI система, 45k₽)\n"
            "  НЕДЕЛЯ 4: 15 демо → 5 клиентов (микс, 75k₽)\n\n"
            "  Месяц 1 итого: ~165 000 ₽"
        )

    def _estimate(self, project_text: str) -> str:
        pt = project_text.lower()

        # Ищем совпадение по ключевым словам
        for ptype in _PROJECT_TYPES:
            keywords = ptype.name.lower().split()
            if any(k in pt for k in keywords):
                low  = ptype.hours_low  * ptype.rate_rub
                high = ptype.hours_high * ptype.rate_rub
                return (
                    f"💰 Оценка проекта: {ptype.name.title()}\n"
                    f"  Стоимость: {low:,.0f}–{high:,.0f} ₽\n"
                    f"  Срок: {ptype.hours_low}–{ptype.hours_high} часов\n"
                    f"  Ставка: {ptype.rate_rub} ₽/час"
                )

        # Грубая оценка если не нашли
        return (
            f"💰 Грубая оценка проекта: «{project_text[:40]}»\n"
            f"  Базовая стоимость: 15 000–90 000 ₽\n"
            f"  Срок: 1–4 недели\n"
            f"  Уточните детали для точной оценки."
        )

    def _help(self) -> str:
        return (
            "💰 ЦЕНООБРАЗОВАНИЕ ARGOS — команды:\n"
            "  расходы | рынок | прайс | тарифы\n"
            "  roi клиент | питч цена | план продаж\n"
            "  оценка [тип проекта]"
        )
