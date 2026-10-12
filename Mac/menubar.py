"""JARVIS in the Mac menu bar (or the Windows system tray), a push-to-talk hotkey, and
"Start at login".

The menu bar icon shows what JARVIS is doing and offers:
  Open hub           - status and every setting, in a window (hub.py)
  Talk to JARVIS     - same as saying "Hey Jarvis"
  Start at login     - a LaunchAgent starts JARVIS when you log in (no Terminal window)
  Show log           - what JARVIS printed (when started at login)
  Quit JARVIS

The hotkey (Option+Space on a Mac, Ctrl+Alt+J on Windows, where Alt+Space opens every
window's menu; "hotkey" in user_settings.json, pynput format such as "<cmd>+<shift>+j") works
from any app. On a Mac, macOS must allow it first: System Settings > Privacy & Security >
Accessibility (and Input Monitoring), for Terminal or, when started at login, for Python.

On Windows the same menu sits on JARVIS's icon in the system tray (by the clock), and
"Start at login" is an entry in the user's Run key (no console window; output goes to jarvis.log).
"""
import os
import plistlib
import subprocess
import sys
import threading
import traceback

import helpers

IS_MAC = sys.platform == 'darwin'
IS_WINDOWS = sys.platform == 'win32'
HERE = os.path.dirname(os.path.abspath(__file__))
LABEL = 'com.jarvis.assistant'
PLIST = os.path.expanduser(f'~/Library/LaunchAgents/{LABEL}.plist')
LOG = os.path.join(HERE, 'jarvis.log')
DEFAULT_HOTKEY = '<ctrl>+<alt>+j' if IS_WINDOWS else '<alt>+<space>'
ICONS = {'': '◉', 'LISTENING': '◎', 'RECOGNIZING': '◎', 'THINKING': '◌', 'SPEAKING': '◉›',
         'ASKING CLAUDE': '◌'}


def open_hub(_sender=None, _item=None) -> None:
    """Opens the hub (hub.py) as its own program, since its window needs a main thread."""
    hidden = {'creationflags': 0x08000000} if IS_WINDOWS else {}  # no console window
    subprocess.Popen([sys.executable, os.path.join(HERE, 'hub.py')], cwd=HERE, stdin=subprocess.DEVNULL,
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, **hidden)


def pretty(hotkey: str) -> str:
    if IS_WINDOWS:
        names = {'<alt>': 'Alt', '<ctrl>': 'Ctrl', '<shift>': 'Shift', '<cmd>': 'Win', '<space>': 'Space'}
        return '+'.join(names.get(part, part.strip('<>').upper()) for part in hotkey.split('+'))
    names = {'<alt>': '⌥', '<cmd>': '⌘', '<ctrl>': '⌃', '<shift>': '⇧', '<space>': 'Space'}
    return ''.join(names.get(part, part.strip('<>').upper()) for part in hotkey.split('+'))


# ---- start at login ------------------------------------------------------------------------

RUN_KEY = r'Software\Microsoft\Windows\CurrentVersion\Run'
RUN_VALUE = 'JARVIS'


def _windows_login_command() -> str:
    pythonw = os.path.join(os.path.dirname(sys.executable), 'pythonw.exe')  # no console window
    return f'"{pythonw}" -W ignore "{os.path.join(HERE, "jarvis.py")}"'


def login_item_enabled() -> bool:
    if IS_WINDOWS:
        import winreg
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
                winreg.QueryValueEx(key, RUN_VALUE)
            return True
        except OSError:
            return False
    return os.path.exists(PLIST)


def set_login_item(enabled: bool) -> None:
    """Writes or removes the LaunchAgent (Mac) or Run-key entry (Windows); it takes effect at
    the next login."""
    if IS_WINDOWS:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as key:
            if enabled:
                winreg.SetValueEx(key, RUN_VALUE, 0, winreg.REG_SZ, _windows_login_command())
            else:
                try:
                    winreg.DeleteValue(key, RUN_VALUE)
                except OSError:
                    pass
        return
    if not enabled:
        if os.path.exists(PLIST):
            os.remove(PLIST)
        return
    path = os.pathsep.join([os.path.expanduser('~/.local/bin'), '/opt/homebrew/bin', '/usr/local/bin',
                            '/usr/bin', '/bin', '/usr/sbin', '/sbin'])
    agent = {
        'Label': LABEL,
        'ProgramArguments': [sys.executable, '-W', 'ignore', os.path.join(HERE, 'jarvis.py')],
        'WorkingDirectory': HERE,
        'RunAtLoad': True,
        'ProcessType': 'Interactive',
        'EnvironmentVariables': {'PATH': path},
        'StandardOutPath': LOG,
        'StandardErrorPath': LOG,
    }
    os.makedirs(os.path.dirname(PLIST), exist_ok=True)
    with open(PLIST, 'wb') as f:
        plistlib.dump(agent, f)


# ---- hotkey ----------------------------------------------------------------------------------

def _read_keyboard_layout_here() -> None:
    """Reads the Mac's keyboard layout now, on the main thread, and has pynput reuse it.

    pynput reads the layout from its own listener thread. Recent macOS (seen on macOS 27) only
    allows that on the main thread and otherwise stops the whole program on the spot
    ("zsh: trace trap"), which closed JARVIS right after the face check.
    """
    import contextlib
    from pynput._util import darwin as pynput_darwin
    from pynput.keyboard import _darwin as pynput_keyboard
    if threading.current_thread() is not threading.main_thread():
        raise RuntimeError('the hotkey must be started from the main thread')
    with pynput_darwin.keycode_context() as layout:
        pass

    @contextlib.contextmanager
    def same_layout():
        yield layout
    pynput_keyboard.keycode_context = same_layout


def start_hotkey(hotkey: str, pressed):
    """Listens for the hotkey anywhere; returns the listener, or None if it can't run."""
    try:
        from pynput import keyboard
        if IS_MAC:
            _read_keyboard_layout_here()
        listener = keyboard.GlobalHotKeys({hotkey: pressed})
        listener.start()
    except Exception as error:
        print(f'Hotkey {pretty(hotkey)} unavailable ({error}).')
        return None
    if IS_MAC and getattr(listener, 'IS_TRUSTED', True) is False:
        print(f'To use {pretty(hotkey)}, allow this app in System Settings > Privacy & Security > Accessibility.')
    return listener


# ---- the app ---------------------------------------------------------------------------------

def run(main, settings) -> None:
    """Runs main (the conversation) with a menu bar icon and the hotkey. Without the menu
    bar (not a Mac, rumps missing, or "menu_bar": false) main simply runs here."""
    def body():
        try:
            main()
        except SystemExit:
            pass
        except Exception:
            traceback.print_exc()
        finally:
            os._exit(0)  # JARVIS said goodbye (or failed): close everything, the menu bar too

    hotkey = settings.get('hotkey') or DEFAULT_HOTKEY
    start_hotkey(hotkey, lambda: helpers.hearing().trigger())
    if IS_WINDOWS and settings.get('menu_bar') is not False:
        try:
            _run_tray(body, settings, hotkey)
            return
        except ImportError:
            pass  # pystray missing: run without the tray icon
    try:
        import rumps
    except ImportError:
        rumps = None
    if not IS_MAC or rumps is None or settings.get('menu_bar') is False:
        body()
        return

    threading.Thread(target=body, daemon=True).start()
    name = settings.get('assistant_name') or 'JARVIS'
    app = rumps.App(name, title=ICONS[''], quit_button=None)

    def talk(_sender):
        helpers.hearing().trigger()

    def toggle_login(sender):
        set_login_item(not login_item_enabled())
        sender.state = int(login_item_enabled())
        rumps.notification(name, '', f'{name} will start when you log in.' if sender.state
                           else f'{name} will no longer start at login.')

    def show_log(_sender):
        if os.path.exists(LOG):
            subprocess.run(['open', '-a', 'Console', LOG])
        else:
            rumps.alert(name, 'There is no log yet. It is written when JARVIS starts at login.')

    login = rumps.MenuItem('Start at login', callback=toggle_login)
    login.state = int(login_item_enabled())
    app.menu = [rumps.MenuItem('Open hub', callback=open_hub),
                rumps.MenuItem(f'Talk to {name}   {pretty(hotkey)}', callback=talk), None,
                login, rumps.MenuItem('Show log', callback=show_log), None,
                rumps.MenuItem(f'Quit {name}', callback=lambda _sender: os._exit(0))]

    def refresh(_timer):  # show what JARVIS is doing (runs on the main thread)
        app.title = ICONS.get(helpers.STATUS, ICONS[''])
    rumps.Timer(refresh, 0.25).start()
    app.run()
    os._exit(0)


# ---- Windows: the system tray ------------------------------------------------------------

def _tray_image(status: str):
    """JARVIS's tray icon: a lime orb, hollow while idle, solid while it listens or talks."""
    from PIL import Image, ImageDraw
    size = 64
    image = Image.new('RGBA', (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    lime = (209, 254, 23, 255)
    draw.ellipse((6, 6, size - 6, size - 6), outline=lime, width=6)
    if status:
        draw.ellipse((18, 18, size - 18, size - 18), fill=lime)
    return image


def _run_tray(body, settings, hotkey) -> None:
    """Runs the conversation (body) in the background with a tray icon on the main thread."""
    import time
    import pystray
    name = settings.get('assistant_name') or 'JARVIS'

    def talk(_icon, _item):
        helpers.hearing().trigger()

    def toggle_login(icon, _item):
        set_login_item(not login_item_enabled())
        icon.notify(f'{name} will start when you sign in.' if login_item_enabled()
                    else f'{name} will no longer start when you sign in.', name)

    def show_log(_icon, _item):
        if os.path.exists(LOG):
            os.startfile(LOG)

    menu = pystray.Menu(
        pystray.MenuItem('Open hub', open_hub),
        pystray.MenuItem(f'Talk to {name}   {pretty(hotkey)}', talk, default=True),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem('Start when I sign in', toggle_login, checked=lambda _item: login_item_enabled()),
        pystray.MenuItem('Show log', show_log),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem(f'Quit {name}', lambda _icon, _item: os._exit(0)))
    icon = pystray.Icon('jarvis', _tray_image(''), name, menu)

    def refresh():  # show what JARVIS is doing in the icon and its tooltip
        shown = None
        while True:
            status = helpers.STATUS
            if status != shown:
                shown = status
                icon.icon = _tray_image(status)
                icon.title = f'{name}: {status.capitalize()}' if status else f'{name}: say "Hey {name}"'
            time.sleep(0.25)

    threading.Thread(target=body, daemon=True).start()
    threading.Thread(target=refresh, daemon=True).start()
    icon.run()
    os._exit(0)
