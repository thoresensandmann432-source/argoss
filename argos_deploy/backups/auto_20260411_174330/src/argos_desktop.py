#!/usr/bin/env python3
"""
argos_desktop.py — ARGOS Desktop GUI (без Kivy)
================================================
Чистый запуск GUI на customtkinter для Windows/Linux/macOS.
Без зависимостей от Kivy/OpenGL.

Использование:
    python argos_desktop.py              # Запуск GUI
    python argos_desktop.py --minimal    # Минималистичный режим
"""

import sys
import os

# ─────────────────────────────────────────────────────────────────────────────
# БЛОКИРОВКА KIVY — должно быть ДО любых импортов ARGOS
# ─────────────────────────────────────────────────────────────────────────────
os.environ["KIVY_NO_ARGS"] = "1"
os.environ["KIVY_NO_ENV_CONFIG"] = "1"
os.environ["KIVY_HEADLESS"] = "1"
os.environ["KIVY_METRICS_ENABLED"] = "0"

# Подавляем загрузку Kivy модулей
sys.modules['kivy'] = type(sys)('kivy')
sys.modules['kivy.app'] = type(sys)('kivy.app')
sys.modules['kivy.uix'] = type(sys)('kivy.uix')
sys.modules['kivy.core'] = type(sys)('kivy.core')
sys.modules['kivy.core.window'] = type(sys)('kivy.core.window')
sys.modules['kivy.graphics'] = type(sys)('kivy.graphics')
sys.modules['kivy.clock'] = type(sys)('kivy.clock')
sys.modules['kivy.lang'] = type(sys)('kivy.lang')

def _fake_kivy_import(*args, **kwargs):
    raise ImportError("Kivy blocked — using customtkinter only")

# Заменяем импортер для kivy
class KivyBlocker:
    def find_module(self, name, path=None):
        if name.startswith('kivy'):
            return self
        return None
    
    def load_module(self, name):
        raise ImportError(f"Kivy module '{name}' blocked — desktop mode uses customtkinter")

# Регистрируем блокировщик
sys.meta_path.insert(0, KivyBlocker())

# ─────────────────────────────────────────────────────────────────────────────
# Теперь можно импортировать ARGOS
# ─────────────────────────────────────────────────────────────────────────────
sys.path.insert(0, str(os.path.dirname(__file__)))

try:
    import customtkinter as ctk
    from src.interface.gui import ArgosGUI
    GUI_MODE = "customtkinter"
except ImportError as e:
    print(f"❌ GUI Error: {e}")
    print("Пожалуйста, установите: pip install customtkinter")
    sys.exit(1)

from src.core import ArgosCore
from src.admin import ArgosAdmin
from src.argos_integrator import ArgosIntegrator
from src.argos_logger import get_logger
from dotenv import load_dotenv

load_dotenv()

log = get_logger("argos.desktop")


def boot_desktop_no_kivy():
    """Загрузка desktop GUI без Kivy."""
    import threading
    import uuid
    from datetime import datetime
    
    log.info("="*60)
    log.info(" ARGOS DESKTOP v3.0 — Kivy-Free Mode")
    log.info("="*60)
    
    # Инициализация без Kivy
    log.info("[INIT] Загрузка ядра...")
    core = ArgosCore()
    
    log.info("[INIT] Загрузка администратора...")
    try:
        from src.factory.flasher import AirFlasher
        admin = ArgosAdmin()
        flasher = AirFlasher()
    except Exception as e:
        log.warning("[INIT] Admin/Flasher: %s", e)
        admin = None
        flasher = None
    
    # Интегратор уже работает в core
    integrator = getattr(core, 'integrator', None)
    if not integrator:
        log.info("[INIT] Запуск интегратора...")
        integrator = ArgosIntegrator(core)
        integrator.integrate_all()
    
    # Получаем статус
    stats = {
        "version": "3.0",
        "node_id": str(uuid.uuid4())[:8],
        "start_time": datetime.now(),
        "skills": len(core.skill_loader._skills) if hasattr(core, 'skill_loader') and core.skill_loader else 0,
        "claude_agents": len(integrator._claude_integrator._agent_cache) if integrator and hasattr(integrator, '_claude_integrator') else 0,
    }
    
    log.info("[INIT] Статус: %s", stats)
    
    # Запуск GUI
    log.info("[GUI] Запуск CustomTkinter интерфейса...")
    
    try:
        app = ArgosGUI(core, admin, flasher, location="desktop")
        
        # Добавляем стартовое сообщение
        is_root = False  # Можно определить позже
        app._append(
            f"👁️ ARGOS DESKTOP v3.0 (Kivy-Free)\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"Создатель: Всеволод\n"
            f"Гео: Desktop\n"
            f"Права: {'ROOT ✅' if is_root else 'User ⚠️'}\n"
            f"ИИ: {core.ai_mode_label() if hasattr(core, 'ai_mode_label') else 'Auto'}\n"
            f"Навыки: {stats['skills']} загружено\n"
            f"Claude агенты: {stats['claude_agents']} доступно\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"Напечатай 'помощь' для списка команд.\n"
            f"Используй 'агент <задача>' для вызова Claude.\n\n",
            "#00FF88",
        )
        
        log.info("[GUI] Интерфейс готов")
        app.mainloop()
        
    except Exception as e:
        log.error("[GUI] Ошибка запуска: %s", e)
        raise


def main():
    """Главная точка входа."""
    import argparse
    
    parser = argparse.ArgumentParser(description="ARGOS Desktop GUI (Kivy-Free)")
    parser.add_argument("--minimal", action="store_true", help="Минималистичный режим")
    parser.add_argument("--theme", default="dark", choices=["dark", "light"], help="Тема")
    
    args = parser.parse_args()
    
    # Настройка темы
    if args.theme == "dark":
        ctk.set_appearance_mode("dark")
    else:
        ctk.set_appearance_mode("light")
    
    try:
        boot_desktop_no_kivy()
    except KeyboardInterrupt:
        log.info("\n[EXIT] Прервано пользователем")
    except Exception as e:
        log.error("[FATAL] %s", e)
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()