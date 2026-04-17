"""
src/infrastructure.py — Инфраструктурный модуль ARGOS
=====================================================
MailServerManager, VPNManager, QuantumMarketplace, ArgosInfrastructure.
"""
from __future__ import annotations

import hashlib
import ipaddress
import random
import re
import socket
import string
import time
import uuid
from dataclasses import dataclass, field
from typing import Optional

__all__ = [
    "ArgosInfrastructure",
    "MailServerManager",
    "VPNManager",
    "VPNClient",
    "QuantumMarketplace",
]


# ══════════════════════════════════════════════════════════════════════════════
# MailServerManager
# ══════════════════════════════════════════════════════════════════════════════

class MailServerManager:
    """Управление почтовым сервером Postfix/Dovecot."""

    def __init__(self) -> None:
        self._accounts: list[str] = []
        self._domain: str = "argos.local"
        self._running: bool = False

    def status(self) -> str:
        return (
            f"📧 ПОЧТОВЫЙ СЕРВЕР\n"
            f"  Статус  : {'работает' if self._running else 'остановлен'}\n"
            f"  Домен   : {self._domain}\n"
            f"  Аккаунты: {len(self._accounts)}\n"
            f"  MX      : mail.{self._domain}"
        )

    def setup_guide(self, domain: str = "") -> str:
        d = domain or self._domain
        return (
            f"📧 УСТАНОВКА почтового сервера для {d}\n\n"
            f"  1. apt install postfix dovecot-core\n"
            f"  2. DNS записи:\n"
            f"     MX   : mail.{d}  (приоритет 10)\n"
            f"     A    : mail.{d}  → ВАШ_IP\n"
            f"     SPF  : spf1 include:{d} -all\n"
            f"     DKIM : генерация через amavis\n"
            f"     DMARC: v=DMARC1; p=quarantine\n"
            f"  3. SSL: certbot --nginx -d mail.{d}\n"
            f"  4. Тест: swaks --to test@{d}"
        )

    def add_account(self, email: str) -> str:
        if not re.match(r"^[^@]+@[^@]+\.[^@]+$", email):
            return f"❌ Некорректный email: {email}"
        if email in self._accounts:
            return f"⚠️ Аккаунт {email} уже существует."
        self._accounts.append(email)
        return f"✅ Аккаунт {email} создан."

    def check_mx(self, domain: str) -> str:
        return (
            f"🔍 DNS MX проверка: {domain}\n"
            f"  MX записи: получение через DNS resolver\n"
            f"  Команда: nslookup -type=MX {domain}\n"
            f"  Онлайн: https://mxtoolbox.com/SuperTool.aspx?action=mx%3a{domain}"
        )


# ══════════════════════════════════════════════════════════════════════════════
# VPNManager / VPNClient
# ══════════════════════════════════════════════════════════════════════════════

@dataclass
class VPNClient:
    name: str
    ip: str
    public_key: str
    private_key: str = ""


class VPNManager:
    """WireGuard VPN менеджер."""

    _SERVER_KEY = "SERVER_PUBKEY_PLACEHOLDER=="
    _BASE_IP    = "10.8.0."
    _NEXT_IP    = 2

    def __init__(self) -> None:
        self._clients: list[VPNClient] = []

    def status(self) -> str:
        return (
            f"🔐 VPN (WireGuard)\n"
            f"  Клиентов: {len(self._clients)}\n"
            f"  Сеть    : 10.8.0.0/24"
        )

    def setup_guide(self, server_ip: str = "0.0.0.0") -> str:
        return (
            f"🔐 WIREGUARD установка (сервер: {server_ip})\n\n"
            f"  apt install wireguard\n"
            f"  wg genkey | tee /etc/wireguard/privatekey | wg pubkey > /etc/wireguard/publickey\n\n"
            f"  /etc/wireguard/wg0.conf:\n"
            f"  [Interface]\n"
            f"  Address = 10.8.0.1/24\n"
            f"  ListenPort = 51820\n"
            f"  PrivateKey = <privatekey>\n\n"
            f"  systemctl enable --now wg-quick@wg0"
        )

    def add_client(self, name: str) -> VPNClient:
        ip = f"{self._BASE_IP}{self._NEXT_IP}"
        self.__class__._NEXT_IP += 1
        pub_key = hashlib.sha256(f"{name}{time.time()}".encode()).hexdigest()[:44] + "="
        priv_key = hashlib.sha256(f"priv{name}{time.time()}".encode()).hexdigest()[:44] + "="
        client = VPNClient(name=name, ip=ip, public_key=pub_key, private_key=priv_key)
        self._clients.append(client)
        return client

    def get_client_config(self, name: str) -> str:
        client = next((c for c in self._clients if c.name == name), None)
        if not client:
            return f"❌ Клиент «{name}» не найден."
        return (
            f"[Interface]\n"
            f"PrivateKey = {client.private_key}\n"
            f"Address = {client.ip}/32\n"
            f"DNS = 1.1.1.1\n\n"
            f"[Peer]\n"
            f"PublicKey = {self._SERVER_KEY}\n"
            f"AllowedIPs = 0.0.0.0/0\n"
            f"Endpoint = YOUR_SERVER:51820"
        )

    def sell_vpn_access(self) -> str:
        return (
            "💼 БИЗНЕС на VPN-доступе\n\n"
            "  Стоимость сервера (Hetzner CX11): 3.29€/мес\n"
            "  Продажа доступа: 200₽/мес × 50 клиентов = 10 000₽\n"
            "  Себестоимость: ~300₽/мес\n"
            "  Прибыль: ~9 700₽/мес\n\n"
            "  Инструменты: WireGuard + бот оплаты + ARGOS автоматизация"
        )

    def socket_mode_ready(self) -> bool:
        return True


# ══════════════════════════════════════════════════════════════════════════════
# QuantumMarketplace
# ══════════════════════════════════════════════════════════════════════════════

_QUANTUM_CATALOG = [
    {"name": "random_numbers",       "price_usd": 0.10, "desc": "QRNG числа"},
    {"name": "portfolio_optimization","price_usd": 2.50, "desc": "Квантовая оптимизация портфеля"},
    {"name": "route_optimization",   "price_usd": 1.50, "desc": "Оптимизация маршрутов"},
    {"name": "chemistry_simulation", "price_usd": 5.00, "desc": "Молекулярное моделирование"},
    {"name": "cryptography_key",     "price_usd": 0.50, "desc": "Квантовый ключ шифрования"},
]

_QUANTUM_PROVIDERS = [
    {"name": "IBM Quantum",    "qubits": 127, "price": "Pay-per-use"},
    {"name": "AWS Braket",     "qubits": 79,  "price": "$0.00035/задача"},
    {"name": "Google Quantum", "qubits": 70,  "price": "Research only"},
    {"name": "IonQ",           "qubits": 32,  "price": "$0.01/задача"},
]


@dataclass
class QuantumJob:
    job_id: str
    service: str
    params: dict
    status: str = "done"
    result: Optional[dict] = None
    price_usd: float = 0.0


class QuantumMarketplace:
    """Квантовый маркетплейс — продажа квантовых вычислений."""

    def __init__(self) -> None:
        self._jobs: list[QuantumJob] = []
        self._total_earned: float = 0.0

    def list_catalog(self) -> str:
        lines = ["⚛️ КВАНТОВЫЙ КАТАЛОГ:"]
        for item in _QUANTUM_CATALOG:
            lines.append(f"  • {item['name']}: ${item['price_usd']:.2f} — {item['desc']}")
        return "\n".join(lines)

    def submit_job(self, service: str, params: dict) -> QuantumJob:
        item = next((i for i in _QUANTUM_CATALOG if i["name"] == service), None)
        price = item["price_usd"] if item else 1.0

        # Генерируем результат
        if service == "random_numbers":
            result = {"numbers": [random.randint(0, 2**32) for _ in range(params.get("count", 10))]}
        elif service == "portfolio_optimization":
            result = {"weights": {a: round(1/len(params.get("assets", ["A"])), 3) for a in params.get("assets", ["BTC"])}}
        elif service == "route_optimization":
            result = {"optimal_distance": random.uniform(100, 1000), "note": "Simulated"}
        else:
            result = {"status": "completed", "note": "Simulated quantum result"}

        job = QuantumJob(
            job_id=str(uuid.uuid4())[:8],
            service=service,
            params=params,
            result=result,
            price_usd=price,
        )
        self._jobs.append(job)
        return job

    def sell_result(self, service: str, params: dict | None = None) -> str:
        job = self.submit_job(service, params or {})
        self._total_earned += job.price_usd
        return (
            f"✅ ПРОДАН квантовый результат\n"
            f"  Сервис : {service}\n"
            f"  Цена   : ${job.price_usd:.2f}\n"
            f"  Итого  : ${self._total_earned:.2f}"
        )

    def status(self) -> str:
        return (
            f"⚛️ КВАНТОВЫЙ маркетплейс\n"
            f"  Задач продано: {len(self._jobs)}\n"
            f"  Заработано   : ${self._total_earned:.2f}"
        )

    def market_overview(self) -> str:
        lines = ["🌐 РЫНОК квантовых вычислений:"]
        for p in _QUANTUM_PROVIDERS:
            lines.append(f"  • {p['name']}: {p['qubits']} кубитов | {p['price']}")
        return "\n".join(lines)


# ══════════════════════════════════════════════════════════════════════════════
# ArgosInfrastructure
# ══════════════════════════════════════════════════════════════════════════════

class ArgosInfrastructure:
    """
    Инфраструктурный модуль ARGOS.
    Объединяет почту, VPN и квантовый маркетплейс.
    """

    def __init__(self, core=None) -> None:
        self._core = core
        self.mail    = MailServerManager()
        self.vpn     = VPNManager()
        self.quantum = QuantumMarketplace()

    def handle_command(self, text: str) -> str:  # noqa: C901
        t = text.strip().lower()

        # Почта
        if t == "почта статус":
            return self.mail.status()
        if t in ("почта настроить", "почта установка"):
            return self.mail.setup_guide()
        if t.startswith("почта аккаунт "):
            email = text[14:].strip()
            return self.mail.add_account(email)
        if t.startswith("почта mx "):
            domain = text[9:].strip()
            return self.mail.check_mx(domain)

        # VPN
        if t == "vpn статус":
            return self.vpn.status()
        if t in ("vpn настроить", "vpn установка"):
            return self.vpn.setup_guide()
        if t.startswith("vpn клиент "):
            name = text[11:].strip()
            c = self.vpn.add_client(name)
            return f"✅ VPN клиент {name} добавлен. IP: {c.ip}"
        if t.startswith("vpn конфиг "):
            name = text[11:].strip()
            return self.vpn.get_client_config(name)
        if t in ("vpn бизнес", "vpn продать"):
            return self.vpn.sell_vpn_access()

        # Квантум
        if t in ("квант задачи", "квант каталог"):
            return self.quantum.list_catalog()
        if t == "квант рынок":
            return self.quantum.market_overview()
        if t.startswith("квант продать "):
            service = text[14:].strip()
            return self.quantum.sell_result(service)
        if t == "квант статус":
            return self.quantum.status()

        # Общий статус
        if t in ("инфра", "инфраструктура", "infrastructure"):
            return (
                f"🏗️ ИНФРАСТРУКТУРА ARGOS\n"
                f"{self.mail.status()}\n\n"
                f"{self.vpn.status()}\n\n"
                f"{self.quantum.status()}"
            )

        return (
            "🏗️ ИНФРАСТРУКТУРА — команды:\n"
            "  почта статус|настроить|аккаунт|mx\n"
            "  vpn статус|настроить|клиент|конфиг|бизнес\n"
            "  квант задачи|рынок|продать|статус\n"
            "  инфра"
        )
