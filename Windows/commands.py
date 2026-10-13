"""Running commands for JARVIS: PowerShell on Windows, zsh on a Mac.

Commands run straight away, except ones that delete or overwrite files (is_risky): those run
only after JARVIS has read the command back and the user has answered with a clear yes, the
same way sending a message works. A misheard request can't wipe anything on its own.
A running command is stopped the moment the user talks.
"""
import os
import re
import shutil
import subprocess
import sys
import threading

IS_WINDOWS = sys.platform == 'win32'
NO_WINDOW = {'creationflags': 0x08000000} if IS_WINDOWS else {}
MAX_OUTPUT = 4000  # characters of output Claude gets back (the end, where errors and results are)

RISKY = re.compile(
    r'\b(remove-item|rm|ri|del|erase|rmdir|rd|clear-content|set-content|out-file|clear-recyclebin'
    r'|format-volume|format-disk|clear-disk|initialize-disk|remove-\w+)\b'
    r'|\bformat\s+[a-z]:'
    r'|\b(move-item|copy-item|mv|cp|move|copy)\b.*\s(-force|-f)\b'
    r'|(?<![>\d&])>(?![>&])',  # > replaces a file's contents (>> only adds to it)
    re.I)
YES = re.compile(r"\b(yes|yeah|yep|yup|sure|go ahead|do it|delete it|correct|that's right|ok|okay|"
                 r"please do)\b", re.I)
NO = re.compile(r"\b(no|nope|don't|do not|cancel|wait|stop|change)\b", re.I)
_read_back = {}  # command -> what the user had said when JARVIS read it back
ASK_FIRST = ('Not run yet: this deletes or overwrites files. Tell the user in plain words what it will '
             'delete or change and ask if you should go ahead. Call again with the same command and '
             'confirmed=true only after they clearly say yes.')


def is_risky(command: str) -> bool:
    return bool(RISKY.search(command))


def _allowed(command, confirmed, heard) -> bool:
    """True only when this exact command was read back earlier and the user has since answered
    with a clear yes. The first call always just records the read-back."""
    key = command.strip()
    said_yes = bool(YES.search(heard or '')) and not NO.search(heard or '')
    if confirmed and key in _read_back and heard != _read_back[key] and said_yes:
        del _read_back[key]
        return True
    _read_back[key] = heard
    return False


def _shell(command):
    if IS_WINDOWS:
        # UTF-8 output, so names with accents or emoji come back readable.
        return ['powershell', '-NoProfile', '-NonInteractive', '-ExecutionPolicy', 'Bypass', '-Command',
                '[Console]::OutputEncoding = [Text.Encoding]::UTF8; ' + command]
    return [shutil.which('zsh') or '/bin/sh', '-lc', command]  # zsh on a Mac; plain sh elsewhere


def run_command(command: str, confirmed: bool = False, heard: str = '', interrupted=None) -> str:
    """Runs a command in the user's home folder and returns its output. interrupted: an Event
    set when the user talks, which stops the command."""
    if is_risky(command) and not _allowed(command, confirmed, heard):
        return ASK_FIRST
    interrupted = interrupted or threading.Event()
    process = subprocess.Popen(_shell(command), stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                               stderr=subprocess.STDOUT, text=True, encoding='utf-8', errors='replace',
                               cwd=os.path.expanduser('~'), **NO_WINDOW)
    output = []
    reader = threading.Thread(target=lambda: output.append(process.communicate()[0] or ''), daemon=True)
    reader.start()
    stopped = False
    while process.poll() is None:
        if interrupted.wait(0.1):
            process.kill()
            stopped = True
            break
    reader.join(5)
    text = (output[0] if output else '').strip()
    if len(text) > MAX_OUTPUT:
        text = '...' + text[-MAX_OUTPUT:]
    if stopped:
        return 'Stopped: the user started talking. Output so far:\n' + (text or '(none)')
    code = process.returncode
    ending = f'\n(exit code {code})' if code else ''
    return (text or ('Done, no output.' if not code else '')) + ending
