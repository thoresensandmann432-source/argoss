# 🌙 Kimi K2.5 — Финальная интеграция с Tool Calling

## ✅ Что реализовано

### 1. **Базовый мост** (`src/connectivity/kimi_bridge.py`)
- Работа с API Moonshot AI
- Streaming и blocking режимы
- Поддержка `kimi-k2.5`, `kimi-k2`, `kimi-latest`
- CLI: `argos_cli.py kimi "запрос"`

### 2. **Tool Calling** (`src/connectivity/kimi_tools.py`) ⭐ НОВОЕ
- **Kimi вызывает ARGOS навыки автоматически!**
- 6 встроенных инструментов:
  - `get_weather` — погода
  - `list_skills` — список навыков
  - `get_time` — текущее время
  - `system_status` — статус системы
  - `web_search` — поиск в интернете
  - `execute_skill` — выполнить любой навык

### 3. **Интеграция в ядро** (`src/core.py`)
- `_ask_kimi()` — базовый режим
- `_ask_kimi_with_tools()` — с инструментами
- Команды:
  - `режим ии kimi` — базовый режим
  - `режим ии kimi с инструментами` — с tools
  - `выключи инструменты kimi` — выключить
- Переменная `ARGOS_KIMI_TOOLS=1` в `.env`

### 4. **Web API** (`src/kimi_api.py`, `src/pip_api.py`)
- `/api/kimi/chat`, `/api/kimi/chat/stream`
- `/api/pip/install`, `/api/pip/list`
- Полная документация в `KIMI_INTEGRATION_COMPLETE.md`

### 5. **Тесты** (`tests/test_kimi_tools.py`)
- Парсинг TOOL_CALL
- Выполнение инструментов
- JSON с вложенными объектами

## 🚀 Использование

### Включить инструменты:
```bash
# Через команду
> режим ии kimi с инструментами
🤖 Режим ИИ: Kimi K2.5 (с инструментами ✅)

# Или в .env
ARGOS_KIMI_TOOLS=1
```

### Примеры:
```
> Какая погода в Москве?
# Kimi: TOOL_CALL: {"name":"get_weather","arguments":{"city":"Москва"}}
# Ответ: В Москве сейчас +15°C, облачно

> Который час?
# Kimi вызовет get_time

> Покажи мои навыки
# Kimi вызовет list_skills
```

## 📦 Файлы

| Файл | Описание |
|------|----------|
| `src/connectivity/kimi_bridge.py` | Базовый мост Kimi |
| `src/connectivity/kimi_tools.py` | Tool Calling |
| `src/core.py` | Интеграция в generate() |
| `src/kimi_api.py` | Web API endpoints |
| `tests/test_kimi_tools.py` | Тесты |
| `setup_kimi.py` | Setup скрипт |
| `.env` | `KIMI_API_KEY` + `ARGOS_KIMI_TOOLS` |
| `KIMI_TOOLS_GUIDE.md` | Подробный гайд |

## 🔧 Технические детали

- Парсинг `TOOL_CALL: {...}` с корректной обработкой вложенных JSON
- Max 3 итерации инструментов
- Fallback на базовый Kimi если tools выключены
- Все тесты проходят ✅

**Ключ API**: https://platform.moonshot.ai