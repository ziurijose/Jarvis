# One-time JARVIS setup on Windows. "Start JARVIS.bat" runs this automatically the first time;
# it can also be run by hand:  powershell -ExecutionPolicy Bypass -File setup_windows.ps1
# Failures are caught through $LASTEXITCODE below. 'Stop' would also abort on uv's progress
# messages, which Windows PowerShell can report as errors because uv writes them to stderr.
$ErrorActionPreference = 'Continue'
Set-Location $PSScriptRoot

# uv installs Python and the packages into this folder only. It needs no admin password, and
# its Python includes tkinter, which draws the listening orb.
$env:Path = "$env:USERPROFILE\.local\bin;$env:Path"
if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
    Write-Host 'Installing uv (the Python installer)...'
    Invoke-RestMethod https://astral.sh/uv/install.ps1 | Invoke-Expression
    $env:Path = "$env:USERPROFILE\.local\bin;$env:Path"
}

Write-Host "Setting up Python 3.13 and JARVIS's packages (a few minutes the first time)..."
uv venv --python 3.13 .venv
if ($LASTEXITCODE -ne 0) { exit 1 }
uv pip install --python .venv\Scripts\python.exe -r requirements-windows.txt
if ($LASTEXITCODE -ne 0) { exit 1 }
Copy-Item requirements-windows.txt .venv\installed-requirements.txt -Force
& "$PSScriptRoot\add_speech.ps1"

if (-not (Get-Command claude -ErrorAction SilentlyContinue)) {
    Write-Host ''
    Write-Host "Note: Claude Code isn't installed, and JARVIS thinks with it. Install it from"
    Write-Host 'https://claude.com/claude-code and sign in once.'
}

Write-Host ''
Write-Host 'Setup done.'
exit 0
