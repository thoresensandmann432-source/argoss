@echo off
REM Argos Windows Autostart
REM Положи этот файл в: %APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\
REM Или добавь в планировщик задач Windows

title Argos Universal OS

REM Путь к проекту — замени на свой
set ARGOS_DIR=%~dp0

REM Активация venv если есть
if exist "%ARGOS_DIR%venv\Scripts\activate.bat" (
    call "%ARGOS_DIR%venv\Scripts\activate.bat"
) else if exist "%ARGOS_DIR%.venv\Scripts\activate.bat" (
    call "%ARGOS_DIR%.venv\Scripts\activate.bat"
)

REM Переходим в папку проекта
cd /d "%ARGOS_DIR%"

REM Запускаем PowerShell bridge (win_bridge_host.py) если порт 5000 свободен
for /f "tokens=5" %%p in ('netstat -ano ^| findstr ":5000" ^| findstr "LISTENING"') do set PORT5000=%%p
if not defined PORT5000 (
    echo [%date% %time%] Старт win_bridge_host на 5000...
    start "" /min python win_bridge_host.py
) else (
    echo [%date% %time%] win_bridge_host уже слушает 5000 (PID %PORT5000%)
)

REM Запускаем Аргос
:start
echo [%date% %time%] Запуск Аргоса...
python main.py --no-gui

REM Если упал — ждём 5 сек и перезапускаем
echo [%date% %time%] Аргос завершился. Перезапуск через 5 сек...
timeout /t 5 /nobreak > nul
goto start
