"""Plays JARVIS's own sounds: its voice and the "I'm listening" chime.

On a Mac the sound goes through afplay, the system's own player, not through PortAudio.
On recent macOS, PortAudio cannot reset its output once a sound has ended, so every sentence
JARVIS spoke printed

    ||PaMacCore (AUHAL)|| Error on line 2796: err='-50', msg=Unknown Error

and left its audio stream open for good (PortAudio only frees a stream it stopped cleanly).
afplay has neither problem, and it plays on whichever output is chosen in System Settings >
Sound at that moment. Other systems, and a Mac where afplay can't start, use sounddevice.

The microphone still goes through sounddevice (listen.py, mic.py). Its stream is opened once
and stays open, so it never reaches the reset that fails.

output_level() says how loud JARVIS is right now, so listen.py can tell the user talking over
JARVIS from JARVIS's own voice coming back through the microphone.
"""
import os
import subprocess
import sys
import tempfile
import threading
import time
import wave

AFPLAY = '/usr/bin/afplay'
USE_AFPLAY = sys.platform == 'darwin' and os.path.exists(AFPLAY)

_lock = threading.Lock()
_players = set()        # afplay processes playing now, so stop() can end them
_used_sounddevice = False
_sounding = []          # sounds playing (or just played), for output_level()
HOP = 0.02              # output_level() resolution, in seconds


def _pcm16(samples):
    """samples (floats from -1 to 1, or whole numbers of any width) as 16-bit audio.
    Returns (frames as bytes, number of channels)."""
    import numpy as np
    audio = np.asarray(samples)
    if audio.ndim == 1:
        audio = audio.reshape(-1, 1)
    if audio.dtype.kind == 'f':
        audio = np.clip(audio, -1.0, 1.0) * 32767
    elif audio.dtype == np.uint8:  # 8-bit sound is unsigned, with silence at 128
        audio = (audio.astype(np.int16) - 128) * 256
    elif audio.dtype.itemsize == 4:
        audio = audio >> 16
    return audio.astype('<i2').tobytes(), audio.shape[1]


def _envelope(samples, rate):
    """Loudness (RMS, 16-bit scale) of samples in HOP-second steps."""
    import numpy as np
    frames, channels = _pcm16(samples)
    audio = np.frombuffer(frames, '<i2').astype(np.float32).reshape(-1, channels).mean(axis=1)
    hop = max(1, int(rate * HOP))
    count = max(1, len(audio) // hop)
    blocks = np.resize(audio, count * hop).reshape(count, hop)
    return np.sqrt((blocks * blocks).mean(axis=1))


def _track(samples, rate):
    """Notes that a sound starts now; returns its record, for _untrack()."""
    try:
        sound = {'start': time.monotonic(), 'envelope': _envelope(samples, rate)}
    except Exception:
        return None
    sound['end'] = sound['start'] + len(sound['envelope']) * HOP
    with _lock:
        now = time.monotonic()
        _sounding[:] = [s for s in _sounding if s['end'] > now - 2] + [sound]
    return sound


def _untrack(sound):
    if sound is not None:
        sound['end'] = min(sound['end'], time.monotonic())


def output_level(behind=0.35, ahead=0.05) -> float:
    """How loud JARVIS has been over the last moment (the loudest step between behind seconds
    ago and ahead seconds from now, on the 16-bit scale). The window covers the delay before
    a sound actually leaves the speaker, and the room's echo after it."""
    now = time.monotonic()
    loudest = 0.0
    with _lock:
        sounds = list(_sounding)
    for sound in sounds:
        first = int((now - behind - sound['start']) / HOP)
        last = int((min(now + ahead, sound['end']) - sound['start']) / HOP)
        first, last = max(0, first), min(len(sound['envelope']), last)
        if last > first:
            loudest = max(loudest, float(sound['envelope'][first:last].max()))
    return loudest


def _write_wav(samples, rate) -> str:
    """Saves samples as a temporary WAV file and returns its path."""
    frames, channels = _pcm16(samples)
    handle, path = tempfile.mkstemp(prefix='jarvis-', suffix='.wav')
    try:
        with os.fdopen(handle, 'wb') as file, wave.open(file, 'wb') as wav:
            wav.setnchannels(channels)
            wav.setsampwidth(2)
            wav.setframerate(int(rate))
            wav.writeframes(frames)
    except Exception:
        _remove(path)
        raise
    return path


def _remove(path) -> None:
    try:
        os.unlink(path)
    except OSError:
        pass


def _afplay(samples, rate, stopped) -> None:
    path = _write_wav(samples, rate)
    try:
        process = subprocess.Popen([AFPLAY, path], stdin=subprocess.DEVNULL,
                                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        sound = _track(samples, rate)
        with _lock:
            _players.add(process)
        try:
            # afplay ends by itself; the limit is only for a player that got stuck.
            limit = time.monotonic() + len(samples) / rate + 10
            while process.poll() is None:
                if (stopped is not None and stopped.is_set()) or time.monotonic() > limit:
                    process.terminate()
                    break
                time.sleep(0.02)
            process.wait()
        finally:
            _untrack(sound)
            with _lock:
                _players.discard(process)
    finally:
        _remove(path)


def _sounddevice(samples, rate, stopped) -> None:
    global _used_sounddevice
    import sounddevice as sd
    _used_sounddevice = True
    sd.play(samples, rate)
    sound = _track(samples, rate)
    try:
        if stopped is None:
            sd.wait()
            return
        end = time.monotonic() + len(samples) / rate + 0.1
        while time.monotonic() < end and not stopped.is_set():
            time.sleep(0.03)
        if stopped.is_set():
            sd.stop()
    finally:
        _untrack(sound)


def play(samples, rate, stopped=None) -> None:
    """Plays samples (a numpy array: floats from -1 to 1, or whole numbers; one column per
    channel) at rate samples a second. Returns when the sound has ended, or at once when
    stopped (a threading.Event) is set or stop() is called."""
    if not len(samples):
        return
    if USE_AFPLAY:
        try:
            _afplay(samples, rate, stopped)
            return
        except OSError:
            pass  # no temporary file, or afplay would not start: nothing has played yet
    _sounddevice(samples, rate, stopped)


def start(samples, rate) -> None:
    """Plays samples without waiting for the sound to end."""
    threading.Thread(target=play, args=(samples, rate), daemon=True).start()


def stop() -> None:
    """Silences whatever is playing."""
    with _lock:
        playing = list(_players)
        for sound in _sounding:
            _untrack(sound)
    for process in playing:
        try:
            process.terminate()
        except OSError:
            pass
    if _used_sounddevice:
        try:
            import sounddevice as sd
            sd.stop()
        except Exception:
            pass
