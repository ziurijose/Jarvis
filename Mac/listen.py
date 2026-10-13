"""JARVIS's hearing: records from the microphone and turns speech into text.

Speech is transcribed on this computer by Whisper (the faster-whisper package). It is far
more accurate than Google's free web service, copes with accents and background noise, and
works offline. If Whisper isn't installed, Google's free service is used instead, in the
computer's own language rather than a fixed one.

The microphone stays open the whole time (MicHub), so nothing is lost between the wake
word and the request: "Hey Jarvis, what's the time?" works in one breath. The wake word is
detected on this computer by openWakeWord, using a few percent of one CPU core.

JARVIS wakes when you call it by its name ("Hey Jarvinky, ..."): every sentence is
transcribed and checked for the name, allowing for how Whisper may spell it. "Hey Jarvis" is
also spotted by the wake word detector.

While JARVIS answers you can cut in (wait_for_interrupt): just start talking, or say "Hey
Jarvis", or press the hotkey. JARVIS stops at once and listens to what you say instead.
"""
import collections
import difflib
import locale
import os
import platform
import re
import subprocess
import threading

import speech_recognition as sr

SAMPLE_RATE = 16000
FRAME = 1280  # 80 ms at 16 kHz: what openWakeWord expects
END_QUIET = 8  # frames of quiet (0.64 s) that end a sentence
SHORT_QUIET = 14  # after under a second of speech ("Hey Jarvinky,"), wait 1.1 s for the rest
# Cutting in is counted over a short window, so the gaps between words don't reset it, and
# needs a voice well above the speech threshold: the user is close to the microphone, while
# other people in the room (or a TV) are not.
BARGE_IN_FRAMES = 7, 10  # frames of the user's voice over JARVIS's, out of the last 10 (0.8 s)
THINKING_FRAMES = 12, 16  # frames of the user talking while JARVIS thinks, out of the last 16 (1.3 s)
BARGE_IN_LOUDNESS = 2.0  # times the speech threshold
EARLY_QUIET = 3  # frames of quiet (0.24 s) after which transcribing starts, while the pause is confirmed


def default_model(language='en'):
    """small.en is accurate and quick on Apple silicon; Intel Macs and PCs get base, which is
    about three times faster. JARVIS_WHISPER_MODEL overrides (tiny, base, small, medium...)."""
    chosen = os.environ.get('JARVIS_WHISPER_MODEL')
    if chosen:
        return chosen
    size = 'small' if platform.machine().lower() in ('arm64', 'aarch64') else 'base'
    return size + '.en' if language == 'en' else size


def system_language():
    """The computer's language as a tag like "en-US"."""
    candidates = [os.environ.get('LC_ALL'), os.environ.get('LANG')]
    try:
        candidates.append(locale.getlocale()[0])
    except ValueError:
        pass
    if platform.system() == 'Darwin':
        try:
            candidates.append(subprocess.run(['defaults', 'read', '-g', 'AppleLocale'],
                                             capture_output=True, text=True, timeout=3).stdout)
        except (OSError, subprocess.SubprocessError):
            pass
    for value in candidates:
        match = re.match(r'([a-z]{2})[_-]([A-Z]{2})', (value or '').strip())
        if match:
            return match.group(1) + '-' + match.group(2)
    return 'en-US'


# What Whisper tends to "hear" in silence or noise. A command is never just one of these.
PHANTOMS = {'', 'you', 'thank you', 'thanks', 'thanks for watching', 'thank you for watching',
            'thank you so much for watching', 'bye', 'okay', 'oh', 'um', 'hmm', 'so'}


def quiet_needed(spoken_frames):
    """Frames of quiet that end a sentence: more after a short start, so a pause after
    "Hey Jarvinky," or "Can you..." doesn't cut the user off."""
    return SHORT_QUIET if spoken_frames * FRAME / SAMPLE_RATE < 1.0 else END_QUIET


# Words that may come before the name when calling the assistant ("Hey Jarvis", "OK Jarvis").
CALLING_WORDS = {'hey', 'hi', 'hello', 'ok', 'okay', 'yo', 'oi', 'please', 'so', 'um', 'uh', 'well',
                 'alright', 'right', 'excuse'}


def _words(text):
    """text's words, and each one lower-cased without punctuation (words that are only
    punctuation are left out)."""
    pairs = [(t, re.sub(r"[^\w]", '', t.lower())) for t in text.split()]
    pairs = [(t, k) for t, k in pairs if k]
    return [t for t, _ in pairs], [k for _, k in pairs]


def mentions_name(text, names):
    """Whether text has one of names in it anywhere (or something close to it)."""
    return _find_name(_words(text)[1], names) is not None


def split_at_name(text, names):
    """If text calls the assistant by one of names ("Hey Jarvinky, what's the time?",
    "What's the time, Jarvinky?"), returns the request in it ('' if there is none); otherwise
    None. The name must start or end the sentence: said in the middle ("and then Jarvis said
    ..."), on TV or in a song, it's a mention, not a call. Whisper may spell the name a little
    differently ("Jarvinki", "Jar Vinky"), so close matches count."""
    tokens, keys = _words(text)
    found = _find_name(keys, names)
    if found is None:
        return None
    i, size = found
    if i == 0 or (i == 1 and keys[0] in CALLING_WORDS):
        rest = tokens[i + size:]
    elif i + size == len(keys):
        rest = tokens[:i]
    else:
        return None
    return ' '.join(rest).strip(' ,.!?;:-')


def _find_name(keys, names):
    """Where the name is among keys, as (index, how many words it takes), or None."""
    def is_name(word, among, close):
        if len(word) < 4:  # a short name ("Max") only counts heard exactly: short words are easily misheard
            return word in among
        return any(difflib.SequenceMatcher(None, word, name).ratio() >= close for name in among)
    found = next(((i, 1) for i in range(len(keys)) if is_name(keys[i], names, 0.75)), None)
    long_names = [name for name in names if len(name) >= 7]
    if found is None and long_names:  # a long name heard as two words: "Jar Vinky"
        found = next(((i, 2) for i in range(len(keys) - 1)
                      if len(keys[i]) >= 3 and is_name(keys[i] + keys[i + 1], long_names, 0.8)), None)
    if found is None:
        return None
    i, size = found
    if size == 1 and i + 1 < len(keys) and long_names:  # "Jarvin key": the name, in two parts
        ratio = lambda word: max(difflib.SequenceMatcher(None, word, n).ratio() for n in long_names)  # noqa: E731
        if ratio(keys[i] + keys[i + 1]) > ratio(keys[i]):
            size = 2
    return i, size


def clean(text):
    """Lower case, punctuation removed, so "Jarvis, are you there?" matches 'jarvis are you there'."""
    text = re.sub(r"[^\w\s'+-]", ' ', text.lower())
    text = text.replace('screen shot', 'screenshot').replace('you tube', 'youtube')
    return re.sub(r'\s+', ' ', text).strip()


class MicHub:
    """One microphone stream, always open. Audio waits (the last ~15 seconds) until someone
    reads it: the wake-word detector, or the recorder that captures a request."""
    KEEP = 190  # frames, about 15 seconds

    def __init__(self, device_index=None):
        self.device_index = device_index
        self.frames = collections.deque()
        self.recent = collections.deque(maxlen=8)  # the last frames read, for unread()
        self.ready = threading.Condition()
        self.stream = None

    def put(self, data: bytes):
        with self.ready:
            self.frames.append(data)
            while len(self.frames) > self.KEEP:  # nobody is listening: forget the oldest
                self.frames.popleft()
            self.ready.notify_all()

    def start(self):
        if self.stream is not None:
            return self
        import sounddevice as sd
        self.stream = sd.RawInputStream(samplerate=SAMPLE_RATE, blocksize=FRAME, channels=1, dtype='int16',
                                        device=self.device_index,
                                        callback=lambda indata, n, t, status: self.put(bytes(indata)))
        self.stream.start()
        return self

    def stop(self):
        """Closes the microphone (the hub's switch): nothing more is heard, and the system's
        mic-in-use light goes out. start() opens it again."""
        stream, self.stream = self.stream, None
        if stream is not None:
            stream.stop()
            stream.close()
        self.forget()

    def read(self, timeout=None):
        """The next 80 ms of audio (bytes), or None after timeout seconds."""
        with self.ready:
            if not self.frames and not self.ready.wait_for(lambda: self.frames, timeout):
                return None
            frame = self.frames.popleft()
            self.recent.append(frame)
            return frame

    def unread(self, count):
        """Put the last count frames back, e.g. the start of a request the wake-word
        detector had already looked at."""
        with self.ready:
            back = list(self.recent)[-count:]
            self.recent.clear()
            self.frames.extendleft(reversed(back))

    def forget(self):
        """Drop audio that arrived while nobody was listening (e.g. JARVIS's own voice)."""
        with self.ready:
            self.frames.clear()
            self.recent.clear()


def level(frame: bytes) -> float:
    """Loudness (RMS) of a frame of 16-bit audio."""
    import numpy as np
    samples = np.frombuffer(frame, np.int16).astype(np.float32)
    return float(np.sqrt(np.mean(samples * samples))) if len(samples) else 0.0


class WakeWord:
    """Spots "Hey Jarvis" (or just "Jarvis") in the audio, on this computer."""
    THRESHOLD = 0.5
    WHILE_SPEAKING = 0.5  # while JARVIS talks (a hit must also be louder than JARVIS's own voice)

    def __init__(self):
        from openwakeword.model import Model
        try:
            self.model = Model(wakeword_models=['hey_jarvis'], inference_framework='onnx')
        except Exception:
            import openwakeword.utils
            openwakeword.utils.download_models(model_names=['hey_jarvis'])
            self.model = Model(wakeword_models=['hey_jarvis'], inference_framework='onnx')

    def heard(self, frame: bytes, threshold) -> bool:
        import numpy as np
        scores = self.model.predict(np.frombuffer(frame, np.int16))
        if max(scores.values()) >= threshold:
            self.model.reset()
            return True
        return False


class EchoGate:
    """Tells the user talking over JARVIS apart from JARVIS's own voice, which the microphone
    also hears from the speakers (there is no echo cancellation).

    For every frame it compares the microphone's loudness with how loud JARVIS was just then
    (playback.output_level). How much of JARVIS reaches the microphone depends on the volume
    and the room, so it is learned while JARVIS talks: a frame counts as the user only when it
    is clearly louder than JARVIS's voice usually comes back. With headphones nothing comes
    back, so any speech counts."""
    KEEP = 250    # loud frames remembered, about 20 seconds of JARVIS talking
    LEARN = 20    # frames to learn from before talking over JARVIS can count
    QUIET = 200   # JARVIS's output below this level is silence (between sentences)

    def __init__(self, ratio=1.8):
        self.ratio = ratio
        self.seen = collections.deque(maxlen=self.KEEP)
        self.loudest = 0.0

    def is_user(self, mic: float, output: float, floor: float, learn=True) -> bool:
        if learn and output >= self.QUIET:
            self.loudest = max(output, self.loudest * 0.999)
            if output > self.loudest * 0.3:  # learn from JARVIS's clearly audible moments
                self.seen.append(mic / output)
        if mic < floor or len(self.seen) < self.LEARN:
            return False
        usual = sorted(self.seen)[len(self.seen) // 2]
        # In JARVIS's pauses its voice may still be on its way (Bluetooth speakers lag), so
        # there too the user must be louder than its voice usually comes back.
        return mic > max(output, self.loudest * 0.3) * usual * self.ratio


def load_wake_word():
    """WakeWord, or None if openWakeWord isn't installed (JARVIS then listens for its name)."""
    try:
        return WakeWord()
    except Exception as e:
        print(f'Wake word unavailable ({e}); JARVIS will listen for its name instead.')
        return None


def _two_notes(first, second):
    try:
        import numpy as np
        import playback
        t = np.linspace(0, 0.07, int(24000 * 0.07), False)
        notes = [np.sin(2 * np.pi * f * t) * np.hanning(len(t)) for f in (first, second)]
        playback.start((np.concatenate(notes) * 0.15).astype(np.float32), 24000)
    except Exception:
        pass


def chime():
    """A soft two-note "I'm listening" sound."""
    _two_notes(880, 1320)


def end_chime():
    """The same notes falling: the conversation is over and JARVIS waits for its name again."""
    _two_notes(1320, 880)


class Hearing:
    _early_job = None  # the background transcription listen() started during a pause

    def __init__(self, mic_index=None, language=None, hints=(), model=None, load=True,
                 assistant_name='Jarvis', wake_word=True, barge_in=True):
        self.mic_index = mic_index
        self.hub = None
        self.wake = None
        self.use_wake_word = wake_word  # the "Hey Jarvis" detector, besides the name
        self.barge_in = barge_in        # talking over JARVIS interrupts it
        self.echo = EchoGate()
        self.assistant_name = assistant_name or 'Jarvis'
        self.names = list(dict.fromkeys(re.sub(r'\W', '', n.lower())
                                        for n in (self.assistant_name, 'jarvis')))
        self.language = language or system_language()
        self.recognizer = sr.Recognizer()  # only for Google's recognizer, the fallback
        self.calibrated = False
        self.noise = 100.0
        self.mic_on = True  # the hub's microphone switch
        self.pressed = threading.Event()  # the hotkey or the menu bar's Talk
        # Names Whisper should spell right, e.g. the assistant's and the user's names.
        words = [h for h in hints if h] + ['Claude', 'Wikipedia', 'YouTube', 'Spotify', 'screenshot']
        self.prompt = ', '.join(dict.fromkeys(words)) + '.'
        self.model_name = model or default_model(self.language[:2])
        self.whisper = None
        self.whisper_error = None
        self._loader = None
        if load:
            # Loading takes a few seconds, so it happens while JARVIS checks your face.
            self._loader = threading.Thread(target=self._load, daemon=True)
            self._loader.start()

    def _load(self):
        try:
            from faster_whisper import WhisperModel
        except ImportError:
            WhisperModel = None
            self.whisper_error = 'faster-whisper is not installed'
        if self.use_wake_word:
            self.wake = load_wake_word()
        if WhisperModel is None:
            return
        try:
            self.whisper = WhisperModel(self.model_name, device='cpu', compute_type='int8')
        except Exception as e:  # no internet for the first download, disk full...
            self.whisper_error = str(e)
            print(f'Whisper could not start ({e}); using Google speech recognition instead.')
            return
        self._warm_up()

    def _warm_up(self):
        """Transcribes a second of silence once, so the first request isn't slower than the
        rest (Whisper and its speech filter get ready on their first use). The filter cuts
        silence out entirely, so a second pass without it makes Whisper itself run."""
        import numpy as np
        silence = np.zeros(SAMPLE_RATE, np.float32)
        try:
            for vad in (True, False):
                segments, _info = self.whisper.transcribe(
                    silence, language=self.language[:2], beam_size=1, vad_filter=vad, temperature=0.0,
                    max_new_tokens=4, initial_prompt=self.prompt, condition_on_previous_text=False,
                    without_timestamps=True)
                list(segments)  # the work happens as the segments are read
        except Exception:
            pass  # only a head start: the first request just takes a little longer

    @property
    def engine(self):
        if self._loader and self._loader.is_alive():
            print('Getting speech recognition ready (the first time downloads it)...')
            self._loader.join()
        return 'whisper' if self.whisper else 'google'

    @property
    def threshold(self):
        """How loud a frame must be to count as speech: well above the room's noise."""
        return max(300.0, self.noise * 3)

    def set_microphone(self, on):
        """The hub's microphone switch. Off closes the microphone; whatever is listening then
        hears nothing until it is on again."""
        if on == self.mic_on:
            return
        self.mic_on = on
        print('Microphone on.' if on else "Microphone off (the hub's switch).")
        if self.hub is not None:
            self.hub.start() if on else self.hub.stop()

    def _start(self):
        if self.hub is None:
            self.hub = MicHub(self.mic_index)
            if self.mic_on:
                self.hub.start()
        # Calibrating on a closed microphone would wait for audio that never comes.
        if not self.calibrated and self.mic_on:
            # One second of the room's sound, once (not before every request).
            levels = [level(f) for f in (self.hub.read(timeout=2) for _ in range(12)) if f]
            from mic import SILENT_LEVEL
            if levels and max(levels) < SILENT_LEVEL and self.mic_index is None:
                self._switch_from_silent_default()
                levels = [level(f) for f in (self.hub.read(timeout=2) for _ in range(12)) if f]
            self.noise = sum(levels) / len(levels) if levels else 100.0
            self.calibrated = True

    def _switch_from_silent_default(self):
        """The default input gave pure silence, so it is a virtual or dead device: use the
        first input that hears anything (set "microphone" in user_settings.json to choose)."""
        from mic import find_live_input
        self.hub.stream.stop()
        self.hub.stream.close()
        live = find_live_input()
        if live:
            print(f'The default microphone is silent; listening on "{live[1]}" instead. '
                  'To pick one yourself, set "microphone" in user_settings.json.')
            self.mic_index = live[0]
        else:
            print('No microphone is picking up any sound. Check one is connected and not muted.')
        self.hub = MicHub(self.mic_index).start()
        for _ in range(6):  # a freshly opened microphone starts with a burst; skip it
            self.hub.read(timeout=2)

    def listen(self, on_listening=None, max_seconds=15, wait_seconds=None, fresh=True):
        """Records one request: waits for speech (up to wait_seconds, or forever), keeps a
        short lead-in so the first word isn't clipped, and stops after a pause (quiet_needed).
        Returns sr.AudioData, or None if nobody spoke in time. fresh=False keeps audio already
        heard (the words right after the wake word, or the start of an interruption)."""
        self._start()
        self.pressed.clear()  # pressing the hotkey now just means "I'm talking"
        if fresh:
            self.hub.forget()
        if on_listening:
            on_listening()
        waited = 0.0
        seconds = FRAME / SAMPLE_RATE
        while True:
            lead_in = collections.deque(maxlen=4)
            frames = None
            while frames is None:  # wait for speech to start
                frame = self.hub.read(timeout=2)
                if frame is None:
                    return None  # the microphone stopped
                loud = level(frame)
                if loud > self.threshold:
                    frames = list(lead_in) + [frame]
                    break
                lead_in.append(frame)
                self.noise = self.noise * 0.97 + loud * 0.03  # follow the room as it changes
                waited += seconds
                if wait_seconds and waited > wait_seconds:
                    return None
            quiet, early = 0, None
            while quiet < quiet_needed(len(frames) - quiet) and len(frames) * seconds < max_seconds:
                frame = self.hub.read(timeout=2)
                if frame is None:
                    break
                frames.append(frame)
                quiet = quiet + 1 if level(frame) < self.threshold * 0.7 else 0
                if quiet == EARLY_QUIET:  # maybe the end: start on the words while that is confirmed
                    early = self._transcribe_early(frames)
            if len(frames) - quiet - len(lead_in) >= 3:  # longer than a click or a bump
                audio = sr.AudioData(b''.join(frames), SAMPLE_RATE, 2)
                if early and quiet >= EARLY_QUIET:  # nothing was said after it started
                    audio.early = early
                return audio

    def trigger(self):
        """Same as saying the wake word (the hotkey and the menu bar call this)."""
        self.pressed.set()

    def wait_for_interrupt(self, stop):
        """While JARVIS answers: returns True as soon as the user cuts in (by talking over it,
        saying the wake word, or pressing the hotkey), or None once stop is set. The words
        that cut in stay in the microphone's buffer, so listen(fresh=False) hears them."""
        import playback
        self._start()
        self.engine  # waits until the wake word detector has loaded
        voiced = collections.deque(maxlen=THINKING_FRAMES[1])  # whether each recent frame was the user
        was_talking = None
        recent = collections.deque(maxlen=12)  # loudness of the last second, for the wake word
        while not stop.is_set():
            if self.pressed.is_set():
                self.pressed.clear()
                return True
            frame = self.hub.read(timeout=0.1)
            if frame is None:
                continue
            loud = level(frame)
            recent.append(loud)
            talking = playback.output_level(behind=1.5) >= EchoGate.QUIET
            # Learns how loud JARVIS's voice comes back, whether or not talking over it is on.
            user = talking and self.echo.is_user(loud, playback.output_level(), self.threshold)
            if self.wake is not None and self.wake.heard(frame, WakeWord.WHILE_SPEAKING):
                # Over JARVIS's voice, only a call louder than its echo counts: JARVIS saying
                # its own name ("I'm Jarvis") must not wake it.
                if not talking or self.echo.is_user(max(recent), playback.output_level(behind=1.0),
                                                    self.threshold, learn=False):
                    self.hub.unread(5)
                    return True
            if not self.barge_in:
                continue
            if talking != was_talking:  # what counted as the user before no longer applies
                voiced.clear()
                was_talking = talking
            close = loud > self.threshold * BARGE_IN_LOUDNESS
            # Talking: the user must be heard over JARVIS's voice. Thinking: the user is still
            # talking, or changed their mind.
            voiced.append(close and (user or not talking))
            needed, window = BARGE_IN_FRAMES if talking else THINKING_FRAMES
            if sum(list(voiced)[-window:]) >= needed:
                self.hub.unread(8)  # the start of what they said
                return True
        return None

    def wait_for_wake(self, stop=None):
        """Blocks until the user calls JARVIS: a sentence that calls it by name ("Hey
        Jarvinky, what's the weather?"), "Hey Jarvis" (the detector), or the hotkey. Returns
        the request said in the same breath, '' if there was none (it follows), or None if
        stop (a threading.Event) is set first."""
        self._start()
        self.engine  # waits until speech recognition has loaded
        self.hub.forget()
        self.pressed.clear()
        seconds = FRAME / SAMPLE_RATE
        lead_in = collections.deque(maxlen=4)
        frames, quiet, woke = None, 0, False
        while not (stop and stop.is_set()):
            if self.pressed.is_set():
                self.pressed.clear()
                return ''
            frame = self.hub.read(timeout=0.2)
            if frame is None:
                continue
            loud = level(frame)
            if self.wake is not None and self.wake.heard(frame, WakeWord.THRESHOLD):
                woke = True
            if frames is None:  # waiting for someone to speak
                if loud > self.threshold:
                    frames, quiet = list(lead_in) + [frame], 0
                    continue
                lead_in.append(frame)
                self.noise = self.noise * 0.97 + loud * 0.03  # follow the room as it changes
                if woke:
                    return ''
                continue
            frames.append(frame)  # someone is speaking: hear the whole sentence
            quiet = quiet + 1 if loud < self.threshold * 0.7 else 0
            if quiet < quiet_needed(len(frames) - quiet) and len(frames) * seconds < 12:
                continue
            spoken = len(frames) - quiet - len(lead_in)
            audio, frames = frames, None
            lead_in.clear()
            if spoken < 3 and not woke:
                continue  # a click or a bump
            text = self.transcribe(sr.AudioData(b''.join(audio), SAMPLE_RATE, 2)) or ''
            request = split_at_name(text, self.names)
            if request is None and woke and not mentions_name(text, self.names):
                # the detector heard it, though Whisper misspelled it
                words = text.split()
                request = ' '.join(words[2:]) if len(words) >= 4 else ''
            woke = False
            if request is not None:
                print(f'Heard: {text}')
                return request
        return None

    def _transcribe_early(self, frames):
        """Starts transcribing frames in the background, for transcribe(audio) to pick up.
        Returns (thread, result), or None while Whisper isn't ready or is still busy with an
        earlier pause (two at once would slow each other down). A run for a pause the user
        talked through is not stopped, so on a slow computer the final run may wait behind it."""
        if self.whisper is None or (self._early_job and self._early_job.is_alive()):
            return None
        audio, result = sr.AudioData(b''.join(frames), SAMPLE_RATE, 2), {}

        def run():
            try:
                result['text'] = self._whisper(audio)
            except Exception:
                pass  # transcribe() then runs Whisper itself
        self._early_job = threading.Thread(target=run, daemon=True)
        self._early_job.start()
        return self._early_job, result

    def transcribe(self, audio):
        """The words in audio, or None if nothing was understood."""
        if self.engine == 'whisper':
            early = getattr(audio, 'early', None)  # listen() started on it during the final pause
            if early:
                early[0].join()
            text = early[1].get('text') if early else None
            if text is None:  # not started early, or that failed
                text = self._whisper(audio)
        else:
            try:
                text = self.recognizer.recognize_google(audio, language=self.language)
            except (sr.UnknownValueError, sr.RequestError):
                return None
        if not text or clean(text) in PHANTOMS or clean(text) == clean(self.prompt):
            return None
        return text

    def _whisper(self, audio):
        import numpy as np
        raw = audio.get_raw_data(convert_rate=SAMPLE_RATE, convert_width=2)
        samples = np.frombuffer(raw, np.int16).astype(np.float32) / 32768.0
        segments, _info = self.whisper.transcribe(
            samples, language=self.language[:2], beam_size=1, vad_filter=True,
            initial_prompt=self.prompt, condition_on_previous_text=False, without_timestamps=True)
        # Drop stretches Whisper itself thinks were not speech.
        kept = [s.text for s in segments if not (s.no_speech_prob > 0.6 and s.avg_logprob < -1.0)]
        return ''.join(kept).strip()


def download_model():
    """Fetches the Whisper model ahead of time (setup runs this)."""
    from faster_whisper import WhisperModel
    name = default_model(system_language()[:2])
    print(f'Downloading the "{name}" speech model (once)...')
    WhisperModel(name, device='cpu', compute_type='int8')
    print('Speech model ready.')
