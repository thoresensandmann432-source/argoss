@echo off
setlocal
REM Auto-setup Python 3.12, venv, install deps, start Telegram bot

REM 1) Ensure Python 3.12 is installed via winget; skip if already present
where python.exe >nul 2>&1
if %errorlevel% neq 0 (
    echo Installing Python 3.12 via winget...
    winget install -e --id Python.Python.3.12 -h
)

REM 2) Use Python 3.12 explicitly
for /f "tokens=*" %%i in ('where python.exe') do set PYEXE=%%i

REM 3) Create venv if missing
if not exist .venv (
    echo Creating venv...
    "%PYEXE%" -m venv .venv
)

REM 4) Activate venv
call .venv\Scripts\activate.bat

REM 5) Upgrade pip
python -m pip install --upgrade pip

REM 6) Install requirements + arc-agi + arcengine
python -m pip install -r requirements.txt
python -m pip install arc-agi arcengine

REM 7) Run telegram bot (or main Argos)
python telegram_bot.py

endlocal
