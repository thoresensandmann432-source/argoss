"""
src/skills/ga4_analytics.py — Google Analytics 4 интеграция для Аргоса.

Использует GA4 Data API (pip install google-analytics-data).
Переменные .env:
  GA4_PROPERTY_ID  — ID свойства GA4 (числовой, например 123456789)
  GOOGLE_APPLICATION_CREDENTIALS — путь к JSON файлу сервисного аккаунта
                                    или используй GA4_CREDENTIALS_JSON

Команды:
  ga4 отчёт                    — отчёт за последние 7 дней
  ga4 сессии [дней]            — кол-во сессий
  ga4 пользователи [дней]      — активные пользователи
  ga4 страницы [дней]          — топ страниц
  ga4 события [дней]           — топ событий
  ga4 статус                   — проверить подключение
"""

from __future__ import annotations

SKILL_DESCRIPTION = "Google Analytics 4: метрики и отчёты"

import json
import os
from datetime import date, timedelta
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.core import ArgosCore

SKILL_NAME = "ga4_analytics"
SKILL_TRIGGERS = ["ga4 отчёт", "ga4 сессии", "ga4 пользователи", "ga4 страницы",
                  "ga4 события", "ga4 статус", "google analytics", "аналитика ga4"]


class GA4Analytics:
    """Google Analytics 4 клиент для Аргоса."""

    def __init__(self, core: "ArgosCore | None" = None):
        self.core = core
        self.property_id = os.getenv("GA4_PROPERTY_ID", "")
        self._client = None

    def handle_command(self, text: str) -> str | None:
        t = text.lower().strip()
        days = self._extract_days(text)

        if "ga4 статус" in t:
            return self.status()
        if "ga4 отчёт" in t or "google analytics" in t:
            return self.full_report(days)
        if "ga4 сессии" in t:
            return self.get_sessions(days)
        if "ga4 пользователи" in t:
            return self.get_users(days)
        if "ga4 страницы" in t:
            return self.top_pages(days)
        if "ga4 события" in t or "аналитика ga4" in t:
            return self.top_events(days)
        return None

    def status(self) -> str:
        """Проверить подключение к GA4."""
        if not self.property_id:
            return ("❌ GA4: не задан GA4_PROPERTY_ID в .env\n"
                    "Пример: GA4_PROPERTY_ID=123456789")
        creds = os.getenv("GOOGLE_APPLICATION_CREDENTIALS") or os.getenv("GA4_CREDENTIALS_JSON")
        if not creds:
            return ("❌ GA4: не заданы учётные данные.\n"
                    "Задайте GOOGLE_APPLICATION_CREDENTIALS=/path/to/sa.json\n"
                    "или GA4_CREDENTIALS_JSON='{...json...}'")
        try:
            client = self._get_client()
            return f"✅ GA4: подключено к свойству {self.property_id}"
        except Exception as e:
            return f"❌ GA4 статус: {e}"

    def full_report(self, days: int = 7) -> str:
        """Полный отчёт за последние N дней."""
        lines = [f"📊 GA4 ОТЧЁТ (последние {days} дней):"]
        lines.append(self.get_sessions(days))
        lines.append(self.get_users(days))
        lines.append(self.top_pages(days, limit=3))
        return "\n".join(lines)

    def get_sessions(self, days: int = 7) -> str:
        """Количество сессий."""
        try:
            from google.analytics.data_v1beta.types import (
                RunReportRequest, DateRange, Metric
            )
            client = self._get_client()
            request = RunReportRequest(
                property=f"properties/{self.property_id}",
                date_ranges=[DateRange(
                    start_date=f"{days}daysAgo",
                    end_date="today"
                )],
                metrics=[Metric(name="sessions")],
            )
            response = client.run_report(request)
            count = response.rows[0].metric_values[0].value if response.rows else "0"
            return f"  Сессии: {int(count):,}"
        except ImportError:
            return self._no_sdk_message("google-analytics-data")
        except Exception as e:
            return f"  Сессии: ❌ {e}"

    def get_users(self, days: int = 7) -> str:
        """Активные пользователи."""
        try:
            from google.analytics.data_v1beta.types import (
                RunReportRequest, DateRange, Metric
            )
            client = self._get_client()
            request = RunReportRequest(
                property=f"properties/{self.property_id}",
                date_ranges=[DateRange(start_date=f"{days}daysAgo", end_date="today")],
                metrics=[
                    Metric(name="activeUsers"),
                    Metric(name="newUsers"),
                ],
            )
            response = client.run_report(request)
            if response.rows:
                active = response.rows[0].metric_values[0].value
                new_ = response.rows[0].metric_values[1].value
                return f"  Пользователи: {int(active):,} (новых: {int(new_):,})"
            return "  Пользователи: нет данных"
        except ImportError:
            return self._no_sdk_message("google-analytics-data")
        except Exception as e:
            return f"  Пользователи: ❌ {e}"

    def top_pages(self, days: int = 7, limit: int = 5) -> str:
        """Топ страниц по просмотрам."""
        try:
            from google.analytics.data_v1beta.types import (
                RunReportRequest, DateRange, Dimension, Metric, OrderBy
            )
            client = self._get_client()
            request = RunReportRequest(
                property=f"properties/{self.property_id}",
                date_ranges=[DateRange(start_date=f"{days}daysAgo", end_date="today")],
                dimensions=[Dimension(name="pagePath")],
                metrics=[Metric(name="screenPageViews")],
                order_bys=[OrderBy(
                    metric=OrderBy.MetricOrderBy(metric_name="screenPageViews"),
                    desc=True
                )],
                limit=limit,
            )
            response = client.run_report(request)
            if not response.rows:
                return "  Страницы: нет данных"
            lines = [f"  Топ-{limit} страниц:"]
            for row in response.rows:
                path = row.dimension_values[0].value
                views = int(row.metric_values[0].value)
                lines.append(f"    {path[:40]} — {views:,} просмотров")
            return "\n".join(lines)
        except ImportError:
            return self._no_sdk_message("google-analytics-data")
        except Exception as e:
            return f"  Страницы: ❌ {e}"

    def top_events(self, days: int = 7, limit: int = 5) -> str:
        """Топ событий."""
        try:
            from google.analytics.data_v1beta.types import (
                RunReportRequest, DateRange, Dimension, Metric, OrderBy
            )
            client = self._get_client()
            request = RunReportRequest(
                property=f"properties/{self.property_id}",
                date_ranges=[DateRange(start_date=f"{days}daysAgo", end_date="today")],
                dimensions=[Dimension(name="eventName")],
                metrics=[Metric(name="eventCount")],
                order_bys=[OrderBy(
                    metric=OrderBy.MetricOrderBy(metric_name="eventCount"),
                    desc=True
                )],
                limit=limit,
            )
            response = client.run_report(request)
            if not response.rows:
                return "  События: нет данных"
            lines = [f"  Топ-{limit} событий:"]
            for row in response.rows:
                event = row.dimension_values[0].value
                count = int(row.metric_values[0].value)
                lines.append(f"    {event} — {count:,}")
            return "\n".join(lines)
        except ImportError:
            return self._no_sdk_message("google-analytics-data")
        except Exception as e:
            return f"  События: ❌ {e}"

    def run(self) -> str:
        return self.status()

    def _get_client(self):
        if self._client:
            return self._client
        from google.analytics.data_v1beta import BetaAnalyticsDataClient
        creds_json = os.getenv("GA4_CREDENTIALS_JSON")
        if creds_json:
            import google.oauth2.service_account as sa
            info = json.loads(creds_json)
            credentials = sa.Credentials.from_service_account_info(
                info, scopes=["https://www.googleapis.com/auth/analytics.readonly"]
            )
            self._client = BetaAnalyticsDataClient(credentials=credentials)
        else:
            self._client = BetaAnalyticsDataClient()
        return self._client

    def _extract_days(self, text: str) -> int:
        import re
        m = re.search(r"(\d+)\s*(?:дн|день|days?)", text, re.I)
        return int(m.group(1)) if m else 7

    def _no_sdk_message(self, package: str) -> str:
        return (f"❌ GA4: установите SDK: pip install {package}\n"
                f"  Также нужен: pip install google-auth")


def handle(text: str, core=None) -> str | None:
    t = text.lower()
    if not any(kw in t for kw in SKILL_TRIGGERS):
        return None
    return GA4Analytics(core).handle_command(text)
