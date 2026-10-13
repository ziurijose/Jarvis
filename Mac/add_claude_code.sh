#!/bin/bash
# Adds Claude Code, JARVIS's brain. Setup runs this; "Start JARVIS.command" runs it again while
# Claude Code is missing. To try again by hand:  bash add_claude_code.sh
cd "$(dirname "$0")"
export PATH="$HOME/.local/bin:$PATH"

if ! command -v claude >/dev/null 2>&1; then
    echo "Adding Claude Code, which JARVIS thinks with..."
    curl -fsSL https://claude.ai/install.sh | bash \
        || echo "Claude Code couldn't be added. To add it later: https://claude.com/claude-code"
fi
exit 0
