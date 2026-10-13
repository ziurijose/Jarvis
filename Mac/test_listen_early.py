"""Tests for listen.Hearing starting Whisper during the pause at the end of a request, with a
stand-in microphone and Whisper. Run with:  python -m unittest test_listen_early"""
import threading
import time
import unittest

import numpy as np

import listen

LOUD, SOFT = 3000, 50


def frames(*parts):
    """frames((20, LOUD), (20, SOFT)) is 20 loud frames, then 20 quiet ones."""
    return [np.full(1280, loudness, dtype=np.int16).tobytes() for count, loudness in parts
            for _ in range(count)]


class FakeHub:
    """Hands out frames at once. In real time Whisper keeps up with a pause, so unless a test
    wants it busy, each frame waits for a transcription started on the frames before it."""

    def __init__(self, heard, hearing, wait):
        self.heard, self.hearing, self.wait = list(heard), hearing, wait

    def read(self, timeout=None):
        if self.wait and self.hearing._early_job:
            self.hearing._early_job.join()
        return self.heard.pop(0) if self.heard else None


def hearing(heard, whisper_seconds=0.0, fail=False):
    h = listen.Hearing.__new__(listen.Hearing)
    h.calls = []  # the length in frames of each clip Whisper was given

    def whisper(audio):
        h.calls.append(len(audio.get_raw_data()) // 2560)
        time.sleep(whisper_seconds)
        if fail:
            raise RuntimeError('whisper broke')
        return 'what time is it'
    h.__dict__.update(hub=FakeHub(heard, h, wait=not whisper_seconds), calibrated=True, _loader=None, whisper=object(), noise=100,
                      pressed=threading.Event(), prompt='Jarvis.', language='en-US', _whisper=whisper)
    return h


class EarlyTranscriptionTest(unittest.TestCase):
    def test_the_text_started_in_the_final_pause_is_used(self):
        h = hearing(frames((20, LOUD), (20, SOFT)))
        audio = h.listen(fresh=False)
        self.assertEqual(h.transcribe(audio), 'what time is it')
        self.assertEqual(h.calls, [20 + listen.EARLY_QUIET])  # once, on the clip up to the pause

    def test_a_pause_the_user_talked_through_is_not_used(self):
        h = hearing(frames((15, LOUD), (4, SOFT), (10, LOUD), (20, SOFT)))
        audio = h.listen(fresh=False)
        self.assertEqual(h.transcribe(audio), 'what time is it')
        self.assertEqual(h.calls[-1], 15 + 4 + 10 + listen.EARLY_QUIET)  # includes the words after it

    def test_no_second_run_while_whisper_is_still_busy(self):
        h = hearing(frames((15, LOUD), (4, SOFT), (10, LOUD), (20, SOFT)), whisper_seconds=0.5)
        audio = h.listen(fresh=False)  # the fake microphone is instant: the first run is still going
        self.assertIsNone(getattr(audio, 'early', None))
        self.assertEqual(h.transcribe(audio), 'what time is it')

    def test_a_failed_early_run_falls_back_to_a_normal_one(self):
        h = hearing(frames((20, LOUD), (20, SOFT)), fail=True)
        audio = h.listen(fresh=False)
        with self.assertRaises(RuntimeError):  # the fallback run uses the same broken fake
            h.transcribe(audio)
        self.assertEqual(len(h.calls), 2)


if __name__ == '__main__':
    unittest.main()
