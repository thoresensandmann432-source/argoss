"""
crypto_monitor.py — Крипто-Страж
  Мониторинг BTC/ETH каждый час, алерт в Telegram при изменении > 5%
"""

SKILL_DESCRIPTION = "Мониторинг криптовалютных курсов и алертов"

import requests
import time
import os
import threading
import asyncio


class CryptoSentinel:
    API_URL = "https://api.coingecko.com/api/v3/simple/price"
    COINS = ["bitcoin", "ethereum"]
    SYMBOLS = {"bitcoin": "BTC", "ethereum": "ETH"}

    def __init__(self, telegram_bot=None):
        self.bot = telegram_bot  # ArgosTelegram instance (опц.)
        self.prev = {}
        self.threshold = 5.0  # % изменения для алерта
        self._running = False

    def get_prices(self) -> dict:
        try:
            params = {
                "ids": ",".join(self.COINS),
                "vs_currencies": "usd",
                "include_24hr_change": "true",
            }
            r = requests.get(self.API_URL, params=params, timeout=8)
            data = r.json()
            return {
                coin: {
                    "price": data[coin]["usd"],
                    "change": data[coin].get("usd_24h_change", 0.0),
                }
                for coin in self.COINS
            }
        except Exception as e:
            return {}

    def check(self) -> list[str]:
        """Возвращает список алертов (пустой если всё тихо)."""
        current = self.get_prices()
        alerts = []

        for coin, info in current.items():
            change = info.get("change", 0.0)
            sym = self.SYMBOLS[coin]
            price = info["price"]

            if abs(change) >= self.threshold:
                direction = "📈 РОСТ" if change > 0 else "📉 ПАДЕНИЕ"
                alerts.append(
                    f"🪙 {sym} АЛЕРТ\n" f"{direction}: {change:+.2f}%\n" f"Цена: ${price:,.2f}"
                )
        self.prev = current
        return alerts

    def report(self) -> str:
        """Разовый отчёт по текущим ценам."""
        prices = self.get_prices()
        if not prices:
            return "❌ CoinGecko недоступен."
        lines = ["🪙 КРИПТО-РЫНОК:"]
        for coin, info in prices.items():
            sym = self.SYMBOLS[coin]
            lines.append(f"  {sym}: ${info['price']:,.2f}  ({info['change']:+.2f}% за 24ч)")
        return "\n".join(lines)

    def start_loop(self, interval_sec: int = 3600):
        """Фоновый мониторинг в отдельном потоке."""
        self._running = True

        def _notify_bot(msg: str):
            if not self.bot:
                return
            try:
                send = getattr(self.bot, "send", None)
                if callable(send):
                    send(msg)
                    return
                if getattr(self.bot, "app", None) and getattr(self.bot, "user_id", None):
                    coro = self.bot.app.bot.send_message(chat_id=self.bot.user_id, text=msg)
                    try:
                        loop = asyncio.get_running_loop()
                        # Уже внутри event loop (Telegram bot) — планируем через threadsafe
                        asyncio.run_coroutine_threadsafe(coro, loop)
                    except RuntimeError:
                        # Нет запущенного loop — запускаем в отдельном потоке
                        def _run_coro():
                            new_loop = asyncio.new_event_loop()
                            try:
                                new_loop.run_until_complete(coro)
                            finally:
                                new_loop.close()
                        threading.Thread(target=_run_coro, daemon=True).start()
            except Exception as e:
                print(f"[CRYPTO-SENTINEL] Ошибка отправки алерта: {e}")
                return

        def _loop():
            while self._running:
                alerts = self.check()
                for msg in alerts:
                    print(f"[CRYPTO-SENTINEL]: {msg}")
                    _notify_bot(msg)
                time.sleep(interval_sec)

        threading.Thread(target=_loop, daemon=True).start()
        return f"Крипто-Страж запущен. Интервал: {interval_sec//60} мин. Порог: {self.threshold}%"

    def stop(self):
        self._running = False
        return "Крипто-Страж остановлен."

# ── Команды для skill_loader ──────────────────────────────────────────────────

_sentinel: CryptoSentinel | None = None


def _get_sentinel(core=None) -> CryptoSentinel:
    global _sentinel
    if _sentinel is None:
        bot = getattr(core, "_telegram_bot", None) if core else None
        _sentinel = CryptoSentinel(telegram_bot=bot)
    return _sentinel


SKILL_COMMANDS = [
    "крипто", "crypto", "btc", "eth", "bitcoin", "ethereum",
    "крипто цена", "крипто отчёт", "крипто старт", "крипто стоп",
    "crypto start", "crypto stop", "crypto status",
]


def dispatch(text: str, core=None, **kwargs) -> str | None:
    t = text.lower().strip()
    if not any(t.startswith(k) or t == k for k in SKILL_COMMANDS):
        return None

    s = _get_sentinel(core)

    if any(k in t for k in ("старт", "start", "запуст")):
        if s._running:
            return "🪙 Мониторинг уже запущен."
        s.start_loop()
        return "🪙 Крипто-мониторинг запущен (интервал 1 ч)."

    if any(k in t for k in ("стоп", "stop", "останов")):
        s.stop_loop()
        return "🪙 Крипто-мониторинг остановлен."

    if any(k in t for k in ("статус", "status")):
        return s.status()

    # По умолчанию — разовый отчёт
    return s.report()


def setup(core=None):
    pass
