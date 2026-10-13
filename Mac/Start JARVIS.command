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
export PATH="$HOME/.local/bin:$PATH"  # where Claude Code installs
if ! command -v claude >/dev/null 2>&1; then
    bash add_claude_code.sh
fi
# Older installs: add Obsidian and graphify once (skipped after a failed try; run add_obsidian.sh to retry).
if { { [ ! -d /Applications/Obsidian.app ] && [ ! -d "$HOME/Applications/Obsidian.app" ]; } \
     || ! command -v graphify >/dev/null 2>&1; } && [ ! -f .venv/.no-obsidian ]; then
    bash add_obsidian.sh
fi

# The hub opens alongside JARVIS. It is its own program (nohup keeps it open if this Terminal
# window closes), so closing the hub leaves JARVIS running.
nohup .venv/bin/python -W ignore hub.py >/dev/null 2>&1 &

exec .venv/bin/python -W ignore jarvis.py
