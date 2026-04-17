"""
src/skills/ton_blockchain.py — TON Blockchain интеграция для Аргоса.

Использует tonsdk (pip install tonsdk) и публичный API toncenter.com.
Переменные .env:
  TON_WALLET_ADDRESS — адрес кошелька для мониторинга
  TON_API_KEY        — ключ API toncenter.com (опционально)
  TON_NETWORK        — mainnet (по умолчанию) или testnet

Команды:
  ton баланс [адрес]       — баланс кошелька в TON
  ton транзакции [адрес]   — последние транзакции
  ton адрес                — мой адрес из .env
  ton статус               — статус сети TON
  ton цена                 — текущая цена TON/USDT
"""

from __future__ import annotations

SKILL_DESCRIPTION = "TON блокчейн: баланс, транзакции, кошелёк"

import os
import json
import sys
import subprocess
import importlib.util
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.core import ArgosCore

SKILL_NAME = "ton_blockchain"
SKILL_TRIGGERS = ["ton баланс", "ton транзакции", "ton адрес", "ton статус",
                  "ton цена", "тон кошелёк", "toncoin", "ton wallet"]
REPO_URL = "https://github.com/flaming-chameleon/ton-wallet-generation.git"
REPO_DIR = Path("integrations") / "ton-wallet-generation"


class TonBlockchain:
    """TON Blockchain клиент — мониторинг кошелька и сети."""

    MAINNET_API = "https://toncenter.com/api/v2"
    TESTNET_API = "https://testnet.toncenter.com/api/v2"

    def __init__(self, core: "ArgosCore | None" = None):
        self.core = core
        self.wallet = os.getenv("TON_WALLET_ADDRESS", "")
        self.api_key = os.getenv("TON_API_KEY", "")
        self.network = os.getenv("TON_NETWORK", "mainnet").lower()
        self.api_url = self.TESTNET_API if "test" in self.network else self.MAINNET_API

    def handle_command(self, text: str) -> str | None:
        t = text.lower().strip()
        if "ton wallet install" in t or "тон кошелек установить" in t or "тон кошелёк установить" in t:
            return self.install_wallet_generator()
        if "ton wallet update" in t or "тон кошелек обновить" in t or "тон кошелёк обновить" in t:
            return self.update_wallet_generator()
        if "ton wallet gen" in t or "тон кошелек сгенерируй" in t or "тон кошелёк сгенерируй" in t:
            count = self._extract_count(t, default=1, limit=100)
            return self.generate_wallets_local(count)
        if "ton баланс" in t or "тон баланс" in t:
            addr = self._extract_address(text) or self.wallet
            return self.get_balance(addr)
        if "ton транзакции" in t:
            addr = self._extract_address(text) or self.wallet
            return self.get_transactions(addr)
        if "ton адрес" in t:
            return f"💎 TON адрес: {self.wallet or '(не задан в TON_WALLET_ADDRESS)'}"
        if "ton статус" in t:
            return self.network_status()
        if "ton цена" in t or "toncoin" in t:
            return self.get_price()
        return None

    def install_wallet_generator(self) -> str:
        """Клонирует и ставит зависимости ton-wallet-generation."""
        try:
            REPO_DIR.parent.mkdir(parents=True, exist_ok=True)
            if REPO_DIR.exists():
                return self.update_wallet_generator()
            run1 = subprocess.run(
                ["git", "clone", REPO_URL, str(REPO_DIR)],
                capture_output=True,
                text=True,
                timeout=120,
            )
            if run1.returncode != 0:
                return f"❌ git clone: {run1.stderr[:300]}"
            req = REPO_DIR / "requirements.txt"
            if req.exists():
                run2 = subprocess.run(
                    [sys.executable, "-m", "pip", "install", "-r", str(req)],
                    capture_output=True,
                    text=True,
                    timeout=180,
                )
                if run2.returncode != 0:
                    return f"⚠️ Репозиторий скачан, но pip install не прошёл: {run2.stderr[:350]}"
            return f"✅ Установлено: {REPO_DIR}"
        except Exception as e:
            return f"❌ install ton wallet: {e}"

    def update_wallet_generator(self) -> str:
        """Обновляет репозиторий и зависимости ton-wallet-generation."""
        try:
            if not REPO_DIR.exists():
                return self.install_wallet_generator()
            run1 = subprocess.run(
                ["git", "-C", str(REPO_DIR), "pull"],
                capture_output=True,
                text=True,
                timeout=120,
            )
            if run1.returncode != 0:
                return f"❌ git pull: {run1.stderr[:300]}"
            req = REPO_DIR / "requirements.txt"
            if req.exists():
                run2 = subprocess.run(
                    [sys.executable, "-m", "pip", "install", "-r", str(req)],
                    capture_output=True,
                    text=True,
                    timeout=180,
                )
                if run2.returncode != 0:
                    return f"⚠️ Обновлено, но pip install не прошёл: {run2.stderr[:350]}"
            return f"✅ Обновлено: {REPO_DIR}"
        except Exception as e:
            return f"❌ update ton wallet: {e}"

    def generate_wallets_local(self, count: int = 1) -> str:
        """Генерирует кошельки через локальный модуль ton-wallet-generation."""
        try:
            if not REPO_DIR.exists():
                install_msg = self.install_wallet_generator()
                if install_msg.startswith("❌") or install_msg.startswith("⚠️"):
                    return install_msg
            mod_path = REPO_DIR / "ton_wallet.py"
            if not mod_path.exists():
                return f"❌ Не найден {mod_path}"
            spec = importlib.util.spec_from_file_location("ton_wallet_ext", str(mod_path))
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            old_cwd = Path.cwd()
            try:
                os.chdir(str(REPO_DIR))
                module.generate_wallets(int(count))
            finally:
                os.chdir(str(old_cwd))
            out_file = REPO_DIR / "wallets.txt"
            return f"✅ Сгенерировано кошельков: {count}\n📄 Файл: {out_file.resolve()}"
        except Exception as e:
            return f"❌ ton wallet gen: {e}"

    def get_balance(self, address: str = "") -> str:
        """Получить баланс кошелька в TON."""
        addr = address or self.wallet
        if not addr:
            return "❌ Укажите адрес или задайте TON_WALLET_ADDRESS в .env"
        try:
            data = self._api_call("getAddressBalance", {"address": addr})
            if data is None:
                return "❌ TON API недоступен"
            nano = int(data.get("result", 0))
            ton = nano / 1e9
            short = f"{addr[:6]}...{addr[-4:]}"
            return f"💎 Баланс [{short}]: {ton:.4f} TON"
        except Exception as e:
            return f"❌ TON баланс: {e}"

    def get_transactions(self, address: str = "", limit: int = 5) -> str:
        """Последние транзакции кошелька."""
        addr = address or self.wallet
        if not addr:
            return "❌ Укажите адрес или задайте TON_WALLET_ADDRESS в .env"
        try:
            data = self._api_call("getTransactions", {
                "address": addr, "limit": limit
            })
            if data is None:
                return "❌ TON API недоступен"
            txs = data.get("result", [])
            if not txs:
                return f"💎 Транзакций не найдено для {addr[:8]}..."
            lines = [f"💎 ТРАНЗАКЦИИ [{addr[:6]}...{addr[-4:]}]:"]
            for tx in txs:
                ts = tx.get("utime", 0)
                from datetime import datetime
                dt = datetime.fromtimestamp(ts).strftime("%d.%m %H:%M")
                in_msg = tx.get("in_msg", {})
                value = int(in_msg.get("value", 0)) / 1e9
                src = (in_msg.get("source") or "внешний")[:12]
                lines.append(f"  [{dt}] +{value:.4f} TON ← {src}")
            return "\n".join(lines)
        except Exception as e:
            return f"❌ TON транзакции: {e}"

    def network_status(self) -> str:
        """Статус сети TON."""
        try:
            data = self._api_call("getMasterchainInfo", {})
            if data is None:
                return "❌ TON сеть недоступна"
            result = data.get("result", {})
            last = result.get("last", {})
            seqno = last.get("seqno", "?")
            return (
                f"💎 TON СЕТЬ ({self.network}):\n"
                f"  Последний блок: #{seqno}\n"
                f"  API: {self.api_url}\n"
                f"  Ключ API: {'задан' if self.api_key else 'не задан (лимит 1 req/s)'}"
            )
        except Exception as e:
            return f"❌ TON статус: {e}"

    def get_price(self) -> str:
        """Текущая цена TON в USDT через CoinGecko."""
        try:
            import urllib.request
            url = "https://api.coingecko.com/api/v3/simple/price?ids=the-open-network&vs_currencies=usd,rub"
            req = urllib.request.Request(url, headers={"User-Agent": "ArgosOS/2.1"})
            with urllib.request.urlopen(req, timeout=8) as resp:
                data = json.loads(resp.read())
            ton_data = data.get("the-open-network", {})
            usd = ton_data.get("usd", "?")
            rub = ton_data.get("rub", "?")
            return f"💎 TON Цена: ${usd} USD | ₽{rub} RUB"
        except Exception as e:
            return f"❌ TON цена: {e}"

    def run(self) -> str:
        return self.network_status()

    def _api_call(self, method: str, params: dict) -> dict | None:
        """Запрос к Toncenter API."""
        import urllib.request
        import urllib.parse
        params_str = urllib.parse.urlencode(params)
        url = f"{self.api_url}/{method}?{params_str}"
        headers = {"User-Agent": "ArgosOS/2.1"}
        if self.api_key:
            headers["X-API-Key"] = self.api_key
        try:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=10) as resp:
                return json.loads(resp.read())
        except Exception:
            return None

    def _extract_address(self, text: str) -> str:
        """Извлечь TON-адрес из текста."""
        import re
        # TON адреса: EQ... или UQ... обычно 48 символов base64
        m = re.search(r"\b(EQ[A-Za-z0-9_\-]{46}|UQ[A-Za-z0-9_\-]{46})\b", text)
        return m.group(1) if m else ""

    def _extract_count(self, text: str, default: int = 1, limit: int = 100) -> int:
        import re
        m = re.search(r"\b(\d{1,4})\b", text)
        if not m:
            return default
        try:
            n = int(m.group(1))
            return max(1, min(n, limit))
        except Exception:
            return default


def handle(text: str, core=None) -> str | None:
    t = text.lower()
    if not any(kw in t for kw in SKILL_TRIGGERS):
        return None
    return TonBlockchain(core).handle_command(text)
