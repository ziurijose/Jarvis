@echo off
rem Double-click on Windows to start JARVIS. The first run installs everything it needs.
cd /d "%~dp0"
set "PATH=%USERPROFILE%\.local\bin;%PATH%"

if not exist ".venv\Scripts\python.exe" (
    powershell -NoProfile -ExecutionPolicy Bypass -File "setup_windows.ps1"
    if errorlevel 1 (
        echo.
        echo Setup failed - the messages above say why.
        pause
        exit /b 1
    )
)

rem After an update: install any new packages (only when requirements-windows.txt changed).
fc /b requirements-windows.txt .venv\installed-requirements.txt >nul 2>&1
if errorlevel 1 (
    echo Updating JARVIS's packages...
    uv pip install --python .venv\Scripts\python.exe -r requirements-windows.txt && copy /y requirements-windows.txt .venv\installed-requirements.txt >nul
)

rem Older installs: add on-device speech (Whisper, wake word, Kokoro) once.
set "NEEDS_SPEECH="
if not exist ".venv\.no-whisper" (.venv\Scripts\python.exe -c "import faster_whisper" >nul 2>&1 || set "NEEDS_SPEECH=1")
if not exist ".venv\.no-wake" (.venv\Scripts\python.exe -c "import openwakeword" >nul 2>&1 || set "NEEDS_SPEECH=1")
if not exist ".venv\.no-kokoro" if not exist "models\kokoro-v1.0.onnx" set "NEEDS_SPEECH=1"
if defined NEEDS_SPEECH powershell -NoProfile -ExecutionPolicy Bypass -File "add_speech.ps1"

.venv\Scripts\python.exe -W ignore jarvis.py
if errorlevel 1 pause
