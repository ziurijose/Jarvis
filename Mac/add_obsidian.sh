#!/bin/bash
# Adds Obsidian, where JARVIS keeps its memory as notes you can read and edit, and graphify,
# which maps those notes as a graph (/graphify in Claude Code). Setup runs this; "Start
# JARVIS.command" runs it once for older installs. Each part can fail without stopping JARVIS,
# which keeps writing its notes either way. To try again later:  bash add_obsidian.sh
cd "$(dirname "$0")"
export PATH="$HOME/.local/bin:$PATH"
ok=1

if [ -d /Applications/Obsidian.app ] || [ -d "$HOME/Applications/Obsidian.app" ]; then
    echo "Obsidian is already installed."
else
    echo "Adding Obsidian, where JARVIS keeps its memory (about 300 MB, once)..."
    url=$(curl -fsSL https://api.github.com/repos/obsidianmd/obsidian-releases/releases/latest | .venv/bin/python -c '
import json, sys
names = [a["browser_download_url"] for a in json.load(sys.stdin).get("assets", []) if a["name"].endswith(".dmg")]
print(names[0] if names else "")' 2>/dev/null)
    mount=$(mktemp -d)
    if [ -n "$url" ] && curl -fL --progress-bar "$url" -o .obsidian.dmg \
            && hdiutil attach -nobrowse -quiet -mountpoint "$mount" .obsidian.dmg \
            && mkdir -p "$HOME/Applications" \
            && cp -R "$mount/Obsidian.app" "$HOME/Applications/"; then
        echo "Obsidian added."
    else
        rm -rf "$HOME/Applications/Obsidian.app"
        echo "Obsidian couldn't be added. To add it by hand: https://obsidian.md/download"
        ok=0
    fi
    hdiutil detach -quiet "$mount" 2>/dev/null
    rmdir "$mount" 2>/dev/null
    rm -f .obsidian.dmg
fi

if ! command -v graphify >/dev/null 2>&1 && ! uv tool install graphifyy; then
    echo "graphify couldn't be added. To add it later:  uv tool install graphifyy && graphify install --platform claude"
    ok=0
elif graphify install --platform claude >/dev/null; then
    echo "graphify is ready: in Claude Code, /graphify maps a folder of notes."
else
    echo "graphify's /graphify command couldn't be added to Claude Code. To add it later:  graphify install --platform claude"
    ok=0
fi

if [ "$ok" = 1 ]; then rm -f .venv/.no-obsidian; else touch .venv/.no-obsidian; fi
exit 0
