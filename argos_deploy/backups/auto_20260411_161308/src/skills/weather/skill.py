"""
weather — Навык Аргоса: получение реального прогноза погоды
Использует wttr.in (бесплатно, без API-ключа).
"""

from __future__ import annotations
import re
import requests

TRIGGERS = [
    "погода", "weather", "прогноз", "температура на улице",
    "какая погода", "какой прогноз", "погоду",
]

# Символы направлений ветра
_WIND_DIR = {
    "N": "↑С", "NE": "↗СВ", "E": "→В", "SE": "↘ЮВ",
    "S": "↓Ю", "SW": "↙ЮЗ", "W": "←З", "NW": "↖СЗ",
    "NNE": "↑↗ССВ", "ENE": "→↗ВСВ", "ESE": "→↘ВЮВ", "SSE": "↓↘ЮЮВ",
    "SSW": "↓↙ЮЮЗ", "WSW": "←↙ЗЮЗ", "WNW": "←↖ЗСЗ", "NNW": "↑↖ССЗ",
}

_WMO_CODES = {
    0: "☀️ Ясно",
    1: "🌤 Преимущественно ясно", 2: "⛅ Переменная облачность", 3: "☁️ Пасмурно",
    45: "🌫 Туман", 48: "🌫 Туман с изморозью",
    51: "🌦 Слабая морось", 53: "🌦 Морось", 55: "🌧 Сильная морось",
    61: "🌧 Слабый дождь", 63: "🌧 Дождь", 65: "🌧 Сильный дождь",
    71: "🌨 Слабый снег", 73: "❄️ Снег", 75: "❄️ Сильный снег",
    77: "🌨 Снежная крупа",
    80: "🌦 Кратковременный дождь", 81: "🌦 Дождь с грозой", 82: "⛈ Ливень",
    85: "🌨 Снегопад", 86: "❄️ Сильный снегопад",
    95: "⛈ Гроза", 96: "⛈ Гроза с градом", 99: "⛈ Сильная гроза с градом",
}


def _extract_city(text: str) -> str:
    """Вытащить название города из текста."""
    t = text.strip()
    # Убираем триггерные слова (сначала длинные)
    for trigger in sorted(TRIGGERS, key=len, reverse=True):
        t = re.sub(re.escape(trigger), "", t, flags=re.IGNORECASE).strip()
    # Убираем служебные слова
    for stop in (r"\bв\b", r"\bво\b", r"\bдля\b", r"\bсейчас\b",
                 r"\bсегодня\b", r"\bзавтра\b", r"\btoday\b", r"\bnow\b",
                 r"\bcurrently\b"):
        t = re.sub(stop, "", t, flags=re.IGNORECASE).strip()
    city = re.sub(r"\s+", " ", t).strip().strip("?!,.")
    return city or "Москва"


def _fetch_wttr(city: str) -> dict | None:
    """Получить JSON с wttr.in."""
    try:
        from urllib.parse import quote
        url = f"https://wttr.in/{quote(city)}?format=j1"
        resp = requests.get(url, timeout=10, headers={"User-Agent": "curl/7.68.0"})
        if resp.status_code == 200:
            return resp.json()
    except Exception:
        pass
    return None


def _format_weather(data: dict, city: str) -> str:
    """Форматировать погодный JSON в читаемый ответ."""
    try:
        cur = data["current_condition"][0]
        temp_c    = cur.get("temp_C", "?")
        feels     = cur.get("FeelsLikeC", "?")
        humidity  = cur.get("humidity", "?")
        wind_kmph = cur.get("windspeedKmph", "?")
        wind_dir  = cur.get("winddir16Point", "")
        wind_sym  = _WIND_DIR.get(wind_dir, wind_dir)
        wmo       = int(cur.get("weatherCode", 0))
        desc_ru   = _WMO_CODES.get(wmo, cur.get("weatherDesc", [{}])[0].get("value", "—"))

        nearest     = data.get("nearest_area", [{}])[0]
        area_name   = nearest.get("areaName",  [{}])[0].get("value", city)
        country     = nearest.get("country",   [{}])[0].get("value", "")
        location_str = f"{area_name}, {country}" if country else area_name

        tomorrow_str = ""
        weather_list = data.get("weather", [])
        if len(weather_list) > 1:
            tom    = weather_list[1]
            tmax   = tom.get("maxtempC", "?")
            tmin   = tom.get("mintempC", "?")
            hourly = tom.get("hourly", [{}])
            mid    = hourly[4] if len(hourly) > 4 else (hourly[0] if hourly else {})
            tom_wmo  = int(mid.get("weatherCode", 0))
            tom_desc = _WMO_CODES.get(tom_wmo, "—")
            tomorrow_str = f"\n🗓 *Завтра:* {tom_desc}, {tmin}…{tmax}°C"

        return (
            f"🌍 *{location_str}*\n"
            f"🌡 *{temp_c}°C* (ощущается {feels}°C)\n"
            f"{desc_ru}\n"
            f"💧 Влажность: {humidity}%\n"
            f"💨 Ветер: {wind_kmph} км/ч {wind_sym}"
            f"{tomorrow_str}"
        )
    except Exception as e:
        return f"⚠️ Не удалось разобрать данные о погоде: {e}"


def setup(core=None):
    """Инициализация навыка."""
    pass


def handle(text: str, core=None) -> str | None:
    """Обработка запроса погоды. Вернуть None если не наш запрос."""
    t = text.lower()
    if not any(tr in t for tr in TRIGGERS):
        return None

    city = _extract_city(text)
    data = _fetch_wttr(city)

    if data is None:
        # Fallback: однострочный текстовый формат
        try:
            from urllib.parse import quote
            resp = requests.get(f"https://wttr.in/{quote(city)}?format=3", timeout=8,
                                headers={"User-Agent": "curl/7.68.0"})
            if resp.status_code == 200:
                return f"☁️ {resp.text.strip()}"
        except Exception:
            pass
        return f"❌ Не удалось получить погоду для '{city}'. Проверьте соединение."

    return _format_weather(data, city)


def teardown():
    """Завершение работы навыка."""
    pass
