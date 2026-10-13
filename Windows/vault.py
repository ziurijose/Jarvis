"""JARVIS's notes in an Obsidian vault: the facts it remembers (JARVIS/Memory.md) and a readable
copy of every conversation (JARVIS/Conversations/YYYY-MM-DD.md).

The vault is any folder the user picks ("vault" in user_settings.json), and their own notes can
live in it too: only the JARVIS folder inside it is touched. Memory.md is the memory itself.
Each top-level line starting with "- " is a fact; every other line is the user's and is left as
it is, so editing the note in Obsidian changes what JARVIS knows.
"""
import datetime
import json
import os
import re
import secrets
import shutil
import subprocess
import sys
import threading
import time
import urllib.parse

import user_settings

HERE = os.path.dirname(os.path.abspath(__file__))
SETTINGS_PATH = user_settings.SETTINGS_PATH
OLD_MEMORY_PATH = os.path.join(HERE, 'memory.json')  # where facts were kept before the vault
DEFAULT_VAULT = os.path.join(os.path.expanduser('~'), 'Documents', 'JARVIS Vault')
FOLDER = 'JARVIS'
MAX_FACTS = 200  # how many go into Claude's instructions; the note itself can hold more
HEADER = ['# What JARVIS remembers', '',
          'JARVIS reads this note at the start of every conversation. Each line starting with "- " is one thing it remembers: add, change or delete lines as you like.',
          '']
FACT = re.compile(r'^[-*] (.*\S)\s*$')  # top level only: indented bullets belong to the user's own notes
_lock = threading.RLock()  # JARVIS and the hub can both write
_warned = set()


def root():
    """The vault folder, read each time so a change made in the hub applies at once."""
    return user_settings.read_settings(SETTINGS_PATH).get('vault') or DEFAULT_VAULT


def folder():
    path = os.path.join(root(), FOLDER)
    os.makedirs(os.path.join(path, 'Conversations'), exist_ok=True)
    return path


def memory_path():
    return os.path.join(folder(), 'Memory.md')


def _read(path):
    """The note's lines, or None if it doesn't exist. utf-8-sig: editors on Windows may add a BOM."""
    try:
        with open(path, encoding='utf-8-sig') as f:
            return f.read().splitlines()
    except FileNotFoundError:
        return None
    except UnicodeDecodeError as error:  # not text JARVIS can safely rewrite: leave the note alone
        raise OSError(f'{os.path.basename(path)} is not UTF-8 text') from error


def _write(path, lines):
    temporary = f'{path}.{os.getpid()}.tmp'  # JARVIS and the hub are separate processes writing the same note
    with open(temporary, 'w', encoding='utf-8', newline='\n') as f:
        f.write(''.join(line + '\n' for line in lines))
    os.replace(temporary, path)  # never left half-written


def _warn(error):
    message = f"The vault can't be written ({error}). Memory changes are not saved."
    if message not in _warned:
        _warned.add(message)
        print(message)


def _one_line(text):
    return ' '.join(str(text).split())


def _fact_rows(lines):
    return [i for i, line in enumerate(lines) if FACT.match(line)]


def _change_memory(change, failed):
    """Runs change(lines) on Memory.md's lines and saves them if they changed."""
    try:
        with _lock:
            path = memory_path()
            lines = _read(path)
            lines = list(HEADER) if lines is None else lines
            before = list(lines)
            result = change(lines)
            if lines != before:
                _write(path, lines)
            return result
    except OSError as error:
        _warn(error)
        return failed


def facts():
    """Every fact, oldest first ([] when the vault can't be read)."""
    try:
        with _lock:
            lines = _read(memory_path()) or []
    except OSError as error:
        _warn(error)
        return []
    return [FACT.match(lines[i]).group(1) for i in _fact_rows(lines)]


def add_fact(text, index=None):
    """Adds a fact at the end, or before the index-th fact (to put back one just deleted)."""
    text = _one_line(text)
    if not text:
        return False

    def change(lines):
        rows = _fact_rows(lines)
        if index is not None and 0 <= int(index) < len(rows):
            lines.insert(rows[int(index)], f'- {text}')
        else:
            lines.append(f'- {text}')
        return True
    return _change_memory(change, False)


def forget_facts(about):
    """Deletes every fact that mentions about (any capitals). Returns how many went."""
    needle = about.strip().lower()
    if not needle:
        return 0

    def change(lines):
        gone = [i for i in _fact_rows(lines) if needle in FACT.match(lines[i]).group(1).lower()]
        for i in reversed(gone):
            del lines[i]
        return len(gone)
    return _change_memory(change, 0)


def _at(lines, index, was):
    """The line number of the index-th fact, if it is still the one the hub showed."""
    rows = _fact_rows(lines)
    if not 0 <= int(index) < len(rows):
        return None
    row = rows[int(index)]
    return row if FACT.match(lines[row]).group(1) == was else None


def edit_fact(index, text, was):
    text = _one_line(text)

    def change(lines):
        row = _at(lines, index, was)
        if row is None or not text:
            return False
        lines[row] = f'- {text}'
        return True
    return _change_memory(change, False)


def delete_fact(index, was):
    def change(lines):
        row = _at(lines, index, was)
        if row is None:
            return False
        del lines[row]
        return True
    return _change_memory(change, False)


# ---- conversations: a readable copy (recall.py searches conversations.jsonl, not these) ----

def _day_path(day):
    return os.path.join(folder(), 'Conversations', f'{day:%Y-%m-%d}.md')


def add_exchange(you, jarvis, when=None):
    """Adds one exchange to the day's note. Never raises: an answer must not fail because of this."""
    when = when or datetime.datetime.now()
    settings = user_settings.read_settings(SETTINGS_PATH)
    user = settings.get('user_name') or 'You'
    assistant = settings.get('assistant_name') or user_settings.DEFAULT_ASSISTANT_NAME
    try:
        with _lock:
            path = _day_path(when)
            lines = _read(path) or [f'# {when:%A} {when.day} {when:%B %Y}', '']
            lines += [f'### {when:%H:%M}', f'**{user}:** {_one_line(you)}',
                      f'**{assistant}:** {_one_line(jarvis)}', '']
            _write(path, lines)
    except OSError as error:
        _warn(error)


def _blocks(lines):
    """(the lines before the first exchange, [each exchange's lines])"""
    head, blocks = [], []
    for line in lines:
        if line.startswith('### '):
            blocks.append([line])
        elif blocks:
            blocks[-1].append(line)
        else:
            head.append(line)
    return head, blocks


def _said(block):
    """What was said in an exchange, without the speakers' names (so forgetting "Jose" doesn't
    match every exchange Jose had)."""
    return ' '.join(line.split(':** ', 1)[-1] for line in block[1:]).lower()


def forget_exchanges(about):
    """Deletes every exchange that mentions about from the day notes. Returns how many went."""
    needle = about.strip().lower()
    if not needle:
        return 0
    removed = 0
    try:
        with _lock:
            notes = os.path.join(folder(), 'Conversations')
            for name in sorted(os.listdir(notes)):
                path = os.path.join(notes, name)
                if not name.endswith('.md') or not os.path.isfile(path):
                    continue
                try:
                    head, blocks = _blocks(_read(path) or [])
                    kept = [block for block in blocks if needle not in _said(block)]
                    if len(kept) == len(blocks):
                        continue
                    if kept:
                        _write(path, head + [line for block in kept for line in block])
                    else:
                        os.remove(path)
                    removed += len(blocks) - len(kept)
                except OSError as error:  # one bad note must not keep the others from being cleaned
                    _warn(error)
    except OSError as error:
        _warn(error)
    return removed


def copy_in_exchanges(items):
    """Adds exchanges from conversations.jsonl that the day notes don't have yet (ones from
    before the vault existed), each in time order. An exchange counts as there when its note has
    the same minute and the same words from the user. Returns how many were added."""
    settings = user_settings.read_settings(SETTINGS_PATH)
    user = settings.get('user_name') or 'You'
    assistant = settings.get('assistant_name') or user_settings.DEFAULT_ASSISTANT_NAME
    by_day = {}
    for item in items:
        try:
            when = datetime.datetime.fromisoformat(item['t'])
        except (KeyError, TypeError, ValueError):
            continue
        by_day.setdefault(when.date(), []).append((when, item))
    added = 0
    try:
        with _lock:
            for day, found in sorted(by_day.items()):
                path = _day_path(day)
                lines = _read(path) or [f'# {day:%A} {day.day} {day:%B %Y}', '']
                head, blocks = _blocks(lines)
                have = {(b[0][4:].strip(), _one_line(b[1].split(':** ', 1)[-1]) if len(b) > 1 else '')
                        for b in blocks}
                new = []
                for when, item in found:
                    you = _one_line(item.get('you', ''))
                    if (f'{when:%H:%M}', you) in have:
                        continue
                    have.add((f'{when:%H:%M}', you))
                    new.append([f'### {when:%H:%M}', f'**{user}:** {you}',
                                f'**{assistant}:** {_one_line(item.get("jarvis", ""))}', ''])
                if not new:
                    continue
                merged = sorted(blocks + new, key=lambda b: b[0][4:].strip())  # stable: same minute keeps its order
                _write(path, head + [line for b in merged for line in (b if b[-1] == '' else b + [''])])
                added += len(new)
    except OSError as error:
        _warn(error)
    return added


# ---- the vault itself ----------------------------------------------------------------------

def _same(a, b):
    return os.path.normcase(os.path.abspath(a)) == os.path.normcase(os.path.abspath(b))


def move_to(new_vault):
    """Moves the JARVIS folder into new_vault. Call it before the setting changes. If new_vault
    already has a JARVIS folder, that one is used and the old one stays where it was."""
    with _lock:
        old = os.path.join(root(), FOLDER)
        new = os.path.join(new_vault, FOLDER)
        if _same(old, new):
            return 'same'
        if os.path.exists(new):
            return 'kept'
        os.makedirs(new_vault, exist_ok=True)
        if os.path.exists(old):
            shutil.move(old, new)
        return 'moved'


def ensure_memory():
    """Creates Memory.md with its header if it isn't there. True when it was just created."""
    try:
        with _lock:
            path = memory_path()
            if os.path.exists(path):
                return False
            _write(path, HEADER)
            return True
    except OSError as error:
        _warn(error)
        return False


def migrate():
    """Moves the facts older versions kept in memory.json into Memory.md, once."""
    try:
        with _lock:
            if not os.path.exists(OLD_MEMORY_PATH) or os.path.exists(memory_path()):
                return False
            with open(OLD_MEMORY_PATH, encoding='utf-8') as f:
                old = json.load(f)
            kept = [_one_line(fact) for fact in old if _one_line(fact)] if isinstance(old, list) else []
            _write(memory_path(), HEADER + [f'- {fact}' for fact in kept])
            os.replace(OLD_MEMORY_PATH, OLD_MEMORY_PATH + '.bak')
            return True
    except (OSError, ValueError) as error:
        print(f'Could not move the old memory into the vault: {error}')
        return False


# ---- Obsidian ------------------------------------------------------------------------------

def obsidian_config_dir():
    """Where Obsidian keeps its list of vaults (obsidian.json)."""
    if sys.platform == 'darwin':
        return os.path.expanduser('~/Library/Application Support/obsidian')
    if sys.platform == 'win32':
        return os.path.join(os.environ.get('APPDATA', ''), 'obsidian')
    return os.path.expanduser('~/.config/obsidian')


def obsidian_installed():
    if sys.platform == 'darwin':
        return any(os.path.isdir(p) for p in ('/Applications/Obsidian.app',
                                               os.path.expanduser('~/Applications/Obsidian.app')))
    if sys.platform == 'win32':
        exe = os.path.join(os.environ.get('LOCALAPPDATA', ''), 'Programs', 'Obsidian', 'Obsidian.exe')
        return os.path.exists(exe) or os.path.isdir(obsidian_config_dir())
    return os.path.isdir(obsidian_config_dir())


def obsidian_running():
    try:
        if sys.platform == 'win32':
            out = subprocess.run(['tasklist', '/FI', 'IMAGENAME eq Obsidian.exe', '/NH'], capture_output=True,
                                 text=True, timeout=10, creationflags=0x08000000).stdout
            return 'obsidian.exe' in out.lower()
        return subprocess.run(['pgrep', '-x', 'Obsidian'], capture_output=True, timeout=10).returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


def register_with_obsidian(config_dir=None):
    """Adds the vault to Obsidian's vault list, so it is there when Obsidian opens. Not while
    Obsidian runs: it rewrites the list when it quits, and the vault would be dropped."""
    if not obsidian_installed():
        return 'no-obsidian'
    config_dir = config_dir or obsidian_config_dir()
    path = os.path.join(config_dir, 'obsidian.json')
    here = os.path.abspath(root())
    try:
        with _lock:
            try:
                with open(path, encoding='utf-8') as f:
                    data = json.load(f)
            except FileNotFoundError:
                data = {}
            vaults = data.setdefault('vaults', {})
            if any(_same(v['path'], here) for v in vaults.values()
                   if isinstance(v, dict) and isinstance(v.get('path'), str)):
                return 'listed'
            if obsidian_running():
                return 'running'
            vaults[secrets.token_hex(8)] = {'path': here, 'ts': int(time.time() * 1000), 'open': True}
            os.makedirs(config_dir, exist_ok=True)
            user_settings.save_json(path, data)
            return 'added'
    except (OSError, ValueError, AttributeError, TypeError) as error:
        print(f"Could not add the vault to Obsidian's list: {error}")
        return 'failed'


def _open_url(url):
    try:
        if sys.platform == 'win32':
            os.startfile(url)
        else:
            # A Mac may not know yet that Obsidian handles obsidian:// links (never launched), so name the app.
            subprocess.Popen(['open', '-a', 'Obsidian', url] if sys.platform == 'darwin' else ['xdg-open', url])
        return True
    except OSError:
        return False


def open_in_obsidian():
    """Opens Memory.md in Obsidian (in its vault)."""
    return _open_url('obsidian://open?path=' + urllib.parse.quote(memory_path()))


def prepare(config_dir=None):
    """At JARVIS's start: the vault is there, older memory is moved in, and Obsidian lists it.
    The first time (Memory.md just made), Obsidian opens on it so the user sees where it is."""
    fresh = migrate() or ensure_memory()
    state = register_with_obsidian(config_dir)
    if state == 'running':
        print('Quit Obsidian and start JARVIS again to add its vault to Obsidian.')
    if fresh and state in ('added', 'listed'):
        open_in_obsidian()
