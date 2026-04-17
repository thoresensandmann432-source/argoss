#!/usr/bin/env python3
"""
setup_kimi.py — Установка и настройка Kimi K2.5 для ARGOS

Быстрая настройка:
    python setup_kimi.py

Интерактивная установка API ключа и тестирование.
"""

import os
import sys

def print_header():
    print("╔══════════════════════════════════════════════════════════════╗")
    print("║  🌙 Kimi K2.5 (Moonshot AI) Setup for ARGOS                  ║")
    print("╚══════════════════════════════════════════════════════════════╝")
    print()

def check_requirements():
    """Проверка наличия requests."""
    try:
        import requests
        print("✅ requests установлен")
        return True
    except ImportError:
        print("❌ requests не найден")
        print("   Установите: pip install requests")
        return False

def get_api_key():
    """Получение API ключа от пользователя."""
    print("\n📋 Получение API ключа:")
    print("   1. Зайдите на https://platform.moonshot.ai")
    print("   2. Создайте аккаунт и API ключ")
    print("   3. Скопируйте ключ (начинается с sk-)")
    print()
    
    api_key = input("🔑 Введите KIMI_API_KEY: ").strip()
    
    if not api_key.startswith("sk-"):
        print("⚠️  Предупреждение: ключ должен начинаться с 'sk-'")
        confirm = input("Продолжить? (y/n): ").lower()
        if confirm != 'y':
            return None
    
    return api_key

def test_api_key(api_key):
    """Тестирование API ключа."""
    import requests
    
    print("\n🧪 Тестирование API ключа...")
    
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    
    try:
        response = requests.get(
            "https://api.moonshot.cn/v1/models",
            headers=headers,
            timeout=10
        )
        
        if response.status_code == 200:
            data = response.json()
            models = [m["id"] for m in data.get("data", [])]
            print(f"✅ API ключ работает!")
            print(f"   Доступные модели: {', '.join(models[:3])}")
            return True
        elif response.status_code == 401:
            print("❌ Неверный API ключ (401 Unauthorized)")
            return False
        else:
            print(f"⚠️  Ошибка HTTP {response.status_code}")
            print(f"   {response.text[:200]}")
            return False
            
    except Exception as e:
        print(f"❌ Ошибка запроса: {e}")
        return False

def save_to_env(api_key):
    """Сохранение ключа в .env файл."""
    env_path = os.path.join(os.path.dirname(__file__), '.env')
    
    # Читаем существующий .env
    lines = []
    kimi_found = False
    
    if os.path.exists(env_path):
        with open(env_path, 'r', encoding='utf-8') as f:
            for line in f:
                if line.startswith('KIMI_API_KEY='):
                    lines.append(f'KIMI_API_KEY={api_key}\n')
                    kimi_found = True
                else:
                    lines.append(line)
    
    if not kimi_found:
        lines.append(f'\n# Kimi K2.5 (Moonshot AI)\n')
        lines.append(f'KIMI_API_KEY={api_key}\n')
    
    with open(env_path, 'w', encoding='utf-8') as f:
        f.writelines(lines)
    
    print(f"✅ API ключ сохранён в {env_path}")

def test_in_argos():
    """Тестирование в ARGOS."""
    print("\n🚀 Тестирование в ARGOS...")
    
    try:
        from src.connectivity.kimi_bridge import KimiBridge
        
        kimi = KimiBridge()
        if not kimi.is_available:
            print("❌ KimiBridge не видит KIMI_API_KEY")
            return False
        
        print("✅ KimiBridge инициализирован")
        
        # Тестовый запрос
        print("\n💬 Тестовый запрос:")
        print("   Запрос: Привет! Какая у тебя модель?")
        print("   Ответ:", end=" ", flush=True)
        
        response = kimi.chat("Привет! Какая у тебя модель и версия?")
        print(response[:100] + "..." if len(response) > 100 else response)
        
        return True
        
    except Exception as e:
        print(f"❌ Ошибка: {e}")
        import traceback
        traceback.print_exc()
        return False

def main():
    print_header()
    
    # Проверка зависимостей
    if not check_requirements():
        sys.exit(1)
    
    # Получение API ключа
    api_key = get_api_key()
    if not api_key:
        print("❌ API ключ не получен")
        sys.exit(1)
    
    # Тестирование
    if not test_api_key(api_key):
        retry = input("\nПовторить ввод? (y/n): ").lower()
        if retry == 'y':
            return main()
        sys.exit(1)
    
    # Сохранение
    save_to_env(api_key)
    
    # Экспорт для текущей сессии
    os.environ['KIMI_API_KEY'] = api_key
    print("✅ KIMI_API_KEY экспортирован в текущую сессию")
    
    # Тест в ARGOS
    success = test_in_argos()
    
    # Итог
    print("\n" + "="*60)
    if success:
        print("✅ Kimi K2.5 успешно настроен!")
        print()
        print("Использование в ARGOS:")
        print("   > режим ии kimi")
        print("   или")
        print("   > set_ai_mode('kimi')")
        print()
        print("Python API:")
        print("   from src.connectivity.kimi_bridge import KimiBridge")
        print("   kimi = KimiBridge()")
        print("   response = kimi.chat('Привет!')")
    else:
        print("⚠️  Настройка завершена с предупреждениями")
    print("="*60)

if __name__ == "__main__":
    main()