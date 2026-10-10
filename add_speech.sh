#!/bin/bash
# Adds JARVIS's on-device speech (Whisper to understand you, the "Hey Jarvis" wake word,
# Kokoro to talk like a person) and conversation search.
# Setup runs this; "Start JARVIS.command" also runs it once for older installs.
# Either can fail without stopping JARVIS: it then uses Google speech recognition or the
# Mac's own voice.  To try again later:  bash add_speech.sh
cd "$(dirname "$0")"
export PATH="$HOME/.local/bin:$PATH"

echo "Adding Whisper speech recognition (a few hundred MB, once)..."
if uv pip install --python .venv/bin/python "faster-whisper>=1.1" \
        && .venv/bin/python -c "import listen; listen.download_model()"; then
    rm -f .venv/.no-whisper
else
    touch .venv/.no-whisper
    echo "Whisper couldn't be added, so JARVIS will use Google's speech recognition."
fi

echo "Adding the \"Hey Jarvis\" wake word..."
if uv pip install --python .venv/bin/python "openwakeword>=0.6" \
        && .venv/bin/python -c "import openwakeword.utils as u; u.download_models(model_names=['hey_jarvis'])"; then
    rm -f .venv/.no-wake
else
    touch .venv/.no-wake
    echo "The wake word couldn't be added, so JARVIS will listen for its name instead."
fi

echo "Adding the natural voice (about 330 MB, once)..."
if uv pip install --python .venv/bin/python "kokoro-onnx>=0.4" \
        && .venv/bin/python -c "import voices; voices.download_kokoro()"; then
    rm -f .venv/.no-kokoro
else
    touch .venv/.no-kokoro
    echo "The natural voice couldn't be added, so JARVIS will use your Mac's voice."
fi

echo "Adding conversation search (about 24 MB, once)..."
.venv/bin/python -c "import recall; recall.download_model()" \
    || echo "Conversation search couldn't be added now; JARVIS will try again when it starts."
exit 0
