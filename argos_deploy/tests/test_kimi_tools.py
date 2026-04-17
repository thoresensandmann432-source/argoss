#!/usr/bin/env python3
"""
test_kimi_tools.py — Тест Tool Calling для Kimi

Проверяет работу инструментов без реальных API запросов.
"""

import os
import sys

# Мокаем API ключ если нет
if not os.getenv("KIMI_API_KEY"):
    os.environ["KIMI_API_KEY"] = "test-key-for-validation"

import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.connectivity.kimi_tools import KimiToolCalling

def test_tools():
    print("🧪 Kimi Tools Test")
    print("=" * 60)
    
    tc = KimiToolCalling()
    
    # 1. Проверка инструментов
    print("\n📦 Доступные инструменты:")
    for name, tool in tc.tools.items():
        print(f"   • {name}: {tool.description}")
    
    assert len(tc.tools) == 6, f"Expected 6 tools, got {len(tc.tools)}"
    print(f"\n✅ Все {len(tc.tools)} инструментов зарегистрированы")
    
    # 2. Проверка парсинга TOOL_CALL
    print("\n🔍 Тест парсинга TOOL_CALL:")
    
    test_cases = [
        ('TOOL_CALL: {"name": "get_time", "arguments": {}}', 
         {"name": "get_time", "arguments": {}}),
        ('TOOL_CALL:{"name":"get_weather","arguments":{"city":"Moscow"}}',
         {"name": "get_weather", "arguments": {"city": "Moscow"}}),
        ('Нет инструмента', None),
    ]
    
    for text, expected in test_cases:
        result = tc._parse_tool_call(text)
        status = "✅" if result == expected else "❌"
        print(f"   {status} '{text[:40]}...' -> {result}")
        if expected is not None:
            assert result is not None, f"Failed to parse: {text}"
    
    # 3. Тест инструмента времени
    print("\n🕐 Тест get_time:")
    result = tc._tool_get_time()
    print(f"   Результат: {result}")
    assert "Текущее время" in result
    print("   ✅ Работает")
    
    # 4. Получение промпта с инструментами
    print("\n📝 Тест get_tools_prompt:")
    prompt = tc.get_tools_prompt()
    print(f"   Длина промпта: {len(prompt)} символов")
    assert "TOOL_CALL" in prompt
    assert "get_weather" in prompt
    print("   ✅ Промпт содержит описание инструментов")
    
    # 5. Тест форматирования диалога
    print("\n💬 Тест форматирования диалога:")
    messages = [
        {"role": "user", "content": "Привет"},
        {"role": "assistant", "content": "Привет!"},
        {"role": "user", "content": "Как дела?"},
    ]
    formatted = tc._format_conversation(messages)
    print(f"   Результат:\n{formatted}")
    assert "Пользователь:" in formatted
    assert "Ассистент:" in formatted
    
    print("\n" + "=" * 60)
    print("✅ Все тесты пройдены!")
    print()
    print("Использование в ARGOS:")
    print('   > режим ии kimi с инструментами')
    print('   > Какая погода в Москве?  # Kimi вызовет get_weather')
    return True

if __name__ == "__main__":
    try:
        test_tools()
        sys.exit(0)
    except AssertionError as e:
        print(f"\n❌ Тест не пройден: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Ошибка: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)