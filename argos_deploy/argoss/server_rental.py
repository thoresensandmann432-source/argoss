"""
src/server_rental.py — Модуль аренды серверов ARGOS
====================================================
ServerCatalog, AccountManager, DeployManager, ArgosServerRental.
"""
from __future__ import annotations

import hashlib
import time
import uuid
from dataclasses import dataclass, field
from typing import Optional

__all__ = [
    "ArgosServerRental", "ServerCatalog", "AccountManager",
    "DeployManager", "ServerPlan",
]


# ══════════════════════════════════════════════════════════════════════════════
# ServerPlan
# ══════════════════════════════════════════════════════════════════════════════

@dataclass
class ServerPlan:
    provider: str
    model: str
    cpu: str
    ram_gb: int
    disk_gb: int
    bandwidth: str
    price_month: float
    price_hour: float
    location: str
    gpu: bool = False
    note: str = ""

    def score(self) -> float:
        """Оценка сервера (ниже цена + больше ресурсов = лучше)."""
        if self.price_month == 0:
            base = 100.0
        else:
            base = (self.ram_gb * 2 + self.disk_gb * 0.1) / max(self.price_month, 0.01)
        return round(min(base, 100.0), 2)

    def to_dict(self) -> dict:
        return {
            "provider":    self.provider,
            "model":       self.model,
            "cpu":         self.cpu,
            "RAM":         f"{self.ram_gb} GB",
            "disk":        f"{self.disk_gb} GB",
            "bandwidth":   self.bandwidth,
            "price_month": self.price_month,
            "location":    self.location,
            "gpu":         self.gpu,
        }


# ══════════════════════════════════════════════════════════════════════════════
# ServerCatalog
# ══════════════════════════════════════════════════════════════════════════════

class ServerCatalog:
    """Каталог серверов с фильтрами."""

    PLANS: list[ServerPlan] = [
        ServerPlan("Oracle",       "Always Free",     "1vCPU", 1,   50,  "Unlimited", 0.0,  0.0,    "US", False, "Бесплатно навсегда"),
        ServerPlan("Oracle",       "Ampere Free",     "4vCPU ARM", 24, 200, "Unlimited", 0.0, 0.0,  "US", False, "ARM64 бесплатно"),
        ServerPlan("Google Cloud", "e2-micro",        "2vCPU", 1,   30,  "1GB",       0.0,  0.0,    "US", False, "Always Free"),
        ServerPlan("AWS",          "t2.micro",        "1vCPU", 1,   30,  "15GB",      0.0,  0.0,    "US", False, "Free Tier 12мес"),
        ServerPlan("Hetzner",      "CX11",            "2vCPU", 2,   20,  "20TB",      3.29, 0.005,  "EU", False),
        ServerPlan("Hetzner",      "CX21",            "2vCPU", 4,   40,  "20TB",      5.83, 0.009,  "EU", False),
        ServerPlan("Hetzner",      "CX31",            "2vCPU", 8,   80,  "20TB",      8.21, 0.012,  "EU", False),
        ServerPlan("Hetzner",      "CAX11 ARM",       "2vCPU", 4,   40,  "20TB",      3.79, 0.006,  "EU", False),
        ServerPlan("DigitalOcean", "Basic 1GB",       "1vCPU", 1,   25,  "1TB",       4.0,  0.006,  "US", False),
        ServerPlan("DigitalOcean", "Basic 2GB",       "1vCPU", 2,   50,  "2TB",       6.0,  0.009,  "US", False),
        ServerPlan("Vultr",        "VC2 1GB",         "1vCPU", 1,   25,  "1TB",       2.50, 0.004,  "US", False),
        ServerPlan("Linode",       "Nanode 1GB",      "1vCPU", 1,   25,  "1TB",       5.0,  0.0075, "US", False),
        ServerPlan("Vast.ai",      "RTX 3090",        "4vCPU", 16,  0,   "Unl",       0.30, 0.30,   "EU", True,  "GPU аренда/час"),
        ServerPlan("RunPod",       "RTX 4090",        "8vCPU", 24,  50,  "Unl",       0.69, 0.69,   "US", True,  "GPU почасово"),
    ]

    def free_options(self) -> list[ServerPlan]:
        return [p for p in self.PLANS if p.price_month == 0.0]

    def gpu_options(self) -> list[ServerPlan]:
        return [p for p in self.PLANS if p.gpu]

    def best_for_argos(self) -> list[ServerPlan]:
        """Лучшие серверы для ARGOS: цена < $10, без GPU."""
        candidates = [p for p in self.PLANS if p.price_month < 10 and not p.gpu]
        return sorted(candidates, key=lambda p: p.score(), reverse=True)[:5]

    def recommendation(
        self,
        budget: float = 0.0,
        need_gpu: bool = False,
    ) -> str:
        if need_gpu:
            plans = self.gpu_options()
            title = "🎮 GPU серверы для тяжёлых задач:"
        elif budget == 0.0:
            plans = self.free_options()
            title = "🆓 Бесплатные серверы:"
        else:
            plans = [p for p in self.PLANS if p.price_month <= budget]
            title = f"💵 Серверы до ${budget:.0f}/мес:"

        if not plans:
            return f"❌ Серверы по заданным критериям не найдены."

        lines = [title]
        for p in plans[:5]:
            price = f"${p.price_month:.2f}/мес" if p.price_month > 0 else "Бесплатно"
            lines.append(f"  • {p.provider} {p.model} — {price}  ({p.cpu}, {p.ram_gb}GB RAM)")
        return "\n".join(lines)

    def compare(self, providers: list[str]) -> str:
        prov_lower = [p.lower() for p in providers]
        found = [p for p in self.PLANS if any(pp in p.provider.lower() for pp in prov_lower)]
        if not found:
            return "❌ Провайдер не найден в каталоге."
        lines = [f"📊 Сравнение {', '.join(providers)}:"]
        for p in found[:6]:
            price = f"${p.price_month:.2f}/мес" if p.price_month > 0 else "Бесплатно"
            lines.append(f"  {p.provider} {p.model}: {price} | {p.cpu} | {p.ram_gb}GB")
        return "\n".join(lines)


# ══════════════════════════════════════════════════════════════════════════════
# AccountManager
# ══════════════════════════════════════════════════════════════════════════════

_PLATFORM_INFO = {
    "hetzner":       {"name": "Hetzner",       "url": "hetzner.com",       "signup": "3 мин"},
    "digitalocean":  {"name": "DigitalOcean",  "url": "digitalocean.com",  "signup": "5 мин"},
    "oracle":        {"name": "Oracle Cloud",  "url": "oracle.com/cloud",  "signup": "15 мин"},
    "aws":           {"name": "AWS",           "url": "aws.amazon.com",    "signup": "10 мин"},
    "vultr":         {"name": "Vultr",         "url": "vultr.com",         "signup": "3 мин"},
    "github":        {"name": "GitHub",        "url": "github.com",        "signup": "2 мин"},
    "vast.ai":       {"name": "Vast.ai",       "url": "vast.ai",           "signup": "5 мин"},
}


@dataclass
class AccountRequest:
    id: str
    platform: str
    email: str
    purpose: str
    status: str = "pending"
    created_at: float = field(default_factory=time.time)


class AccountManager:
    """Менеджер аккаунтов на хостинг-платформах."""

    def __init__(self) -> None:
        self._requests: list[AccountRequest] = []
        self._accounts: dict[str, dict] = {}

    def request_account(self, platform: str, email: str, purpose: str) -> AccountRequest:
        req_id = hashlib.md5(f"{platform}{email}{time.time()}".encode()).hexdigest()
        req = AccountRequest(id=req_id, platform=platform.lower(), email=email, purpose=purpose)
        self._requests.append(req)
        return req

    def confirm_account(self, short_id: str) -> str:
        req = next((r for r in self._requests if r.id.endswith(short_id)), None)
        if not req:
            return f"❌ Запрос {short_id} не найден."
        req.status = "confirmed"
        info = _PLATFORM_INFO.get(req.platform, {"name": req.platform, "url": "", "signup": "?"})
        steps = [
            f"✅ ПОДТВЕРЖДЕНО: аккаунт {info['name']}",
            f"",
            f"  1. Перейди на {info.get('url', req.platform)}",
            f"  2. Нажми 'Sign Up' / 'Регистрация'",
            f"  3. Введи email: {req.email}",
            f"  4. Подтверди email",
            f"  5. Выбери бесплатный тариф",
            f"  6. Сообщи ARGOS credentials командой: зарегистрирован {req.platform}",
        ]
        return "\n".join(steps)

    def register_created(self, platform: str, credentials: dict) -> str:
        self._accounts[platform.lower()] = credentials
        return f"✅ Аккаунт {platform} зарегистрирован в системе."

    def pending_requests(self) -> list[AccountRequest]:
        return [r for r in self._requests if r.status == "pending"]

    def all_accounts(self) -> str:
        if not self._accounts:
            return "📭 Аккаунтов пока нет."
        lines = ["🗂️ Зарегистрированные аккаунты:"]
        for platform, creds in self._accounts.items():
            lines.append(f"  • {platform}: {list(creds.keys())}")
        return "\n".join(lines)

    def show_platform(self, name: str) -> str:
        info = _PLATFORM_INFO.get(name.lower())
        if not info:
            return f"❌ Платформа «{name}» не найдена в базе."
        return (
            f"🖥️ {info['name']}\n"
            f"  Сайт    : {info['url']}\n"
            f"  Регистрация: {info['signup']}"
        )


# ══════════════════════════════════════════════════════════════════════════════
# DeployManager
# ══════════════════════════════════════════════════════════════════════════════

@dataclass
class Server:
    id: str
    provider: str
    ip: str
    plan: str
    model: str
    cost_month: float
    status: str = "active"


class DeployManager:
    """Менеджер деплоя ARGOS на серверы."""

    def __init__(self) -> None:
        self._servers: dict[str, Server] = {}
        self._deploys: dict[str, dict] = {}

    def register_server(
        self,
        provider: str,
        ip: str,
        plan: str,
        model: str,
        cost_month: float,
    ) -> Server:
        srv_id = str(uuid.uuid4())[:8]
        srv = Server(id=srv_id, provider=provider, ip=ip, plan=plan,
                     model=model, cost_month=cost_month)
        self._servers[srv_id] = srv
        return srv

    def request_deploy(self, server_id: str) -> dict:
        srv = self._servers.get(server_id)
        if not srv:
            return {"error": f"Сервер {server_id} не найден.", "online": False}
        deploy_id = str(uuid.uuid4())[:8]
        deploy = {
            "id": deploy_id,
            "server_id": server_id,
            "server_ip": srv.ip,
            "provider": srv.provider,
            "status": "pending",
        }
        self._deploys[deploy_id] = deploy
        return deploy

    def confirm_deploy(self, short_id: str) -> str:
        dep = next((d for d in self._deploys.values() if d["id"].endswith(short_id)), None)
        if not dep:
            return f"❌ Деплой {short_id} не найден."
        dep["status"] = "deployed"
        ip = dep["server_ip"]
        return (
            f"✅ ПОДТВЕРЖДЁН деплой на {ip}\n"
            f"  ssh root@{ip}\n"
            f"  cd /opt/argos && python main.py --no-gui"
        )

    def list_servers(self) -> str:
        if not self._servers:
            return "📭 Серверов нет. Добавь командой: добавь сервер"
        lines = ["🖥️ МОИ СЕРВЕРЫ:"]
        for srv in self._servers.values():
            lines.append(
                f"  • {srv.provider} {srv.ip} [{srv.model}] "
                f"${srv.cost_month:.2f}/мес — {srv.status}"
            )
        return "\n".join(lines)

    def check_server(self, server_id: str) -> dict:
        srv = self._servers.get(server_id)
        if not srv:
            return {"error": f"Сервер {server_id} не найден.", "online": False}
        return {"server_id": server_id, "ip": srv.ip, "online": True, "status": srv.status}


# ══════════════════════════════════════════════════════════════════════════════
# ArgosServerRental
# ══════════════════════════════════════════════════════════════════════════════

class ArgosServerRental:
    """
    Модуль аренды серверов ARGOS.
    Объединяет каталог, аккаунты и деплой.
    """

    def __init__(self, core=None) -> None:
        self._core = core
        self.catalog = ServerCatalog()
        self.accounts = AccountManager()
        self.deploy = DeployManager()

    def handle_command(self, text: str) -> str:  # noqa: C901
        t = text.strip().lower()

        if t in ("серверы", "servers"):
            return self.catalog.recommendation(6.0)

        if t in ("бесплатные", "free"):
            return self.catalog.recommendation(0.0)

        if t == "gpu":
            return self.catalog.recommendation(need_gpu=True)

        if t in ("топ", "лучшие"):
            plans = self.catalog.best_for_argos()
            lines = ["🏆 ЛУЧШИЕ серверы для ARGOS:"]
            for p in plans:
                price = f"${p.price_month:.2f}/мес" if p.price_month > 0 else "Бесплатно"
                lines.append(f"  • {p.provider} {p.model} — {price} | score={p.score():.1f}")
            return "\n".join(lines)

        if t.startswith("бюджет "):
            try:
                budget = float(t.split()[1])
                return self.catalog.recommendation(budget)
            except (ValueError, IndexError):
                return "❌ Укажи бюджет числом: бюджет 5"

        if t.startswith("сравни "):
            providers = [p.strip() for p in text[7:].split(",")]
            return self.catalog.compare(providers)

        if t == "аккаунты":
            return self.accounts.all_accounts()

        if t.startswith("платформа "):
            return self.accounts.show_platform(text[10:].strip())

        if t.startswith("создай аккаунт "):
            parts = [p.strip() for p in text[15:].split("|")]
            if len(parts) < 3:
                return "❌ Формат: создай аккаунт Платформа|Email|Цель"
            req = self.accounts.request_account(parts[0], parts[1], parts[2])
            return (
                f"📋 ЗАПРОС аккаунта {parts[0]}\n"
                f"  ID: {req.id[-8:]}\n"
                f"  Email: {parts[1]}\n"
                f"  Подтверди: подтверди аккаунт {req.id[-8:]}"
            )

        if t.startswith("подтверди аккаунт "):
            short_id = text[18:].strip()
            return self.accounts.confirm_account(short_id)

        if t in ("мои серверы", "my servers"):
            return self.deploy.list_servers()

        if t.startswith("добавь сервер "):
            parts = [p.strip() for p in text[14:].split("|")]
            if len(parts) < 4:
                return "❌ Формат: добавь сервер Провайдер|IP|Модель|Цена"
            try:
                cost = float(parts[3])
            except ValueError:
                return "❌ Цена должна быть числом."
            srv = self.deploy.register_server(parts[0], parts[1], parts[2], parts[2], cost)
            return (
                f"✅ Сервер добавлен: {srv.ip}\n"
                f"  ID: {srv.id}\n"
                f"  Деплой: деплой {srv.id}"
            )

        if t.startswith("деплой "):
            srv_id = text[7:].strip()
            result = self.deploy.request_deploy(srv_id)
            if "error" in result:
                return f"❌ {result['error']}"
            dep_id = result["id"]
            return (
                f"🚀 ЗАПРОС деплоя на {result['server_ip']}\n"
                f"  Deploy ID: {dep_id}\n"
                f"  Подтверди: подтверди деплой {dep_id[-8:]}"
            )

        if t.startswith("подтверди деплой "):
            short_id = text[17:].strip()
            return self.deploy.confirm_deploy(short_id)

        if t in ("ожидающие", "pending"):
            reqs = self.accounts.pending_requests()
            if not reqs:
                return "✅ Нет ожидающих запросов."
            lines = [f"⏳ Ожидающие запросы ({len(reqs)}):"]
            lines.append("  Аккаунты:")
            for r in reqs:
                lines.append(f"    • {r.platform} | {r.email} | {r.id[-8:]}")
            return "\n".join(lines)

        return (
            "🖥️ АРЕНДА СЕРВЕРОВ — команды:\n"
            "  серверы | бесплатные | gpu | топ\n"
            "  бюджет N | сравни Провайдер\n"
            "  создай аккаунт P|Email|Цель\n"
            "  добавь сервер P|IP|Model|Цена\n"
            "  деплой ID | мои серверы"
        )
