@echo off
title Lineage OS Installer for Samsung GUI
cd /d "%~dp0"
echo Starting Lineage OS Installer for Samsung GUI...
python main.py
if %ERRORLEVEL% NEQ 0 (
    echo.
    echo [ERROR] Application exited with an error. Installing requirements...
    pip install -r requirements.txt
    python main.py
    pause
)
