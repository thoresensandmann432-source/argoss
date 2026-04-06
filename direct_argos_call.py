import sys
import os

# Добавляем путь к проекту
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

def call_argos_function():
    """Прямой вызов функций Argos"""
    try:
        # Попробуем импортировать основные модули
        import importlib.util
        
        # Попробуем найти основной модуль
        possible_main_files = [
            'main.py',
            'argos_cli.py', 
            'core.py'
        ]
        
        for filename in possible_main_files:
            if os.path.exists(filename):
                print(f"✅ Найден файл: {filename}")
                # Здесь можно попробовать импортировать и вызвать функции напрямую
                break
        else:
            print("❌ Не найдены основные файлы")
            
        # Попробуем импортировать argos_cli напрямую
        if os.path.exists('argos_cli.py'):
            import argos_cli
            print("✅ Модуль argos_cli импортирован")
            
            # Попробуем вызвать функции
            print("🔧 Доступные атрибуты:")
            for attr in dir(argos_cli):
                if not attr.startswith('_'):
                    print(f"  - {attr}")
                    
    except ImportError as e:
        print(f"❌ Ошибка импорта: {e}")
    except Exception as e:
        print(f"❌ Ошибка: {e}")

if __name__ == "__main__":
    call_argos_function()
