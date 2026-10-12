"""JARVIS's Windows abilities: apps, browser, music, volume, notes, reminders and email.

The counterpart of mac.py. Where Windows has no general equivalent of a Mac feature
(Calendar, iMessage, Apple Shortcuts), brain.py simply doesn't offer that tool here, so Claude
never promises something JARVIS can't do.

  Apps      - found through the Start menu, so "Spotify" or "Word" work like a person would
              say them, whether the app came from the Microsoft Store or an installer.
  Music     - Windows' media controls (what the volume pop-up's play button uses), so it works
              with Spotify, browsers and anything else that plays.
  Notes     - text files in Documents\\JARVIS Notes.
  Reminders - kept by JARVIS in reminders.json and spoken aloud when due, while it is running.
  Email     - opens a ready-written draft in the default mail app; the user presses Send.
"""
import datetime
import difflib
import json
import os
import re
import subprocess
import threading
import time
import uuid
import webbrowser

HERE = os.path.dirname(os.path.abspath(__file__))
REMINDERS_PATH = os.path.join(HERE, 'reminders.json')
CREATE_NO_WINDOW = 0x08000000  # keeps a console window from flashing up


def _powershell(command: str, timeout: int = 30) -> str:
    out = subprocess.run(['powershell', '-NoProfile', '-NonInteractive', '-Command', command],
                         capture_output=True, text=True, encoding='utf-8', errors='replace',
                         timeout=timeout, creationflags=CREATE_NO_WINDOW)
    return out.stdout


# ---- apps ------------------------------------------------------------------------------

_start_apps = {}


def start_menu_apps(refresh=False) -> dict:
    """Start-menu app names -> AppIDs, for Store apps and installed programs alike."""
    if refresh or not _start_apps:
        listing = _powershell('Get-StartApps | ForEach-Object { $_.Name + "`t" + $_.AppID }')
        _start_apps.clear()
        for line in listing.splitlines():
            name, _, app_id = line.partition('\t')
            if app_id.strip():
                _start_apps[name.strip()] = app_id.strip()
    return _start_apps


def _simple(text: str) -> str:
    return re.sub(r'[^a-z0-9]', '', text.lower())


def find_app(name: str):
    """(Start-menu name, AppID) of the app best matching name, or None."""
    apps = start_menu_apps()
    wanted = _simple(name)
    if not wanted:
        return None
    for exact in apps:                      # "spotify" -> "Spotify"
        if _simple(exact) == wanted:
            return exact, apps[exact]
    starts = [a for a in apps if _simple(a).startswith(wanted)]  # "word" -> "Word"
    if starts:
        best = min(starts, key=len)
        return best, apps[best]
    contains = [a for a in apps if wanted in _simple(a)]          # "chrome" -> "Google Chrome"
    if contains:
        best = min(contains, key=len)
        return best, apps[best]
    close = difflib.get_close_matches(wanted, [_simple(a) for a in apps], n=1, cutoff=0.8)
    if close:
        best = next(a for a in apps if _simple(a) == close[0])
        return best, apps[best]
    return None


def open_app(name: str) -> str:
    found = find_app(name)
    if not found:  # maybe installed since the list was read
        start_menu_apps(refresh=True)
        found = find_app(name)
    if found:
        subprocess.Popen(['explorer.exe', 'shell:AppsFolder\\' + found[1]], creationflags=CREATE_NO_WINDOW)
        return f'Opened {found[0]}.'
    try:
        os.startfile(name)  # e.g. "notepad", "calc", or a full path
        return f'Opened {name}.'
    except OSError:
        raise RuntimeError(f'there is no app called "{name}"')


def quit_app(name: str) -> str:
    """Closes an app politely (like clicking its X), so it can save its work."""
    import psutil
    wanted = _simple(name)
    found = find_app(name)
    names = {wanted} | ({_simple(found[0])} if found else set())
    pids = set()
    for process in psutil.process_iter(['pid', 'name', 'exe']):
        exe_name = _simple(os.path.splitext(process.info['name'] or '')[0])
        if exe_name and any(n and (n == exe_name or n in exe_name or exe_name in n) for n in names):
            pids.add(process.info['pid'])
    if not pids:
        return f'{name} is not running.'
    for pid in pids:
        subprocess.run(['taskkill', '/PID', str(pid)], capture_output=True, creationflags=CREATE_NO_WINDOW)
    return f'Closed {found[0] if found else name}.'


# ---- browser ---------------------------------------------------------------------------

BROWSERS = {
    'chrome': [r'%ProgramFiles%\Google\Chrome\Application\chrome.exe',
               r'%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe',
               r'%LocalAppData%\Google\Chrome\Application\chrome.exe'],
    'edge': [r'%ProgramFiles(x86)%\Microsoft\Edge\Application\msedge.exe',
             r'%ProgramFiles%\Microsoft\Edge\Application\msedge.exe'],
    'firefox': [r'%ProgramFiles%\Mozilla Firefox\firefox.exe',
                r'%ProgramFiles(x86)%\Mozilla Firefox\firefox.exe'],
    'brave': [r'%ProgramFiles%\BraveSoftware\Brave-Browser\Application\brave.exe',
              r'%LocalAppData%\BraveSoftware\Brave-Browser\Application\brave.exe'],
    'opera': [r'%LocalAppData%\Programs\Opera\opera.exe'],
}
BROWSER_NAMES = {'chrome': 'Google Chrome', 'edge': 'Microsoft Edge', 'firefox': 'Firefox',
                 'brave': 'Brave', 'opera': 'Opera'}


def _browser_path(browser: str):
    key = next((k for k in BROWSERS if k in _simple(browser)), None)
    for path in BROWSERS.get(key, []):
        path = os.path.expandvars(path)
        if os.path.isfile(path):
            return key, path
    return key, None


def open_in_browser(url: str, browser: str = '') -> str:
    """Opens url in the browser the user named, else Google Chrome, else the default browser."""
    for choice in ([browser] if browser else []) + ['chrome']:
        key, path = _browser_path(choice)
        if path:
            subprocess.Popen([path, url], creationflags=CREATE_NO_WINDOW)
            return BROWSER_NAMES[key]
    webbrowser.open(url)
    return 'the default browser'


# ---- music and volume --------------------------------------------------------------------

async def _media(action: str):
    from winrt.windows.media.control import (
        GlobalSystemMediaTransportControlsSessionManager as Manager,
        GlobalSystemMediaTransportControlsSessionPlaybackStatus as Status,
    )
    manager = await Manager.request_async()
    sessions = list(manager.get_sessions())
    # Prefer Spotify, then whatever Windows considers current, then anything.
    session = (next((s for s in sessions if 'spotify' in s.source_app_user_model_id.lower()), None)
               or manager.get_current_session() or (sessions[0] if sessions else None))
    if session is None:
        return None
    app = session.source_app_user_model_id.split('!')[-1].split('.')[0] or 'Music'
    if action == 'play':
        if session.get_playback_info().playback_status != Status.PLAYING:
            await session.try_play_async()
    elif action == 'pause':
        await session.try_pause_async()
    elif action == 'next':
        await session.try_skip_next_async()
    elif action == 'previous':
        await session.try_skip_previous_async()
    return app


def music(action: str) -> str:
    """play, pause, next, previous - in whatever is playing (Spotify first). With nothing open,
    "play" starts Spotify (or the first music app installed) and plays it."""
    import asyncio
    app = asyncio.run(_media(action))
    if app:
        return f'{app}: {action}.'
    if action != 'play':
        return 'Nothing is playing.'
    for candidate in ('Spotify', 'Apple Music', 'iTunes', 'Media Player'):
        if find_app(candidate):
            open_app(candidate)
            for _ in range(40):  # the app registers with Windows' media controls once it has loaded
                time.sleep(0.5)
                app = asyncio.run(_media('play'))
                if app:
                    return f'{app}: playing.'
            return f'Opened {candidate}; press play there.'
    return 'No music app found. Install Spotify, or open a song in the browser.'


def _speaker_volume():
    from pycaw.pycaw import AudioUtilities
    return AudioUtilities.GetSpeakers().EndpointVolume


def set_volume(percent: int) -> str:
    level = max(0, min(100, int(percent)))
    volume = _speaker_volume()
    volume.SetMute(0, None)
    volume.SetMasterVolumeLevelScalar(level / 100, None)
    return f'Volume set to {level} percent.'


# ---- notes -----------------------------------------------------------------------------

def _documents_folder() -> str:
    import ctypes
    folder_id = uuid.UUID('{FDD39AD0-238F-46AF-ADB4-6C85480369C7}')  # FOLDERID_Documents
    guid = (ctypes.c_byte * 16).from_buffer_copy(folder_id.bytes_le)
    path_ptr = ctypes.c_wchar_p()
    if ctypes.windll.shell32.SHGetKnownFolderPath(guid, 0, None, ctypes.byref(path_ptr)) == 0:
        path = path_ptr.value
        ctypes.windll.ole32.CoTaskMemFree(path_ptr)
        return path
    return os.path.join(os.path.expanduser('~'), 'Documents')


def notes_folder() -> str:
    return os.path.join(_documents_folder(), 'JARVIS Notes')


def add_note(title: str, body: str = '') -> str:
    folder = notes_folder()
    os.makedirs(folder, exist_ok=True)
    safe = re.sub(r'[<>:"/\\|?*]+', '', title).strip()[:80] or 'Note'
    path = os.path.join(folder, f'{safe}.txt')
    stamp = datetime.datetime.now().strftime('%Y-%m-%d %H:%M')
    with open(path, 'a', encoding='utf-8') as f:
        if f.tell():
            f.write('\n\n')
        f.write(f'{title}\n{stamp}\n\n{body}'.rstrip() + '\n')
    return f'Saved the note "{title}" in Documents, JARVIS Notes.'


# ---- reminders -------------------------------------------------------------------------

_reminders_lock = threading.Lock()


def _load_reminders() -> list:
    try:
        with open(REMINDERS_PATH, encoding='utf-8') as f:
            return json.load(f)
    except (OSError, ValueError):
        return []


def _save_reminders(items: list) -> None:
    with open(REMINDERS_PATH, 'w', encoding='utf-8') as f:
        json.dump(items, f, indent=1)


def _parse_when(text: str) -> datetime.datetime:
    try:
        return datetime.datetime.fromisoformat(text.strip().replace('Z', ''))
    except ValueError:
        raise ValueError(f'Give the time as ISO 8601, e.g. 2026-10-09T15:00 (got "{text}").')


def add_reminder(text: str, due: str = '', list_name: str = '') -> str:
    when = _parse_when(due) if due else None
    with _reminders_lock:
        items = _load_reminders()
        items.append({'text': text.strip(), 'due': when.isoformat(timespec='minutes') if when else None,
                      'list': list_name or '', 'done': False, 'alerted': False})
        _save_reminders(items)
    if when:
        return f'Reminder set for {when:%a %d %b at %H:%M}. I\'ll say it then, as long as I\'m running.'
    return 'Reminder added.'


def list_reminders(list_name: str = '') -> str:
    items = [r for r in _load_reminders() if not r.get('done')
             and (not list_name or r.get('list', '').lower() == list_name.lower())]
    if not items:
        return 'No open reminders.'
    lines = []
    for r in items:
        due = f" (due {_parse_when(r['due']):%a %d %b %H:%M})" if r.get('due') else ''
        lines.append(r['text'] + due)
    return '\n'.join(lines)


def complete_reminder(text: str) -> str:
    with _reminders_lock:
        items = _load_reminders()
        hits = [r for r in items if not r.get('done') and text.lower() in r['text'].lower()]
        for r in hits:
            r['done'] = True
        _save_reminders(items)
    return f'Marked {len(hits)} reminder(s) done.'


def due_reminders() -> list:
    """Reminders whose time has come and that haven't been announced yet; marks them announced."""
    now = datetime.datetime.now()
    with _reminders_lock:
        items = _load_reminders()
        due = [r for r in items if r.get('due') and not r.get('done') and not r.get('alerted')
               and _parse_when(r['due']) <= now]
        for r in due:
            r['alerted'] = True
        if due:
            _save_reminders(items)
    return [r['text'] for r in due]


def watch_reminders(announce, every: float = 20.0) -> None:
    """Calls announce(text) for each reminder as it comes due (runs in the background)."""
    def loop():
        while True:
            try:
                for text in due_reminders():
                    announce(text)
            except Exception as error:
                print(f'Reminder check failed: {error}')
            time.sleep(every)
    threading.Thread(target=loop, daemon=True).start()


# ---- email -----------------------------------------------------------------------------

def draft_email(to: str, subject: str, body: str) -> str:
    """Opens a new email in the default mail app with everything filled in. Nothing is sent:
    the user reads it and presses Send themselves."""
    from urllib.parse import quote
    if '@' not in to:
        return f'I need {to}\'s email address to write to them. Ask the user for it.'
    os.startfile(f'mailto:{quote(to.strip())}?subject={quote(subject)}&body={quote(body)}')
    return f'The email to {to} is open in the mail app, ready for the user to check and send.'
