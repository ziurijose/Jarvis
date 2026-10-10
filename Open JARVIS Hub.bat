@echo off
rem Double-click to open the JARVIS hub: status and every setting. Run "Start JARVIS.bat" once first.
cd /d "%~dp0"
if not exist ".venv\Scripts\pythonw.exe" (
    echo JARVIS isn't installed yet. Double-click "Start JARVIS.bat" first.
    pause
    exit /b 1
)
start "" ".venv\Scripts\pythonw.exe" hub.py
