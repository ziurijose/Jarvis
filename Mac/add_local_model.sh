#!/bin/bash
# Adds what JARVIS's brain needs: the free local model (Node.js, TurboLLM and the model that suits
# this Mac) and Claude Code, which takes over when the local model can't.
# Setup runs this; "Start JARVIS.command" also runs it once for older installs. Each part can fail
# without stopping JARVIS (it then uses what it has). To try again later:  bash add_local_model.sh
cd "$(dirname "$0")"
NODE_DIR="$PWD/.node"
export PATH="$NODE_DIR/bin:$HOME/.local/bin:$PATH"

node_ok() {  # Node.js 22.13 or newer (what TurboLLM needs)
    command -v node >/dev/null 2>&1 \
        && node -e 'const [a,b]=process.versions.node.split(".").map(Number);process.exit(a>22||(a===22&&b>=13)?0:1)' 2>/dev/null
}

if ! node_ok; then
    echo "Adding Node.js, which runs TurboLLM (about 50 MB, once)..."
    case "$(uname -m)" in arm64|aarch64) arch=arm64 ;; *) arch=x64 ;; esac
    os=$(uname -s | tr '[:upper:]' '[:lower:]')  # darwin (or linux)
    version=$(curl -fsSL https://nodejs.org/dist/index.json | .venv/bin/python -c '
import json, sys
releases = [r["version"] for r in json.load(sys.stdin) if r["version"].startswith("v22.") and r.get("lts")]
print(releases[0] if releases else "")')
    if [ -n "$version" ] \
            && curl -fL --progress-bar "https://nodejs.org/dist/$version/node-$version-$os-$arch.tar.gz" -o .node.tar.gz \
            && rm -rf "$NODE_DIR" && mkdir -p "$NODE_DIR" \
            && tar -xzf .node.tar.gz -C "$NODE_DIR" --strip-components 1 && node_ok; then
        echo "Node.js $version added."
    else
        echo "Node.js couldn't be added, so the local model can't run yet; JARVIS will use Claude Code."
    fi
    rm -f .node.tar.gz
fi

if node_ok && [ ! -x "$NODE_DIR/bin/turbollm" ]; then
    echo "Adding TurboLLM, which runs the local model..."
    npm install --global --prefix "$NODE_DIR" --no-fund --no-audit turbollm \
        || echo "TurboLLM couldn't be added; JARVIS will try again next time it starts."
fi

if ! command -v claude >/dev/null 2>&1; then
    echo "Adding Claude Code, for the requests the local model can't do..."
    curl -fsSL https://claude.ai/install.sh | bash \
        || echo "Claude Code couldn't be added. To add it later: https://claude.com/claude-code"
fi

if [ -x "$NODE_DIR/bin/turbollm" ]; then
    echo "Getting the local model ready: the fastest one this Mac runs well (a few GB, once)..."
    if .venv/bin/python -W ignore -c "import brain; brain.prepare_local_model()"; then
        rm -f .venv/.no-local
    else
        touch .venv/.no-local
        echo "The local model isn't ready yet; JARVIS will finish it when it starts, using Claude meanwhile."
    fi
else
    touch .venv/.no-local
fi
exit 0
