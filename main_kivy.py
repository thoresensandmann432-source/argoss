# ARGOS Universal OS — Android / Kivy entry point
# -*- coding: utf-8 -*-
"""
main_kivy.py — точка входа для buildozer (Android APK).

Запускает ArgosLocalApp (Kivy UI) или показывает
сообщение об ошибке если Kivy не установлен.
"""

import os
import sys

# Добавляем корень проекта в путь — нужно для Android
_ROOT = os.path.dirname(os.path.abspath(__file__))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

# Отключаем stdin на Android (нет TTY)
try:
    if not sys.stdin.isatty():
        sys.stdin = open(os.devnull, "r")
except Exception:
    pass

# Kivy environment
os.environ.setdefault("KIVY_NO_CONSOLELOG", "1")
os.environ.setdefault("KIVY_NO_ENV_CONFIG", "0")


def main():
    try:
        from src.interface.kivy_local_ui import ArgosLocalApp
        app = ArgosLocalApp()
        app.run()
    except ImportError as e:
        # Fallback: минимальное Kivy-приложение
        try:
            from kivy.app import App
            from kivy.uix.label import Label

            class FallbackApp(App):
                def build(self):
                    return Label(
                        text="ARGOS: UI недоступен\n" + str(e),
                        halign="center",
                        font_size="18sp",
                    )

            FallbackApp().run()
        except Exception:
            print("[ARGOS] Fatal: " + str(e))
            sys.exit(1)
    except Exception as e:
        import traceback
        traceback.print_exc()
        try:
            from kivy.app import App
            from kivy.uix.label import Label

            class ErrorApp(App):
                def build(self):
                    return Label(
                        text="ARGOS Error:\n" + str(e),
                        halign="center",
                        font_size="16sp",
                    )

            ErrorApp().run()
        except Exception:
            print("[ARGOS] Fatal error: " + str(e))
            sys.exit(1)


if __name__ == "__main__":
    main()
