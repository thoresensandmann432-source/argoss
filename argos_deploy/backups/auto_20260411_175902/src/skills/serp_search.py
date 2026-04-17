"""
serp_search.py — Поисковой движок ARGOS (SerpAPI + DuckDuckGo fallback)
═══════════════════════════════════════════════════════════════════════
Команды: поищи [запрос] | найди в интернете | serp [запрос]

Приоритет:
  1. SerpAPI (Google) — если SERPAPI_KEY в .env
  2. DuckDuckGo (duckduckgo-search) — бесплатно, без ключа
  3. Простой HTTP-поиск как fallback
═══════════════════════════════════════════════════════════════════════
"""

from __future__ import annotations

SKILL_DESCRIPTION = "Веб-поиск через SerpAPI или DuckDuckGo"

import os
import json
from typing import Optional

try:
    import requests
    _REQ = True
except ImportError:
    _REQ = False

try:
    try:
        from ddgs import DDGS          # новый пакет ddgs
    except ImportError:
        from duckduckgo_search import DDGS  # старый duckduckgo-search
    _DDG = True
except ImportError:
    _DDG = False

from src.argos_logger import get_logger

log = get_logger("argos.serp")

SERPAPI_BASE = "https://serpapi.com/search"


class SerpSearch:
    """
    Универсальный веб-поиск для ARGOS.
    SerpAPI (Google) если есть ключ, иначе DuckDuckGo.
    """

    def __init__(self):
        self._serp_key = os.getenv("SERPAPI_KEY", os.getenv("SERP_API_KEY", ""))
        self._timeout  = 10

    @property
    def backend(self) -> str:
        if self._serp_key and _REQ:
            return "serpapi"
        if _DDG:
            return "duckduckgo"
        return "unavailable"

    def search(self, query: str, num: int = 5) -> list[dict]:
        """
        Ищет в интернете. Возвращает список результатов:
        [{"title": ..., "link": ..., "snippet": ...}]
        """
        if self._serp_key and _REQ:
            return self._serp_search(query, num)
        if _DDG:
            return self._ddg_search(query, num)
        log.warning("SerpSearch: нет доступного бэкенда")
        return []

    def _serp_search(self, query: str, num: int) -> list[dict]:
        try:
            params = {
                "q": query,
                "api_key": self._serp_key,
                "engine": "google",
                "num": num,
                "hl": "ru",
            }
            r = requests.get(SERPAPI_BASE, params=params, timeout=self._timeout)
            data = r.json()
            results = []
            for item in data.get("organic_results", [])[:num]:
                results.append({
                    "title":   item.get("title", ""),
                    "link":    item.get("link", ""),
                    "snippet": item.get("snippet", ""),
                })
            return results
        except Exception as e:
            log.warning("SerpAPI error: %s", e)
            return self._ddg_search(query, num)  # fallback

    def _ddg_search(self, query: str, num: int) -> list[dict]:
        try:
            with DDGS() as ddgs:
                results = list(ddgs.text(query, max_results=num))
            return [{"title": r.get("title",""), "link": r.get("href",""),
                     "snippet": r.get("body","")} for r in results]
        except Exception as e:
            log.warning("DuckDuckGo error: %s", e)
            return []

    def format_results(self, results: list[dict]) -> str:
        if not results:
            return "❌ Ничего не найдено"
        lines = [f"🔍 Результаты поиска ({len(results)}):"]
        for i, r in enumerate(results, 1):
            lines.append(f"\n{i}. {r['title']}")
            if r.get("snippet"):
                lines.append(f"   {r['snippet'][:120]}")
            if r.get("link"):
                lines.append(f"   🔗 {r['link']}")
        return "\n".join(lines)

    def quick_search(self, query: str, num: int = 5) -> str:
        """Поиск + форматирование в одну строку."""
        results = self.search(query, num)
        header = f"[via {self.backend}]"
        return f"{header}\n{self.format_results(results)}"

    def status(self) -> str:
        lines = ["🔍 SerpSearch:"]
        if self._serp_key:
            lines.append(f"  ✅ SerpAPI: ключ задан ({self._serp_key[:8]}...)")
        else:
            lines.append("  ℹ️  SerpAPI: SERPAPI_KEY не задан — нужен платный план")
        if _DDG:
            lines.append("  ✅ DuckDuckGo: установлен (бесплатный fallback)")
        else:
            lines.append("  ⚠️  DuckDuckGo: pip install duckduckgo-search")
        lines.append(f"  Активный бэкенд: {self.backend}")
        return "\n".join(lines)

    def execute(self) -> str:
        return self.status()

    def report(self) -> str:
        return self.status()

    def handle_command(self, text: str) -> str:
        t = (text or "").strip()
        tl = t.lower()
        if tl in {"serp", "серп", "serpapi", "serp status", "серп статус"}:
            return self.status()
        query = t
        for marker in ("серп", "serp", "serpapi", "поищи", "найди в интернете", "найди в google", "search"):
            if marker in tl:
                idx = tl.find(marker)
                query = t[idx + len(marker):].strip(" :,-")
                break
        if not query:
            return self.status()
        return self.quick_search(query)
