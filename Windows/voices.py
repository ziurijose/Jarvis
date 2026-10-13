"""The assistant's voice.

By default JARVIS speaks with Kokoro, a small neural voice model that runs on this computer:
it sounds like a person, needs no internet, and starts talking in a fraction of a second,
because each sentence plays while the next one is being generated. Voicebox voices (when
that app is running) can be chosen instead. If Kokoro isn't installed, JARVIS uses the
best voice the computer has: on a Mac, a Premium or Enhanced voice if one is installed.

A chosen voice is stored in user_settings.json as {'source', 'id', 'name', 'language'}:
  source 'kokoro'   -> id is a Kokoro voice, e.g. 'bm_george'
  source 'voicebox' -> id is a Voicebox profile id, spoken via its local REST API
  source 'system'   -> id is a pyttsx3 voice id (only offered when Kokoro is missing)
"""
import io
import os
import queue
import re
import subprocess
import sys
import threading
import urllib.request
import wave
from concurrent.futures import ThreadPoolExecutor

import requests

import playback

VOICEBOX_URL = 'http://127.0.0.1:17493'  # Voicebox's fixed local API address
IS_MAC = sys.platform == 'darwin'

MODELS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'models')
KOKORO_RELEASE = 'https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/'
KOKORO_MODEL = os.path.join(MODELS_DIR, 'kokoro-v1.0.onnx')
KOKORO_VOICE_FILE = os.path.join(MODELS_DIR, 'voices-v1.0.bin')
SPEED = 1.1  # a touch quicker than Kokoro's default, still natural

# (id, name shown in setup, accent). George first: the default, a calm British butler.
KOKORO_VOICES = [('bm_george', 'George', 'en-gb'), ('bm_lewis', 'Lewis', 'en-gb'),
                 ('bm_daniel', 'Daniel', 'en-gb'), ('bf_emma', 'Emma', 'en-gb'),
                 ('bf_isabella', 'Isabella', 'en-gb'), ('am_michael', 'Michael', 'en-us'),
                 ('am_adam', 'Adam', 'en-us'), ('am_onyx', 'Onyx', 'en-us'),
                 ('af_heart', 'Heart', 'en-us'), ('af_bella', 'Bella', 'en-us'),
                 ('af_nicole', 'Nicole', 'en-us'), ('af_sarah', 'Sarah', 'en-us')]
DEFAULT_VOICE = {'source': 'kokoro', 'id': KOKORO_VOICES[0][0], 'name': KOKORO_VOICES[0][1],
                 'language': KOKORO_VOICES[0][2]}


# ---- Kokoro --------------------------------------------------------------------------

_kokoro = None
_kokoro_error = None
_kokoro_lock = threading.Lock()
_generator = ThreadPoolExecutor(max_workers=1)


def kokoro_installed() -> bool:
    if not (os.path.exists(KOKORO_MODEL) and os.path.exists(KOKORO_VOICE_FILE)):
        return False
    try:
        import kokoro_onnx  # noqa: F401
        return True
    except ImportError:
        return False


def _kokoro_engine():
    """The loaded Kokoro model, or None if it can't run here."""
    global _kokoro, _kokoro_error
    with _kokoro_lock:
        if _kokoro is None and _kokoro_error is None:
            if not kokoro_installed():
                _kokoro_error = 'not installed'
            else:
                try:
                    import onnxruntime as rt
                    from kokoro_onnx import Kokoro
                    # Leave a core free so listening (the wake word) keeps up while JARVIS talks.
                    options = rt.SessionOptions()
                    options.intra_op_num_threads = max(1, (os.cpu_count() or 2) - 1)
                    session = rt.InferenceSession(KOKORO_MODEL, options, providers=['CPUExecutionProvider'])
                    _kokoro = Kokoro.from_session(session, KOKORO_VOICE_FILE)
                except Exception as error:
                    _kokoro_error = str(error)
                    print(f'The natural voice could not start ({error}); using the built-in voice.')
        return _kokoro


def warm_up() -> None:
    """Load Kokoro in the background so the first sentence is quick."""
    def work():
        engine = _kokoro_engine()
        if engine:
            _synthesize(engine, DEFAULT_VOICE, 'Hello.')
    threading.Thread(target=work, daemon=True).start()


def sentences(text: str) -> list:
    """Short pieces to speak one by one: the first is ready quickly, the rest are made while
    it plays. Long sentences are split at commas so no piece takes long to generate."""
    pieces = []
    for sentence in re.split(r'(?<=[.!?;:])\s+|\n+', text.strip()):
        while len(sentence) > 220 and ', ' in sentence[60:220]:
            cut = sentence.rindex(', ', 60, 220) + 1
            pieces.append(sentence[:cut])
            sentence = sentence[cut:].strip()
        if sentence.strip():
            pieces.append(sentence.strip())
    return pieces


# A clock time such as 3:08 or 10:30, and the am/pm after it if there is one.
CLOCK = re.compile(r'(?<![\d:])(\d{1,2}):([0-5]\d)(?![\d:])(?=(\s?[AaPp]\.?[Mm]\b)?)')


def _clock(match):
    hour, minute, meridiem = match.groups()
    if minute == '00':
        return hour if meridiem else f"{hour} o'clock"
    return f'{hour} oh {minute[1]}' if minute[0] == '0' else f'{hour} {minute}'


def _synthesize(engine, voice, text):
    # Kokoro's phonemizer reads "3:08" as "three, zero eight" (the colon becomes a pause),
    # so clock times are written the way people say them: "3 oh 8", "10 30", "3 o'clock".
    text = CLOCK.sub(_clock, text)
    with _kokoro_lock:  # one generation at a time; onnxruntime already uses every core
        return engine.create(text, voice=voice['id'], speed=SPEED, lang=voice.get('language') or 'en-us')


def kokoro_say(voice: dict, text: str) -> None:
    """Speak with Kokoro, playing each sentence while the next is generated. Raises if
    Kokoro is unavailable."""
    engine = _kokoro_engine()
    if engine is None:
        raise RuntimeError(f'Kokoro is unavailable ({_kokoro_error})')
    pieces = sentences(text)
    if not pieces:
        return
    pending = _generator.submit(_synthesize, engine, voice, pieces[0])
    for following in pieces[1:] + [None]:
        samples, rate = pending.result()
        if following:
            pending = _generator.submit(_synthesize, engine, voice, following)
        playback.play(samples, rate)  # waits until finished so JARVIS never listens to itself


def download_kokoro(progress=print) -> None:
    """Fetch Kokoro's model (about 330 MB) into models/. Setup runs this once."""
    os.makedirs(MODELS_DIR, exist_ok=True)
    for path in (KOKORO_VOICE_FILE, KOKORO_MODEL):
        if os.path.exists(path):
            continue
        progress(f'Downloading {os.path.basename(path)}...')
        partial = path + '.part'
        urllib.request.urlretrieve(KOKORO_RELEASE + os.path.basename(path), partial)
        os.replace(partial, path)
    progress('Natural voice ready.')


def kokoro_voices() -> list:
    if not kokoro_installed():
        return []
    return [{'source': 'kokoro', 'id': vid, 'name': f'{name} ({"British" if lang == "en-gb" else "American"})',
             'language': lang} for vid, name, lang in KOKORO_VOICES]


class Speech:
    """Speaks text as it arrives, sentence by sentence: while one sentence plays, the next is
    being generated, so a long answer starts as soon as its first sentence is written.
    stop() silences it at once (used when the user interrupts)."""

    def __init__(self, voice=None, on_piece=None):
        self.voice = voice
        self.on_piece = on_piece  # called with each piece of text as it starts playing
        self.pending = ''
        self.queued = False  # whether any text has been queued to speak yet
        self.sentences = queue.Queue()
        self.ready = queue.Queue(maxsize=2)
        self.stopped = threading.Event()
        self.spoke = False
        self._process = None
        self._maker = threading.Thread(target=self._make, daemon=True)
        self._player = threading.Thread(target=self._play, daemon=True)
        self._maker.start()
        self._player.start()

    def feed(self, text: str) -> None:
        self.pending += text
        while True:
            # The first piece may end at a comma, so the voice starts sooner.
            ends = r'[.!?;:,](?=\s)|\n' if not self.queued else r'[.!?;:](?=\s)|\n'
            # Tiny pieces ("Sure.") stay with what follows: cut at the first end past them.
            match = next((m for m in re.finditer(ends, self.pending)
                          if m.end() >= 25 or '\n' in self.pending[:m.end()]), None)
            if not match:
                break
            self._queue(self.pending[:match.end()])
            self.pending = self.pending[match.end():]

    def flush(self) -> None:
        """Says what is held back (a short or unfinished-looking last sentence) now."""
        self.feed('\n')

    def finish(self) -> None:
        self._queue(self.pending)
        self.pending = ''
        self.sentences.put(None)

    def say(self, text: str) -> None:
        self.feed(text)
        self.finish()
        self.wait()

    def _queue(self, text):
        text = speakable(text)
        if text:
            self.queued = True
            for piece in sentences(text):
                self.sentences.put(piece)

    def stop(self) -> None:
        self.stopped.set()
        self.sentences.put(None)  # wakes the generator if it is waiting for text
        try:
            self.ready.put_nowait(None)  # wakes the player if it is waiting for a sentence
        except queue.Full:
            pass  # it has sentences waiting, so it isn't blocked, and sees stopped next
        playback.stop()
        if self._process and self._process.poll() is None:
            self._process.terminate()

    def wait(self) -> None:
        self._player.join()

    # Generating (one thread) and playing (another) run side by side.
    def _make(self):
        voice = self.voice if self.voice and self.voice.get('source') == 'kokoro' else DEFAULT_VOICE
        engine = None if (self.voice or {}).get('source') == 'voicebox' else _kokoro_engine()
        while True:
            text = self.sentences.get()
            if text is None or self.stopped.is_set():
                self._hand_over(None)
                return
            item = ('text', text)
            if engine is not None:
                try:
                    item = ('pcm',) + tuple(_synthesize(engine, voice, text)) + (text,)
                except Exception as error:
                    print(f'The natural voice failed ({error}).')
            if not self._hand_over(item):
                return

    def _hand_over(self, item) -> bool:
        """Passes item to the player; False if speech was stopped first (the player has quit,
        so nothing would ever take it)."""
        while not self.stopped.is_set():
            try:
                self.ready.put(item, timeout=0.1)
                return True
            except queue.Full:
                pass
        return False

    def _play(self):
        import time
        while True:
            item = self.ready.get()
            if item is None or self.stopped.is_set():
                return
            self.spoke = True
            if self.on_piece:
                try:
                    self.on_piece(item[-1] if item[0] == 'text' else item[3])
                except Exception:
                    pass
            if item[0] == 'pcm':
                playback.play(item[1], item[2], stopped=self.stopped)
            elif self.voice and self.voice.get('source') == 'voicebox':
                try:
                    voicebox_say(self.voice, item[1])
                except (requests.RequestException, RuntimeError):
                    self.voice = None
            elif IS_MAC:
                voice = best_mac_voice()
                self._process = subprocess.Popen(say_command(voice, item[1]))
                while self._process.poll() is None and not self.stopped.is_set():
                    time.sleep(0.03)
            else:
                say_isolated({'source': 'system'} if not self.voice else self.voice, item[1])


def say_command(voice, text: str) -> list:
    """The Mac's say command for text. Text starting with "-" gets a space in front, so say
    reads it aloud instead of taking it as an option (such as -o, which writes a file)."""
    return ['say'] + (['-v', voice] if voice else []) + ['-r', '195', ' ' + text if text.startswith('-') else text]


def speakable(text: str) -> str:
    """Text as it should be spoken: no markdown symbols or web addresses."""
    text = re.sub(r'https?://\S+', '', text)
    text = re.sub(r'[*_#`>|]+', '', text)
    return re.sub(r'[ \t]+', ' ', text).strip()


# ---- the Mac's own voices --------------------------------------------------------------

_mac_voice = []


def best_mac_voice():
    """The most natural English voice installed on this Mac: Premium, then Enhanced, else None
    (the system voice). Premium voices are added in System Settings > Accessibility >
    Spoken Content > System voice > Manage Voices."""
    if not _mac_voice:
        best, best_rank = None, 0
        try:
            listing = subprocess.run(['say', '-v', '?'], capture_output=True, text=True, timeout=5).stdout
        except (OSError, subprocess.SubprocessError):
            listing = ''
        for line in listing.splitlines():
            match = re.match(r'(.+?)\s{2,}(en_[A-Z]{2})\s', line)
            if not match:
                continue
            name = match.group(1).strip()
            rank = 3 if '(Premium)' in name else 2 if '(Enhanced)' in name else 0
            if rank > best_rank:
                best, best_rank = name, rank
        _mac_voice.append(best)
    return _mac_voice[0]


def mac_say(text: str) -> None:
    voice = best_mac_voice()
    subprocess.run(say_command(voice, text))


# ---- listing -------------------------------------------------------------------------

def voicebox_voices(timeout: float = 1.5) -> list:
    """Voice profiles from a running Voicebox app; empty if it isn't running."""
    try:
        response = requests.get(f'{VOICEBOX_URL}/profiles', timeout=timeout)
        response.raise_for_status()
        profiles = response.json()
    except (requests.RequestException, ValueError):
        return []
    return [{'source': 'voicebox', 'id': p['id'], 'name': p['name'],
             'language': p.get('language') or 'en'} for p in profiles]


def system_voices() -> list:
    """The computer's own voices. On macOS only English ones (there are dozens in total)."""
    import pyttsx3
    voices = []
    for voice in pyttsx3.init().getProperty('voices'):
        languages = [str(lang).lower() for lang in (voice.languages or [])]
        if IS_MAC and languages and not any('en' in lang for lang in languages):
            continue
        name = voice.name.replace('Microsoft ', '').replace(' Desktop', '')
        voices.append({'source': 'system', 'id': voice.id, 'name': name, 'language': 'en'})
    return voices


def all_voices() -> list:
    """Natural voices first. The computer's robotic voices only when Kokoro is missing."""
    natural = kokoro_voices()
    return natural + voicebox_voices() + ([] if natural else system_voices())


# ---- speaking ------------------------------------------------------------------------

def _play_wav(wav_bytes: bytes) -> None:
    import numpy as np
    with wave.open(io.BytesIO(wav_bytes)) as wav:
        rate, channels, width = wav.getframerate(), wav.getnchannels(), wav.getsampwidth()
        frames = wav.readframes(wav.getnframes())
    dtype = {1: np.uint8, 2: np.int16, 4: np.int32}[width]
    audio = np.frombuffer(frames, dtype=dtype).reshape(-1, channels)
    playback.play(audio, rate)  # waits until finished so JARVIS never listens to itself


def voicebox_say(voice: dict, text: str, timeout: float = 180) -> None:
    """Generate speech in a Voicebox profile and play it. Raises on any failure.

    /generate/stream returns the finished WAV directly. The first call after Voicebox
    starts can be slow while it loads the voice model, hence the long timeout.
    """
    response = requests.post(f'{VOICEBOX_URL}/generate/stream', timeout=timeout,
                             json={'profile_id': voice['id'], 'text': text,
                                   'language': voice.get('language') or 'en'})
    if response.status_code != 200:
        try:
            detail = response.json().get('detail')
        except ValueError:
            detail = response.reason
        raise RuntimeError(f'Voicebox could not speak ({response.status_code}): {detail}')
    _play_wav(response.content)


def system_say(voice, text: str) -> None:
    import pyttsx3
    engine = pyttsx3.init()
    if voice and voice.get('id'):
        engine.setProperty('voice', voice['id'])
    engine.say(text)
    engine.runAndWait()


def say(voice, text: str) -> None:
    """Speak and wait until finished. Voicebox and Kokoro voices are used when chosen; anything
    else gets the default natural voice, or the computer's own voice if Kokoro is missing."""
    Speech(voice).say(text)


def say_isolated(voice, text: str):
    """Speak and wait until finished, safely from any thread. Returns an error message
    or None.

    Built-in voices run in a separate Python process: the speech engines are tied to the
    thread that created them, and running them inside a window's event loop can stall it.
    """
    source = (voice or {}).get('source')
    if source == 'voicebox':
        try:
            voicebox_say(voice, text)
            return None
        except RuntimeError as error:
            return str(error)
        except requests.RequestException:
            return 'Voicebox is not responding. Is the app still open?'
    if source == 'kokoro' or kokoro_installed():
        try:
            kokoro_say(voice if source == 'kokoro' else DEFAULT_VOICE, text)
            return None
        except Exception as error:
            if source == 'kokoro':
                return f'The natural voice could not speak: {error}'
    if IS_MAC:
        mac_say(text)
        return None
    voice_id = (voice or {}).get('id') or ''
    code = ('import pyttsx3, sys; e = pyttsx3.init(); '
            'sys.argv[1] and e.setProperty("voice", sys.argv[1]); '
            'e.say(sys.argv[2]); e.runAndWait()')
    result = subprocess.run([sys.executable, '-c', code, voice_id, text])
    return None if result.returncode == 0 else 'The built-in voice could not speak.'


def say_in_background(voice, text: str, on_done=None) -> None:
    """Speak without blocking the caller; on_done(error_or_None) runs when speech ends."""
    def work():
        error = say_isolated(voice, text)
        if on_done:
            on_done(error)
    threading.Thread(target=work, daemon=True).start()
