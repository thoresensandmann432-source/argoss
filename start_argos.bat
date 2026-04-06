@echo off
cd /d C:\Users\AvA\debug\argoss
set PYTHONUNBUFFERED=1
set ARGOS_AUTO_VENV=off
set ARGOS_AUTO_ARC=off
python -u main.py --no-gui >> C:\Users\AvA\debug\argos_new.log 2>&1
