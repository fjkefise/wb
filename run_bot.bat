@echo off
title WB Price Monitor Bot
cd /d "%~dp0"

REM Check if venv exists
if not exist ".venv\Scripts\python.exe" (
    echo Installing virtual environment...
    python -m venv .venv
    call .venv\Scripts\pip install -q -r requirements.txt
)

REM Activate venv and run bot
call .venv\Scripts\activate.bat
python main.py bot
pause
