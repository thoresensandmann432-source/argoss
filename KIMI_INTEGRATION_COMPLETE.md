# 🌙 Kimi K2.5 (Moonshot AI) Интеграция — Итоговый отчёт

## ✅ Что реализовано

### 1. Мост Kimi (`src/connectivity/kimi_bridge.py`)
- **KimiBridge** — класс для работы с API Moonshot AI
  - Поддержка streaming и blocking режимов
  - Динамический выбор модели (`kimi-k2.5`, `kimi-k2`, `kimi-latest`)
  - Нативная поддержка контекста (чат-история)
  - Проверка баланса аккаунта
  - Автоопределение доступности по `KIMI_API_KEY`
  
- **KimiSkillAdapter** — интеграция как навык ARGOS

### 2. Конфигурация провайдера (`src/ai_providers.py`)
Добавлена запись:
```python
"kimi": AIProvider(
    name="Kimi K2.5",
    max_rpm=60,
    max_tpm=120_000,
    max_context=256_000,
    env_key="KIMI_API_KEY",
    base_url="https://api.moonshot.cn/v1"
)
```

### 3. Интеграция в ядро (`src/core.py`)
- `_has_kimi_config()` — проверка конфигурации
- `_ask_kimi()` — метод отправки запросов
- Нормализация режима: `kimi`, `moonshot`, `k2`, `k2.5`, `km` → `"kimi"`
- Командная обработка: `режим ии kimi`, `модель кими`
- Поддержка в `generate()` для автоматического роутинга

### 4. Tool Calling (`src/connectivity/kimi_tools.py`)
**Kimi теперь может вызывать навыки ARGOS!**
- 6 встроенных инструментов: погода, время, навыки, поиск, система, выполнение
- Автоматический парсинг `TOOL_CALL: {"name": "...", "arguments": {...}}`
- До 3 итераций инструментов за запрос
- Мульти-тур диалог с контекстом

Команды:
```
> режим ии kimi с инструментами
> выключи инструменты kimi
```

Переменная: `ARGOS_KIMI_TOOLS=1` (в .env)

### 5. Web API (`src/kimi_api.py`)
Flask/FastAPI endpoints:
- `POST /api/kimi/chat` — текстовый запрос
- `POST /api/kimi/chat/stream` — потоковый SSE
- `GET /api/kimi/models` — список моделей
- `GET /api/kimi/status` — статус API
- `POST /api/kimi/agent/execute` — выполнение агента
- `GET /api/kimi/balance` — баланс аккаунта

### 5. Pip Manager (`src/pip_manager_ext.py`, `src/pip_api.py`)
- Программное управление пакетами Python
- API endpoints для install/uninstall/list/outdated/check
- `ArgosSkillAdapter` для команд: "установи пакет X", "проверь зависимости"

### 6. CLI Client (`src/argos_client.py`, `argos_cli.py`)
```bash
# HTTP клиент
python argos_cli.py chat "Привет!"
python argos_cli.py kimi "Напиши код" --agent programming
python argos_cli.py pip list
python argos_cli.py pip install requests
```

### 7. Настройка (`setup_kimi.py`)
Интерактивный скрипт:
- Проверка `requests`
- Запрос API ключа
- Тестирование соединения
- Сохранение в `.env`
- Проверка через KimiBridge

## 🔧 Переменные окружения

Добавлены в `.env` и `.env.example`:
```bash
# Kimi K2.5 (Moonshot AI) — https://platform.moonshot.ai
KIMI_API_KEY=sk-your_token_here
```

## 🛠️ Tool Calling — Kimi использует навыки

Kimi теперь может **динамически вызывать навыки ARGOS**:

### Встроенные инструменты:
- `get_weather` — погода в городе
- `list_skills` — список всех навыков
- `get_time` — текущее время
- `system_status` — статус системы
- `web_search` — поиск в интернете
- `execute_skill` — выполнить любой навык

### Как работает:
1. Пользователь: "Какая погода в Москве?"
2. Kimi видит доступные инструменты
3. Kimi отвечает: `TOOL_CALL: {"name": "get_weather", "arguments": {"city": "Москва"}}`
4. Выполняется навык `weather`
5. Kimi получает результат и формирует ответ

### Управление:
```bash
> режим ии kimi с инструментами  # Включить tools
> выключи инструменты kimi      # Выключить tools
```

### Переменные окружения:
```bash
# Kimi K2.5 (Moonshot AI) — https://platform.moonshot.ai
KIMI_API_KEY=sk-your_token_here
ARGOS_KIMI_TOOLS=1  # 1=включить, 0=отключить
```

## 🚀 Использование

### Python API:
```python
from src.connectivity.kimi_bridge import KimiBridge

kimi = KimiBridge()
if kimi.is_available:
    kimi.set_system_prompt("Ты senior developer")
    response = kimi.chat("Напиши Python функцию для quicksort")
```

### ARGOS командная строка:
```
> режим ии kimi
✅ Режим ИИ: Kimi K2.5

> kimi мост что такое recursion?
🤖 Recursion — это...
```

### HTTP API:
```bash
curl -X POST http://localhost:5000/api/kimi/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "Hello"}'
```

## 📁 Созданные файлы

| Файл | Описание |
|------|----------|
| `src/connectivity/kimi_bridge.py` | Основной мост Kimi |
| `src/ai_providers.py` | Обновлён список провайдеров |
| `src/core.py` | Интеграция в ядро |
| `src/kimi_api.py` | Web API endpoints |
| `src/pip_manager_ext.py` | Pip менеджер |
| `src/pip_api.py` | Pip API routes |
| `src/argos_client.py` | HTTP клиент для API |
| `argos_cli.py` | CLI утилита |
| `setup_kimi.py` | Setup скрипт |
| `.env` / `.env.example` | Переменные окружения |

## 🔌 Добавление роутов в Web сервер

Для активации API в `main.py` или `argos_service.py`:

```python
from src.kimi_api import setup_kimi_routes
from src.pip_api import setup_pip_routes

# После создания app
setup_kimi_routes(app, core)
setup_pip_routes(app, core)
```

## 📝 Примечания

- **Ключ API**: начинается с `sk-`, получить на https://platform.moonshot.ai
- **Модели по умолчанию**: `kimi-k2.5` (256k контекста)
- **Rate limits**: 60 RPM, 120k TPM
- **Совместимость**: OpenAI-совместимый API (`/chat/completions`)

## ✨ Запуск полной проверки

```bash
# 1. Настройка
python setup_kimi.py

# 2. Запуск ARGOS
python main.py

# 3. Тест через CLI
python argos_cli.py kimi "Привет!"

# 4. Тест через API
curl http://localhost:5000/api/kimi/status
```

---

**Статус**: ✅ Полностью интегрировано и готово к использованию