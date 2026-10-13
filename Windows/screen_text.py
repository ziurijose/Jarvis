"""The active window's controls as text, for Claude to read instead of a screenshot.

Windows UI Automation (the accessibility interface screen readers use) lists a window's buttons,
fields and links with their names and places. Measured on Calculator and a Gmail inbox, Claude
answered "where do I click?" from this list as accurately as from a screenshot and faster every
time (2.6 s against 3.1 to 3.9 s), even when the list was larger than the image. Windows that
draw their own controls (Voicemeeter, games, videos) list next to nothing, so describe() returns
None for them and look_at_screen takes a screenshot instead. Elsewhere (a Mac) it is always None.
"""
import sys
import threading
import time

import control

MIN_CONTROLS = 5      # fewer and the window draws its own controls: a screenshot shows more
MAX_CHARS = 16000     # measured faster up to about 13,000; past this a screenshot is the safe bet
MAX_SECONDS = 1.0     # reading it usually takes 20 to 200 ms; slower than this, don't wait on it
KINDS = {50000: 'button', 50002: 'checkbox', 50003: 'combobox', 50004: 'edit', 50005: 'link',
         50007: 'listitem', 50011: 'menuitem', 50013: 'radio', 50015: 'slider', 50019: 'tab',
         50024: 'treeitem', 50029: 'item', 50031: 'button'}  # the kinds of control one clicks or types in
NAME, KIND, RECT, OFFSCREEN = 30005, 30003, 30001, 30022  # UI Automation property ids
_local = threading.local()  # COM objects belong to the thread that made them


def _automation():
    if getattr(_local, 'uia', None) is None:
        import comtypes
        import comtypes.client
        comtypes.CoInitialize()
        comtypes.client.GetModule('UIAutomationCore.dll')
        from comtypes.gen import UIAutomationClient as U
        uia = comtypes.client.CreateObject(U.CUIAutomation, interface=U.IUIAutomation)
        cache = uia.CreateCacheRequest()
        for prop in (NAME, KIND, RECT, OFFSCREEN):
            cache.AddProperty(prop)  # fetched in one go, not one call per control
        _local.uia, _local.cache = uia, cache
    return _local.uia, _local.cache


def _read():
    """(the active window's title, its controls as dicts, seconds it took)."""
    if sys.platform != 'win32':
        raise OSError('UI Automation is Windows only')
    import ctypes
    started = time.monotonic()
    uia, cache = _automation()
    window = uia.ElementFromHandle(ctypes.windll.user32.GetForegroundWindow())
    found = window.FindAllBuildCache(4, uia.CreateTrueCondition(), cache)  # 4: every descendant
    controls = []
    for n in range(found.Length):
        e = found.GetElement(n)
        controls.append({'kind': e.GetCachedPropertyValue(KIND), 'name': e.GetCachedPropertyValue(NAME) or '',
                         'rect': tuple(e.GetCachedPropertyValue(RECT)),
                         'offscreen': bool(e.GetCachedPropertyValue(OFFSCREEN))})
    return window.CurrentName or '', controls, time.monotonic() - started


def describe():
    """The active window's controls, one per line with its centre in screenshot pixels, or None
    when a screenshot would serve Claude better (or this isn't Windows)."""
    try:
        title, found, seconds = _read()
    except Exception:  # no UI Automation, or the window closed while it was read
        return None
    rows = []
    for c in found:
        name = ' '.join(str(c['name']).split())[:80]
        if c['kind'] not in KINDS or not name or c['offscreen']:
            continue
        left, top, width, height = c['rect']
        x, y = control.from_screen(left + width / 2, top + height / 2)
        rows.append(f'{KINDS[c["kind"]]} "{name}" at {x},{y}')
    text = '\n'.join([f'Window "{title}", its controls (positions in screenshot pixels):'] + rows)
    if len(rows) < MIN_CONTROLS or len(text) > MAX_CHARS or seconds > MAX_SECONDS:
        return None
    return text
