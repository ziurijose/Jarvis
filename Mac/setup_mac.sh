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
bash add_claude_code.sh
bash add_obsidian.sh

# macOS asks for the camera and microphone by itself. These two it doesn't: Terminal needs them
# for JARVIS to use the mouse and keyboard (and the Option+Space hotkey), and to see the screen.
if [ -t 0 ]; then
    echo
    echo "Two Mac settings JARVIS needs. A settings window opens for each one: switch Terminal on"
    echo "(if Terminal isn't listed, click + and choose Applications > Utilities > Terminal)."
    read -r -p "Press Return to open Accessibility (mouse, keyboard and the hotkey)... "
    open "x-apple.systempreferences:com.apple.preference.security?Privacy_Accessibility"
    read -r -p "Press Return when done, to open Screen Recording (seeing the screen)... "
    open "x-apple.systempreferences:com.apple.preference.security?Privacy_ScreenCapture"
    read -r -p "Press Return when done. "
fi

if command -v claude >/dev/null 2>&1 || [ -x "$HOME/.local/bin/claude" ]; then
    echo
    echo "One more: JARVIS thinks with Claude Code, so sign in to it once: open a new Terminal"
    echo "window, type  claude  and press Return, and follow the steps."
fi

echo
echo "Setup done."
