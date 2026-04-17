"""
telegram_bot.py — Аргос Telegram Bridge v2.1

Возможности:
  • Роли: ADMIN (полный доступ) / USER (базовый доступ) / BOT (авторизованные боты)
  • Авторизация ботов: список BOT_IDS в .env — боты могут писать и получать ответы
  • Голосовой ответ: TTS → .ogg файл обратно пользователю
  • Ollama Vision: анализ фото через LLaVA если Gemini недоступен
  • Аудио/Голос/Фото/APK — полная поддержка медиа

Переменные окружения:
  TELEGRAM_BOT_TOKEN   — токен бота
  ADMIN_IDS            — ID администраторов через запятую (полный доступ)
  USER_IDS             — ID обычных пользователей (базовый доступ, через запятую)
  BOT_IDS              — ID авторизованных ботов (через запятую, могут писать как user)
  TG_VOICE_REPLY       — on/off — отвечать голосом (default: off)
  TG_VOICE_ENGINE      — gtts / pyttsx3 (default: gtts)
  TG_VOICE_LANG        — язык для gTTS (default: ru)
"""

from __future__ import annotations

import asyncio
import base64
import io
import os
import random
import re
import socket
import shlex
import subprocess
import tempfile
import time
from pathlib import Path
import urllib.request
import urllib.parse
import requests
from urllib.parse import urlparse
from typing import Optional

from telegram import Update, ReplyKeyboardMarkup, KeyboardButton, InputFile, Message
from telegram.error import InvalidToken, TelegramError, TimedOut, NetworkError
from telegram.ext import (
    Application, MessageHandler, CommandHandler,
    filters, ContextTypes,
)
from src.integration_orchestrator import run_full_integration

HISTORY_MESSAGES_LIMIT = 10
ARTIFACT_RETENTION_SECONDS = 15 * 60
ARTIFACT_MAX_FILES = 10
IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp"}
DOCUMENT_SUFFIXES = {
    ".txt", ".pdf", ".zip", ".7z", ".rar", ".json", ".csv", ".md",
    ".doc", ".docx", ".xlsx", ".xls", ".ppt", ".pptx",
}

HF_TXT2IMG_MODEL = os.getenv("HF_TXT2IMG_MODEL", "stabilityai/sdxl-turbo")
HF_IMAGE_PROMPT_SPACE = os.getenv("HF_IMAGE_PROMPT_SPACE", "NetNarco/Image-prompt-generator").strip()
HF_IMAGE_PROMPT_ENABLED = os.getenv("HF_IMAGE_PROMPT_ENABLED", "on").strip().lower() in ("1", "true", "on", "yes", "да", "вкл")
HF_IMAGE_SPACE_LIST = [
    x.strip() for x in os.getenv(
        "HF_IMAGE_SPACES",
        ",".join([
            "black-forest-labs/FLUX.2-dev",
            "mrfakename/Z-Image-Turbo",
            "Tongyi-MAI/Z-Image-Turbo",
            "dwzhu/PaperBanana",
            "Asahina2K/animagine-xl-4.0",
            "IbarakiDouji/FurryToonMix",
        ]),
    ).split(",")
    if x.strip()
]
HF_SPACE_FAIL_COOLDOWN_SECONDS = int(os.getenv("HF_SPACE_FAIL_COOLDOWN_SECONDS", "900") or "900")
HF_SPACE_FAIL_BACKOFF_MAX = int(os.getenv("HF_SPACE_FAIL_BACKOFF_MAX", "4") or "4")
_HF_SPACE_ERROR_CACHE: dict[str, dict] = {}


def _resolve_hf_token() -> str:
    """Единая точка получения HF токена (включая TOKEN0/underscore варианты)."""
    direct_names = ("HF_TOKEN", "HUGGINGFACE_TOKEN", "HUGGINGFACE_TOKEN0", "HF_TOKEN0")
    for key in direct_names:
        val = (os.getenv(key) or "").strip()
        if val:
            return val
    for i in range(20):
        for key in (f"HUGGINGFACE_TOKEN_{i}", f"HUGGINGFACE_TOKEN{i}", f"HF_TOKEN_{i}", f"HF_TOKEN{i}"):
            val = (os.getenv(key) or "").strip()
            if val:
                return val
    return ""


def _mask_secret(secret: str, keep: int = 4) -> str:
    value = (secret or "").strip()
    if not value:
        return "—"
    if len(value) <= keep * 2:
        return "*" * len(value)
    return f"{value[:keep]}...{value[-keep:]}"


def _project_env_path() -> Path:
    # src/connectivity/telegram_bot.py -> project root
    return Path(__file__).resolve().parents[2] / ".env"


def _upsert_env_key(path: Path, key: str, value: str) -> bool:
    """Обновляет/добавляет ключ в .env. Возвращает True при успехе."""
    key = (key or "").strip()
    if not key:
        return False
    try:
        if path.exists():
            lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
        else:
            lines = []
        pattern = re.compile(rf"^\s*{re.escape(key)}\s*=")
        replaced = False
        out: list[str] = []
        for line in lines:
            if pattern.match(line):
                out.append(f"{key}={value}")
                replaced = True
            else:
                out.append(line)
        if not replaced:
            out.append(f"{key}={value}")
        path.write_text("\n".join(out) + "\n", encoding="utf-8")
        return True
    except Exception:
        return False

# Разрешённые домены (только открытые источники)
ALLOWED_DOMAINS = {
    "unsplash.com",
    "api.unsplash.com",
    "images.unsplash.com",
    "source.unsplash.com",
    "loremflickr.com",
    "picsum.photos",
    "picvario.ru",
    "huggingface.co",
    "huggingfaceusercontent.com",
    "shaip.com",
    "technologika.ru",
    "pexels.com",
    "images.pexels.com",
    "openverse.engineering",
    "commons.wikimedia.org",
    "files.freemusicarchive.org",
    "freemusicarchive.org",
    "freemusicarchive.com",
    "jamendo.com",
    "storage-freemusicarchive-org.storage.googleapis.com",
    "raw.githubusercontent.com",
    "githubusercontent.com",
    "github.com",
    "gutenberg.org",
    "www.gutenberg.org",
    "samplefiles.org",
    "wq7tlqy4nukd4.ok.kimi.link",
    "worldbank.org",
    "data.worldbank.org",
    "api.worldbank.org",
    "datahelpdesk.worldbank.org",
    "un.org",
    "data.un.org",
    "oecd.org",
    "data.oecd.org",
    "census.gov",
    "api.census.gov",
    "opendatasoft.com",
    "data.cityofnewyork.us",
    "openweathermap.org",
    "api.openweathermap.org",
    "twilio.com",
    "api.twilio.com",
    "sendgrid.com",
    "api.sendgrid.com",
    "clearbit.com",
    "ipstack.com",
    "abstractapi.com",
    "apify.com",
    "api.apify.com",
    "pdf.co",
    "api.pdf.co",
    "bit.ly",
    "bitly.com",
    "dev.bitly.com",
    "opencagedata.com",
}
# По умолчанию ВСЕГДА полный интернет-поиск (не спрашивать разрешение)
CONTENT_ALLOW_ALL = True

def get_allowed_domains():
    return sorted(ALLOWED_DOMAINS)

def update_allowed_domains(add=None, remove=None):
    add = add or []
    remove = remove or []
    for d in add:
        if d:
            ALLOWED_DOMAINS.add(d.strip().lower())
    for d in remove:
        if d:
            ALLOWED_DOMAINS.discard(d.strip().lower())
    return get_allowed_domains()

# ── Вспомогательные fetch-функции для открытых API изображений ───────────────
def _fetch_openverse_images(query: str, limit: int = 5):
    try:
        import requests
        resp = requests.get(
            "https://api.openverse.engineering/v1/images",
            params={"q": query, "page_size": limit, "license_type": "commercial"},
            timeout=10,
        )
        if not resp.ok:
            return []
        data = resp.json()
        results = data.get("results", [])
        return [r.get("url") or r.get("thumbnail") for r in results if r.get("url")]
    except Exception:
        return []

def _fetch_wikimedia_images(query: str, limit: int = 5):
    try:
        import requests
        resp = requests.get(
            "https://commons.wikimedia.org/w/api.php",
            params={
                "action": "query",
                "format": "json",
                "prop": "imageinfo",
                "iiprop": "url",
                "generator": "search",
                "gsrsearch": query,
                "gsrlimit": limit,
            },
            timeout=10,
        )
        if not resp.ok:
            return []
        data = resp.json()
        pages = data.get("query", {}).get("pages", {})
        out = []
        for p in pages.values():
            info = p.get("imageinfo")
            if info:
                url = info[0].get("url")
                if url:
                    out.append(url)
        return out
    except Exception:
        return []

def _fetch_pexels_images(query: str, limit: int = 5):
    api_key = os.getenv("PEXELS_API_KEY", "").strip()
    if not api_key:
        return []
    try:
        import requests
        resp = requests.get(
            "https://api.pexels.com/v1/search",
            params={"query": query, "per_page": limit},
            headers={"Authorization": api_key},
            timeout=10,
        )
        if not resp.ok:
            return []
        photos = resp.json().get("photos", [])
        return [p.get("src", {}).get("original") or p.get("src", {}).get("large") for p in photos if p.get("src")]
    except Exception:
        return []

def _fetch_unsplash_api_images(query: str, limit: int = 5):
    api_key = os.getenv("UNSPLASH_ACCESS_KEY", "").strip()
    if not api_key:
        return []
    try:
        import requests
        resp = requests.get(
            "https://api.unsplash.com/search/photos",
            params={"query": query, "per_page": limit},
            headers={"Authorization": f"Client-ID {api_key}"},
            timeout=10,
        )
        if not resp.ok:
            return []
        results = resp.json().get("results", [])
        urls = []
        for r in results:
            u = r.get("urls", {}).get("regular") or r.get("urls", {}).get("full") or r.get("urls", {}).get("raw")
            if u:
                urls.append(u)
        return urls
    except Exception:
        return []

def _hf_generate_image(prompt: str):
    """Генеративный запасной вариант через HF Inference API (txt2img)."""
    token = _resolve_hf_token()
    if not token:
        return None
    try:
        import requests
        url = f"https://api-inference.huggingface.co/models/{HF_TXT2IMG_MODEL}"
        headers = {"Authorization": f"Bearer {token}"}
        payload = {"inputs": prompt, "options": {"wait_for_model": True}}
        resp = requests.post(url, json=payload, headers=headers, timeout=60)
        if not resp.ok:
            return None
        return resp.content  # bytes (png)
    except Exception:
        return None

def _hf_enhance_image_prompt(prompt: str) -> str | None:
    """Опционально улучшает image-prompt через HF Space (gradio_client)."""
    if not HF_IMAGE_PROMPT_ENABLED or not HF_IMAGE_PROMPT_SPACE:
        return None
    clean = (prompt or "").strip()
    if not clean:
        return None
    try:
        from gradio_client import Client
        kwargs = {}
        hf_token = _resolve_hf_token()
        if hf_token:
            kwargs["hf_token"] = hf_token
        try:
            client = Client(HF_IMAGE_PROMPT_SPACE, **kwargs)
        except TypeError:
            client = Client(HF_IMAGE_PROMPT_SPACE)
        for api_name in ("/predict", "/run", "/generate", "/generate_prompt"):
            try:
                out = client.predict(clean, api_name=api_name)
                if isinstance(out, str) and out.strip():
                    return out.strip()
                if isinstance(out, (list, tuple)):
                    for item in out:
                        if isinstance(item, str) and item.strip():
                            return item.strip()
            except Exception:
                continue
    except Exception:
        return None
    return None

def _to_image_bytes_from_any(value):
    """Пытается извлечь bytes изображения из ответа Space."""
    if value is None:
        return None
    if isinstance(value, bytes):
        return value
    if isinstance(value, str):
        v = value.strip()
        if not v:
            return None
        if os.path.exists(v):
            try:
                with open(v, "rb") as f:
                    return f.read()
            except Exception:
                return None
        if v.startswith("http://") or v.startswith("https://"):
            try:
                with urllib.request.urlopen(v, timeout=20) as r:
                    return r.read()
            except Exception:
                return None
        return None
    if isinstance(value, dict):
        for key in ("image", "url", "path", "name"):
            if key in value:
                b = _to_image_bytes_from_any(value.get(key))
                if b:
                    return b
        return None
    if isinstance(value, (list, tuple)):
        for item in value:
            b = _to_image_bytes_from_any(item)
            if b:
                return b
    return None

def _hf_generate_image_via_spaces(prompt: str):
    """Fallback генерации через список HF Spaces (gradio_client)."""
    clean = (prompt or "").strip()
    if not clean or not HF_IMAGE_SPACE_LIST:
        return None
    try:
        from gradio_client import Client
    except Exception:
        return None
    hf_token = _resolve_hf_token()
    kwargs = {"hf_token": hf_token} if hf_token else {}
    now = time.time()
    spaces = [
        s for s in HF_IMAGE_SPACE_LIST
        if float((_HF_SPACE_ERROR_CACHE.get(s, {}) or {}).get("until", 0)) <= now
    ]
    if not spaces:
        # Если все в кулдауне — пробуем все, чтобы не залипнуть полностью.
        spaces = list(HF_IMAGE_SPACE_LIST)
    random.shuffle(spaces)
    for space in spaces:
        last_error = ""
        try:
            try:
                client = Client(space, **kwargs)
            except TypeError:
                client = Client(space)
        except Exception as e:
            last_error = str(e)
            rec = _HF_SPACE_ERROR_CACHE.get(space, {})
            fails = int(rec.get("fails", 0)) + 1
            mult = min(max(fails, 1), max(HF_SPACE_FAIL_BACKOFF_MAX, 1))
            _HF_SPACE_ERROR_CACHE[space] = {
                "fails": fails,
                "until": time.time() + HF_SPACE_FAIL_COOLDOWN_SECONDS * mult,
                "error": last_error[:300],
            }
            continue
        named_endpoints = {}
        try:
            api_info = client.view_api(return_format="dict") or {}
            named_endpoints = api_info.get("named_endpoints", {}) or {}
        except Exception:
            named_endpoints = {}

        preferred = ["/generate_image", "/generate", "/txt2img", "/predict", "/run", "/image"]
        endpoint_names = [x for x in preferred if x in named_endpoints] or list(named_endpoints.keys()) or preferred
        for api_name in endpoint_names:
            try:
                if api_name in named_endpoints:
                    spec = named_endpoints.get(api_name, {})
                    args = []
                    for p in spec.get("parameters", []):
                        pname = (p.get("parameter_name") or "").lower()
                        label = (p.get("label") or "").lower()
                        component = (p.get("component") or "").lower()
                        if "prompt" in pname or pname in {"text", "query", "inputs"} or "prompt" in label:
                            args.append(clean)
                        elif p.get("parameter_has_default", False):
                            args.append(p.get("parameter_default"))
                        elif component == "checkbox":
                            args.append(False)
                        elif component in {"slider", "number"}:
                            args.append(1)
                        else:
                            args.append("")
                    out = client.predict(*args, api_name=api_name)
                else:
                    if api_name in {"/generate_image", "/generate_image_1"}:
                        out = client.predict(clean, 1024, 1024, 9, 42, True, api_name=api_name)
                    else:
                        out = client.predict(clean, api_name=api_name)
                img = _to_image_bytes_from_any(out)
                if img:
                    _HF_SPACE_ERROR_CACHE.pop(space, None)
                    return img
            except Exception as e:
                last_error = str(e)
                continue
        rec = _HF_SPACE_ERROR_CACHE.get(space, {})
        fails = int(rec.get("fails", 0)) + 1
        mult = min(max(fails, 1), max(HF_SPACE_FAIL_BACKOFF_MAX, 1))
        _HF_SPACE_ERROR_CACHE[space] = {
            "fails": fails,
            "until": time.time() + HF_SPACE_FAIL_COOLDOWN_SECONDS * mult,
            "error": (last_error or "empty_result")[:300],
        }
    return None

def _translit_ru_to_lat(s: str) -> str:
    table = {
        "а": "a","б": "b","в": "v","г": "g","д": "d","е": "e","ё": "e","ж": "zh","з": "z","и": "i","й": "y","к": "k","л": "l","м": "m",
        "н": "n","о": "o","п": "p","р": "r","с": "s","т": "t","у": "u","ф": "f","х": "h","ц": "ts","ч": "ch","ш": "sh","щ": "shch","ъ": "",
        "ы": "y","ь": "","э": "e","ю": "yu","я": "ya",
    }
    return "".join(table.get(ch, ch) for ch in s.lower())

def _maybe_translate_ru_to_en(q: str) -> str:
    """Мини-словарь + пословный перевод + транслитерация."""
    phrase_map = {
        "цой": "viktor tsoi",
        "виктор цой": "viktor tsoi",
        "баба яга": "baba yaga",
        "колобок": "kolobok fairy tale",
        "кот и собака": "cat and dog",
        "кошка и собака": "cat and dog",
        "кот и пес": "cat and dog",
    }
    key_full = q.lower().strip()
    if key_full in phrase_map:
        return phrase_map[key_full]

    mapping = {
        # Природа / животные — все падежные формы
        "кот": "cat",   "кота": "cat",  "коту": "cat",  "котом": "cat",
        "коте": "cat",  "котов": "cats",
        "котик": "cat", "котика": "cat",
        "кошка": "cat", "кошки": "cat", "кошку": "cat",
        "котенок": "kitten", "котята": "kittens",
        "собака": "dog", "собаки": "dogs", "собаку": "dog", "собакой": "dog",
        "пес": "dog",   "пса": "dog",   "псу": "dog",
        "щенок": "puppy", "щенка": "puppy", "щенки": "puppies",
        "лошадь": "horse", "лошади": "horses", "лошадей": "horses", "лошадку": "horse",
        "конь": "horse", "коня": "horse",
        "птица": "bird",  "птицы": "birds", "птичка": "bird",
        "орел": "eagle",  "орла": "eagle",
        "медведь": "bear","медведя": "bear",
        "волк": "wolf",   "волка": "wolf",  "волки": "wolves",
        "лиса": "fox",    "лисы": "fox",    "лису": "fox",
        "заяц": "rabbit", "зайца": "rabbit",
        "олень": "deer",  "оленя": "deer",
        "тигр": "tiger",  "тигра": "tiger",
        "лев": "lion",    "льва": "lion",   "львица": "lioness",
        "слон": "elephant","слона": "elephant",
        "обезьяна": "monkey","обезьяны": "monkey",
        "рыба": "fish",   "рыбы": "fish",
        "акула": "shark",
        # Природа
        "лес": "forest",  "леса": "forest", "лесу": "forest",
        "море": "sea",    "моря": "sea",    "морю": "sea",
        "океан": "ocean",
        "река": "river",  "реки": "river",
        "гора": "mountain","горы": "mountains","горах": "mountains",
        "небо": "sky",    "облака": "clouds",
        "закат": "sunset","рассвет": "sunrise",
        "снег": "snow",   "зима": "winter", "зимой": "winter",
        "лето": "summer", "осень": "autumn","весна": "spring",
        "дождь": "rain",  "радуга": "rainbow",
        "пляж": "beach",  "пляже": "beach",
        "пустыня": "desert",
        "водопад": "waterfall",
        "пейзаж": "landscape",
        "парк": "park",
        # Города / архитектура
        "город": "city",  "города": "city",
        "улица": "street","дом": "house",
        "замок": "castle","дворец": "palace",
        "мост": "bridge",
        # Объекты / разное
        "машина": "car",  "машины": "cars",  "автомобиль": "car",
        "мотоцикл": "motorcycle",
        "самолет": "airplane","самолёт": "airplane",
        "корабль": "ship","лодка": "boat",
        "поезд": "train",
        "цветы": "flowers","цветок": "flower","роза": "rose",
        "розы": "roses",  "ромашка": "daisy","ромашки": "daisies",
        "кофе": "coffee",
        "киберпанк": "cyberpunk",
        "качели": "swing",
        "и": "and",
    }
    key = key_full
    if key in mapping:
        return mapping[key]
    tokens = [mapping.get(tok, tok) for tok in key.split()]
    if tokens != key.split():
        return " ".join(tokens)
    translit = _translit_ru_to_lat(key_full)
    if translit and translit != key_full:
        return translit
    return q

# ── РОЛИ ──────────────────────────────────────────────────────────────────────
ROLE_ADMIN = "admin"
ROLE_USER  = "user"
ROLE_BOT   = "bot"
ROLE_NONE  = None

# Команды/интенты, запрещённые для роли USER
_USER_BLOCKED_PREFIXES = (
    "консоль", "терминал", "выключи систему", "убей процесс",
    "удали файл", "удали папку", "установи persistence",
    "установи автозапуск", "удали автозапуск",
    "роль доступа", "установи роль",
)


def _load_id_set(env_key: str) -> set[str]:
    """Загружает список ID из переменной окружения через запятую."""
    raw = os.getenv(env_key, "").strip()
    if not raw:
        return set()
    return {x.strip() for x in raw.split(",") if x.strip()}


def _is_allowed(url: str) -> bool:
    try:
        host = urlparse(url).hostname or ""
        host = host.lower()
        return any(host == d or host.endswith(f".{d}") for d in ALLOWED_DOMAINS)
    except Exception:
        return False


def _set_content_mode(mode: str) -> str:
    """admin-only toggle for content whitelist"""
    global CONTENT_ALLOW_ALL
    if mode.lower() in ("free", "all", "on"):
        CONTENT_ALLOW_ALL = True
        return "🔓 Контент: свобода (whitelist отключён)"
    if mode.lower() in ("safe", "off"):
        CONTENT_ALLOW_ALL = False
        return "🔒 Контент: только whitelist"
    return f"ℹ️ Текущий режим: {'free' if CONTENT_ALLOW_ALL else 'safe'}"


class ArgosTelegram:
    def __init__(self, core, admin=None, flasher=None):
        self.core    = core
        self.admin   = admin
        self.flasher = flasher
        self.token   = os.getenv("TELEGRAM_BOT_TOKEN", "")
        self.app: Optional[Application] = None
        # Память отправленных изображений: query -> последний URL, чтобы не повторять один и тот же кадр.
        self._last_image_url_by_query: dict[str, str] = {}
        # Контекст погоды по чату: ожидаем город / последний успешный запрос.
        self._awaiting_weather_city: set[str] = set()
        self._last_weather_query_by_chat: dict[str, str] = {}
        # Последняя ошибка Telegram для диагностики
        self._last_tg_error: str = ""
        self._last_tg_error_ts: float = 0.0

        # ── Роли и авторизация ──
        self.admin_ids: set[str] = _load_id_set("ADMIN_IDS")
        self.user_ids:  set[str] = _load_id_set("USER_IDS")
        self.bot_ids:   set[str] = _load_id_set("BOT_IDS")

        # Обратная совместимость: USER_ID (одиночный или через запятую) → admin
        legacy = os.getenv("USER_ID", "").strip()
        if legacy:
            self.admin_ids.add(legacy.split(",")[0].strip())  # первый ID → admin (legacy)

        # allowed_ids — из USER_ID env var (с поддержкой запятой)
        _uid_str = os.getenv("USER_ID", "").strip()
        self.allowed_ids: set[str] = {uid.strip() for uid in _uid_str.split(",") if uid.strip()}

        # ── Голосовой ответ ──
        self.voice_reply  = os.getenv("TG_VOICE_REPLY", "off").strip().lower() in ("1", "on", "yes", "true")
        self.voice_engine = os.getenv("TG_VOICE_ENGINE", "gtts").strip().lower()
        self.voice_lang   = os.getenv("TG_VOICE_LANG",   "ru").strip()
        self._recent_artifacts_by_chat: dict[str, dict[str, object]] = {}
        self._poll_lock_socket: Optional[socket.socket] = None
        # Сетевые параметры Telegram (чтобы не падать на кратковременных таймаутах).
        self.tg_connect_timeout = float(os.getenv("TG_CONNECT_TIMEOUT_SEC", "20") or "20")
        self.tg_read_timeout = float(os.getenv("TG_READ_TIMEOUT_SEC", "30") or "30")
        self.tg_write_timeout = float(os.getenv("TG_WRITE_TIMEOUT_SEC", "30") or "30")
        self.tg_pool_timeout = float(os.getenv("TG_POOL_TIMEOUT_SEC", "30") or "30")
        self.tg_updates_connect_timeout = float(
            os.getenv("TG_GET_UPDATES_CONNECT_TIMEOUT_SEC", str(self.tg_connect_timeout))
            or str(self.tg_connect_timeout)
        )
        self.tg_updates_read_timeout = float(
            os.getenv("TG_GET_UPDATES_READ_TIMEOUT_SEC", "35") or "35"
        )
        self.tg_updates_write_timeout = float(
            os.getenv("TG_GET_UPDATES_WRITE_TIMEOUT_SEC", "35") or "35"
        )
        self.tg_updates_pool_timeout = float(
            os.getenv("TG_GET_UPDATES_POOL_TIMEOUT_SEC", "35") or "35"
        )
        self.tg_bootstrap_retries = int(os.getenv("TG_BOOTSTRAP_RETRIES", "-1") or "-1")
        self.tg_poll_timeout = int(os.getenv("TG_POLL_TIMEOUT_SEC", "30") or "30")
        self.tg_proxy = (
            os.getenv("TG_PROXY_URL", "").strip()
            or os.getenv("HTTPS_PROXY", "").strip()
            or os.getenv("HTTP_PROXY", "").strip()
            or None
        )


    # ── АВТОРИЗАЦИЯ ───────────────────────────────────────────────────────────

    def _get_role(self, update: Update) -> str | None:
        """Определяет роль отправителя. Возвращает ROLE_* или None."""
        user = update.effective_user
        if user is None:
            return ROLE_NONE
        uid = str(user.id)
        if uid in self.admin_ids:
            return ROLE_ADMIN
        if uid in self.user_ids:
            return ROLE_USER
        if uid in self.bot_ids or getattr(user, "is_bot", False):
            # Бот авторизован только если его ID в BOT_IDS
            return ROLE_BOT if uid in self.bot_ids else ROLE_NONE
        # Проверяем allowed_ids (упрощённый режим авторизации через USER_ID)
        if uid in getattr(self, "allowed_ids", set()):
            return ROLE_USER
        return ROLE_NONE

    def _auth(self, update: Update) -> bool:
        """True если отправитель имеет хоть какую-то роль."""
        return self._get_role(update) is not ROLE_NONE

    def _is_admin(self, update: Update) -> bool:
        return self._get_role(update) == ROLE_ADMIN

    # ── Placeholders that should never be used as real tokens ────────────────
    _TOKEN_PLACEHOLDERS = frozenset({"", "none", "changeme", "your_token_here", "токен", "token"})

    def can_start(self) -> tuple[bool, str]:
        """Проверяет, можно ли запустить бота (токен и USER_ID заданы корректно).

        Returns:
            (ok, reason) — ok=True если конфигурация валидна, иначе ok=False и reason объясняет причину.
        """
        token = (self.token or "").strip()
        # Проверка токена
        if not token or token.lower() in self._TOKEN_PLACEHOLDERS:
            return False, "Токен не задан или является заглушкой"
        if ":" not in token:
            return False, "Неверный формат токена (ожидается <id>:<secret>)"
        _, secret = token.split(":", 1)
        if len(secret) < 30:
            return False, "Неверный формат токена (секрет слишком короткий)"
        # Проверка USER_ID
        user_id = (getattr(self, "user_id", "") or "").strip()
        allowed = getattr(self, "allowed_ids", set()) or set()
        if not user_id and not allowed:
            return False, "USER_ID не задан"
        return True, "ok"

    def _check_user_blocked(self, text: str) -> bool:
        """True если команда запрещена для роли USER."""
        t = text.lower().strip()
        return any(t.startswith(p) for p in _USER_BLOCKED_PREFIXES)

    def _handle_hf_token_message(self, text: str, role: str | None) -> str | None:
        """
        Обрабатывает сообщения вида:
          HUGGINGFACE_TOKEN0
          HUGGINGFACE_TOKEN0=hf_xxx
          HF_TOKEN=hf_xxx
          hf_xxx  (голый токен)
        """
        raw = (text or "").strip()
        if not raw:
            return None

        var_match = re.match(
            r"^(HUGGINGFACE_TOKEN(?:_\d+|\d+)?|HF_TOKEN(?:_\d+|\d+)?)\s*(?:[:=]\s*(\S+))?$",
            raw,
            flags=re.IGNORECASE,
        )
        bare_token_match = re.match(r"^(hf_[A-Za-z0-9]{20,})$", raw)

        if not var_match and not bare_token_match:
            return None

        # Голый токен — кладём в HUGGINGFACE_TOKEN0
        if bare_token_match:
            var_name = "HUGGINGFACE_TOKEN0"
            token_value = bare_token_match.group(1).strip()
        else:
            var_name = (var_match.group(1) or "").upper()
            token_value = (var_match.group(2) or "").strip()

        # Запрос статуса без значения: "HUGGINGFACE_TOKEN0"
        if not token_value:
            current = (os.getenv(var_name) or "").strip()
            resolved = _resolve_hf_token()
            msg = [
                "🤗 HuggingFace token status:",
                f"  {var_name}: {'✅ задан' if current else '❌ не задан'}",
                f"  Активный (resolve): {'✅ найден' if resolved else '❌ не найден'}",
                "  Формат установки: HUGGINGFACE_TOKEN0=hf_xxx",
            ]
            try:
                from src.skills.huggingface_ai import HuggingFaceAI

                msg.append(f"  Пул: {HuggingFaceAI.pool_status()}")
            except Exception:
                pass
            return "\n".join(msg)

        if not token_value.startswith("hf_"):
            return "❌ Неверный формат HF токена. Должен начинаться с `hf_`."

        if role != ROLE_ADMIN:
            return "⛔ Устанавливать токены может только ADMIN."

        # Применяем в runtime
        os.environ[var_name] = token_value
        if var_name == "HUGGINGFACE_TOKEN0":
            os.environ["HUGGINGFACE_TOKEN_0"] = token_value
        if var_name == "HF_TOKEN0":
            os.environ["HF_TOKEN_0"] = token_value
        if var_name in {"HUGGINGFACE_TOKEN0", "HUGGINGFACE_TOKEN_0", "HF_TOKEN0", "HF_TOKEN_0"} and not os.getenv("HF_TOKEN"):
            os.environ["HF_TOKEN"] = token_value

        # Сохраняем в .env
        env_file = _project_env_path()
        saved_keys = []
        if _upsert_env_key(env_file, var_name, token_value):
            saved_keys.append(var_name)
        if var_name == "HUGGINGFACE_TOKEN0":
            if _upsert_env_key(env_file, "HUGGINGFACE_TOKEN_0", token_value):
                saved_keys.append("HUGGINGFACE_TOKEN_0")
        if var_name == "HF_TOKEN0":
            if _upsert_env_key(env_file, "HF_TOKEN_0", token_value):
                saved_keys.append("HF_TOKEN_0")

        # Пытаемся обновить пул HF-скила
        pool_status = "неизвестно"
        try:
            from src.skills.huggingface_ai import HuggingFaceAI

            pool_status = HuggingFaceAI.pool_status()
        except Exception:
            pass

        return (
            "✅ HF токен обновлён.\n"
            f"  Ключ: {var_name}\n"
            f"  Значение: {_mask_secret(token_value)}\n"
            f"  .env: {'обновлён (' + ', '.join(saved_keys) + ')' if saved_keys else 'не удалось обновить'}\n"
            f"  Пул: {pool_status}"
        )

    async def _deny(self, update: Update, reason: str = "Доступ запрещён."):
        if update.message:
            await update.message.reply_text(f"⛔ {reason}")

    # ── ГОЛОСОВОЙ ОТВЕТ ───────────────────────────────────────────────────────

    def _tts_to_ogg(self, text: str) -> Optional[bytes]:
        """Генерирует .ogg (opus) из текста. Возвращает байты или None."""
        clean = text[:500]  # Telegram voice limit
        try:
            if self.voice_engine == "gtts":
                return self._tts_gtts(clean)
            return self._tts_pyttsx3(clean)
        except Exception:
            return None

    def _tts_gtts(self, text: str) -> Optional[bytes]:
        try:
            from gtts import gTTS
            buf = io.BytesIO()
            gTTS(text=text, lang=self.voice_lang, slow=False).write_to_fp(buf)
            mp3_bytes = buf.getvalue()
            # Конвертация MP3 → OGG (opus) через ffmpeg если доступен
            return self._mp3_to_ogg(mp3_bytes)
        except ImportError:
            return None

    def _mp3_to_ogg(self, mp3_bytes: bytes) -> bytes:
        """Конвертирует MP3 в OGG opus. Пробует ffmpeg, затем pydub, затем mp3 as-is."""
        # Вариант 1: ffmpeg (лучшее качество)
        import shutil
        ffmpeg = shutil.which("ffmpeg")
        if ffmpeg:
            try:
                proc = subprocess.run(
                    [ffmpeg, "-y", "-f", "mp3", "-i", "pipe:0",
                     "-c:a", "libopus", "-b:a", "64k", "-f", "ogg", "pipe:1"],
                    input=mp3_bytes, capture_output=True, timeout=15,
                )
                if proc.returncode == 0 and proc.stdout:
                    return proc.stdout
            except Exception:
                pass
        # Вариант 2: pydub (pip install pydub)
        try:
            from pydub import AudioSegment
            import io as _io
            seg = AudioSegment.from_mp3(_io.BytesIO(mp3_bytes))
            buf = _io.BytesIO()
            seg.export(buf, format="ogg", codec="libopus")
            return buf.getvalue()
        except Exception:
            pass
        # Fallback: mp3 как есть (Telegram примет как аудио-файл)
        return mp3_bytes

    def _tts_pyttsx3(self, text: str) -> Optional[bytes]:
        try:
            import pyttsx3
            engine = pyttsx3.init()
            for v in engine.getProperty("voices"):
                if "russian" in v.name.lower() or "ru" in v.id.lower():
                    engine.setProperty("voice", v.id)
                    break
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
                wav_path = tmp.name
            engine.save_to_file(text, wav_path)
            engine.runAndWait()
            with open(wav_path, "rb") as f:
                wav_bytes = f.read()
            os.remove(wav_path)
            return self._wav_to_ogg(wav_bytes)
        except Exception:
            return None

    def _wav_to_ogg(self, wav_bytes: bytes) -> bytes:
        try:
            proc = subprocess.run(
                ["ffmpeg", "-y", "-f", "wav", "-i", "pipe:0",
                 "-c:a", "libopus", "-b:a", "64k", "-f", "ogg", "pipe:1"],
                input=wav_bytes,
                capture_output=True,
                timeout=15,
            )
            if proc.returncode == 0 and proc.stdout:
                return proc.stdout
        except (FileNotFoundError, subprocess.TimeoutExpired):
            pass
        return wav_bytes

    async def _reply_with_voice(self, message: Message, text: str, force_voice: bool = False):
        """Отправляет голосовой ответ; при force_voice игнорирует toggle voice_reply."""
        if self.voice_reply or force_voice:
            audio_bytes = await asyncio.to_thread(self._tts_to_ogg, text)
            if audio_bytes:
                # Пробуем как voice (OGG opus)
                try:
                    await message.reply_voice(
                        voice=io.BytesIO(audio_bytes),
                        caption=text[:200] + ("…" if len(text) > 200 else ""),
                    )
                    return
                except Exception:
                    pass
                # Fallback: отправляем как аудио-файл
                try:
                    await message.reply_audio(
                        audio=io.BytesIO(audio_bytes),
                        filename="argos_reply.mp3",
                        title="Аргос",
                    )
                    return
                except Exception:
                    pass
        # fallback — текст
        await message.reply_text(text[:4000])

    async def _safe_reply_text(self, message: Message, text: str, markdown: bool = True):
        """Надёжная отправка текста в Telegram с graceful fallback на plain text."""
        payload = (text or "")[:4000]
        if markdown:
            try:
                await message.reply_text(payload, parse_mode="Markdown")
                return
            except Exception:
                pass
        await message.reply_text(payload, parse_mode=None)

    def _acquire_poll_lock(self) -> tuple[bool, str]:
        """Гарантирует, что локально работает только один polling-экземпляр бота."""
        host = os.getenv("ARGOS_TG_LOCK_HOST", "127.0.0.1").strip() or "127.0.0.1"
        port = int(os.getenv("ARGOS_TG_LOCK_PORT", "58443") or "58443")
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            sock.bind((host, port))
            sock.listen(1)
            self._poll_lock_socket = sock
            return True, f"{host}:{port}"
        except OSError:
            try:
                sock.close()
            except Exception:
                pass
            return False, f"{host}:{port}"

    def _release_poll_lock(self):
        sock = self._poll_lock_socket
        self._poll_lock_socket = None
        if sock is None:
            return
        try:
            sock.close()
        except Exception:
            pass

    def _build_apk_sync(self) -> tuple[bool, str]:
        """Synchronous APK build. Returns (ok, path_or_error_message)."""
        import shlex
        cmd = os.getenv("ARGOS_APK_BUILD_CMD", "").strip()
        if not cmd:
            return False, "ARGOS_APK_BUILD_CMD is not set"
        if not cmd.strip():
            return False, "ARGOS_APK_BUILD_CMD is empty"
        try:
            args = shlex.split(cmd)
        except ValueError:
            return False, "ARGOS_APK_BUILD_CMD parse error"
        try:
            result = subprocess.run(args, capture_output=True, text=True, timeout=600)
            if result is not None and result.returncode != 0:
                return False, f"Сборка завершилась с ошибкой: {result.stderr[:200]}"
        except subprocess.CalledProcessError as e:
            return False, f"Сборка завершилась с ошибкой: {e}"
        except Exception as e:
            return False, f"Build error: {e}"
        apk_path = self._find_apk_artifact()
        if not apk_path:
            return False, "APK file not found after build"
        return True, apk_path

    def _find_apk_artifact(self) -> str | None:
        """Search for APK file in typical build locations."""
        import glob
        patterns = ["build/bin/*.apk", "bin/*.apk", "*.apk", "build/*.apk", "app/build/outputs/apk/**/*.apk"]
        for pattern in patterns:
            matches = glob.glob(pattern, recursive=True)
            if matches:
                return sorted(matches, key=os.path.getmtime, reverse=True)[0]
        return None

    async def cmd_tg_health(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        """Пинг Telegram + статус последней ошибки."""
        started = time.perf_counter()
        try:
            me = await ctx.bot.get_me()
            latency_ms = (time.perf_counter() - started) * 1000
            msg = [
                "🤖 Telegram health",
                f"  Bot: @{getattr(me, 'username', '?')}",
                f"  ID: {getattr(me, 'id', '?')}",
                f"  Ping: {latency_ms:.0f} ms",
            ]
        except Exception as e:
            msg = [
                "🤖 Telegram health",
                f"  Ошибка пинга: {e}",
            ]

        if self._last_tg_error:
            ts = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(self._last_tg_error_ts))
            msg.append(f"  Последняя ошибка: [{ts}] {self._last_tg_error}")
        else:
            msg.append("  Последняя ошибка: нет")

        await self._safe_reply_text(update.message, "\n".join(msg), markdown=False)

    # --- Запуск бота ------------------------------------------------------
    def run(self):
        """Блокирующий запуск Telegram бота (используется в отдельном потоке)."""
        if not self.token:
            print("[TG] TELEGRAM_BOT_TOKEN не задан")
            return
        retry_delay = max(3, int(os.getenv("TG_RETRY_DELAY_SEC", "8") or "8"))
        retries = 0
        while True:
            try:
                # Инициализация приложения (timeouts + proxy)
                builder = (
                    Application.builder()
                    .token(self.token)
                    .connect_timeout(self.tg_connect_timeout)
                    .read_timeout(self.tg_read_timeout)
                    .write_timeout(self.tg_write_timeout)
                    .pool_timeout(self.tg_pool_timeout)
                    .get_updates_connect_timeout(self.tg_updates_connect_timeout)
                    .get_updates_read_timeout(self.tg_updates_read_timeout)
                    .get_updates_write_timeout(self.tg_updates_write_timeout)
                    .get_updates_pool_timeout(self.tg_updates_pool_timeout)
                )
                if self.tg_proxy:
                    builder = builder.proxy(self.tg_proxy)
                self.app = builder.build()

                # Команды
                self.app.add_handler(CommandHandler("start", self.cmd_start))
                self.app.add_handler(CommandHandler("status", self.cmd_status))
                self.app.add_handler(CommandHandler("voice_on", self.cmd_voice_on))
                self.app.add_handler(CommandHandler("voice_off", self.cmd_voice_off))
                self.app.add_handler(CommandHandler("voice_reply", self.cmd_voice_reply_toggle))
                self.app.add_handler(CommandHandler("roles", self.cmd_roles))
                self.app.add_handler(CommandHandler("providers", self.cmd_providers))
                self.app.add_handler(CommandHandler("skills", self.cmd_skills))
                self.app.add_handler(CommandHandler("skills_check", self.cmd_skills_check))
                self.app.add_handler(CommandHandler("arc_status", self.cmd_arc_status))
                self.app.add_handler(CommandHandler("arc_play", self.cmd_arc_play))
                self.app.add_handler(CommandHandler("limits", self.cmd_limits))
                self.app.add_handler(CommandHandler("agents", self.cmd_agents))
                self.app.add_handler(CommandHandler("network", self.cmd_network))
                self.app.add_handler(CommandHandler("sync", self.cmd_sync))
                self.app.add_handler(CommandHandler("crypto", self.cmd_crypto))
                self.app.add_handler(CommandHandler("history", self.cmd_history))
                self.app.add_handler(CommandHandler("geo", self.cmd_geo))
                self.app.add_handler(CommandHandler("memory", self.cmd_memory))
                self.app.add_handler(CommandHandler("alerts", self.cmd_alerts))
                self.app.add_handler(CommandHandler("replicate", self.cmd_replicate))
                self.app.add_handler(CommandHandler("smart", self.cmd_smart))
                self.app.add_handler(CommandHandler("iot", self.cmd_iot))
                self.app.add_handler(CommandHandler("apk", self.cmd_apk))
                self.app.add_handler(CommandHandler("help", self.cmd_help))
                self.app.add_handler(CommandHandler(["tghealth", "tg_health"], self.cmd_tg_health))

                # Сообщения
                self.app.add_handler(MessageHandler(filters.VOICE, self.handle_voice))
                self.app.add_handler(MessageHandler(filters.PHOTO, self.handle_photo))
                self.app.add_handler(MessageHandler(filters.AUDIO, self.handle_audio))
                self.app.add_handler(MessageHandler(filters.Document.ALL, self.handle_document))
                self.app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_message))
                self.app.add_error_handler(self._handle_telegram_error)

                print("[TG] polling started")
                self.app.run_polling(
                    close_loop=False,
                    timeout=self.tg_poll_timeout,
                    bootstrap_retries=self.tg_bootstrap_retries,
                )
                print("[TG] polling stopped")
                return
            except InvalidToken:
                print("[TG] Неверный TELEGRAM_BOT_TOKEN — остановка.")
                return
            except (TimedOut, NetworkError, TelegramError) as e:
                retries += 1
                self._last_tg_error = str(e)
                self._last_tg_error_ts = time.time()
                print(f"[TG] Telegram сеть/API ошибка (retry={retries}): {e}")
                time.sleep(retry_delay)
            except Exception as e:
                retries += 1
                self._last_tg_error = str(e)
                self._last_tg_error_ts = time.time()
                print(f"[TG] Неожиданная ошибка polling (retry={retries}): {e}")
                time.sleep(retry_delay)

    async def _handle_telegram_error(self, update, context):
        error = getattr(context, "error", None)
        text = str(error or "")
        self._last_tg_error = text
        self._last_tg_error_ts = time.time()
        if "terminated by other getUpdates request" in text or "Conflict:" in text:
            if getattr(self, "_conflict_notified", False):
                return
            self._conflict_notified = True
            print("[TG-BRIDGE]: Конфликт polling — другой экземпляр бота уже использует getUpdates.")
            try:
                updater = getattr(context.application, "updater", None)
                if updater is not None:
                    await updater.stop()
            except Exception:
                pass
            try:
                await context.application.stop()
            except Exception:
                pass
            return
        print(f"[TG-BRIDGE]: Error handler caught: {text}")

    # ── OLLAMA VISION ─────────────────────────────────────────────────────────

    # ── КЛАВИАТУРЫ ────────────────────────────────────────────────────────────

    def _admin_keyboard(self) -> ReplyKeyboardMarkup:
        return ReplyKeyboardMarkup(
            [
                [KeyboardButton("/status"),    KeyboardButton("/history"),   KeyboardButton("/help")],
                [KeyboardButton("/voice_on"),  KeyboardButton("/voice_off"), KeyboardButton("/skills")],
                [KeyboardButton("/crypto"),    KeyboardButton("/alerts"),    KeyboardButton("/apk")],
                [KeyboardButton("/smart"),     KeyboardButton("/iot"),       KeyboardButton("/memory")],
                [KeyboardButton("/providers"), KeyboardButton("/limits"),    KeyboardButton("/agents")],
                [KeyboardButton("/network"),   KeyboardButton("/restart"),   KeyboardButton("/update")],
                [KeyboardButton("/patches")],
            ],
            resize_keyboard=True,
            one_time_keyboard=False,
            input_field_placeholder="Команда или директива...",
        )

    def _user_keyboard(self) -> ReplyKeyboardMarkup:
        return ReplyKeyboardMarkup(
            [
                [KeyboardButton("/status"),   KeyboardButton("/history"),  KeyboardButton("/help")],
                [KeyboardButton("/skills"),   KeyboardButton("/crypto"),   KeyboardButton("/alerts")],
                [KeyboardButton("/apk"),      KeyboardButton("/voice_on"), KeyboardButton("/voice_off")],
                [KeyboardButton("/smart"),    KeyboardButton("/memory"),   KeyboardButton("/iot")],
            ],
            resize_keyboard=True,
            one_time_keyboard=False,
            input_field_placeholder="Команда или вопрос...",
        )

    # ── КОМАНДЫ ───────────────────────────────────────────────────────────────

    async def cmd_start(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        role = self._get_role(update)
        if role is ROLE_NONE:
            await self._deny(update, "Нет доступа. Обратитесь к администратору.")
            return
        keyboard = self._admin_keyboard() if role == ROLE_ADMIN else self._user_keyboard()
        role_label = {"admin": "👑 Администратор", "user": "👤 Пользователь", "bot": "🤖 Бот"}.get(role, role)
        text = (
            f"👁️ *АРГОС ОНЛАЙН*\n"
            f"Ваша роль: {role_label}\n\n"
            f"Отправь директиву текстом, голосом, фото или аудио.\n"
            f"/help — полный список команд"
        )
        try:
            await update.message.reply_text(text, parse_mode="Markdown", reply_markup=keyboard)
        except Exception:
            await update.message.reply_text(text, reply_markup=keyboard)

    async def cmd_status(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        if not self._auth(update): return await self._deny(update)
        # Используем кэш sensor_bridge — не блокирует
        health  = self.core.sensors.get_full_report()
        state   = self.core.quantum.generate_state()
        ai_mode = self.core.ai_mode_label()
        p2p_str = ""
        if self.core.p2p:
            try:
                net = self.core.p2p.network_status()
                p2p_str = f"\n🌐 P2P: {net[:80]}"
            except Exception:
                pass
        msg = (
            f"📊 *СИСТЕМНЫЙ ДОКЛАД*\n\n"
            f"{health}"
            f"{p2p_str}\n\n"
            f"⚛️ Квантовое состояние: `{state['name']}`\n"
            f"🤖 AI режим: `{ai_mode}`"
        )
        await self._safe_reply_text(update.message, msg[:4000], markdown=True)

    async def cmd_voice_on(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        if not self._auth(update): return await self._deny(update)
        self.core.voice_on = True
        self.voice_reply = True
        await update.message.reply_text("🔊 Голосовой модуль активирован. Аргос будет отвечать голосом.")

    async def cmd_voice_off(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        if not self._auth(update): return await self._deny(update)
        self.core.voice_on = False
        self.voice_reply = False
        await update.message.reply_text("🔇 Голосовой модуль отключён.")

    async def cmd_voice_reply_toggle(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        """Переключает только голосовой ОТВЕТ в Telegram (TTS → .ogg)."""
        if not self._auth(update): return await self._deny(update)
        self.voice_reply = not self.voice_reply
        state = "включён ✅" if self.voice_reply else "выключен ❌"
        engine = self.voice_engine.upper()
        await update.message.reply_text(
            f"🔊 Голосовой ответ {state}\n"
            f"Движок: {engine} | Язык: {self.voice_lang}\n"
        )

    async def cmd_roles(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        """Показывает текущие роли (только для admin)."""
        if not self._is_admin(update):
            return await self._deny(update, "Только для администратора.")
        admins = ", ".join(sorted(self.admin_ids)) or "не задано"
        users  = ", ".join(sorted(self.user_ids))  or "не задано"
        bots   = ", ".join(sorted(self.bot_ids))   or "не задано"
        voice_st = "✅ вкл" if self.voice_reply else "❌ выкл"
        await self._safe_reply_text(
            update.message,
            f"🔑 *РОЛИ И ДОСТУП*\n\n"
            f"👑 Admins: `{admins}`\n"
            f"👤 Users:  `{users}`\n"
            f"🤖 Bots:   `{bots}`\n\n"
            f"🔊 Голосовой ответ: {voice_st}\n"
            f"Настройка через .env:\n"
            f"  ADMIN\\_IDS=id1,id2\n"
            f"  USER\\_IDS=id3,id4\n"
            f"  BOT\\_IDS=botid1,botid2",
            markdown=True,
        )

    async def cmd_providers(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        if not self._auth(update): return await self._deny(update)
        try:
            from src.ai_providers import providers_status
            text = providers_status()
        except Exception as e:
            text = f"AI Providers: {e}"
        await update.message.reply_text(text[:4000])

    async def cmd_agents(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        if not self._auth(update):
            return await self._deny(update)
        try:
            from src.argos_claude_api import ArgosClaudeAPI
            api = ArgosClaudeAPI(self.core)
            if not api.is_ready():
                await update.message.reply_text("❌ Интегратор агентов не инициализирован.")
                return
            agents = api.list_agents(limit=30)
            if not agents:
                await update.message.reply_text("❌ Агентов не найдено.")
                return
            lines = ["🤖 Агенты проекта:"]
            for a in agents:
                lines.append(f"- {a['name']} [{a.get('category','?')}]")
            lines.append("")
            lines.append("Чтобы применить: `используй навык <имя>` или `агент <имя>: <задача>`")
            await update.message.reply_text("\n".join(lines)[:4000])
        except Exception as e:
            await update.message.reply_text(f"❌ agents: {e}")

    def _build_limits_report(self) -> str:
        lines = ["📈 Лимиты и состояние провайдеров"]
        try:
            from src.ai_router import _GEMINI_POOL, _provider_state, _COOLDOWN
            key_count = 0
            for i in range(20):
                if os.getenv(f"GEMINI_API_KEY_{i}") or os.getenv(f"GEMINI_API_KEY{i}"):
                    key_count += 1
            if os.getenv("GEMINI_API_KEY"):
                key_count += 1
            lines.append(f"• Gemini ключей: {key_count}")
            lines.append(f"• Gemini RPM/ключ: {os.getenv('GEMINI_RPM_PER_KEY', '5')}")
            lines.append(f"• Gemini pool: {_GEMINI_POOL.status()}")
            lines.append(f"• Cooldown роутера: {_COOLDOWN}s")
            if _provider_state:
                now = time.time()
                cooling = []
                for name, last_fail in _provider_state.items():
                    left = max(0, int(_COOLDOWN - (now - float(last_fail))))
                    if left > 0:
                        cooling.append(f"{name}:{left}s")
                lines.append("• Router cooldown: " + (", ".join(cooling) if cooling else "нет"))
            else:
                lines.append("• Router cooldown: нет")
        except Exception as e:
            lines.append(f"• AI Router: {e}")

        if self.core:
            try:
                disabled = getattr(self.core, "_provider_disabled_until", {}) or {}
                reasons = getattr(self.core, "_provider_disable_reason", {}) or {}
                if disabled:
                    now = time.time()
                    rows = []
                    for name, until in disabled.items():
                        left = max(0, int(float(until) - now))
                        if left > 0:
                            reason = reasons.get(name, "ошибка")
                            rows.append(f"{name}:{left}s ({reason[:60]})")
                    lines.append("• Core cooldown: " + (", ".join(rows) if rows else "нет"))
                else:
                    lines.append("• Core cooldown: нет")
                lines.append(f"• AI режим: {self.core.ai_mode_label()}")
                if hasattr(self.core, "gigachat_rotation_status"):
                    try:
                        lines.append("• GigaChat rotation: " + self.core.gigachat_rotation_status())
                    except Exception:
                        pass
            except Exception as e:
                lines.append(f"• Core: {e}")

        deepseek = "есть" if os.getenv("DEEPSEEK_API_KEY") else "нет"
        gigachat = "есть" if (os.getenv("GIGACHAT_ACCESS_TOKEN") or (os.getenv("GIGACHAT_CLIENT_ID") and os.getenv("GIGACHAT_CLIENT_SECRET"))) else "нет"
        yandex = "есть" if (os.getenv("YANDEX_IAM_TOKEN") and os.getenv("YANDEX_FOLDER_ID")) else "нет"
        lines.append(f"• DeepSeek ключ: {deepseek}")
        lines.append(f"• GigaChat ключи: {gigachat}")
        lines.append(f"• YandexGPT ключи: {yandex}")
        return "\n".join(lines)

    async def cmd_limits(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        if not self._auth(update):
            return await self._deny(update)
        await update.message.reply_text(self._build_limits_report()[:4000])

    async def cmd_skills(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        if not self._auth(update): return await self._deny(update)
        # Берём актуальный runtime-лоадер ядра (manifest + flat skills).
        if self.core.skill_loader:
            report = self.core.skill_loader.list_skills()
        else:
            try:
                from src.skills.evolution import ArgosEvolution
                report = ArgosEvolution().list_skills()
            except ImportError:
                report = "❌ SkillLoader недоступен."
        await update.message.reply_text(report[:4000])

    async def cmd_skills_check(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        if not self._auth(update):
            return await self._deny(update)
        if not self.core.skill_loader:
            return await update.message.reply_text("❌ SkillLoader недоступен.")
        report = self.core.skill_loader.smoke_check_all(core=self.core)
        # Длинный отчёт отправляем частями
        chunk = []
        size = 0
        for line in report.splitlines():
            if size + len(line) + 1 > 3500:
                await update.message.reply_text("\n".join(chunk))
                chunk = [line]
                size = len(line) + 1
            else:
                chunk.append(line)
                size += len(line) + 1
        if chunk:
            await update.message.reply_text("\n".join(chunk))

    async def cmd_arc_status(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        if not self._auth(update):
            return await self._deny(update)
        try:
            port = int(os.getenv("CONTENT_API_PORT", "5050") or "5050")
            r = requests.get(f"http://127.0.0.1:{port}/arc/status", timeout=8)
            rs = requests.get(f"http://127.0.0.1:{port}/arc/stats", timeout=8)
            data = r.json() if r.ok else {"state": "error", "message": f"http {r.status_code}"}
            stats = rs.json() if rs.ok else {}
            lines = [
                "🎮 ARC STATUS",
                f"state: {data.get('state', 'unknown')}",
                f"env: {data.get('env_id', '-')}",
                f"steps: {data.get('steps', '-')}",
                f"action: {data.get('action_name', '-')}",
                f"score: {data.get('score', '-')}",
                f"actions: {data.get('total_actions', '-')}",
                f"levels_completed: {data.get('total_levels_completed', '-')}",
                f"msg: {data.get('message', '-')}",
                "",
                "🧠 LEARNING",
                f"runs_total: {stats.get('runs_total', '-')}",
                f"runs_ok: {stats.get('runs_ok', '-')}",
                f"best_score: {stats.get('best_score', '-')}",
                f"best_env: {stats.get('best_env', '-')}",
                f"recommended_steps: {stats.get('recommended_steps', '-')}",
                f"qml_mode: {stats.get('qml_mode', '-')}",
                f"ibm_quantum: {stats.get('ibm_quantum', '-')}",
            ]
            await update.message.reply_text("\n".join(lines)[:4000])
        except Exception as e:
            await update.message.reply_text(f"❌ ARC status error: {e}")

    async def cmd_arc_play(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        if not self._auth(update):
            return await self._deny(update)
        args = ctx.args or []
        env_id = args[0] if len(args) >= 1 else "ls20"
        try:
            steps = int(args[1]) if len(args) >= 2 else 0
        except Exception:
            steps = 10
        render = False
        if len(args) >= 3:
            render = args[2].strip().lower() in ("1", "true", "on", "yes", "да")
        action_name = args[3].strip().upper() if len(args) >= 4 else None
        try:
            port = int(os.getenv("CONTENT_API_PORT", "5050") or "5050")
            payload = {"env_id": env_id, "steps": steps, "render": render, "action_name": action_name}
            r = requests.post(f"http://127.0.0.1:{port}/arc/play", json=payload, timeout=12)
            if r.ok:
                await update.message.reply_text(
                    f"🎮 ARC run started: env={env_id}, steps={steps or 'auto'}, render={render}, action={action_name or 'policy'}\n"
                    f"Проверь /arc_status через 5-10 секунд."
                )
            else:
                await update.message.reply_text(f"❌ ARC play HTTP {r.status_code}: {r.text[:300]}")
        except Exception as e:
            await update.message.reply_text(f"❌ ARC play error: {e}")

    async def cmd_network(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        if not self._auth(update): return await self._deny(update)
        if self.core.p2p:
            await update.message.reply_text(self.core.p2p.network_status())
        else:
            await update.message.reply_text("P2P не запущен.")

    async def cmd_sync(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        if not self._auth(update): return await self._deny(update)
        await update.message.reply_text("🔄 Синхронизирую навыки...")
        if self.core.p2p:
            result = self.core.p2p.sync_skills_from_network()
            await update.message.reply_text(result)
        else:
            await update.message.reply_text("P2P не запущен.")

    async def cmd_crypto(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        if not self._auth(update): return await self._deny(update)
        try:
            from src.skills.crypto_monitor import CryptoSentinel
            report = CryptoSentinel().report()
            await update.message.reply_text(report)
        except Exception as e:
            await update.message.reply_text(f"❌ Крипто: {e}")

    async def cmd_history(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        if not self._auth(update): return await self._deny(update)
        if self.core.db:
            hist = self.core.db.format_history(HISTORY_MESSAGES_LIMIT)
            await update.message.reply_text(hist[:4000])
        else:
            await update.message.reply_text("БД не подключена.")

    async def cmd_geo(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        if not self._auth(update): return await self._deny(update)
        try:
            from src.connectivity.spatial import SpatialAwareness
            report = SpatialAwareness(db=self.core.db).get_full_report()
            await update.message.reply_text(report)
        except Exception as e:
            await update.message.reply_text(f"❌ Геолокация: {e}")

    async def cmd_memory(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        if not self._auth(update): return await self._deny(update)
        args = ctx.args or []
        sub = args[0].lower() if args else ""

        if sub == "clean":
            # Ручная дедупликация по команде /memory clean
            if not self.core.memory:
                return await update.message.reply_text("Память не активирована.")
            await update.message.reply_text("🧹 Запускаю дедупликацию памяти...")
            try:
                result = await asyncio.to_thread(self.core.memory.deduplicate)
                await update.message.reply_text(result)
            except Exception as e:
                await update.message.reply_text(f"❌ Ошибка дедупликации: {e}")
            return

        if self.core.memory:
            await update.message.reply_text(self.core.memory.format_memory()[:4000])
        else:
            await update.message.reply_text("Память не активирована.")

    async def cmd_alerts(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        if not self._auth(update): return await self._deny(update)
        if self.core.alerts:
            await update.message.reply_text(self.core.alerts.status())
        else:
            await update.message.reply_text("Система алертов не активирована.")

    async def cmd_replicate(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        if not self._is_admin(update):
            return await self._deny(update, "Только для администратора.")
        await update.message.reply_text("📦 Создаю реплику системы...")
        try:
            result = self.core.replicator.create_replica()
            await update.message.reply_text(result)
        except Exception as e:
            await update.message.reply_text(f"❌ {e}")

    async def cmd_smart(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        if not self._auth(update): return await self._deny(update)
        if self.core.smart_sys:
            await update.message.reply_text(self.core.smart_sys.full_status()[:4000])
        else:
            await update.message.reply_text("Умные системы не подключены.")

    async def cmd_iot(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        if not self._auth(update): return await self._deny(update)
        if self.core.iot_bridge:
            await update.message.reply_text(self.core.iot_bridge.status()[:4000])
        else:
            await update.message.reply_text("IoT Bridge не подключен.")

    async def cmd_apk(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        if not self._is_admin(update):
            return await self._deny(update, "Только для администратора.")
        await update.message.reply_text("📦 Запускаю сборку APK...")
        ok, payload = await asyncio.to_thread(self._build_apk_sync)
        if not ok:
            await update.message.reply_text(f"❌ {payload}")
            return
        try:
            with open(payload, "rb") as f:
                await update.message.reply_document(
                    document=f,
                    filename=os.path.basename(payload),
                    caption="✅ APK готов"
                )
        except Exception as e:
            await update.message.reply_text(f"❌ Не удалось отправить APK: {e}")

    async def cmd_help(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        role = self._get_role(update)
        if role is ROLE_NONE:
            return await self._deny(update)
        text = self._help_admin() if role == ROLE_ADMIN else self._help_user()
        await self._safe_reply_text(update.message, text, markdown=True)

    def _help_admin(self) -> str:
        return (
            "👁️ *АРГОС — АДМИНИСТРАТОР*\n\n"
            "*Система:*\n"
            "• `/status` — мониторинг ЦП/ОЗУ/диска\n"
            "• `/roles` — роли и авторизация\n"
            "• `/providers` — статус AI-провайдеров\n"
            "• `/limits` — лимиты/кулдауны провайдеров\n"
            "• `/agents` — агенты проекта\n"
            "• `/alerts` — алерты системы\n"
            "• `/network` — P2P сеть\n"
            "• `/replicate` — создать копию\n"
            "• `/apk` — сборка APK\n\n"
            "*Управление файлами:*\n"
            "• `покажи файлы [путь]`\n"
            "• `прочитай файл [путь]`\n"
            "• `создай файл [имя] [текст]`\n"
            "• `удали файл [путь]`\n"
            "• `консоль [команда]`\n\n"
            "*IoT / Smart:*\n"
            "• `/smart` — умные системы\n"
            "• `/iot` — IoT устройства\n\n"
            "*AI модели:*\n"
            "• `режим ии [gemini/ollama/groq/deepseek]`\n"
            "• `модель обучить` / `модель статус`\n"
            "• `модель квантовый статус`\n"
            "• `статус провайдеров`\n\n"
            "*Голос и медиа:*\n"
            "• `/voice_on` / `/voice_off` — TTS\n"
            "• `/voicereply` — голосовой ответ в Telegram\n"
            "• Голосовое сообщение → распознаётся и выполняется\n"
            "• Фото → анализ через Vision AI (Gemini или Ollama LLaVA)\n"
            "• Аудиофайл → расшифровка через Whisper\n\n"
            "*Память:*\n"
            "• `/memory` — долгосрочная память\n"
            "• `/history` — история диалога\n"
            "• `запомни [ключ]: [значение]`\n\n"
            "*Прочее:*\n"
            "• `/crypto` — BTC/ETH курсы\n"
            "• `/skills` — список навыков\n"
            "• `/skills_check` — диагностика запуска всех skills (37/37)\n"
            "• `помощь` — полный список команд ядра"
        )

    def _help_user(self) -> str:
        return (
            "👁️ *АРГОС — ПОЛЬЗОВАТЕЛЬ*\n\n"
            "• `/status` — состояние системы\n"
            "• `/crypto` — курсы криптовалют\n"
            "• `/memory` — ваши записи\n"
            "• `/smart` — умные системы\n"
            "• `/history` — история диалога\n\n"
            "*Голос и медиа:*\n"
            "• Голосовое сообщение → выполняется как команда\n"
            "• Фото → анализ изображения\n"
            "• Аудио → расшифровка текста\n\n"
            "*Запросы к ИИ:*\n"
            "• Просто напиши любой вопрос или команду\n"
            "• `запомни [что-то]` — сохранить в память\n"
            "• `расскажи про [тема]` — поиск + ответ"
        )

    # ── ОСНОВНЫЕ ОБРАБОТЧИКИ ──────────────────────────────────────────────────

    async def handle_voice(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        role = self._get_role(update)
        if role is ROLE_NONE:
            return await self._deny(update, "Доступ запрещён.")
        voice = update.message.voice if update.message else None
        if not voice:
            return await update.message.reply_text("❌ Голосовое не обнаружено.")
        await update.message.reply_text("🎙 Распознаю голос...")
        temp_path = None
        try:
            tg_file = await ctx.bot.get_file(voice.file_id)
            with tempfile.NamedTemporaryFile(suffix=".ogg", delete=False) as tmp:
                temp_path = tmp.name
            await tg_file.download_to_drive(custom_path=temp_path)
            text = await asyncio.to_thread(self.core.transcribe_audio_path, temp_path)
            if not text:
                return await update.message.reply_text("🤷 Не удалось распознать. Попробуй ещё раз.")
            import re as _re
            text = _re.sub(r"^[A-Za-zА-Яа-яЁё][A-Za-zА-Яа-яЁё0-9_]{0,30}:\s*", "", text).strip()
            await update.message.reply_text(f"📝 Распознано: *{text}*", parse_mode="Markdown")
            if role == ROLE_USER and self._check_user_blocked(text):
                return await self._deny(update, "Эта команда доступна только администратору.")
            result = await self.core.process_logic_async(text, self.admin, self.flasher)
            answer = result["answer"]
            state  = result["state"]
            if self.voice_reply:
                await self._reply_with_voice(update.message, answer[:500])
                if len(answer) > 50:
                    await update.message.reply_text(f"👁️ *ARGOS* `[{state}]`\n\n{answer[:4000]}", parse_mode="Markdown")
            else:
                await update.message.reply_text(f"👁️ *ARGOS* `[{state}]`\n\n{answer[:4000]}", parse_mode="Markdown")
        except Exception as e:
            await update.message.reply_text(f"❌ Ошибка голосового: {e}")
        finally:
            if temp_path and os.path.exists(temp_path):
                try: os.remove(temp_path)
                except Exception: pass

    async def handle_photo(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        role = self._get_role(update)
        if role is ROLE_NONE:
            return await self._deny(update, "Доступ запрещён.")
        photo = update.message.photo[-1] if update.message.photo else None
        if not photo:
            return await update.message.reply_text("❌ Изображение не обнаружено.")
        caption = update.message.caption or "Подробно опиши что изображено."
        await update.message.reply_text("🖼 Анализирую изображение...")
        temp_path = None
        try:
            tg_file = await ctx.bot.get_file(photo.file_id)
            with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as tmp:
                temp_path = tmp.name
            await tg_file.download_to_drive(custom_path=temp_path)
            if self.core.vision:
                result_text = await asyncio.to_thread(self.core.vision.analyze_image, temp_path, caption)
            else:
                result_text = "❌ Vision модуль не инициализирован."
            if self.voice_reply and result_text:
                await self._reply_with_voice(update.message, result_text[:500])
            await update.message.reply_text(result_text[:4000])
        except Exception as e:
            await update.message.reply_text(f"❌ Ошибка анализа: {e}")
        finally:
            if temp_path and os.path.exists(temp_path):
                try: os.remove(temp_path)
                except Exception: pass

    async def handle_audio(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        role = self._get_role(update)
        if role is ROLE_NONE:
            return await self._deny(update, "Доступ запрещён.")
        audio = update.message.audio if update.message else None
        if not audio:
            return await update.message.reply_text("❌ Аудиофайл не обнаружен.")
        await update.message.reply_text("🎵 Расшифровываю аудио...")
        temp_path = None
        try:
            tg_file = await ctx.bot.get_file(audio.file_id)
            suffix = os.path.splitext(audio.file_name)[1] if audio.file_name else ".mp3"
            with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
                temp_path = tmp.name
            await tg_file.download_to_drive(custom_path=temp_path)
            text = await asyncio.to_thread(self.core.transcribe_audio_path, temp_path)
            if not text:
                return await update.message.reply_text("🤷 Не удалось расшифровать аудио.")
            await update.message.reply_text(f"📝 Распознано: *{text}*", parse_mode="Markdown")
            if role == ROLE_USER and self._check_user_blocked(text):
                return await self._deny(update, "Эта команда доступна только администратору.")
            result = await self.core.process_logic_async(text, self.admin, self.flasher)
            answer = result["answer"]
            state  = result["state"]
            if self.voice_reply:
                await self._reply_with_voice(update.message, answer[:500])
            await update.message.reply_text(f"👁️ *ARGOS* `[{state}]`\n\n{answer[:4000]}", parse_mode="Markdown")
        except Exception as e:
            await update.message.reply_text(f"❌ Ошибка аудио: {e}")
        finally:
            if temp_path and os.path.exists(temp_path):
                try: os.remove(temp_path)
                except Exception: pass

    # ── ПРЯМОЕ ВЫПОЛНЕНИЕ ФАЙЛОВЫХ КОМАНД ────────────────────────────────────
    # Обходит core.process_logic и ToolCalling полностью.
    # Вызывается ДО process_logic_async для известных команд.

    _FILE_COMMANDS = (
        # Файлы
        "создай файл", "напиши файл",
        "прочитай файл", "открой файл",
        "удали файл", "удали папку",
        "покажи файлы", "список файлов",
        "файлы ", "добавь в файл",
        "допиши в файл", "дополни файл",
        "отредактируй файл", "измени файл",
        "скопируй файл", "переименуй файл",
        # Терминал / процессы
        "консоль ", "терминал ",
        "список процессов", "убей процесс",
        "статус системы", "чек-ап",
        "осознай систему", "осознай свою систему", "осознай проект",
        "сканируй систему", "просканируй систему", "проанализируй систему",
        "сканируй проект", "просканируй проект", "проанализируй проект",
        "осознай файлы", "осознай свои файлы", "сканируй файлы",
        "просканируй файлы", "структура проекта", "обзор проекта",
        # Навыки — перехватываем ДО Ollama
        "список навыков", "навыки аргоса", "все навыки",
        "диагностика навыков", "проверь навыки", "навыки статус",
        "запусти навык ", "выполни навык ", "используй навык ", "навыки",
        # Навыки по имени
        "крипто", "биткоин", "bitcoin",
        "сканируй сеть", "сетевой призрак",
        "дайджест", "проверь железо",
        "погода", "weather",
        "серп", "serp", "serpapi", "поищи ",
        "реадме", "ридми", "прочитай реадме", "проверь реадме", "readme", "read me", "прочитай его",
        "ton ", "тон ", "ton wallet", "тон кошелек", "тон кошелёк",
        "ai спроси", "ask grok", "ask openai", "ai grok", "ai openai",
        "hf ", "huggingface", "hf space", "hf semantic", "hf index", "hf search", "hf dataset",
        "интегрируй все", "полная интеграция", "full integration",
        "автоагент", "agent auto", "анализ файлов", "файлмонитор", "file monitor",
        "агенты проекта", "помощники проекта", "примени агентов", "примени помощников", "/agents", "agents",
        # Управление системой / контроль
        "статус", "status", "помощь", "help",
        "роль", "роли", "провайдеры", "providers", "/providers", "/skills",
        "лимиты", "limits", "/limits",
        "память", "alerts", "алерты", "умные системы",
        "iot", "network", "sync", "history", "geo", "apk",
        # Управление AI режимами / проверка провайдеров
        "включи гига чат", "включи гигачат", "режим ии гигачат", "режим gigachat",
        "включи gemini", "включи гемини", "режим ии gemini", "режим ии гемини",
        "включи яндекс", "включи yandex", "включи yandexgpt", "режим ии yandexgpt", "режим ии яндекс",
        "проверь доступ к гемини", "проверь gemini", "check gemini",
        "включи auto", "режим ии auto", "режим авто",
        # AICoder
        "запусти aicoder", "включи aicoder", "aicoder",
        # Desktop Actions — мышь/клавиатура/скриншот
        "мышь", "mouse",
        "клавиша", "нажми", "key ",
        "печатай", "type ",
        "скриншот", "screenshot",
        "горячие клавиши", "экран статус", "desktop status",
    )

    def _try_direct_execute(self, text: str) -> str | None:
        """
        Выполняет файловые и системные команды напрямую через self.admin,
        минуя core.process_logic и ToolCalling полностью.
        Возвращает строку-ответ или None если команда не распознана.
        """
        t = text.lower().strip()
        if self.core and hasattr(self.core, "_looks_like_bulk_text_dump"):
            try:
                if self.core._looks_like_bulk_text_dump(text):
                    return self.core._analyze_bulk_text_dump(text)
            except Exception:
                pass
        if self.core and hasattr(self.core, "_extract_direct_url"):
            try:
                direct_url = self.core._extract_direct_url(text)
            except Exception:
                direct_url = None
            if direct_url:
                try:
                    if getattr(self.core, "web_explorer", None):
                        return self.core.web_explorer.fetch_page(direct_url)
                    return "⚠️ Web Explorer не инициализирован. Не могу прочитать ссылку."
                except Exception as e:
                    return f"❌ Ошибка чтения URL: {e}"
        if not any(t.startswith(cmd) or t == cmd.strip()
                   for cmd in self._FILE_COMMANDS):
            return None

        # ── Desktop Actions — мышь/клавиатура/скриншот ───────────────────
        _desktop_kw = ("мышь", "mouse", "клавиша", "нажми", "key ", "печатай",
                       "type ", "скриншот", "screenshot", "горячие клавиши",
                       "экран статус", "desktop status")
        if any(t.startswith(kw) for kw in _desktop_kw):
            if self.core and self.core.skill_loader:
                try:
                    res = self.core.skill_loader.dispatch(text, core=self.core)
                    if res is not None:
                        return res
                except Exception as _e:
                    return f"❌ desktop_actions: {_e}"
            return "❌ skill_loader не инициализирован"

        _skill_passthrough = (
            "ton ", "тон ", "ton wallet", "тон кошелек", "тон кошелёк",
            "ai спроси", "ask grok", "ask openai", "ai grok", "ai openai",
            "hf ", "huggingface",
            "serp", "серп", "serpapi", "поищи ",
            "автоагент", "agent auto", "анализ файлов", "файлмонитор", "file monitor",
        )
        if any(t.startswith(kw) for kw in _skill_passthrough):
            if self.core and getattr(self.core, "skill_loader", None):
                try:
                    res = self.core.skill_loader.dispatch(text, core=self.core)
                    if res is not None:
                        return str(res)
                except Exception as _e:
                    return f"❌ skill dispatch: {_e}"

        if t in ("интегрируй все", "полная интеграция", "full integration"):
            try:
                return run_full_integration()
            except Exception as e:
                return f"❌ full integration: {e}"

        if t in ("агенты проекта", "помощники проекта", "примени агентов", "примени помощников", "/agents", "agents"):
            try:
                from src.argos_claude_api import ArgosClaudeAPI
                api = ArgosClaudeAPI(self.core)
                if not api.is_ready():
                    return "❌ Интегратор агентов не инициализирован."
                agents = api.list_agents(limit=30)
                if not agents:
                    return "❌ Агентов не найдено."
                lines = ["🤖 Агенты проекта:"]
                for a in agents:
                    lines.append(f"- {a['name']} [{a.get('category','?')}]")
                lines.append("")
                lines.append("Чтобы применить: `используй навык <имя>` или `агент <имя>: <задача>`")
                return "\n".join(lines)
            except Exception as e:
                return f"❌ agents: {e}"

        if any(k in t for k in ("реадме", "ридми", "прочитай реадме", "проверь реадме", "readme", "read me", "прочитай его")):
            from pathlib import Path as _P
            roots = [
                _P.cwd(),
                _P(__file__).resolve().parents[2],  # project root
                _P(__file__).resolve().parents[1],  # src/
                _P(__file__).resolve().parents[0],  # src/connectivity/
            ]
            names = ("README.md", "readme.md", "Readme.md")
            for root in roots:
                for name in names:
                    candidate = root / name
                    try:
                        if candidate.exists():
                            try:
                                return candidate.read_text(encoding="utf-8", errors="ignore")[:12000]
                            except Exception:
                                with open(candidate, "r", encoding="utf-8", errors="ignore") as f:
                                    return f.read(12000)
                    except Exception:
                        continue
            # Последняя попытка — рекурсивный поиск по верхнему уровню проекта.
            for root in roots[:2]:
                try:
                    found = sorted(root.glob("**/README.md"))
                except Exception:
                    found = []
                for candidate in found[:3]:
                    try:
                        return candidate.read_text(encoding="utf-8", errors="ignore")[:12000]
                    except Exception:
                        continue
            return "❌ README.md не найден в проекте."

        if t in ("провайдеры", "providers", "/providers", "статус провайдеров"):
            try:
                from src.ai_providers import providers_status
                return providers_status()
            except Exception as e:
                return f"❌ providers: {e}"

        if t in ("список навыков", "навыки", "/skills", "skills", "навыки аргоса", "все навыки"):
            if self.core and getattr(self.core, "skill_loader", None):
                try:
                    return self.core.skill_loader.list_skills()
                except Exception as e:
                    return f"❌ skills: {e}"
            return "❌ skill_loader не инициализирован"

        if t in ("лимиты", "limits", "/limits", "лимиты провайдеров", "лимиты ai"):
            return self._build_limits_report()

        # ── Быстрые команды переключения AI режимов / проверки провайдеров ─
        if self.core:
            if any(k in t for k in ("включи гига чат", "включи гигачат", "режим ии гигачат", "режим gigachat")):
                try:
                    return self.core.set_ai_mode("gigachat")
                except Exception as e:
                    return f"❌ Не удалось переключить на GigaChat: {e}"

            if any(k in t for k in ("включи gemini", "включи гемини", "режим ии gemini", "режим ии гемини")):
                try:
                    return self.core.set_ai_mode("gemini")
                except Exception as e:
                    return f"❌ Не удалось переключить на Gemini: {e}"

            if any(k in t for k in ("включи яндекс", "включи yandex", "включи yandexgpt", "режим ии yandexgpt", "режим ии яндекс")):
                try:
                    return self.core.set_ai_mode("yandexgpt")
                except Exception as e:
                    return f"❌ Не удалось переключить на YandexGPT: {e}"

            if any(k in t for k in ("включи auto", "режим ии auto", "режим авто")):
                try:
                    return self.core.set_ai_mode("auto")
                except Exception as e:
                    return f"❌ Не удалось переключить на Auto: {e}"

            if any(k in t for k in ("проверь доступ к гемини", "проверь gemini", "check gemini")):
                try:
                    from src.ai_providers import providers_status
                    mode = self.core.ai_mode_label() if hasattr(self.core, "ai_mode_label") else "unknown"
                    gem_keys = []
                    for i in range(20):
                        if os.getenv(f"GEMINI_API_KEY_{i}") or os.getenv(f"GEMINI_API_KEY{i}"):
                            gem_keys.append(i)
                    has_fallback = bool(os.getenv("GEMINI_API_KEY"))
                    model_ready = bool(getattr(self.core, "model", None))
                    return (
                        f"{providers_status()}\n\n"
                        f"Текущий AI режим: {mode}\n"
                        f"Gemini ключей в пуле: {len(gem_keys)}"
                        + (" + fallback" if has_fallback else "")
                        + f"\nGemini client инициализирован: {'да' if model_ready else 'нет'}"
                    )
                except Exception as e:
                    return f"❌ Проверка Gemini не удалась: {e}"

            if any(k in t for k in ("запусти aicoder", "включи aicoder")):
                if getattr(self.core, "skill_loader", None):
                    try:
                        if hasattr(self.core.skill_loader, "dispatch_by_name"):
                            res = self.core.skill_loader.dispatch_by_name("ai_coder", text=text, core=self.core)
                            if res is not None:
                                return str(res)
                        for cmd in ("запусти навык ai_coder", "запусти навык aicoder", "используй навык ai_coder"):
                            res = self.core.skill_loader.dispatch(cmd, core=self.core)
                            if res is not None:
                                return str(res)
                    except Exception as e:
                        return f"❌ Ошибка запуска AICoder: {e}"
                return "❌ AICoder/skill_loader недоступен"

        # ── Навыки и система — НЕ требуют admin ──────────────────────────
        import os as _os3
        from pathlib import Path as _P3

        if self.core and (
            any(
                t.startswith(cmd) for cmd in (
                    "осознай систему", "осознай свою систему", "осознай проект",
                    "сканируй систему", "просканируй систему", "проанализируй систему",
                    "сканируй проект", "просканируй проект", "проанализируй проект",
                    "осознай файлы", "осознай свои файлы", "сканируй файлы",
                    "просканируй файлы", "структура проекта", "обзор проекта",
                )
            )
            or (
                any(m in t for m in ("осознай", "сканируй", "просканируй", "проанализируй", "аудит", "обзор"))
                and any(m in t for m in ("систем", "проект", "файл", "структур", "ядр", "навык", "модул"))
            )
        ):
            try:
                if hasattr(self.core, "_system_awareness_report"):
                    return self.core._system_awareness_report(self.admin)
            except Exception as e:
                return f"❌ Self-scan ошибка: {e}"

        if t in ("список навыков", "навыки аргоса", "все навыки", "навыки",
                  "диагностика навыков", "проверь навыки"):
            # Скан src/skills/ напрямую
            for _base3 in [_P3(__file__).resolve().parent,
                           _P3(__file__).resolve().parent.parent,
                           _P3.cwd()]:
                for _sub3 in ("src" + _os3.sep + "skills", "skills"):
                    _sd3 = _base3 / _sub3
                    if _sd3.exists():
                        _pkg_names3 = {f.name for f in _sd3.iterdir()
                                       if f.is_dir() and (f/"__init__.py").exists()}
                        _pkg3 = [f"  📦 {f.name}" for f in sorted(_sd3.iterdir())
                                 if f.is_dir() and (f/"__init__.py").exists()
                                 and not f.name.startswith("_")]
                        _flt3 = [f"  📄 {f.stem}" for f in sorted(_sd3.iterdir())
                                 if f.is_file() and f.suffix == ".py"
                                 and not f.name.startswith("_")
                                 and f.stem not in _pkg_names3]
                        _all3 = _pkg3 + _flt3
                        if _all3:
                            return (f"📚 НАВЫКИ АРГОСА ({len(_all3)}):\n"
                                    + "\n".join(_all3)
                                    + f"\n\nКаталог: {_sd3}")
            # Fallback через core
            if self.core:
                try:
                    if hasattr(self.core, "_skills_diagnostic"):
                        return self.core._skills_diagnostic()
                    if self.core.skill_loader:
                        return self.core.skill_loader.list_skills()
                except Exception:
                    pass
            return "📚 Навыки: укажи `диагностика навыков` для детальной информации"


        # Гарантируем admin
        adm = self.admin
        if adm is None:
            try:
                from src.admin import ArgosAdmin
                adm = ArgosAdmin()
                self.admin = adm
            except Exception as e:
                return f"❌ admin недоступен: {e}"

        try:
            # ── Навыки — абсолютный приоритет ────────────────────────────
            if t in ("список навыков", "навыки аргоса", "все навыки", "навыки"):
                # Прямой скан директории навыков
                import os as _os2
                from pathlib import Path as _P2
                for _base2 in [_P2(__file__).parent.parent,
                                _P2(__file__).parent,
                                _P2.cwd()]:
                    for _sub2 in ("src/skills", "skills"):
                        _sd2 = _base2 / _sub2.replace("/", _os2.sep)
                        if _sd2.exists():
                            _pkg2, _flt2 = [], []
                        _pkg_names2 = set()
                        for _f2 in sorted(_sd2.iterdir()):
                            if _f2.name.startswith("_"):
                                continue
                            if _f2.is_dir() and (_f2 / "__init__.py").exists():
                                _pkg2.append(f"  📦 {_f2.name}")
                                _pkg_names2.add(_f2.name)
                            elif _f2.is_file() and _f2.suffix == ".py":
                                if _f2.stem not in _pkg_names2:
                                    _flt2.append(f"  📄 {_f2.stem}")
                            _all2 = _pkg2 + _flt2
                            if _all2:
                                return (f"📚 НАВЫКИ АРГОСА ({len(_all2)} найдено):\n"
                                        + "\n".join(_all2)
                                        + f"\n\nКаталог: {_sd2}")
                # Если навыков нет — спросить core
                if self.core and getattr(self.core, "skill_loader", None):
                    try:
                        return self.core.skill_loader.list_skills()
                    except Exception:
                        pass
                return "📚 Навыки: src/skills не найден"

            if any(kw in t for kw in ("диагностика навыков", "проверь навыки", "навыки статус")):
                if self.core and hasattr(self.core, "_skills_diagnostic"):
                    return self.core._skills_diagnostic()

            if any(t.startswith(k) for k in ("запусти навык ", "выполни навык ", "используй навык ")):
                if self.core and getattr(self.core, "skill_loader", None):
                    try:
                        res = self.core.skill_loader.dispatch(text, core=self.core)
                        if res is not None:
                            return res
                    except Exception as e:
                        return f"❌ Ошибка запуска навыка: {e}"
                return "❌ skill_loader не инициализирован"

            # ── Создать файл ──────────────────────────────────────────────
            if any(t.startswith(k) for k in ("создай файл", "напиши файл")):
                body = text
                for k in ("создай файл", "напиши файл"):
                    body = body.replace(k, "").replace(k.capitalize(), "")
                body = body.strip()
                parts = body.split(maxsplit=1)
                fname    = parts[0] if parts else "note.txt"
                fcontent = parts[1] if len(parts) > 1 else ""
                return adm.create_file(fname, fcontent)

            # Прочитать файл
            if any(t.startswith(k) for k in ("прочитай файл", "открой файл")):
                path = text
                for k in ("прочитай файл", "открой файл"):
                    path = path.replace(k, "").replace(k.capitalize(), "").strip()
                return adm.read_file(path.strip())

            # Список файлов
            if any(t.startswith(k) for k in ("покажи файлы", "список файлов", "файлы ")):
                path = text
                for k in ("покажи файлы", "список файлов", "файлы"):
                    path = path.replace(k, "").replace(k.capitalize(), "").strip()
                return adm.list_dir(path or ".")

            # Удалить файл
            if any(t.startswith(k) for k in ("удали файл", "удали папку")):
                path = text
                for k in ("удали файл", "удали папку"):
                    path = path.replace(k, "").replace(k.capitalize(), "").strip()
                return adm.delete_item(path.strip())

            # Добавить в файл
            if any(t.startswith(k) for k in ("добавь в файл", "допиши в файл", "дополни файл")):
                tail = text
                for k in ("добавь в файл", "допиши в файл", "дополни файл"):
                    if k in t:
                        tail = text.split(k, 1)[-1].strip()
                        break
                parts = tail.split(maxsplit=1)
                if len(parts) >= 2:
                    return adm.append_file(parts[0], parts[1])
                return "Формат: добавь в файл [путь] [текст]"

            # Скопировать
            if t.startswith("скопируй файл"):
                tail = text.replace("скопируй файл", "").strip()
                parts = tail.split(maxsplit=1)
                if len(parts) == 2:
                    return adm.copy_file(parts[0], parts[1])
                return "Формат: скопируй файл [откуда] [куда]"

            # Переименовать
            if t.startswith("переименуй файл"):
                tail = text.replace("переименуй файл", "").strip()
                parts = tail.split(maxsplit=1)
                if len(parts) == 2:
                    return adm.rename_file(parts[0], parts[1])
                return "Формат: переименуй файл [старое] [новое]"

            # Консоль
            if t.startswith("консоль ") or t.startswith("терминал "):
                cmd = text.split(None, 1)[1].strip() if len(text.split()) > 1 else ""
                if cmd:
                    return adm.run_cmd(cmd, user="telegram")
                return "Формат: консоль [команда]"

            # Список процессов
            if t.startswith("список процессов"):
                return adm.list_processes()

            # Статус системы
            if any(t.startswith(k) for k in ("статус системы", "чек-ап")):
                return adm.get_stats()

            # Убить процесс
            if t.startswith("убей процесс"):
                name = text.replace("убей процесс", "").strip()
                return adm.kill_process(name) if name else "Укажи имя процесса"

            # ── СПИСОК НАВЫКОВ — читаем файловую систему напрямую ──────
            if any(t.strip() == k for k in
                   ("список навыков", "навыки аргоса", "все навыки", "навыки")):
                import os as _os
                from pathlib import Path as _P
                sd = None
                for _b in [_P(__file__).parent, _P.cwd()]:
                    for _sub in ("src/skills", "skills"):
                        _c = _b / _sub.replace("/", _os.sep)
                        if _c.exists():
                            sd = _c
                            break
                    if sd: break
                if sd:
                    pkg  = [f"  📦 {f.name}" for f in sorted(sd.iterdir())
                            if f.is_dir() and not f.name.startswith("_")]
                    flat = [f"  📄 {f.stem}" for f in sorted(sd.glob("*.py"))
                            if not f.stem.startswith("_")]
                    total = len(pkg) + len(flat)
                    lines = [f"📚 НАВЫКИ ({total}):"]  
                    if pkg:  lines += ["  [ПАКЕТЫ]"]  + pkg
                    if flat: lines += ["  [ФАЙЛЫ]"]   + flat
                    lines.append(f"  📂 {sd}")
                    return "\n".join(lines)
                return "❌ src/skills не найден"

            # ── ДИАГНОСТИКА навыков ─────────────────────────────────────
            if any(k in t for k in
                   ("диагностика навыков", "проверь навыки", "навыки статус")):
                core = self.core
                if core and hasattr(core, "_skills_diagnostic"):
                    return core._skills_diagnostic()
                return "❌ _skills_diagnostic недоступен"

        except Exception as e:
            return f"❌ Ошибка выполнения: {e}"

        return None


    async def handle_document(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        """
        Принимает .py файлы от admin, применяет как патч к кодовой базе.

        Безопасность:
          - Только ADMIN_IDS могут отправлять патчи
          - Синтаксическая проверка перед применением
          - Автоматическая очистка __pycache__ (Windows-совместимо)
          - Резервная копия оригинала перед перезаписью
          - Отчёт о применении
        """
        if not self._is_admin(update):
            await self._deny(update, "Патчи только для администратора.")
            return

        doc = update.message.document if update.message else None
        if not doc:
            return

        fname = doc.file_name or ""
        # Telegram добавляет " (N)" к дублирующимся именам: "core (14).py" → "core.py"
        import re as _re
        fname = _re.sub(r' \(\d+\)(?=\.)', '', fname)
        # Принимаем только .py файлы
        if not fname.endswith(".py"):
            await self._safe_reply_text(
                update.message,
                f"❌ Только .py файлы. Получен: `{fname}`",
                markdown=True,
            )
            return

        await self._safe_reply_text(update.message, f"📥 Получен патч `{fname}`. Применяю...", markdown=True)

        import os, shutil, sys, importlib, tempfile, ast
        from pathlib import Path

        temp_path = None
        try:
            # 1. Скачиваем патч во временный файл
            tg_file = await ctx.bot.get_file(doc.file_id)
            with tempfile.NamedTemporaryFile(suffix=".py", delete=False,
                                             mode='wb') as tmp:
                temp_path = tmp.name
            await tg_file.download_to_drive(custom_path=temp_path)

            # 2. Читаем содержимое
            with open(temp_path, 'r', encoding='utf-8') as f:
                patch_code = f.read()

            # 3. Синтаксическая проверка
            try:
                ast.parse(patch_code)
            except SyntaxError as se:
                await self._safe_reply_text(
                    update.message,
                    f"❌ Синтаксическая ошибка в патче:\n`{se}`",
                    markdown=True,
                )
                return

            # 4. Определяем куда сохранять
            # Имя файла → путь в проекте
            # patch_core.py          → core.py
            # patch_src_agent.py     → src/agent.py
            # src_connectivity_foo.py → src/connectivity/foo.py
            target_path = self._resolve_patch_target(fname)

            if target_path is None:
                # Файл не является патчем — сохраняем как есть рядом с main.py
                target_path = fname.replace("patch_", "")

            target = Path(target_path)

            # 5. Резервная копия если файл существует
            backup_path = None
            if target.exists():
                backup_path = str(target) + ".bak"
                shutil.copy2(str(target), backup_path)

            # 6. Создаём папку если нужно (Windows-совместимо)
            target.parent.mkdir(parents=True, exist_ok=True)

            # 7. Записываем патч
            with open(str(target), 'w', encoding='utf-8') as f:
                f.write(patch_code)

            # 8. Очищаем __pycache__ (Windows: удаляем .pyc для этого файла)
            cache_cleared = self._clear_pyc_cache(target)

            # 9. Горячая перезагрузка модуля если возможно
            hot_reload_msg = self._hot_reload_module(target_path)

            # 10. Отчёт
            lines = [
                f"✅ Патч `{fname}` применён!",
                f"📄 Файл: `{target_path}`",
                f"📦 Размер: {target.stat().st_size} байт",
                f"🗑 Кеш: {cache_cleared}",
            ]
            if backup_path:
                lines.append(f"💾 Резервная копия: `{backup_path}`")
            if hot_reload_msg:
                lines.append(f"🔄 {hot_reload_msg}")
            lines.append("\n⚡ Изменения вступят в силу при следующем запросе.")

            await self._safe_reply_text(update.message, "\n".join(lines), markdown=True)

        except Exception as e:
            await update.message.reply_text(f"❌ Ошибка применения патча: {e}")
        finally:
            if temp_path and os.path.exists(temp_path):
                try:
                    os.remove(temp_path)
                except Exception:
                    pass

    def _resolve_patch_target(self, fname: str) -> str | None:
        """
        Определяет путь назначения по имени файла патча.

        Правила именования:
          patch_core.py            → core.py
          patch_admin.py           → src/admin.py  (если есть в src/)
          patch_src_agent.py       → src/agent.py
          patch_src_skills_foo.py  → src/skills/foo.py
          tool_calling.py          → src/tool_calling.py  (без prefix)
          agent.py                 → src/agent.py
          core.py                  → core.py
        """
        import os
        from pathlib import Path

        # Убираем prefix "patch_"
        name = fname
        if name.startswith("patch_"):
            name = name[6:]  # убрать "patch_"

        # Если имя содержит подчёркивания как разделители путей
        # src_connectivity_foo.py → src/connectivity/foo.py
        if "_" in name and not name.startswith("_"):
            parts = name.replace(".py", "").split("_")
            # Пробуем интерпретировать как путь
            for i in range(len(parts), 0, -1):
                candidate_dir = os.path.join(*parts[:i])
                candidate_file = "_".join(parts[i:]) + ".py"
                candidate = os.path.join(candidate_dir, candidate_file)
                if os.path.exists(candidate):
                    return candidate

        # Прямые совпадения
        known_locations = {
            "core.py":          "core.py",
            "admin.py":         "src/admin.py",
            "agent.py":         "src/agent.py",
            "tool_calling.py":  "src/tool_calling.py",
            "telegram_bot.py":  "src/connectivity/telegram_bot.py",
            "system_health.py": "src/connectivity/system_health.py",
            "orangepi_bridge.py": "src/connectivity/orangepi_bridge.py",
            "argos_logger.py":  "src/argos_logger.py",
            "argos_model.py":   "src/argos_model.py",
            "neural_swarm.py":  "src/neural_swarm.py",
            "sensor_bridge.py": "src/connectivity/sensor_bridge.py",
            "p2p_bridge.py":    "src/connectivity/p2p_bridge.py",
            "ollama_trainer.py": "src/ollama_trainer.py",
        }
        if name in known_locations:
            return known_locations[name]

        # Ищем файл в src/ рекурсивно
        for root, _, files in os.walk("src"):
            if name in files:
                return os.path.join(root, name)

        # Файл не найден — сохраняем рядом с main.py
        return name

    def _clear_pyc_cache(self, target_path) -> str:
        """Удаляет .pyc кеш для файла. Windows-совместимо."""
        import os, glob
        from pathlib import Path

        target = Path(target_path)
        cleared = 0

        # Папка __pycache__ рядом с файлом
        cache_dir = target.parent / "__pycache__"
        if cache_dir.exists():
            stem = target.stem
            for pyc in cache_dir.glob(f"{stem}.*.pyc"):
                try:
                    pyc.unlink()
                    cleared += 1
                except Exception:
                    pass
            # Если папка пуста — удаляем
            try:
                if not any(cache_dir.iterdir()):
                    cache_dir.rmdir()
            except Exception:
                pass

        # Также проверяем корневой __pycache__
        root_cache = Path("__pycache__")
        if root_cache.exists():
            for pyc in root_cache.glob(f"{target.stem}.*.pyc"):
                try:
                    pyc.unlink()
                    cleared += 1
                except Exception:
                    pass

        return f"очищено {cleared} .pyc файлов"

    def _hot_reload_module(self, path: str) -> str:
        """Пытается горячо перезагрузить модуль без перезапуска."""
        import sys, importlib
        from pathlib import Path

        # Конвертируем путь в имя модуля
        # src/agent.py → src.agent
        # core.py → core (не модуль — пропускаем)
        path_obj = Path(path)
        if path_obj.parts[0] == "src":
            module_name = ".".join(path_obj.with_suffix("").parts)
        else:
            return ""  # корневые файлы не перезагружаем горячо

        if module_name in sys.modules:
            try:
                mod = sys.modules[module_name]
                importlib.reload(mod)
                return f"Модуль `{module_name}` перезагружен"
            except Exception as e:
                return f"Горячая перезагрузка не удалась: {e}"

        return ""

    async def handle_message(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        role = self._get_role(update)
        if role is ROLE_NONE:
            await self._deny(update, "Доступ запрещён. Попытка входа зафиксирована.")
            return

        user_text = update.message.text or ""
        if not user_text.strip():
            return

        # Убираем префикс "Имя:" если сообщение переслано или скопировано с именем
        import re as _re
        user_text = _re.sub(r"^[A-Za-zА-Яа-яЁё][A-Za-zА-Яа-яЁё0-9_]{0,30}:\s*", "", user_text).strip()
        if not user_text:
            return
        lt = user_text.lower().strip()
        chat_id = str(getattr(update.effective_chat, "id", "") or "")

        # Настройка HF токенов прямо из сообщения (admin-only для записи).
        hf_token_answer = self._handle_hf_token_message(user_text, role)
        if hf_token_answer is not None:
            await self._safe_reply_text(
                update.message,
                f"👁️ ARGOS [Direct]\n\n{hf_token_answer}",
                markdown=False,
            )
            return

        # Погода: жёсткий direct-роутинг, чтобы не уходить в Analytic-заглушки.
        if self.core and getattr(self.core, "skill_loader", None):
            is_weather_intent = (
                ("погод" in lt)
                or lt.startswith("weather")
                or lt in ("температура", "прогноз")
            )
            if is_weather_intent:
                try:
                    # Если это общий вопрос "погода" без города — запомним, что ждём город.
                    if lt in ("погода", "weather", "текущая погода", "погода сейчас"):
                        self._awaiting_weather_city.add(chat_id)
                        last_q = self._last_weather_query_by_chat.get(chat_id, "").strip()
                        query = last_q if last_q else ""
                    else:
                        self._awaiting_weather_city.discard(chat_id)
                        query = user_text
                    cmd = f"weather {query}".strip()
                    res = self.core.skill_loader.dispatch(cmd, core=self.core)
                    if res is not None:
                        if query:
                            self._last_weather_query_by_chat[chat_id] = query
                        await self._safe_reply_text(
                            update.message,
                            f"👁️ *ARGOS* `[Direct]`\n\n{res}",
                            markdown=True,
                        )
                        return
                except Exception:
                    pass
            elif chat_id in self._awaiting_weather_city and lt and len(lt) <= 120:
                # Пользователь после "погода" прислал только город/локацию.
                try:
                    query = user_text
                    res = self.core.skill_loader.dispatch(f"weather {query}", core=self.core)
                    if res is not None:
                        self._awaiting_weather_city.discard(chat_id)
                        self._last_weather_query_by_chat[chat_id] = query
                        await self._safe_reply_text(
                            update.message,
                            f"👁️ *ARGOS* `[Direct]`\n\n{res}",
                            markdown=True,
                        )
                        return
                except Exception:
                    pass

        # Batch-команды в одном сообщении (по строкам), например hf ...
        if "\n" in user_text:
            parts = [p.strip() for p in user_text.splitlines() if p.strip()]
            if parts and all(
                p.lower().startswith(("hf ", "/providers", "/skills", "/limits", "serp", "серп", "поищи", "найди "))
                for p in parts
            ):
                out_lines = []
                for part in parts:
                    direct = self._try_direct_execute(part)
                    out_lines.append(f"> {part}\n{direct or '❌ Не выполнено'}")
                await self._safe_reply_text(
                    update.message,
                    "👁️ *ARGOS* `[Direct]`\n\n" + "\n\n".join(out_lines),
                    markdown=True,
                )
                return

        # Проверка блокировок для USER
        if role == ROLE_USER and self._check_user_blocked(user_text):
            await self._deny(update, "Эта команда доступна только администратору.")
            return

        # Админ-тоггл режима контент-фетчера: "/content free" или "/content safe"
        if role == ROLE_ADMIN and user_text.lower().startswith(("/content", "контент")):
            parts = user_text.split(maxsplit=1)
            mode = parts[1] if len(parts) > 1 else ""
            msg = _set_content_mode(mode or "info")
            await self._safe_reply_text(update.message, msg, markdown=False)
            return

        # Сначала пробуем системные/файловые direct-команды, чтобы не терять контроль.
        direct_answer = self._try_direct_execute(user_text)
        if direct_answer is not None:
            await self._safe_reply_text(
                update.message,
                f"👁️ *ARGOS* `[Direct]`\n\n{direct_answer}",
                markdown=True,
            )
            return

        # ── Быстрый фото-поиск без захода в ядро ─────────────────────────
        # "фото <запрос>" → шлём картинку по URL (Unsplash source)
        # Быстрый контент-фечер: если в тексте проскакивают расширения или "фото"/"song"/"mp3"/"pdf"
        lt = user_text.lower()
        exts = [".jpg", ".jpeg", ".png", ".gif", ".webp", ".mp3", ".wav", ".flac", ".ogg", ".pdf", ".txt", ".zip"]
        ext_aliases = {"mp3": ".mp3", "wav": ".wav", "flac": ".flac", "ogg": ".ogg"}
        keywords = [
            "фото", "photo", "song", "песня", "песню", "музыка", "муз", "трек", "track",
            "звук", "sound", "audio", "music", "mp3", "wav", "flac", "ogg",
            "нарисуй", "нарисовать", "рисунок", "картинку", "draw", "сгенерируй", "generate image", "создай картинку", "арт"
        ]
        detection_tokens = exts + list(ext_aliases.keys()) + keywords
        if any(x in lt for x in detection_tokens):
            # выделяем предмет запроса: после первого слова/ключа
            query = user_text
            for key in (
                "фото", "photo", "нарисуй", "нарисовать", "рисунок", "картинку", "draw", "сгенерируй", "generate image", "создай картинку", "арт",
                "song", "песня", "песню", "музыка", "music", "audio", "звук", "sound",
                "трек", "track", "mp3", "wav", "flac", "ogg", "pdf"
            ):
                if key in lt:
                    query = user_text.lower().split(key, 1)[1].strip(" ,./\\")
                    if not query:
                        query = key
                    break
            # определяем примерное расширение
            preferred_ext = ".jpg"
            for ext in exts:
                if ext in lt:
                    preferred_ext = ext
                    break
            if preferred_ext == ".jpg":
                for token, mapped in ext_aliases.items():
                    if token in lt:
                        preferred_ext = mapped
                        break
            if preferred_ext == ".jpg":
                audio_words = {"song", "песня", "песню", "музыка", "муз", "трек", "track", "audio", "sound", "music"}
                if any(w in lt for w in audio_words):
                    preferred_ext = ".mp3"

            tmp_path = None
            candidates = []
            image_candidates = []

            # 1) Поиск изображений только через проверенные открытые API
            translated = _maybe_translate_ru_to_en(query)
            enhanced = _hf_enhance_image_prompt(translated or query)
            q_variants = []
            if enhanced:
                q_variants.append(enhanced[:180])
            if translated and translated != query:
                q_variants.append(translated)
            q_variants.append(query)

            if preferred_ext in (".jpg", ".jpeg", ".png", ".gif", ".webp"):
                for qv in q_variants:
                    image_candidates.extend((u, "") for u in _fetch_openverse_images(qv, 10))
                    image_candidates.extend((u, "") for u in _fetch_wikimedia_images(qv, 10))
                    image_candidates.extend((u, "") for u in _fetch_pexels_images(qv, 10))
                    image_candidates.extend((u, "") for u in _fetch_unsplash_api_images(qv, 10))
            else:
                # для документов/аудио оставляем текстовый поиск DDG
                try:
                    from duckduckgo_search import DDGS
                    with DDGS() as ddgs:
                        for qv in q_variants:
                            results = list(ddgs.text(f"{qv} filetype:{preferred_ext.strip('.')}", max_results=5))
                            candidates.extend([r.get("href") for r in results])
                            results2 = list(ddgs.text(f"{qv} {preferred_ext}", max_results=5))
                            candidates.extend([r.get("href") for r in results2])
                except Exception:
                    pass

            # 2) Фоллбэки по типам
            if preferred_ext in (".mp3", ".wav", ".flac", ".ogg"):
                # свободные примерные аудио
                candidates.append("https://files.freemusicarchive.org/storage-freemusicarchive-org/music/no_curator/Kai_Engel/Irsens_Tale/Kai_Engel_-_03_-_Moonlight_Reprise.mp3")
                candidates.append("https://files.freemusicarchive.org/storage-freemusicarchive-org/music/no_curator/Komiku/It's_time_for_adventure_/Komiku_-_12_-_Quest_Of_Hero.mp3")
                candidates.append("https://samplefiles.org/wp-content/uploads/2017/11/file_example_WAV_1MG.wav")
                candidates.append("https://samplefiles.org/wp-content/uploads/2017/11/file_example_WAV_10MG.wav")
                candidates.append("https://samplelib.com/lib/preview/ogg/sample-6s.ogg")
            elif preferred_ext in (".pdf", ".txt", ".zip"):
                candidates.append("https://samplefiles.org/wp-content/uploads/2020/09/sample-pdf-file.pdf")
                candidates.append("https://samplefiles.org/wp-content/uploads/2017/10/file-sample_150kB.pdf")
                candidates.append("https://samplefiles.org/wp-content/uploads/2017/10/file-sample_100kB.doc")

            # если это картинки — ранжируем по совпадению слов, иначе как было
            if preferred_ext in (".jpg", ".jpeg", ".png", ".gif", ".webp") and image_candidates:
                tokens = set()
                for v in q_variants:
                    tokens.update(t.lower() for t in v.split() if t)
                def score(pair):
                    url, title = pair
                    text = (title or "").lower() + " " + (url or "").lower()
                    return sum(1 for t in tokens if t and t in text)
                ranked = sorted(image_candidates, key=score, reverse=True)
                candidates = [u for (u, _) in ranked]

            # фильтруем по разрешённым доменам, если не свободный режим
            if not CONTENT_ALLOW_ALL:
                candidates = [u for u in candidates if u and _is_allowed(u)]

            # если всё отфильтровалось, подставляем безопасные примеры по типу
            if not candidates:
                if preferred_ext in (".jpg", ".jpeg", ".png", ".gif", ".webp"):
                    # Для изображений случайные fallback-источники отключены.
                    # Если нет кандидатов из OpenVerse/Wikimedia/Pexels/Unsplash API,
                    # ниже сработает HF-генерация.
                    candidates = []
                elif preferred_ext in (".mp3", ".wav", ".flac", ".ogg"):
                    candidates = [
                        "https://files.freemusicarchive.org/storage-freemusicarchive-org/music/no_curator/Kai_Engel/Irsens_Tale/Kai_Engel_-_03_-_Moonlight_Reprise.mp3",
                        "https://samplefiles.org/wp-content/uploads/2017/11/file_example_WAV_1MG.wav",
                        "https://samplelib.com/lib/preview/ogg/sample-6s.ogg"
                    ]
                else:
                    candidates = [
                        "https://samplefiles.org/wp-content/uploads/2020/09/sample-pdf-file.pdf"
                    ]

            # удаляем дубликаты, сохраняя порядок
            seen = set()
            deduped = []
            for u in candidates:
                if u and u not in seen:
                    deduped.append(u)
                    seen.add(u)

            # Не отправляем тот же URL повторно для того же запроса.
            if preferred_ext in (".jpg", ".jpeg", ".png", ".gif", ".webp"):
                last_url = self._last_image_url_by_query.get(query.lower().strip())
                if last_url:
                    filtered = [u for u in deduped if u != last_url]
                else:
                    filtered = deduped
            else:
                filtered = deduped

            # Выбираем лучший URL (первый из неповторяющихся, или просто первый)
            send_pool = filtered if filtered else deduped
            chosen_url = send_pool[0] if send_pool else None

            if preferred_ext in (".jpg", ".jpeg", ".png", ".gif", ".webp"):
                img_bytes = None
                if not chosen_url:
                    # Нет URL из открытых источников — генерируем через HF
                    await update.message.reply_text("🎨 Генерирую изображение...")
                    img_bytes = await asyncio.to_thread(
                        _hf_generate_image_via_spaces, (enhanced or translated or query)
                    )
                    if not img_bytes:
                        img_bytes = await asyncio.to_thread(
                            _hf_generate_image, (enhanced or translated or query)
                               )
                if img_bytes:
                    try:
                        import io as _io
                        await update.message.reply_photo(
                            photo=_io.BytesIO(img_bytes), caption=f"🖼 {query[:200]}"
                        )
                    except Exception as _e:
                        await self._safe_reply_text(
                            update.message,
                            f"❌ Не удалось отправить изображение: {_e}",
                            markdown=False,
                        )
                elif chosen_url:
                    try:
                        self._last_image_url_by_query[query.lower().strip()] = chosen_url
                        await update.message.reply_photo(
                            photo=chosen_url, caption=f"🖼 {query[:200]}"
                        )
                    except Exception:
                        img_bytes = await asyncio.to_thread(
                            _hf_generate_image_via_spaces, (enhanced or translated or query)
                        )
                        if not img_bytes:
                            img_bytes = await asyncio.to_thread(
                                _hf_generate_image, (enhanced or translated or query)
                            )
                        if img_bytes:
                            try:
                                import io as _io
                                await update.message.reply_photo(
                                    photo=_io.BytesIO(img_bytes), caption=f"🖼 {query[:200]}"
                                )
                            except Exception:
                                await self._safe_reply_text(
                                    update.message, f"❌ Изображение недоступно для: {query}", markdown=False
                                )
                        else:
                            await self._safe_reply_text(
                                update.message, f"❌ Изображение не найдено для: {query}", markdown=False
                            )
                else:
                    await self._safe_reply_text(
                        update.message, f"❌ Изображение не найдено для: {query}", markdown=False
                    )

            elif preferred_ext in (".mp3", ".wav", ".flac", ".ogg"):
                if chosen_url:
                    try:
                        await update.message.reply_audio(
                            audio=chosen_url, caption=f"🎵 {query[:200]}"
                        )
                    except Exception:
                        try:
                            await update.message.reply_document(
                                document=chosen_url, caption=f"🎵 {query[:200]}"
                            )
                        except Exception:
                            await self._safe_reply_text(
                                update.message, f"🎵 Аудио: {chosen_url}", markdown=False
                            )
                else:
                    await self._safe_reply_text(
                        update.message, f"❌ Аудиофайл не найден для: {query}", markdown=False
                    )

            else:
                if chosen_url:
                    try:
                        await update.message.reply_document(
                            document=chosen_url, caption=f"📄 {query[:200]}"
                        )
                    except Exception:
                        await self._safe_reply_text(
                            update.message, f"📄 Файл: {chosen_url}", markdown=False
                        )
                else:
                    await self._safe_reply_text(
                        update.message, f"❌ Файл не найден для: {query}", markdown=False
                    )
            return

        # -- Основной путь: ответ от ядра ------------------------------------------
        try:
            result = await self.core.process_logic_async(user_text, self.admin, self.flasher)
            answer = result["answer"]
            state  = result["state"]
        except Exception as _exc:
            answer = f"❌ Ошибка обработки: {_exc}"
            state  = "Error"
        if self.voice_reply:
            await self._reply_with_voice(update.message, answer[:500])
        await self._safe_reply_text(
            update.message,
            f"👁️ *ARGOS* `[{state}]`\n\n{answer[:4000]}",
            markdown=True,
        )
