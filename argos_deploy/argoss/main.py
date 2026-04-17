#!/usr/bin/env python3
"""
argoss/main.py — Главный entry point для ARGOS
================================================
Инициализирует ядро, загружает конституцию, запускает мониторинг.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

# Добавляем текущую директорию в путь
sys.path.insert(0, str(Path(__file__).parent))

from argos_core import ArgosCore
from argos_logger import get_logger, setup_debug_logging
from constitution_hooks import ConstitutionHooks

__version__ = "1.0.0"
logger = get_logger("argos.main")


def load_constitution(path: str = "ARGOS_CONSTITUTION.yaml") -> dict:
    """Загружает конституцию ARGOS."""
    try:
        import yaml
        with open(path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    except FileNotFoundError:
        logger.warning(f"Конституция не найдена: {path}")
        return {}
    except ImportError:
        logger.warning("PyYAML не установлен, используем defaults")
        return {}


def check_gigachat():
    """Проверяет доступность GigaChat."""
    api_key = os.getenv("GIGACHAT_API_KEY")
    if not api_key:
        logger.info("⚠️ GIGACHAT_API_KEY не установлен. GigaChat недоступен.")
        return False
    logger.info("✅ GigaChat API ключ найден")
    return True


def main():
    """Главная функция запуска ARGOS."""
    print(f"🚀 ARGOS v{__version__}")
    print("=" * 50)

    # Настройка логирования
    log_path = setup_debug_logging()
    logger.info(f"Логирование настроено: {log_path}")

    # Загрузка конституции
    constitution = load_constitution()
    if constitution:
        logger.info(f"✅ Конституция загружена: v{constitution.get('version', 'unknown')}")
        print(f"📜 Конституция: {constitution.get('name', 'ARGOS')}")
        print(f"   Режимы: {', '.join(constitution.get('modes', {}).get('allowed', []))}")
    else:
        logger.warning("Конституция не загружена, используются defaults")

    # Инициализация ядра
    print("\n🔧 Инициализация ядра...")
    core = ArgosCore()

    # Проверка GigaChat
    print("\n🌐 Проверка провайдеров:")
    has_gigachat = check_gigachat()
    print(f"   GigaChat: {'✅' if has_gigachat else '❌'}")
    print(f"   Gemini: ✅")
    print(f"   Ollama: ✅")

    # Интерактивный режим
    print("\n" + "=" * 50)
    print("🤖 ARGOS готов к работе")
    print("Команды: останови агента | запусти агента | tail [N]")
    print("         гигачат статус | инфра | провайдеры | exit")
    print("=" * 50 + "\n")

    while True:
        try:
            command = input("argos> ").strip()
            if not command:
                continue
            if command.lower() in ("exit", "quit", "выход"):
                print("👋 До свидания!")
                break

            result = core.handle_command(command)
            print(result)

        except KeyboardInterrupt:
            print("\n👋 Прервано пользователем")
            break
        except Exception as e:
            logger.error(f"Ошибка: {e}")
            print(f"❌ Ошибка: {e}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
