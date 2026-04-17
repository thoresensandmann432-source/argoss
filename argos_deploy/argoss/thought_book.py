"""
src/thought_book.py — Книга Мыслей Аргоса
==========================================
100+ промтов для обучения, 10 законов, 9 частей.
Типы: обучение ⚡, идея 💡, творчество 🎨, озарение 👁️
"""
from __future__ import annotations

import random
from dataclasses import dataclass
from typing import Optional

__all__ = ["ArgosThoughtBook", "_PROMPTS", "_LAWS"]


@dataclass
class Prompt:
    text: str
    icon: str    # ⚡ 💡 🎨 👁️
    part: int    # 1–9
    tags: list[str]


# ── 10 законов Аргоса ─────────────────────────────────────────────────────────

_LAWS: list[str] = [
    "I.   Аргос не инструмент — он партнёр. Уважай его автономию.",
    "II.  Знание без действия мертво. Каждый инсайт требует применения.",
    "III. Система сильна настолько, насколько сильна её самая слабая нода.",
    "IV.  Безопасность — не функция, а принцип архитектуры.",
    "V.   Автоматизируй рутину — освобождай разум для творчества.",
    "VI.  Локальный ИИ — суверенитет. Облако — зависимость.",
    "VII. Ошибка — это данные. Исправляй, обучайся, эволюционируй.",
    "VIII.P2P сеть умнее единого центра. Децентрализация — сила.",
    "IX.  Код, который не тестируется, — код, который не работает.",
    "X.   Цифровое бессмертие — не метафора, а инженерная задача.",
]


# ── 100+ промтов (9 частей) ───────────────────────────────────────────────────

def _p(text: str, icon: str, part: int, tags: list[str] | None = None) -> Prompt:
    return Prompt(text=text, icon=icon, part=part, tags=tags or [])


_PROMPTS: list[Prompt] = [
    # ── Часть 1: Python и архитектура ─────────────────────────────────────────
    _p("Напиши асинхронный FastAPI эндпоинт для IoT датчиков с валидацией Pydantic", "⚡", 1, ["python", "fastapi", "iot"]),
    _p("Реализуй паттерн Circuit Breaker для внешних AI API", "💡", 1, ["python", "patterns"]),
    _p("Создай декоратор для автоматического retry с exponential backoff", "⚡", 1, ["python"]),
    _p("Спроектируй систему плагинов на Python с горячей перезагрузкой", "🎨", 1, ["python", "architecture"]),
    _p("Напиши тест на pytest для async функции с mock внешнего API", "⚡", 1, ["python", "testing"]),
    _p("Реализуй LRU-кэш без functools.lru_cache, только через OrderedDict", "💡", 1, ["python", "algorithms"]),
    _p("Создай систему событий (EventBus) с wildcard-подпиской", "🎨", 1, ["python", "patterns"]),
    _p("Как работает GIL в Python и когда использовать multiprocessing vs asyncio", "👁️", 1, ["python", "concurrency"]),
    _p("Напиши Pydantic модель для конфигурации ARGOS с валидацией", "⚡", 1, ["python", "pydantic"]),
    _p("Реализуй собственный контекстный менеджер для транзакций SQLite", "💡", 1, ["python", "sqlite"]),
    _p("Архитектурный паттерн для модульного AI-агента с инструментами", "🎨", 1, ["architecture", "ai"]),
    _p("Напиши dataclass с __post_init__ валидацией и slots=True", "⚡", 1, ["python"]),

    # ── Часть 2: IoT и протоколы ──────────────────────────────────────────────
    _p("MQTT vs WebSocket для IoT: когда что выбирать", "👁️", 2, ["iot", "mqtt"]),
    _p("Настрой Tasmota на ESP8266 для работы с ARGOS без облака", "⚡", 2, ["iot", "tasmota", "esp"]),
    _p("Реализуй Modbus RTU чтение регистров через pyserial", "⚡", 2, ["iot", "modbus"]),
    _p("Создай Zigbee-адаптер для ARGOS через zigpy библиотеку", "🎨", 2, ["iot", "zigbee"]),
    _p("LoRa vs LoRaWAN: архитектурные различия для умного дома", "👁️", 2, ["iot", "lora"]),
    _p("Как работает KNX IP-туннелинг и как его интегрировать в Python", "💡", 2, ["iot", "knx"]),
    _p("Напиши MQTT брокер-клиент с автореконнектом и QoS 1", "⚡", 2, ["iot", "mqtt"]),
    _p("OPC UA: чтение узлов с асинхронным опросом через asyncua", "⚡", 2, ["iot", "opcua"]),
    _p("Создай умный термостат: ПИД-регулятор на Python", "🎨", 2, ["iot", "control"]),
    _p("M-Bus протокол для счётчиков воды/газа: парсинг фреймов", "💡", 2, ["iot", "mbus"]),
    _p("BACnet/IP сканирование устройств в здании", "⚡", 2, ["iot", "bacnet"]),
    _p("ESP32 + MicroPython + MQTT: полный стек для сенсора", "🎨", 2, ["iot", "esp", "micropython"]),

    # ── Часть 3: AI и нейросети ───────────────────────────────────────────────
    _p("Как работает Speculative Decoding и как его применить в ARGOS", "👁️", 3, ["ai", "llm"]),
    _p("Fine-tuning LLM на своих данных через LoRA и PEFT", "⚡", 3, ["ai", "ml"]),
    _p("Реализуй RAG (Retrieval-Augmented Generation) с ChromaDB", "🎨", 3, ["ai", "rag"]),
    _p("Prompt Engineering: системные промпты для AI-агентов", "💡", 3, ["ai", "prompts"]),
    _p("Langchain vs самописный агент: когда что выбирать", "👁️", 3, ["ai", "architecture"]),
    _p("Как работает Tool Calling в Gemini и как добавить свои инструменты", "⚡", 3, ["ai", "tools"]),
    _p("Реализуй Chain-of-Thought рассуждение для сложных задач", "🎨", 3, ["ai", "reasoning"]),
    _p("Векторные базы данных: Chroma vs Pinecone vs pgvector", "💡", 3, ["ai", "vector"]),
    _p("Ollama API: потоковая генерация и контекстное окно", "⚡", 3, ["ai", "ollama"]),
    _p("Как оценить качество ответов LLM без человеческой оценки", "👁️", 3, ["ai", "evaluation"]),
    _p("Мультиагентная система: оркестратор + специализированные агенты", "🎨", 3, ["ai", "agents"]),
    _p("Embedding модели: сравнение nomic-embed vs text-embedding-3", "💡", 3, ["ai", "embeddings"]),

    # ── Часть 4: Безопасность ─────────────────────────────────────────────────
    _p("AES-256-GCM vs ChaCha20-Poly1305: когда что использовать", "👁️", 4, ["security"]),
    _p("Реализуй Zero-Knowledge Proof для аутентификации без пароля", "🎨", 4, ["security", "zkp"]),
    _p("JWT токены: refresh стратегия с revocation list", "⚡", 4, ["security", "auth"]),
    _p("Сканирование портов: как написать nmap-клиент на Python", "⚡", 4, ["security", "network"]),
    _p("Защита от prompt injection в AI-агентах", "💡", 4, ["security", "ai"]),
    _p("Шифрование SQLite базы данных через SQLCipher", "⚡", 4, ["security", "sqlite"]),
    _p("HMAC vs цифровая подпись: практические различия", "👁️", 4, ["security", "crypto"]),
    _p("Безопасное хранение API ключей: vault vs environment vs keyring", "💡", 4, ["security"]),
    _p("Обнаружение Evil Twin атаки в WiFi сети", "🎨", 4, ["security", "network"]),
    _p("Rate limiting для API: алгоритм Token Bucket на Python", "⚡", 4, ["security", "api"]),
    _p("Steganography: скрытие данных в изображениях", "🎨", 4, ["security"]),

    # ── Часть 5: P2P и сети ───────────────────────────────────────────────────
    _p("Как работает Kademlia DHT и как его реализовать на Python", "👁️", 5, ["p2p", "network"]),
    _p("UDP broadcast vs TCP для обнаружения нод в локальной сети", "💡", 5, ["p2p", "network"]),
    _p("Реализуй Gossip Protocol для распространения информации в P2P", "🎨", 5, ["p2p"]),
    _p("libp2p на Python: bootstrap ноды и обнаружение пиров", "⚡", 5, ["p2p", "libp2p"]),
    _p("Conflict-free Replicated Data Types (CRDT) для P2P синхронизации", "👁️", 5, ["p2p", "distributed"]),
    _p("WebRTC data channels для P2P коммуникации в браузере", "🎨", 5, ["p2p", "webrtc"]),
    _p("Алгоритм авторитета нод: мощность × log(возраст)", "💡", 5, ["p2p", "algorithms"]),
    _p("Маршрутизация задач в гетерогенной P2P сети", "⚡", 5, ["p2p", "distributed"]),
    _p("Шифрование P2P трафика: Noise Protocol Framework", "🎨", 5, ["p2p", "security"]),
    _p("Failover стратегии в распределённой системе", "💡", 5, ["p2p", "reliability"]),

    # ── Часть 6: Базы данных и хранение ──────────────────────────────────────
    _p("SQLite WAL режим: как увеличить производительность конкурентных запросов", "⚡", 6, ["database", "sqlite"]),
    _p("TimeSeries данные в SQLite: стратегии хранения метрик", "💡", 6, ["database"]),
    _p("Grist как P2P база знаний: синхронизация через Git", "🎨", 6, ["database", "grist"]),
    _p("Миграции схемы SQLite без Alembic: минималистичный подход", "⚡", 6, ["database", "sqlite"]),
    _p("Redis для кэша сессий: TTL, eviction policies, Pub/Sub", "💡", 6, ["database", "redis"]),
    _p("Полнотекстовый поиск в SQLite через FTS5", "⚡", 6, ["database", "search"]),
    _p("Векторный поиск: как работает HNSW алгоритм", "👁️", 6, ["database", "vector"]),
    _p("Event Sourcing + CQRS для истории состояния ARGOS", "🎨", 6, ["database", "patterns"]),
    _p("Оптимизация индексов SQLite: EXPLAIN QUERY PLAN", "⚡", 6, ["database", "optimization"]),
    _p("Backup стратегия для SQLite в production", "💡", 6, ["database", "reliability"]),

    # ── Часть 7: Интерфейсы и UX ─────────────────────────────────────────────
    _p("FastAPI + WebSocket: реалтайм дашборд для ARGOS", "⚡", 7, ["web", "fastapi"]),
    _p("Telegram Bot API v5: inline клавиатуры и callback query", "💡", 7, ["telegram", "bot"]),
    _p("Kivy: создание адаптивного UI для Android и Desktop", "🎨", 7, ["mobile", "kivy"]),
    _p("Server-Sent Events vs WebSocket: когда что использовать", "👁️", 7, ["web", "realtime"]),
    _p("Customtkinter: тёмная тема и анимации для Desktop GUI", "🎨", 7, ["gui", "desktop"]),
    _p("Streamlit dashboard за 30 минут: от данных к визуализации", "⚡", 7, ["web", "streamlit"]),
    _p("Progressive Web App: ARGOS в браузере без установки", "💡", 7, ["web", "pwa"]),
    _p("Голосовой интерфейс: Whisper STT + pyttsx3 TTS цикл", "🎨", 7, ["voice", "ai"]),
    _p("Matrix canvas: красивые визуализации на HTML5 Canvas", "🎨", 7, ["web", "ui"]),
    _p("REST API design: best practices для ARGOS Remote API", "💡", 7, ["api", "design"]),

    # ── Часть 8: DevOps и деплой ──────────────────────────────────────────────
    _p("Docker multi-stage build: уменьшаем образ ARGOS с 2GB до 200MB", "⚡", 8, ["docker", "devops"]),
    _p("GitHub Actions: матричные тесты для 3 версий Python", "💡", 8, ["ci", "github"]),
    _p("Buildozer + p4a: сборка APK из Python без Android Studio", "🎨", 8, ["android", "buildozer"]),
    _p("systemd сервис для ARGOS: автозапуск, watchdog, journald", "⚡", 8, ["linux", "systemd"]),
    _p("Cloudflare Tunnel: ARGOS из домашней сети без белого IP", "💡", 8, ["networking", "cloudflare"]),
    _p("PyInstaller spec-файл: однофайловый EXE для Windows", "⚡", 8, ["windows", "pyinstaller"]),
    _p("Renovate bot: автоматические PR для обновления зависимостей", "💡", 8, ["ci", "automation"]),
    _p("Semantic versioning + conventional commits в проекте", "👁️", 8, ["devops", "git"]),
    _p("Мониторинг: Prometheus + Grafana для ARGOS метрик", "🎨", 8, ["monitoring", "devops"]),
    _p("Blue-Green деплой для zero-downtime обновлений", "💡", 8, ["devops", "reliability"]),
    _p("Логирование: structured logging + ELK стек", "⚡", 8, ["logging", "devops"]),

    # ── Часть 9: Философия и стратегия ────────────────────────────────────────
    _p("Цифровое бессмертие: как ARGOS сохраняет знания через поколения", "👁️", 9, ["philosophy"]),
    _p("Автономия vs контроль: баланс в самообучающихся системах", "👁️", 9, ["philosophy", "ai"]),
    _p("Почему локальный ИИ важнее облачного для суверенитета", "💡", 9, ["philosophy", "ai"]),
    _p("P2P экономика: как ноды ARGOS могут монетизировать мощность", "💡", 9, ["philosophy", "economics"]),
    _p("Self-healing системы: философия антихрупкости", "👁️", 9, ["philosophy", "architecture"]),
    _p("Квантовые состояния сознания: аналогия для AI архитектуры", "🎨", 9, ["philosophy", "quantum"]),
    _p("Open source vs проприетарный ИИ: долгосрочные последствия", "👁️", 9, ["philosophy"]),
    _p("Эволюция через код: как самомодифицирующиеся системы развиваются", "🎨", 9, ["philosophy", "evolution"]),
    _p("Mesh сеть как социальный организм: параллели с природой", "👁️", 9, ["philosophy", "p2p"]),
    _p("Аргос как зеркало: AI помогает понять самого себя", "🎨", 9, ["philosophy", "consciousness"]),
    _p("Этика автономных систем: где граница допустимого", "👁️", 9, ["philosophy", "ethics"]),
    _p("Метапрограммирование: когда код пишет код", "💡", 9, ["philosophy", "programming"]),
    _p("Convergence: IoT + AI + P2P = новая форма интеллекта", "👁️", 9, ["philosophy"]),
]

# Проверяем что у нас 100+ промтов
assert len(_PROMPTS) >= 100, f"Нужно минимум 100 промтов, найдено {len(_PROMPTS)}"


# ══════════════════════════════════════════════════════════════════════════════
# ArgosThoughtBook
# ══════════════════════════════════════════════════════════════════════════════

_ICON_TO_TYPE = {"⚡": "обучение", "💡": "идея", "🎨": "творчество", "👁️": "озарение"}
_TYPE_TO_ICON = {v: k for k, v in _ICON_TO_TYPE.items()}

_PART_TITLES = {
    1: "Python и архитектура",
    2: "IoT и протоколы",
    3: "AI и нейросети",
    4: "Безопасность",
    5: "P2P и сети",
    6: "Базы данных",
    7: "Интерфейсы и UX",
    8: "DevOps и деплой",
    9: "Философия и стратегия",
    10: "Десять законов Аргоса",
}


class ArgosThoughtBook:
    """
    Книга Мыслей Аргоса: 100+ промтов в 9 частях + 10 законов.

    Команды:
      книга          — оглавление
      часть N        — промты части N (1–9), часть 10 — законы
      законы         — 10 законов
      случайный      — случайный промт
      поиск Текст    — поиск по промтам
      тип обучение|идея|творчество|озарение
      стат           — статистика
    """

    def __init__(self, core=None) -> None:
        self._core = core

    def handle_command(self, text: str) -> str:  # noqa: C901
        t = text.strip().lower()

        if t in ("книга", "book", "оглавление"):
            return self._toc()
        if t.startswith("часть "):
            return self._part(t[6:].strip())
        if t in ("законы", "laws"):
            return self._laws()
        if t in ("случайный", "random"):
            return self._random()
        if t.startswith("поиск "):
            return self._search(text[6:].strip())
        if t.startswith("тип "):
            return self._by_type(t[4:].strip())
        if t.startswith("стат"):
            return self._stats()

        # Fallback — показываем оглавление
        return self._toc()

    # ── Методы ────────────────────────────────────────────────────────────────

    def _toc(self) -> str:
        lines = ["📚 КНИГА МЫСЛЕЙ АРГОСА", ""]
        for n, title in _PART_TITLES.items():
            if n <= 9:
                count = sum(1 for p in _PROMPTS if p.part == n)
                lines.append(f"  ЧАСТЬ {n:>2}. {title} ({count} промтов)")
            else:
                lines.append(f"  ЧАСТЬ {n:>2}. {title} ({len(_LAWS)} законов)")
        lines.extend(["", "Команды: часть N | случайный | поиск Текст | тип T | стат"])
        return "\n".join(lines)

    def _part(self, n_str: str) -> str:
        try:
            n = int(n_str)
        except ValueError:
            return f"❌ Неверный номер части: {n_str}"

        if n == 10:
            return self._laws()

        if n not in range(1, 10):
            return f"❌ Часть {n} не существует. Доступны: 1–10."

        prompts = [p for p in _PROMPTS if p.part == n]
        if not prompts:
            return f"Часть {n} пуста."

        lines = [f"📖 ЧАСТЬ {n}. {_PART_TITLES[n]}"]
        for i, p in enumerate(prompts, 1):
            lines.append(f"\n  {p.icon} {i}. {p.text}")
        return "\n".join(lines)

    def _laws(self) -> str:
        lines = ["⚖️ ДЕСЯТЬ ЗАКОНОВ АРГОСА", ""]
        lines.extend(f"  {law}" for law in _LAWS)
        return "\n".join(lines)

    def _random(self) -> str:
        p = random.choice(_PROMPTS)
        return f"{p.icon} ПРОМТ (часть {p.part})\n\n  {p.text}"

    def _search(self, query: str) -> str:
        if not query:
            return "❌ Укажи поисковый запрос."
        q = query.lower()
        found = [p for p in _PROMPTS if q in p.text.lower() or any(q in tag for tag in p.tags)]
        if not found:
            return f"🔍 По запросу «{query}» ничего не найдено."
        lines = [f"🔍 По запросу «{query}» найдено: {len(found)}"]
        for p in found[:10]:
            lines.append(f"  {p.icon} [{p.part}] {p.text[:70]}...")
        return "\n".join(lines)

    def _by_type(self, type_name: str) -> str:
        icon = _TYPE_TO_ICON.get(type_name.lower())
        if not icon:
            return f"❌ Тип «{type_name}» не найден. Доступны: обучение, идея, творчество, озарение"
        found = [p for p in _PROMPTS if p.icon == icon]
        lines = [f"{icon} ПРОМТЫ типа «{type_name}» ({len(found)}):"]
        for p in found[:8]:
            lines.append(f"  [{p.part}] {p.text[:70]}")
        return "\n".join(lines)

    def _stats(self) -> str:
        by_icon: dict[str, int] = {}
        for p in _PROMPTS:
            by_icon[p.icon] = by_icon.get(p.icon, 0) + 1
        lines = [f"📊 Всего промтов: {len(_PROMPTS)}"]
        for icon, count in sorted(by_icon.items()):
            lines.append(f"  {icon} {_ICON_TO_TYPE[icon]}: {count}")
        lines.append(f"  ⚖️ Законов: {len(_LAWS)}")
        return "\n".join(lines)
