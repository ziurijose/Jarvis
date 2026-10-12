"""Tests for listen.Hearing.wait_for_interrupt deciding whether "Hey Jarvis" during an answer is
the user or JARVIS's own voice, with a stand-in microphone and wake word detector.
Run with:  python -m unittest test_interrupt"""
import threading
import unittest
from unittest import mock

import numpy as np

import listen


def frame(loudness):
    return np.full(1280, loudness, dtype=np.int16).tobytes()


class FakeMic:
    def __init__(self, frames, stop):
        self.frames, self.stop = list(frames), stop

    def read(self, timeout=None):
        if self.frames:
            return self.frames.pop(0)
        self.stop.set()
        return None

    def unread(self, count):
        pass


class FakeWake:
    def __init__(self, at):
        self.at, self.count = at, 0

    def heard(self, frame, threshold):
        self.count += 1
        return self.count == self.at


def interrupted(loudness, jarvis_output, wake_at):
    stop = threading.Event()
    hearing = object.__new__(listen.Hearing)
    hearing.__dict__.update(hub=FakeMic([frame(n) for n in loudness], stop), calibrated=True,
                            _loader=None, whisper=True, noise=100, wake=FakeWake(wake_at),
                            echo=listen.EchoGate(), pressed=threading.Event(), barge_in=False)
    with mock.patch('playback.output_level', return_value=jarvis_output):
        return hearing.wait_for_interrupt(stop) is True


class WakeWordWhileSpeaking(unittest.TestCase):
    def test_jarvis_saying_its_own_name_does_not_wake_it(self):
        # Its voice comes back at half its level, steadily: that's its echo, not the user.
        self.assertFalse(interrupted([1000] * 40, jarvis_output=2000, wake_at=35))

    def test_the_user_calling_over_its_voice_does(self):
        self.assertTrue(interrupted([1000] * 30 + [6000] * 5 + [1000] * 5, jarvis_output=2000, wake_at=35))

    def test_the_user_calling_while_it_is_quiet_does(self):
        self.assertTrue(interrupted([400] * 10, jarvis_output=0, wake_at=5))


if __name__ == '__main__':
    unittest.main()
