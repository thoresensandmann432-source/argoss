@echo off
setlocal ENABLEDELAYEDEXPANSION
REM One-shot helper: ensure Python 3.12 + venv + arc-agi/arcengine, then start Argos main.py
REM Usage: double-click or run in cmd from repo dir

set TARGET_PY=python.exe
set WINGET_ID=Python.Python.3.12

where %TARGET_PY% >nul 2>&1
if %errorlevel% neq 0 (
    echo [INFO] Installing Python 3.12 via winget...
    winget install -e --id %WINGET_ID% -h
)

for /f "tokens=*" %%i in ('where %TARGET_PY%') do set PYEXE=%%i
if not defined PYEXE (
    echo [ERROR] python.exe not found. Install Python 3.12 manually.
    exit /b 1
)

echo [INFO] Using %PYEXE%

if not exist .venv (
    echo [INFO] Creating venv...
    "%PYEXE%" -m venv .venv
)

call .venv\Scripts\activate.bat
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python -m pip install arc-agi arcengine

echo [INFO] Starting Argos (main.py --no-gui)...
python main.py --no-gui

endlocal
