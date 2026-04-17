"""
src/skills/ebay_parser.py — Парсер eBay для Аргоса.

Парсинг без API ключа через публичный HTML (requests + BeautifulSoup).
Поддержка: поиск товаров, фильтрация по цене, мониторинг.
Переменные .env:
  EBAY_AFFILIATE_ID — (опционально) ID партнёрской программы

Команды:
  ebay поиск <запрос>            — поиск товаров на eBay
  ebay поиск <запрос> до <цена>  — поиск с ценовым ограничением
  ebay цена <запрос>             — диапазон цен
  ebay статус                    — статус парсера
"""

from __future__ import annotations

SKILL_DESCRIPTION = "Парсинг eBay без API: поиск товаров и мониторинг цен"

import re
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.core import ArgosCore

SKILL_NAME = "ebay_parser"
SKILL_TRIGGERS = ["ebay поиск", "ebay цена", "ebay статус", "ебэй поиск", "парсить ebay"]

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}


class EbayParser:
    """Парсер eBay — поиск товаров через HTML scraping."""

    BASE_URL = "https://www.ebay.com/sch/i.html"

    def __init__(self, core: "ArgosCore | None" = None):
        self.core = core

    def handle_command(self, text: str) -> str | None:
        t = text.lower().strip()
        if "ebay статус" in t:
            return self.status()
        if "ebay цена" in t:
            query = re.sub(r"ebay\s+цена\s+", "", t, flags=re.I).strip()
            return self.price_range(query)
        if "ebay поиск" in t or "ебэй поиск" in t or "парсить ebay" in t:
            return self._parse_search_command(text)
        return None

    def search(self, query: str, max_price: float | None = None, limit: int = 5) -> str:
        """Поиск товаров на eBay."""
        try:
            import requests
            from bs4 import BeautifulSoup
        except ImportError:
            return "❌ eBay: установите зависимости: pip install requests beautifulsoup4"

        try:
            params = {
                "_nkw": query,
                "_sacat": "0",
                "LH_BIN": "1",  # Buy It Now
                "_sop": "15",   # Сортировка: по цене от мин
            }
            if max_price:
                params["_udhi"] = str(max_price)

            resp = requests.get(self.BASE_URL, params=params, headers=_HEADERS, timeout=12)
            resp.raise_for_status()
            soup = BeautifulSoup(resp.text, "html.parser")

            # Основные карточки товаров eBay
            items = soup.select("li.s-item")
            if not items:
                items = soup.select(".s-item__wrapper")

            results = []
            for item in items[:limit + 2]:  # берём с запасом
                title_el = item.select_one(".s-item__title")
                price_el = item.select_one(".s-item__price")
                link_el = item.select_one("a.s-item__link")
                shipping_el = item.select_one(".s-item__shipping")

                if not title_el or not price_el:
                    continue
                title = title_el.get_text(strip=True)
                if title.lower() in ("shop on ebay", "new listing"):
                    continue
                price_text = price_el.get_text(strip=True)
                price_val = self._parse_price(price_text)
                link = link_el["href"] if link_el else ""
                shipping = shipping_el.get_text(strip=True) if shipping_el else ""

                results.append({
                    "title": title[:60],
                    "price": price_text,
                    "price_val": price_val,
                    "link": link[:80],
                    "shipping": shipping[:30],
                })
                if len(results) >= limit:
                    break

            if not results:
                return f"🛒 eBay: результатов не найдено для '{query}'"

            lines = [f"🛒 eBay: '{query}' (топ {len(results)}):"]
            for i, r in enumerate(results, 1):
                lines.append(f"\n  {i}. {r['title']}")
                lines.append(f"     💰 {r['price']}"
                             + (f" + {r['shipping']}" if r['shipping'] else ""))
                if r['link']:
                    lines.append(f"     🔗 {r['link'][:70]}")
            return "\n".join(lines)

        except Exception as e:
            return f"❌ eBay поиск: {e}"

    def price_range(self, query: str) -> str:
        """Диапазон цен для запроса (мин, макс, средняя)."""
        try:
            import requests
            from bs4 import BeautifulSoup
        except ImportError:
            return "❌ eBay: pip install requests beautifulsoup4"

        try:
            params = {"_nkw": query, "_sacat": "0", "LH_BIN": "1", "_sop": "15"}
            resp = requests.get(self.BASE_URL, params=params, headers=_HEADERS, timeout=12)
            soup = BeautifulSoup(resp.text, "html.parser")

            prices = []
            for price_el in soup.select(".s-item__price")[:20]:
                val = self._parse_price(price_el.get_text(strip=True))
                if val:
                    prices.append(val)

            if not prices:
                return f"🛒 eBay: нет данных о ценах для '{query}'"

            prices.sort()
            min_p = prices[0]
            max_p = prices[-1]
            avg_p = sum(prices) / len(prices)
            med_p = prices[len(prices) // 2]

            return (
                f"💰 eBay цены для '{query}' ({len(prices)} товаров):\n"
                f"  Минимум:  ${min_p:.2f}\n"
                f"  Медиана:  ${med_p:.2f}\n"
                f"  Среднее:  ${avg_p:.2f}\n"
                f"  Максимум: ${max_p:.2f}"
            )
        except Exception as e:
            return f"❌ eBay диапазон цен: {e}"

    def status(self) -> str:
        try:
            import requests
            resp = requests.get("https://www.ebay.com", headers=_HEADERS, timeout=6)
            ok = resp.status_code == 200
        except Exception:
            ok = False
        return (
            f"🛒 EBAY PARSER:\n"
            f"  Статус: {'✅ доступен' if ok else '❌ недоступен'}\n"
            f"  Зависимости: requests, beautifulsoup4\n"
            f"  Метод: HTML scraping (без API)"
        )

    def run(self) -> str:
        return self.status()

    def _parse_search_command(self, text: str) -> str:
        """Парсинг: ebay поиск <query> [до <price>]"""
        text_clean = re.sub(r"(?:ebay|ебэй)\s+поиск\s*", "", text, flags=re.I).strip()
        max_price = None
        m = re.search(r"\s+до\s+([\d.,]+)", text_clean, re.I)
        if m:
            max_price = float(m.group(1).replace(",", "."))
            text_clean = text_clean[:m.start()].strip()
        return self.search(text_clean, max_price=max_price)

    def _parse_price(self, text: str) -> float | None:
        """Извлечь числовое значение цены из строки."""
        text = text.replace(",", "")
        m = re.search(r"[\d.]+", text)
        if m:
            try:
                return float(m.group())
            except ValueError:
                pass
        return None


def handle(text: str, core=None) -> str | None:
    t = text.lower()
    if not any(kw in t for kw in SKILL_TRIGGERS):
        return None
    return EbayParser(core).handle_command(text)
