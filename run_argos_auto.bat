@echo off
setlocal ENABLEDELAYEDEXPANSION
REM Auto-run Argos: ensure Python 3.12, create/update .venv, install deps (arc-agi/arcengine), start main.py --no-gui

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

REM Start win_bridge_host if port free and requested
set BRIDGE_PORT=5000
for /f "tokens=5" %%p in ('netstat -ano ^| findstr :%BRIDGE_PORT% ^| findstr LISTENING') do set PIDLISTEN=%%p
if not defined PIDLISTEN (
    if /I "%ARGOS_WIN_BRIDGE%"=="on" (
        echo [INFO] Starting win_bridge_host.py on %BRIDGE_PORT%...
        start "win_bridge_host" /B python win_bridge_host.py
    )
) else (
    echo [WARN] Port %BRIDGE_PORT% busy (PID %PIDLISTEN%), skipping win_bridge_host
)

echo [INFO] Starting Argos main.py --no-gui ...
python main.py --no-gui

endlocal
