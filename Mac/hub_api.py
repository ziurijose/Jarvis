"""The hub's Python side: what ui/hub.html calls through window.pywebview.api.

The hub is a separate program from JARVIS. It edits JARVIS's files (user_settings.json) and
reads status.json, which JARVIS rewrites whenever it starts listening, thinking or speaking.
Settings take effect when JARVIS restarts, which the hub does for you.
"""
import json
import os
import subprocess
import sys
import time

import user_settings
import voices
from menubar import login_item_enabled, set_login_item

HERE = os.path.dirname(os.path.abspath(__file__))
IS_WINDOWS = sys.platform == 'win32'
STATUS_PATH = os.path.join(HERE, 'status.json')
MEMORY_PATH = os.path.join(HERE, 'memory.json')  # brain.py's list of facts about the user
MAX_FACTS = 200  # brain.remember keeps the newest 200
THINKING = {'fast': 'low', 'balanced': 'medium', 'deep': 'high'}  # what the hub says -> claude_effort
MODELS = [('', 'Default'), ('claude-opus-5-5', 'Opus 5.5 (smartest)'),
          ('claude-sonnet-5-5', 'Sonnet 5.5 (balanced)'), ('claude-haiku-5-5', 'Haiku 5.5 (fastest)')]
LANGUAGES = [('', "This computer's language"), ('en-US', 'English (US)'), ('en-GB', 'English (UK)'),
             ('es-ES', 'Spanish'), ('fr-FR', 'French'), ('de-DE', 'German'), ('it-IT', 'Italian'),
             ('pt-BR', 'Portuguese (Brazil)')]
# Inputs that aren't a microphone to pick: loopbacks (they hear the computer, not the user)
# and Windows' stand-ins for "the default device", which the empty choice already covers.
NOT_MICROPHONES = ('voicemeeter', 'stereo mix', 'what u hear', 'loopback', 'cable output', 'wave out',
                   'sound mapper', 'primary sound capture')


# ---- JARVIS's process ----------------------------------------------------------------

def process_alive(pid):
    """True if pid is a running Python (so a reused process number isn't mistaken for JARVIS)."""
    import psutil
    try:
        process = psutil.Process(pid)
        return process.is_running() and 'python' in process.name().lower()
    except (psutil.Error, ValueError, TypeError):
        return False


def kill_process(pid):
    """Stops JARVIS and what it started (its on-screen HUD, Claude Code)."""
    import psutil
    try:
        process = psutil.Process(pid)
        family = process.children(recursive=True) + [process]
    except psutil.Error:
        return
    for p in family:
        try:
            p.kill()
        except psutil.Error:
            pass
    psutil.wait_procs(family, timeout=5)


def launch_jarvis():
    """Starts JARVIS with no console window, the way "Start when I sign in" does."""
    script = os.path.join(HERE, 'jarvis.py')
    if IS_WINDOWS:
        pythonw = os.path.join(os.path.dirname(sys.executable), 'pythonw.exe')
        DETACHED_PROCESS, CREATE_NEW_PROCESS_GROUP = 0x00000008, 0x00000200
        subprocess.Popen([pythonw if os.path.exists(pythonw) else sys.executable, '-W', 'ignore', script],
                         cwd=HERE, creationflags=DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP,
                         stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    else:
        subprocess.Popen([sys.executable, '-W', 'ignore', script], cwd=HERE, start_new_session=True,
                         stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def _clean(text):
    return ' '.join(str(text or '').split())


class HubApi:
    """Methods the page calls. Attributes starting with an underscore are hidden from it."""

    def __init__(self, settings_path=user_settings.SETTINGS_PATH, status_path=STATUS_PATH,
                 memory_path=MEMORY_PATH):
        self._settings_path = settings_path
        self._status_path = status_path
        self._memory_path = memory_path
        self._voices = []
        self._window = None

    def _read(self):
        try:
            with open(self._settings_path, encoding='utf-8') as f:
                return json.load(f)
        except (OSError, ValueError):
            return {}

    # ---- settings ----------------------------------------------------------------------

    def load(self):
        """Every setting in the form the page shows."""
        s = self._read()
        effort = s.get('claude_effort') or 'low'
        return {
            'user_name': s.get('user_name', ''),
            'assistant_name': s.get('assistant_name') or user_settings.DEFAULT_ASSISTANT_NAME,
            'voice': s.get('voice') or voices.DEFAULT_VOICE,
            'language': s.get('language', ''),
            'brain': s.get('brain') or 'auto',  # auto (local, Claude Code when needed), local or claude
            'model': s.get('claude_model', ''),
            'thinking': next((k for k, v in THINKING.items() if v == effort), 'fast'),
            'wake_word': s.get('wake_word', True) is not False,
            'barge_in': s.get('barge_in', True) is not False,
            'microphone': s.get('microphone', ''),
            'hotkey': s.get('hotkey', ''),
            'face_lock': s.get('face_lock', True) is not False,
            'face_strictness': int(s.get('face_lock_threshold', 80)),
            'city': s.get('city', ''),
            'menu_bar': s.get('menu_bar', True) is not False,
            'start_at_login': login_item_enabled(),
            'models': MODELS,
            'languages': LANGUAGES,
        }

    def save(self, form):
        """Saves what the page sent; returns {'ok': True} or {'ok': False, 'error': ...}."""
        s = self._read()
        for key, label in (('user_name', 'Your name'), ('assistant_name', 'Its name')):
            if key in form:
                if not _clean(form[key]):
                    return {'ok': False, 'error': f'{label} can\'t be blank.'}
                s[key] = _clean(form[key])[:30]
        if form.get('brain') in ('auto', 'local', 'claude'):
            if form['brain'] == 'auto':
                s.pop('brain', None)  # the default
            else:
                s['brain'] = form['brain']
        if 'thinking' in form:
            s['claude_effort'] = THINKING.get(form['thinking'], 'low')
        if form.get('voice_index') is not None and self._voices:
            s['voice'] = self._voices[int(form['voice_index'])]
        for key in ('wake_word', 'barge_in', 'face_lock', 'menu_bar'):
            if key in form:
                s[key] = bool(form[key])
        if 'face_strictness' in form:
            s['face_lock_threshold'] = min(max(int(form['face_strictness']), 40), 120)
        # Text settings: blank means "the default", which is the setting being absent.
        for form_key, key in (('model', 'claude_model'), ('language', 'language'), ('microphone', 'microphone'),
                              ('hotkey', 'hotkey'), ('city', 'city')):
            if form_key in form:
                value = _clean(form[form_key])
                if value:
                    s[key] = value
                else:
                    s.pop(key, None)
        user_settings.write_settings(s, self._settings_path)  # whole: a cleared setting is removed
        if 'start_at_login' in form and bool(form['start_at_login']) != login_item_enabled():
            set_login_item(bool(form['start_at_login']))
        return {'ok': True}

    # ---- voices and microphones --------------------------------------------------------

    def list_voices(self):
        """The voices to choose from, and which one is chosen now."""
        self._voices = voices.all_voices()
        current = self.load()['voice']
        chosen = next((i for i, v in enumerate(self._voices)
                       if v.get('source') == current.get('source') and v.get('id') == current.get('id')), 0)
        return {'voices': [{'name': v['name'], 'source': v['source']} for v in self._voices], 'chosen': chosen}

    def preview_voice(self, index, user, assistant):
        voice = self._voices[int(index)]
        voices.say_in_background(voice, f"Hello, {_clean(user) or 'there'}. I'm {_clean(assistant) or 'JARVIS'}.",
                                 lambda error: self._push('onPreviewDone', str(error) if error else None))

    def list_microphones(self):
        import sounddevice as sd
        names = []
        for device in sd.query_devices():
            name = device['name']
            if (device['max_input_channels'] > 0 and name not in names
                    and not any(word in name.lower() for word in NOT_MICROPHONES)):
                names.append(name)
        return names

    def _push(self, function, *args):
        try:
            self._window.evaluate_js(f'{function}({", ".join(json.dumps(a) for a in args)})')
        except Exception:
            pass  # the window is closing

    # ---- memory: what JARVIS remembers about the user (it rereads it every conversation) --

    def _facts(self):
        try:
            with open(self._memory_path, encoding='utf-8') as f:
                facts = json.load(f)
            return facts if isinstance(facts, list) else []
        except (OSError, ValueError):
            return []

    def _save_facts(self, facts):
        with open(self._memory_path, 'w', encoding='utf-8') as f:
            json.dump(facts[-MAX_FACTS:], f, indent=1, ensure_ascii=False)

    def list_memory(self):
        return [{'index': i, 'text': str(text)} for i, text in enumerate(self._facts())]

    def add_memory(self, text, index=None):
        """Adds a fact at the end, or at index (to put back one that was just deleted)."""
        text = _clean(text)
        if not text:
            return {'ok': False, 'error': 'Type something for it to remember.'}
        facts = self._facts()
        facts.insert(len(facts) if index is None else min(max(int(index), 0), len(facts)), text)
        self._save_facts(facts)
        return {'ok': True}

    def edit_memory(self, index, text, was):
        """was is the fact as the page showed it: if JARVIS changed the list since, nothing is touched."""
        text = _clean(text)
        facts = self._facts()
        if not text:
            return {'ok': False, 'error': 'A fact can\'t be blank. Delete it instead.'}
        if not 0 <= int(index) < len(facts) or facts[int(index)] != was:
            return {'ok': False, 'error': 'That changed while you were editing. Have another look.'}
        facts[int(index)] = text
        self._save_facts(facts)
        return {'ok': True}

    def delete_memory(self, index, was):
        facts = self._facts()
        if not 0 <= int(index) < len(facts) or facts[int(index)] != was:
            return {'ok': False, 'error': 'That changed in the meantime. Have another look.'}
        del facts[int(index)]
        self._save_facts(facts)
        return {'ok': True}

    # ---- JARVIS itself -----------------------------------------------------------------

    def _pid(self):
        try:
            with open(self._status_path, encoding='utf-8') as f:
                data = json.load(f)
        except (OSError, ValueError):
            return None, {}
        return data.get('pid'), data

    def status(self):
        pid, data = self._pid()
        if not pid or not process_alive(pid):
            return {'running': False, 'status': '', 'brain': ''}
        return {'running': True, 'status': data.get('status', ''), 'brain': data.get('brain', '')}

    def stop(self):
        pid, _data = self._pid()
        if pid and process_alive(pid):
            kill_process(pid)
            for _ in range(50):  # up to 10 seconds
                if not process_alive(pid):
                    break
                time.sleep(0.2)
        return self.status()

    def start(self):
        if not self.status()['running']:
            launch_jarvis()
        return True

    def restart(self):
        """Restarts JARVIS from a separate little process, so closing the hub straight after
        Save can't cut the restart off halfway."""
        hidden = {'creationflags': 0x08000000} if IS_WINDOWS else {'start_new_session': True}
        subprocess.Popen([sys.executable, os.path.abspath(__file__), '--restart'], cwd=HERE,
                         stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, **hidden)
        return True

    def _restart_now(self):
        self.stop()
        launch_jarvis()


if __name__ == '__main__' and sys.argv[1:] == ['--restart']:
    HubApi()._restart_now()
