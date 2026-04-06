# 🛠️ Kimi Tool Calling — Использование навыков

## Что реализовано

Теперь Kimi K2.5 может **динамически вызывать навыки ARGOS** через специальный формат Tool Calling.

## Как работает

```
Пользователь: "Какая погода в Москве?"
    ↓
Kimi видит доступные инструменты в system prompt
    ↓
Kimi отвечает: TOOL_CALL: {"name": "get_weather", "arguments": {"city": "Mосква"}}
    ↓
Выполняется функция _tool_weather → результат
    ↓
Kimi получает результат и формирует финальный ответ
```

## Доступные инструменты

| Инструмент | Описание | Пример аргументов |
|------------|----------|-------------------|
| `get_weather` | Погода в городе | `{"city": "Москва"}` |
| `list_skills` | Список навыков | `{}` |
| `get_time` | Текущее время | `{}` |
| `system_status` | Статус системы | `{}` |
| `web_search` | Поиск в интернете | `{"query": "Python 3.12"}` |
| `execute_skill` | Выполнить навык | `{"skill_name": "weather", "query": "погода"}` |

## Управление

### Включить/выключить:
```bash
# Через команду
> режим ии kimi с инструментами
🤖 Режим ИИ: Kimi K2.5 (с инструментами ✅)

> выключи инструменты kimi
🔧 Инструменты Kimi отключены
```

### Через .env:
```bash
ARGOS_KIMI_TOOLS=1  # 1=включить, 0=отключить
```

## Примеры использования

### Команды пользователя:
```
> Какая погода в Санкт-Петербурге?
# Kimi вызовет get_weather, получит данные, ответит

> Который час?
# Kimi вызовет get_time

> Покажи мои навыки
# Kimi вызовет list_skills

> Найди в интернете последние новости Python
# Kimi вызовет web_search
```

## Файлы

- `src/connectivity/kimi_tools.py` — Tool Calling система
- `src/core.py` — интеграция в generate()
- `tests/test_kimi_tools.py` — тесты

## API для разработчиков

```python
from src.connectivity.kimi_tools import KimiToolCalling

tc = KimiToolCalling(core=argos_core)

# Регистрируем свой инструмент
tc.register_tool(
    name="my_function",
    description="Делает что-то полезное",
    parameters={
        "type": "object",
        "properties": {
            "param": {"type": "string", "description": "Параметр"}
        },
        "required": ["param"]
    },
    function=my_actual_function
)

# Используем с инструментами
result = tc.chat_with_tools("Выполни my_function с param=test")
```

## Формат промпта

Kimi получает такой system prompt:
```
Доступные инструменты:

get_weather: Получить текущую погоду в указанном городе
  Параметры:
    - city: Название города (обязательно)

...

Чтобы использовать инструмент, ответь ТОЧНО в формате:
TOOL_CALL: {"name": "имя_инструмента", "arguments": {"параметр": "значение"}}

Если инструменты не нужны, отвечай обычно.
```

## Технические детали

- Максимум 3 итерации инструментов за один запрос
- Поддерживается контекст (conversation history)
- Формат TOOL_CALL разбирается корректно даже с вложенными JSON
- Fallback на обычный Kimi если tools выключены