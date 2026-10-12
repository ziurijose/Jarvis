# Adds JARVIS's on-device speech (Whisper to understand you, the "Hey Jarvis" wake word,
# Kokoro to talk like a person) and conversation search.
# Setup runs this; "Start JARVIS.bat" also runs it once for older installs.
# Either can fail without stopping JARVIS: it then uses Google speech recognition or Windows'
# own voice.  To try again later:  powershell -ExecutionPolicy Bypass -File add_speech.ps1
Set-Location $PSScriptRoot
$env:Path = "$env:USERPROFILE\.local\bin;$env:Path"
$python = '.venv\Scripts\python.exe'

Write-Host 'Adding Whisper speech recognition (a few hundred MB, once)...'
uv pip install --python $python "faster-whisper>=1.1"
if ($LASTEXITCODE -eq 0) { & $python -c "import listen; listen.download_model()" }
if ($LASTEXITCODE -eq 0) { Remove-Item .venv\.no-whisper -ErrorAction SilentlyContinue }
else { New-Item .venv\.no-whisper -ItemType File -Force | Out-Null
       Write-Host "Whisper couldn't be added, so JARVIS will use Google's speech recognition." }

Write-Host 'Adding the "Hey Jarvis" wake word...'
uv pip install --python $python "openwakeword>=0.6"
if ($LASTEXITCODE -eq 0) { & $python -c "import openwakeword.utils as u; u.download_models(model_names=['hey_jarvis'])" }
if ($LASTEXITCODE -eq 0) { Remove-Item .venv\.no-wake -ErrorAction SilentlyContinue }
else { New-Item .venv\.no-wake -ItemType File -Force | Out-Null
       Write-Host "The wake word couldn't be added, so JARVIS will listen for its name instead." }

Write-Host 'Adding the natural voice (about 330 MB, once)...'
uv pip install --python $python "kokoro-onnx>=0.4"
if ($LASTEXITCODE -eq 0) { & $python -c "import voices; voices.download_kokoro()" }
if ($LASTEXITCODE -eq 0) { Remove-Item .venv\.no-kokoro -ErrorAction SilentlyContinue }
else { New-Item .venv\.no-kokoro -ItemType File -Force | Out-Null
       Write-Host "The natural voice couldn't be added, so JARVIS will use Windows' own voice." }

Write-Host 'Adding conversation search (about 24 MB, once)...'
& $python -c "import recall; recall.download_model()"
if ($LASTEXITCODE -ne 0) { Write-Host "Conversation search couldn't be added now; JARVIS will try again when it starts." }
exit 0
