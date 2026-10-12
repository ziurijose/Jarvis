"""Shared pieces: speaking, the on-screen HUD, listening, and screenshots."""
import datetime
import json
import os
import subprocess
import sys
import time

from listen import Hearing
from mic import find_input_device
from platform_utils import screenshots_folder
import voices as voice_lib

VOICE = None  # the voice chosen in setup; jarvis.py sets it. None = the default voice


def speak(audio) -> None:
    voice_lib.say(VOICE, str(audio))


def screenshot() -> str:
    """Save a screenshot to the system's Screenshots folder and return its path."""
    import pyautogui
    folder = screenshots_folder()
    os.makedirs(folder, exist_ok=True)
    stamp = datetime.datetime.now().strftime('%Y-%m-%d %H%M%S')
    path = os.path.join(folder, f'JARVIS screenshot {stamp}.png')
    pyautogui.screenshot().save(path)
    return path


# JARVIS listens on the computer's default microphone (the one chosen in System Settings >
# Sound > Input). To use a different one, add "microphone": "<part of its name>" to
# user_settings.json.
MIC_NAME = None


def _mic_index():
    index = find_input_device(MIC_NAME)
    if MIC_NAME and index is None:
        print(f'Microphone "{MIC_NAME}" not found, using the system default')
    return index


_hud_process = None
HUD_TITLE = 'JARVIS'  # jarvis.py replaces this with the assistant name chosen in setup

STATUS = ''  # what JARVIS is doing now ('LISTENING', 'THINKING'...), for the menu bar
BRAIN_NAME = ''  # 'Claude Code' or 'Claude API'; jarvis.py sets it
# The hub (hub.py, a separate program) reads this to show what JARVIS is doing.
STATUS_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'status.json')


def write_status() -> None:
    """Writes STATUS for the hub. Best effort: the hub is optional."""
    data = {'status': STATUS, 'brain': BRAIN_NAME, 'pid': os.getpid(), 'updated': time.time()}
    try:
        temporary = STATUS_PATH + '.tmp'
        with open(temporary, 'w', encoding='utf-8') as f:
            json.dump(data, f)
        os.replace(temporary, STATUS_PATH)  # the hub never reads a half-written file
    except OSError:
        pass


def hud(command: str) -> None:
    """Send a command ("show <STATUS>", "caption <text>" or "hide") to the on-screen HUD,
    starting it if needed."""
    global _hud_process, STATUS
    if command.startswith('show') or command == 'hide':
        STATUS = command[4:].strip().upper() if command.startswith('show') else ''
        write_status()
    try:
        if _hud_process is None or _hud_process.poll() is not None:
            hud_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'hud.py')
            _hud_process = subprocess.Popen([sys.executable, hud_path, HUD_TITLE],
                                            stdin=subprocess.PIPE, text=True)
        _hud_process.stdin.write(' '.join(command.split()) + '\n')
        _hud_process.stdin.flush()
    except OSError:
        pass  # the HUD is cosmetic; JARVIS keeps working without it


_hearing = None


def start_hearing(settings=None) -> None:
    """Set up listening (jarvis.py calls this at startup, so Whisper loads in the background).

    user_settings.json can turn off "wake_word" (then JARVIS listens for its own name, which
    is slower) or "barge_in" (then only "Hey Jarvis" or the hotkey interrupts it)."""
    global _hearing, MIC_NAME
    settings = settings or {}
    MIC_NAME = settings.get('microphone') or None
    hints = [settings.get('assistant_name'), settings.get('user_name')]
    _hearing = Hearing(mic_index=_mic_index(), language=settings.get('language'), hints=hints,
                       assistant_name=settings.get('assistant_name') or 'Jarvis',
                       wake_word=settings.get('wake_word', True) is not False,
                       barge_in=settings.get('barge_in', True) is not False)


def hearing() -> Hearing:
    if _hearing is None:
        start_hearing()
    return _hearing
