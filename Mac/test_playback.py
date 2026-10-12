"""Tests for playback.py's sounddevice path, with a stand-in for sounddevice so no speaker is needed.
Run with:  python -m unittest test_playback"""
import sys
import threading
import time
import types
import unittest
from unittest import mock

import numpy as np

import playback


class FakeOutputStream:
    """Plays by calling the callback from its own thread, as PortAudio does."""
    lock = threading.Lock()
    open_now = 0
    most_open = 0
    closed_by_other_thread = 0
    frames_played = 0

    def __init__(self, samplerate, channels, dtype, callback, finished_callback):
        self.channels, self.dtype = channels, dtype
        self.callback, self.finished_callback = callback, finished_callback
        self.owner = threading.current_thread()
        self.aborted = threading.Event()
        with FakeOutputStream.lock:
            FakeOutputStream.open_now += 1
            FakeOutputStream.most_open = max(FakeOutputStream.most_open, FakeOutputStream.open_now)

    def _run(self):
        while not self.aborted.is_set():
            out = np.zeros((480, self.channels), dtype=self.dtype)
            try:
                self.callback(out, 480, None, None)
            except sd.CallbackAbort:
                break
            with FakeOutputStream.lock:
                FakeOutputStream.frames_played += 480
            time.sleep(0.001)
        self.finished_callback()

    def __enter__(self):
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()
        return self

    def abort(self):
        self.aborted.set()

    def __exit__(self, *_):
        self.aborted.set()
        self.thread.join()
        with FakeOutputStream.lock:
            FakeOutputStream.open_now -= 1
            if threading.current_thread() is not self.owner:
                FakeOutputStream.closed_by_other_thread += 1


sd = types.SimpleNamespace(OutputStream=FakeOutputStream, CallbackAbort=type('CallbackAbort', (Exception,), {}))


class SoundDevicePlayback(unittest.TestCase):
    def setUp(self):
        self._saved = sys.modules.get('sounddevice'), playback.USE_AFPLAY
        sys.modules['sounddevice'] = sd
        playback.USE_AFPLAY = False
        FakeOutputStream.open_now = FakeOutputStream.most_open = 0
        FakeOutputStream.closed_by_other_thread = FakeOutputStream.frames_played = 0

    def tearDown(self):
        module, playback.USE_AFPLAY = self._saved
        if module is None:
            sys.modules.pop('sounddevice', None)
        else:
            sys.modules['sounddevice'] = module

    def test_sounds_from_many_threads_never_share_or_overlap_a_stream(self):
        tone = np.zeros(4800, dtype=np.float32)
        threads = [threading.Thread(target=playback.play, args=(tone, 24000)) for _ in range(6)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(10)
        self.assertEqual(FakeOutputStream.most_open, 1)
        self.assertEqual(FakeOutputStream.closed_by_other_thread, 0)
        self.assertGreaterEqual(FakeOutputStream.frames_played, 6 * 4800)

    def test_stop_ends_the_sound_playing_now(self):
        long_tone = np.zeros(24000 * 60, dtype=np.float32)
        threading.Timer(0.1, playback.stop).start()
        start = time.monotonic()
        playback.play(long_tone, 24000)
        self.assertLess(time.monotonic() - start, 2)

    def test_stopped_event_ends_the_sound(self):
        stopped = threading.Event()
        threading.Timer(0.1, stopped.set).start()
        start = time.monotonic()
        playback.play(np.zeros(24000 * 60, dtype=np.float32), 24000, stopped=stopped)
        self.assertLess(time.monotonic() - start, 2)

    def test_a_stalled_device_does_not_hang_forever(self):
        class Stalled(FakeOutputStream):
            def _run(self):
                self.aborted.wait()  # never calls back, never finishes, until aborted

        sd.OutputStream = Stalled
        self.addCleanup(setattr, sd, 'OutputStream', FakeOutputStream)
        with mock.patch.object(playback, 'STALL_SECONDS', 0.3):
            start = time.monotonic()
            playback.play(np.zeros(2400, dtype=np.float32), 24000)  # a 0.1 s sound
        self.assertLess(time.monotonic() - start, 2)

    def test_formats_become_ones_portaudio_plays(self):
        self.assertEqual(playback._for_stream(np.zeros(10, dtype=np.float64)).dtype, np.float32)
        self.assertEqual(playback._for_stream(np.zeros(10, dtype=np.int32)).dtype, np.int16)
        self.assertEqual(playback._for_stream(np.zeros((10, 2), dtype=np.float32)).shape, (10, 2))
        self.assertEqual(playback._for_stream(np.zeros(10, dtype=np.int16)).shape, (10, 1))


if __name__ == '__main__':
    unittest.main()
