"""The mouse and keyboard, for JARVIS to use by voice ("click Send", "press enter", "scroll down").

Claude picks places on the screenshots look_at_screen gives it. Those are at most SHOT_WIDTH
pixels wide, so every coordinate here is in screenshot pixels and is scaled to the real
screen before the mouse moves (this also covers Windows display scaling and Retina screens).

Emergency stop: push the mouse into a corner of the screen. The next action raises Stopped,
and anything JARVIS was holding down is let go.
"""
import ctypes
import functools
import io
import sys
import time

import pyperclip

IS_MAC = sys.platform == 'darwin'
IS_WINDOWS = sys.platform == 'win32'
SHOT_WIDTH = 1280   # look_at_screen's width; Claude Code reads it at full size, so clicks land true
MAX_SECONDS = 30    # longest wait or hold, so JARVIS never sits frozen
BUTTONS = ('left', 'right', 'middle')
KEY_ALIASES = {'control': 'ctrl', 'return': 'enter', 'escape': 'esc', 'del': 'delete', 'spacebar': 'space',
               'option': 'alt', 'pgup': 'pageup', 'pgdn': 'pagedown', 'page up': 'pageup',
               'page down': 'pagedown', 'arrowup': 'up', 'arrowdown': 'down', 'arrowleft': 'left',
               'arrowright': 'right', 'plus': '+', 'caps lock': 'capslock', 'print screen': 'printscreen'}
SYSTEM_KEYS = ('win', 'windows', 'super', 'meta', 'cmd', 'command')
# Keys Windows must be told are "extended": pyautogui sends them without that flag, so they
# arrive as number-pad keys, and with Num Lock on Windows then cancels Shift (shift+home
# moved the cursor without selecting anything).
EXTENDED_KEYS = {'up', 'down', 'left', 'right', 'home', 'end', 'pageup', 'pagedown', 'pgup', 'pgdn',
                 'insert', 'delete', 'del', 'divide', 'numlock', 'apps', 'win', 'winleft', 'winright',
                 'ctrlright', 'altright', 'printscreen', 'prntscrn', 'prtsc', 'prtscr'}

_shot_size = None   # (width, height) of the last full screenshot
_held_keys = []
_held_buttons = []


class Stopped(Exception):
    """The user pushed the mouse into a screen corner to stop JARVIS."""


ACTION_PAUSE = 0.03  # after each mouse or key action; pyautogui's own 0.1 s made seven clicks take 0.7 s


def _gui():
    import pyautogui
    pyautogui.PAUSE = ACTION_PAUSE
    return pyautogui


def _action(func):
    """Lets go of everything on any failure, and turns the corner stop into Stopped."""
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except Exception as error:
            release_all()
            if isinstance(error, _gui().FailSafeException):
                raise Stopped('Stopped: the user pushed the mouse into a screen corner. Stop the task '
                              'and tell them you stopped.') from None
            raise
    return wrapper


def release_all():
    """Lets go of every key and mouse button JARVIS is holding down."""
    if not _held_keys and not _held_buttons:
        return  # the usual case; also spares loading pyautogui after every request
    gui = _gui()
    old, gui.FAILSAFE = gui.FAILSAFE, False  # letting go must work even with the mouse in a corner
    try:
        while _held_keys:
            _key_up(_held_keys.pop())
        while _held_buttons:
            gui.mouseUp(button=_held_buttons.pop())
    finally:
        gui.FAILSAFE = old


# ---- coordinates -------------------------------------------------------------------------

def _shot_of(width, height):
    w = min(width, SHOT_WIDTH)
    return w, round(height * w / width)


def _scale():
    """(real screen size, screenshot size) for converting between them."""
    screen = tuple(_gui().size())
    return screen, _shot_size or _shot_of(*screen)


def _to_screen(x, y):
    (w, h), (sw, sh) = _scale()
    x = min(max(round(float(x) * w / sw), 0), w - 1)
    y = min(max(round(float(y) * h / sh), 0), h - 1)
    if x in (0, w - 1) and y in (0, h - 1):  # an exact corner would trip the emergency stop
        x, y = (1 if x == 0 else w - 2), (1 if y == 0 else h - 2)
    return x, y


def from_screen(x, y):
    """A real screen position in screenshot pixels (the other way round from _to_screen)."""
    (w, h), (sw, sh) = _scale()
    return round(float(x) * sw / w), round(float(y) * sh / h)


def screenshot_png(region=None):
    """The screen as PNG bytes and its (width, height). With region [x0, y0, x1, y1] in
    screenshot pixels, that area at full detail instead (for reading small text)."""
    global _shot_size
    gui = _gui()
    image = gui.screenshot()
    shot = _shot_of(image.width, image.height)
    if region:
        base = _shot_size or shot
        f = image.width / base[0]
        x0, y0, x1, y1 = (round(float(v) * f) for v in region)
        image = image.crop((min(x0, x1), min(y0, y1), max(x0, x1), max(y0, y1)))
        if image.width > SHOT_WIDTH:
            image = image.resize(_shot_of(image.width, image.height))
    else:
        _shot_size = shot
        image = image.resize(shot) if shot != image.size else image
    buffer = io.BytesIO()
    image.convert('RGB').save(buffer, 'PNG')
    return buffer.getvalue(), image.size


# ---- keys --------------------------------------------------------------------------------

def _keys(combo):
    """'Control+Return' -> ['ctrl', 'enter']; unknown key names are an error."""
    gui = _gui()
    keys = []
    for part in str(combo).split('+') if combo != '+' else ['+']:
        key = KEY_ALIASES.get(part.strip().lower(), part.strip().lower())
        if key in SYSTEM_KEYS:
            key = 'command' if IS_MAC else 'win'
        if key == '' and part:
            key = ' '
        keys.append(key)
    unknown = [k for k in keys if k not in gui.KEYBOARD_KEYS and k != 'space']
    if unknown or not keys:
        raise ValueError(f'Unknown key name {", ".join(unknown) or combo!r}. Use names like enter, esc, '
                         'tab, ctrl, shift, alt, win, f5, up, pageup, a, joined with + for combos.')
    return ['space' if k == ' ' else k for k in keys]


def _windows_extended_key(key, up):
    KEYEVENTF_EXTENDEDKEY, KEYEVENTF_KEYUP = 0x1, 0x2
    gui = _gui()
    gui.failSafeCheck()
    vk = gui.platformModule.keyboardMapping[key] % 0x100
    scan = ctypes.windll.user32.MapVirtualKeyW(vk, 0)
    ctypes.windll.user32.keybd_event(vk, scan, KEYEVENTF_EXTENDEDKEY | (KEYEVENTF_KEYUP if up else 0), 0)


def _key_down(key):
    if IS_WINDOWS and key in EXTENDED_KEYS:
        _windows_extended_key(key, False)
    else:
        _gui().keyDown(key)


def _key_up(key):
    if IS_WINDOWS and key in EXTENDED_KEYS:
        _windows_extended_key(key, True)
    else:
        _gui().keyUp(key)


def _button(button):
    if button not in BUTTONS:
        raise ValueError(f'button must be one of {", ".join(BUTTONS)}.')
    return button


def _press_modifiers(hold):
    keys = _keys(hold) if hold else []
    for key in keys:
        _key_down(key)
    return keys


def _let_go(keys):
    for key in reversed(keys):
        _key_up(key)


def _seconds(seconds):
    return min(max(float(seconds or 0), 0), MAX_SECONDS)


# ---- the tools ---------------------------------------------------------------------------

@_action
def move_mouse(x, y, seconds=0):
    sx, sy = _to_screen(x, y)
    _gui().moveTo(sx, sy, duration=_seconds(seconds))
    return f'Pointer moved to {x}, {y}.'


@_action
def click(x=None, y=None, button='left', clicks=1, hold=''):
    _button(button)
    clicks = min(max(int(clicks), 1), 3)
    keys = _press_modifiers(hold)
    try:
        where = {}
        if x is not None and y is not None:
            where['x'], where['y'] = _to_screen(x, y)
        _gui().click(**where, clicks=clicks, button=button)
    finally:
        _let_go(keys)
    return 'Clicked.'


@_action
def mouse_down(button='left', x=None, y=None):
    _button(button)
    if x is not None and y is not None:
        _gui().moveTo(*_to_screen(x, y))
    _gui().mouseDown(button=button)
    if button not in _held_buttons:
        _held_buttons.append(button)
    return f'Holding the {button} button.'


@_action
def mouse_up(button='left', x=None, y=None):
    _button(button)
    if x is not None and y is not None:
        _gui().moveTo(*_to_screen(x, y))
    _gui().mouseUp(button=button)
    if button in _held_buttons:
        _held_buttons.remove(button)
    return f'Let go of the {button} button.'


@_action
def drag(from_x, from_y, to_x, to_y, button='left', hold='', seconds=0.5):
    _button(button)
    gui = _gui()
    gui.moveTo(*_to_screen(from_x, from_y))
    keys = _press_modifiers(hold)
    try:
        # Too quick a drag looks like a click to many apps.
        gui.dragTo(*_to_screen(to_x, to_y), duration=max(_seconds(seconds), 0.2), button=button)
    finally:
        _let_go(keys)
    return 'Dragged.'


def _windows_wheel(amount, horizontal):
    MOUSEEVENTF_WHEEL, MOUSEEVENTF_HWHEEL = 0x0800, 0x1000
    ctypes.windll.user32.mouse_event(MOUSEEVENTF_HWHEEL if horizontal else MOUSEEVENTF_WHEEL, 0, 0,
                                     ctypes.c_int(amount), 0)


@_action
def scroll(direction, amount=3, x=None, y=None, hold=''):
    if direction not in ('up', 'down', 'left', 'right'):
        raise ValueError('direction must be up, down, left or right.')
    amount = min(max(int(amount), 1), 50)
    signed = amount if direction in ('up', 'right') else -amount
    horizontal = direction in ('left', 'right')
    gui = _gui()
    if x is not None and y is not None:
        gui.moveTo(*_to_screen(x, y))
    keys = _press_modifiers(hold)
    try:
        if IS_WINDOWS:
            # pyautogui sends 1/120 of a notch per click on Windows, and its hscroll scrolls
            # vertically. One event per notch, as a real wheel does: apps such as Notepad count
            # one big event as a single notch.
            gui.failSafeCheck()
            for _ in range(amount):
                _windows_wheel(120 if signed > 0 else -120, horizontal)
                time.sleep(0.02)
        elif horizontal:
            gui.hscroll(signed)
        else:
            gui.scroll(signed)
    finally:
        _let_go(keys)
    return f'Scrolled {direction}.'


@_action
def cursor_position():
    (w, h), (sw, sh) = _scale()
    x, y = _gui().position()
    return f'The pointer is at {round(x * sw / w)}, {round(y * sh / h)} on the screenshot.'


@_action
def type_text(text):
    text = str(text)
    if text.isascii() and all(c.isprintable() or c in '\n\t' for c in text):
        _gui().write(text, interval=0.01)
    else:  # pyautogui can only type keys on the keyboard; anything else goes in by pasting
        try:
            old = pyperclip.paste()
        except Exception:
            old = ''
        pyperclip.copy(text)
        _gui().hotkey('command' if IS_MAC else 'ctrl', 'v')
        time.sleep(0.3)  # let the app read the clipboard before it is put back
        pyperclip.copy(old)
    return 'Typed.'


@_action
def press_keys(keys, times=1):
    combo = _keys(keys)
    for _ in range(min(max(int(times), 1), 100)):
        for key in combo:
            _key_down(key)
        for key in reversed(combo):
            _key_up(key)
    return f'Pressed {keys}.'


@_action
def key_down(keys):
    for key in _keys(keys):
        _key_down(key)
        if key not in _held_keys:
            _held_keys.append(key)
    return f'Holding {keys}.'


@_action
def key_up(keys):
    for key in reversed(_keys(keys)):
        _key_up(key)
        if key in _held_keys:
            _held_keys.remove(key)
    return f'Let go of {keys}.'


@_action
def hold_keys(keys, seconds=1):
    combo = _keys(keys)
    for key in combo:
        _key_down(key)
    try:
        time.sleep(_seconds(seconds))
    finally:
        _let_go(combo)
    return f'Held {keys}.'


def wait(seconds=1):
    time.sleep(_seconds(seconds))
    return 'Waited.'


# ---- waiting for the screen to settle ------------------------------------------------------

POLL = 0.15          # seconds between looks; a look costs about 30 ms
SETTLED = 0.5        # still this long after a change: the app or page has finished drawing
UNCHANGED = 1.5      # nothing changed for this long: it was already done
CHANGED_SHARE = 0.02  # a frame differs when over 2% of it changed; a blinking cursor or a spinner is less


def _thumbnail():
    return _gui().screenshot().convert('L').resize((160, 90))


def _differs(a, b):
    from PIL import ImageChops
    changed = sum(ImageChops.difference(a, b).point(lambda v: 255 if v > 24 else 0).histogram()[255:])
    return changed > CHANGED_SHARE * a.width * a.height


def wait_for_screen(seconds, stop, grab=None, differs=None, now=time.monotonic):
    """Waits until the screen settles (an app opened, a page loaded), at most seconds, instead
    of a fixed guess. stop: an Event set when the user talks."""
    grab, differs = grab or _thumbnail, differs or _differs
    started = now()
    last, still_since, changed = grab(), started, False
    while now() - started < seconds:
        if stop.wait(POLL):
            return 'Stopped waiting: the user started talking.'
        frame = grab()
        if differs(frame, last):
            changed, still_since = True, now()
        last = frame
        if now() - still_since >= (SETTLED if changed else UNCHANGED):
            took = now() - started
            return (f'The screen changed and settled after {took:.1f}s.' if changed
                    else f'Nothing changed on screen in {took:.1f}s.')
    return f'Waited {seconds:g}s; the screen was still changing.'
