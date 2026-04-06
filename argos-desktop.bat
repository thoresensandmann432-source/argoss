@echo off
chcp 65001 >nul
title ARGOS Desktop v3.0 (Kivy-Free)
echo.
echo ╔══════════════════════════════════════════════════════════════╗
echo ║  ARGOS DESKTOP v3.0 — Kivy-Free Mode                        ║
echo ║  Чистый GUI на customtkinter без OpenGL/Kivy                 ║
echo ╚══════════════════════════════════════════════════════════════╝
echo.

REM Проверяем Python
python --version >nul 2>&1
if errorlevel 1 (
    echo ❌ Python не найден. Установите Python 3.10+
    pause
    exit /b 1
)

REM Проверяем customtkinter
python -c "import customtkinter" >nul 2>&1
if errorlevel 1 (
    echo ⚠️  customtkinter не найден. Устанавливаю...
    pip install customtkinter --quiet
    if errorlevel 1 (
        echo ❌ Не удалось установить customtkinter
        pause
        exit /b 1
    )
)

echo ✅ customtkinter OK
echo.
echo 🚀 Запуск ARGOS Desktop...
echo.

REM Запускаем desktop версию без Kivy
python src/argos_desktop.py %*

if errorlevel 1 (
    echo.
    echo ❌ Ошибка запуска
    pause
)

pause