#!/bin/bash
# One-time JARVIS setup on macOS. "Start JARVIS.command" runs this automatically the first
# time; it can also be run by hand from Terminal:  bash setup_mac.sh
set -e
cd "$(dirname "$0")"

# uv installs Python and the packages into this folder only. It needs no admin password
# and no Homebrew, and its Python includes tkinter, which draws the setup window and HUD.
export PATH="$HOME/.local/bin:$PATH"
if ! command -v uv >/dev/null 2>&1; then
    echo "Installing uv (the Python installer)..."
    curl -LsSf https://astral.sh/uv/install.sh | sh
    export PATH="$HOME/.local/bin:$PATH"
fi

echo "Setting up Python 3.13 and JARVIS's packages (a few minutes the first time)..."
uv venv --python 3.13 .venv
uv pip install --python .venv/bin/python -r requirements-mac.txt
cp requirements-mac.txt .venv/installed-requirements.txt
bash add_speech.sh

if ! command -v claude >/dev/null 2>&1; then
    echo
    echo "Note: Claude Code isn't installed, so \"ask Claude\" won't work yet."
    echo "Everything else works. To add it: https://claude.com/claude-code"
fi

echo
echo "Setup done."
