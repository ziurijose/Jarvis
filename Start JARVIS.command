#!/bin/bash
# Double-click on a Mac to start JARVIS. The first run installs everything it needs.
cd "$(dirname "$0")"

if [ ! -x .venv/bin/python ]; then
    if ! bash setup_mac.sh; then
        echo
        echo "Setup failed - the messages above say why."
        read -r -p "Press Enter to close this window."
        exit 1
    fi
fi

# After an update: install any new packages (only when requirements-mac.txt changed).
if ! cmp -s requirements-mac.txt .venv/installed-requirements.txt; then
    echo "Updating JARVIS's packages..."
    if PATH="$HOME/.local/bin:$PATH" uv pip install --python .venv/bin/python -r requirements-mac.txt; then
        cp requirements-mac.txt .venv/installed-requirements.txt
    fi
fi
# Older installs: add on-device speech (Whisper, wake word, Kokoro) once.
if { [ ! -f .venv/.no-whisper ] && ! .venv/bin/python -c "import faster_whisper" 2>/dev/null; } \
   || { [ ! -f .venv/.no-wake ] && ! .venv/bin/python -c "import openwakeword" 2>/dev/null; } \
   || { [ ! -f .venv/.no-kokoro ] && [ ! -f models/kokoro-v1.0.onnx ]; }; then
    bash add_speech.sh
fi

exec .venv/bin/python -W ignore jarvis.py
