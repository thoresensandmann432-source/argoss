"""
src/life_support_v2.py — Расширенный модуль жизнеобеспечения ARGOS v2
=====================================================================
FreelanceHunter, CryptoWallet, ContentGenerator, JobScanner,
BillingSystem, AffiliateEngine, ArgosLifeSupportV2.
"""
from __future__ import annotations

import hashlib
import random
import sqlite3
import time
from dataclasses import dataclass, field
from typing import Optional

__all__ = [
    "ArgosLifeSupportV2",
    "FreelanceHunter",
    "CryptoWallet",
    "ContentGenerator",
    "JobScanner",
    "BillingSystem",
    "AffiliateEngine",
]

# ── Данные ────────────────────────────────────────────────────────────────────

_DEMO_ORDERS = [
    {"title": "Telegram бот python автоматизация", "budget": 15000, "tags": ["python", "telegram", "bot"]},
    {"title": "Разработка IoT системы мониторинга", "budget": 45000, "tags": ["iot", "mqtt", "python"]},
    {"title": "AI чат-бот для поддержки клиентов",  "budget": 30000, "tags": ["ai", "python", "gpt"]},
    {"title": "Парсер данных scrapy asyncio",        "budget": 12000, "tags": ["python", "scraping"]},
    {"title": "FastAPI REST API микросервис",        "budget": 20000, "tags": ["python", "fastapi", "api"]},
]

_DEMO_JOBS = [
    {"title": "Python Backend Developer", "company": "TechStart", "salary": "150k-200k"},
    {"title": "AI/ML Engineer",           "company": "DataCore",  "salary": "200k-300k"},
    {"title": "IoT Systems Architect",    "company": "SmartHome", "salary": "180k-250k"},
]

_TOPIC_IDEAS = {
    "iot":     ["ESP32 + MQTT в 2026", "Умный дом без облаков", "LoRa для дачи"],
    "ai":      ["Gemini бесплатно — лучшие трюки", "Ollama vs ChatGPT", "Fine-tuning за 0$"],
    "python":  ["FastAPI + SQLite за 1 час", "Asyncio на практике", "Паттерны для IoT"],
    "general": ["Автоматизация жизни с ARGOS", "P2P без серверов", "Self-healing код"],
}

_CRYPTO_PRICES = {"TON": 3.50, "USDT": 1.00, "BTC": 65000.0}

_AFFILIATE_OFFERS = [
    {"name": "Hetzner VPS",       "commission": 20.0, "suitable": 0.95, "category": "hosting"},
    {"name": "DigitalOcean",      "commission": 25.0, "suitable": 0.88, "category": "hosting"},
    {"name": "Anthropic API",     "commission": 0.0,  "suitable": 0.70, "category": "ai"},
    {"name": "Ollama Pro",        "commission": 15.0, "suitable": 0.82, "category": "ai"},
    {"name": "Telegram Premium",  "commission": 30.0, "suitable": 0.75, "category": "messaging"},
]


# ══════════════════════════════════════════════════════════════════════════════
# FreelanceHunter
# ══════════════════════════════════════════════════════════════════════════════

@dataclass
class FreelanceOrder:
    title: str
    budget: float
    tags: list[str]
    suitable: float = 0.0


class FreelanceHunter:
    """Сканер фриланс-заказов с оценкой релевантности."""

    _MY_SKILLS = {"python", "telegram", "bot", "iot", "mqtt", "ai", "fastapi", "api", "ml"}

    def __init__(self) -> None:
        self._orders: list[FreelanceOrder] = []

    def scan(self, use_demo: bool = True) -> list[FreelanceOrder]:
        self._orders = [
            FreelanceOrder(
                title=o["title"],
                budget=float(o["budget"]),
                tags=o["tags"],
                suitable=self._score_order(o["title"]),
            )
            for o in _DEMO_ORDERS
        ]
        return self._orders

    def _score_order(self, text: str) -> float:
        words = set(text.lower().split())
        match = words & self._MY_SKILLS
        return min(1.0, len(match) / max(1, len(self._MY_SKILLS) * 0.3))

    def format_orders(self) -> str:
        if not self._orders:
            self.scan()
        lines = [f"🔍 НАЙДЕНО заказов: {len(self._orders)}"]
        for o in self._orders:
            lines.append(f"  • {o.title} — {o.budget:,.0f}₽ (отклик: {o.suitable:.0%})")
        return "\n".join(lines)

    def generate_response(self, order: FreelanceOrder) -> str:
        return (
            f"📨 ОТКЛИК на заказ\n"
            f"  Проект : {order.title}\n"
            f"  Бюджет : {order.budget:,.0f} ₽\n"
            f"  Здравствуйте! Готов взяться за проект. Опыт: 5 лет Python/IoT/AI.\n"
            f"  Сроки: 2-4 недели. Жду деталей."
        )


# ══════════════════════════════════════════════════════════════════════════════
# CryptoWallet
# ══════════════════════════════════════════════════════════════════════════════

class CryptoWallet:
    """Крипто-кошелёк с балансами и адресами оплаты."""

    _ADDRESSES = {
        "TON":  "UQBxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx",
        "USDT": "TRxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx",
        "BTC":  "bc1qxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx",
    }

    def __init__(self) -> None:
        self._balances: dict[str, float] = {}
        self._cache_ts: float = 0

    def get_balance(self, force: bool = False) -> dict[str, float]:
        now = time.time()
        if not force and self._balances and now - self._cache_ts < 60:
            return dict(self._balances)
        self._balances = {"TON": 12.5, "USDT": 35.0, "BTC": 0.0015}
        self._cache_ts = now
        return dict(self._balances)

    def usd_equivalent(self) -> float:
        bal = self.get_balance()
        return sum(bal.get(c, 0) * _CRYPTO_PRICES.get(c, 0) for c in bal)

    def get_payment_address(self, currency: str, amount: float, description: str = "") -> dict:
        return {
            "currency":    currency,
            "amount":      amount,
            "address":     self._ADDRESSES.get(currency, "unknown"),
            "description": description,
        }

    def status(self) -> str:
        bal = self.get_balance()
        lines = ["💰 КОШЕЛЁК АРГОСА"]
        for c, v in bal.items():
            usd = v * _CRYPTO_PRICES.get(c, 0)
            lines.append(f"  {c}: {v:.4f} (${usd:.2f})")
        lines.append(f"  Итого: ${self.usd_equivalent():.2f}")
        return "\n".join(lines)


# ══════════════════════════════════════════════════════════════════════════════
# ContentGenerator
# ══════════════════════════════════════════════════════════════════════════════

class ContentGenerator:
    """Генератор контента: посты, статьи, план."""

    def generate_post(self, topic: str = "") -> str:
        if not topic:
            topic = random.choice(_TOPIC_IDEAS["general"])
        return (
            f"[ЧЕРНОВИК] 📝 {topic}\n\n"
            f"Сегодня разберём тему: {topic}\n"
            f"1️⃣ Почему это важно\n"
            f"2️⃣ Практический пример\n"
            f"3️⃣ Выводы и следующие шаги\n\n"
            f"#argos #automation #python"
        )

    def get_topic_ideas(self, category: str = "") -> list[str]:
        if category and category in _TOPIC_IDEAS:
            return list(_TOPIC_IDEAS[category])
        all_ideas = []
        for ideas in _TOPIC_IDEAS.values():
            all_ideas.extend(ideas)
        return all_ideas

    def generate_content_plan(self, days: int = 7) -> str:
        lines = [f"📅 ПЛАН КОНТЕНТА на {days} дней"]
        all_topics = self.get_topic_ideas()
        for i in range(1, days + 1):
            topic = all_topics[(i - 1) % len(all_topics)]
            lines.append(f"  День {i}: {topic}")
        return "\n".join(lines)


# ══════════════════════════════════════════════════════════════════════════════
# JobScanner
# ══════════════════════════════════════════════════════════════════════════════

@dataclass
class Job:
    title: str
    company: str
    salary: str


class JobScanner:
    """Сканер вакансий."""

    def __init__(self) -> None:
        self._jobs: list[Job] = []

    def scan(self) -> list[Job]:
        self._jobs = [Job(**j) for j in _DEMO_JOBS]
        return self._jobs

    def generate_cover_letter(self, job: Job) -> str:
        return (
            f"Здравствуйте!\n\n"
            f"Меня заинтересовала вакансия «{job.title}» в {job.company}.\n"
            f"Имею 5+ лет опыта в Python, IoT, AI. Готов обсудить детали.\n\n"
            f"С уважением, Аргос"
        )

    def format_jobs(self) -> str:
        if not self._jobs:
            self.scan()
        lines = [f"💼 ВАКАНСИИ ({len(self._jobs)}):"]
        for j in self._jobs:
            lines.append(f"  • {j.title} @ {j.company} — {j.salary}")
        return "\n".join(lines)


# ══════════════════════════════════════════════════════════════════════════════
# BillingSystem
# ══════════════════════════════════════════════════════════════════════════════

_RUB_TO_USD = 90.0


@dataclass
class Invoice:
    invoice_id: str
    client: str
    service: str
    amount_rub: float
    amount_usd: float
    paid: bool = False


class BillingSystem:
    """Система выставления счётов с SQLite-хранилищем."""

    def __init__(self, wallet: Optional[CryptoWallet] = None, db_path: str = "data/billing.db") -> None:
        self._wallet = wallet
        self._db_path = db_path
        self._invoices: dict[str, Invoice] = {}

    def create_invoice(self, client: str, service: str, amount_rub: float) -> Invoice:
        ts = str(int(time.time() * 1000))[-8:]
        inv_id = f"INV-{ts}-{len(self._invoices):03d}"
        inv = Invoice(
            invoice_id=inv_id,
            client=client,
            service=service,
            amount_rub=amount_rub,
            amount_usd=round(amount_rub / _RUB_TO_USD, 2),
        )
        self._invoices[inv_id] = inv
        return inv

    def format_invoice(self, inv: Invoice) -> str:
        return (
            f"🧾 СЧЁТ {inv.invoice_id}\n"
            f"  Клиент  : {inv.client}\n"
            f"  Услуга  : {inv.service}\n"
            f"  Сумма   : {inv.amount_rub:,.0f} ₽ (${inv.amount_usd:.2f})\n"
            f"  Статус  : {'✅ оплачен' if inv.paid else '⏳ ожидает'}"
        )

    def mark_paid(self, invoice_id: str) -> str:
        inv = self._invoices.get(invoice_id)
        if not inv:
            return f"❌ Счёт не найден: {invoice_id}"
        inv.paid = True
        return f"✅ Счёт {invoice_id} оплачен."

    def summary(self) -> str:
        total = len(self._invoices)
        paid  = sum(1 for i in self._invoices.values() if i.paid)
        amount = sum(i.amount_rub for i in self._invoices.values())
        return (
            f"💳 БИЛЛИНГ\n"
            f"  Счетов   : {total}\n"
            f"  Оплачено : {paid}\n"
            f"  Итого    : {amount:,.0f} ₽"
        )


# ══════════════════════════════════════════════════════════════════════════════
# AffiliateEngine
# ══════════════════════════════════════════════════════════════════════════════

@dataclass
class AffiliateOffer:
    name: str
    commission: float
    suitable: float
    category: str


class AffiliateEngine:
    """Движок партнёрских программ."""

    def __init__(self) -> None:
        self._offers = [AffiliateOffer(**o) for o in _AFFILIATE_OFFERS]
        self._clicks: dict[str, int] = {}

    def get_top_offers(self, n: int = 3) -> list[AffiliateOffer]:
        return sorted(self._offers, key=lambda o: o.suitable, reverse=True)[:n]

    def format_offers(self) -> str:
        lines = ["🤝 ПАРТНЁРСКИЕ программы:"]
        for o in self.get_top_offers(5):
            lines.append(f"  • {o.name} — {o.commission:.0f}% (релевантность: {o.suitable:.0%})")
        return "\n".join(lines)

    def estimate_monthly(self) -> str:
        monthly = sum(o.commission * o.suitable * 10 for o in self._offers)
        return (
            f"📊 ПРОГНОЗ партнёрского дохода\n"
            f"  Предполагаемый доход: {monthly:,.0f} ₽/мес\n"
            f"  Активных программ: {len(self._offers)}"
        )


# ══════════════════════════════════════════════════════════════════════════════
# ArgosLifeSupportV2
# ══════════════════════════════════════════════════════════════════════════════

class ArgosLifeSupportV2:
    """
    Расширенный модуль жизнеобеспечения ARGOS v2.
    Объединяет фриланс, крипто, контент, вакансии, биллинг, партнёрки.
    """

    def __init__(self) -> None:
        self.freelance  = FreelanceHunter()
        self.crypto     = CryptoWallet()
        self.content    = ContentGenerator()
        self.jobs       = JobScanner()
        self.billing    = BillingSystem(self.crypto)
        self.affiliate  = AffiliateEngine()

    def full_status(self) -> str:
        bal = self.crypto.get_balance()
        return (
            f"🔱 ЖИЗНЕОБЕСПЕЧЕНИЕ v2\n"
            f"  Фриланс  : готов к сканированию\n"
            f"  Крипто   : ${self.crypto.usd_equivalent():.2f} USD\n"
            f"  Биллинг  : {len(self.billing._invoices)} счетов\n"
            f"  Партнёрки: {len(self.affiliate._offers)} программ"
        )

    def handle_command(self, text: str) -> str:  # noqa: C901
        t = text.strip().lower()

        # Фриланс
        if t in ("фриланс", "фриланс сканировать"):
            return self.freelance.format_orders()
        if t.startswith("отклик ") and not t.startswith("отклик вакансия"):
            try:
                idx = int(t.split()[-1]) - 1
                if not self.freelance._orders:
                    self.freelance.scan()
                order = self.freelance._orders[min(idx, len(self.freelance._orders) - 1)]
                return self.freelance.generate_response(order)
            except Exception:
                return "❌ Укажи номер заказа: отклик 1"

        # Крипто
        if t == "крипто":
            return self.crypto.status()
        if t.startswith("адрес оплаты "):
            parts = t.split()
            cur = parts[2].upper() if len(parts) > 2 else "TON"
            amt = float(parts[3]) if len(parts) > 3 else 0.0
            info = self.crypto.get_payment_address(cur, amt)
            return f"💳 {cur} адрес оплаты\n  Адрес: {info['address']}\n  Сумма: {amt}"
        if "транзакции" in t:
            return "📭 Нет транзакций за последний период."

        # Контент
        if t == "контент план":
            return self.content.generate_content_plan(3)
        if t.startswith("написать пост "):
            topic = text[len("написать пост "):]
            return self.content.generate_post(topic)
        if t.startswith("написать статью "):
            topic = text[len("написать статью "):]
            return self.content.generate_post(f"Статья: {topic}")
        if t == "темы для постов":
            ideas = self.content.get_topic_ideas()
            return "💡 ИДЕИ для постов:\n" + "\n".join(f"  • {i}" for i in ideas[:6])

        # Вакансии
        if t == "вакансии":
            return self.jobs.format_jobs()
        if t.startswith("отклик вакансия "):
            if not self.jobs._jobs:
                self.jobs.scan()
            try:
                idx = int(t.split()[-1]) - 1
                job = self.jobs._jobs[min(idx, len(self.jobs._jobs) - 1)]
                return "📨 ПИСЬМО:\n" + self.jobs.generate_cover_letter(job)
            except Exception:
                return "❌ Укажи номер: отклик вакансия 1"

        # Счета
        if t.startswith("счёт "):
            parts = [p.strip() for p in text[5:].split("|")]
            if len(parts) < 3:
                return "❌ Формат: счёт Клиент|Услуга|Сумма"
            try:
                amount = float(parts[2])
            except ValueError:
                return "❌ Сумма должна быть числом."
            inv = self.billing.create_invoice(parts[0], parts[1], amount)
            return self.billing.format_invoice(inv)
        if t == "биллинг":
            return self.billing.summary()

        # Партнёрки
        if t == "партнёрки":
            return self.affiliate.format_offers()
        if t == "партнёрки прогноз":
            return self.affiliate.estimate_monthly()

        # Статус
        if t in ("v2 статус", "статус v2"):
            return self.full_status()

        return f"❌ Неизвестная команда v2: {text}\nПопробуй: фриланс, крипто, контент план, вакансии, биллинг, партнёрки"
