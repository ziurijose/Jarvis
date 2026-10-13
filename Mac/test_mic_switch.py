"""Tests for the microphone switch: off closes the microphone (so nothing is heard and the
system's mic-in-use light goes out), on opens it again, and the hub's setting in
user_settings.json is what decides. Run with:  python -m unittest test_mic_switch"""
import json
import os
import sys
import tempfile
import time
import types
import unittest

import helpers
import listen


class FakeStream:
    opened = []

    def __init__(self, **options):
        self.running = self.closed = False
        FakeStream.opened.append(self)

    def start(self):
        self.running = True

    def stop(self):
        self.running = False

    def close(self):
        self.closed = True


class MicTest(unittest.TestCase):
    def setUp(self):
        FakeStream.opened = []
        self.real_sd = sys.modules.get('sounddevice')
        sys.modules['sounddevice'] = types.SimpleNamespace(RawInputStream=FakeStream)
        self.addCleanup(self._restore)

    def _restore(self):
        if self.real_sd is None:
            sys.modules.pop('sounddevice', None)
        else:
            sys.modules['sounddevice'] = self.real_sd

    def hearing(self):
        return listen.Hearing(load=False, language='en-US')

    def test_off_closes_the_microphone_and_on_opens_it_again(self):
        h = self.hearing()
        h.calibrated = True
        h._start()
        first = FakeStream.opened[0]
        h.hub.put(b'old audio')
        h.set_microphone(False)
        self.assertTrue(first.closed)
        self.assertIsNone(h.hub.read(timeout=0.05))  # nothing heard while it is off
        h.set_microphone(True)
        self.assertEqual(len(FakeStream.opened), 2)
        self.assertTrue(FakeStream.opened[1].running)

    def test_starting_with_the_microphone_off_does_not_open_it_or_wait(self):
        h = self.hearing()
        h.set_microphone(False)
        started = time.monotonic()
        h._start()
        self.assertLess(time.monotonic() - started, 1)  # no 24-second calibration on silence
        self.assertFalse(any(s.running for s in FakeStream.opened))
        self.assertFalse(h.calibrated)  # it calibrates once the microphone is on

    def test_switching_to_what_it_already_is_does_nothing(self):
        h = self.hearing()
        h.calibrated = True
        h._start()
        h.set_microphone(True)
        self.assertEqual(len(FakeStream.opened), 1)


class SettingTest(unittest.TestCase):
    def setUp(self):
        handle, self.path = tempfile.mkstemp(suffix='.json')
        os.close(handle)
        self.addCleanup(os.remove, self.path)

    def write(self, settings):
        with open(self.path, 'w', encoding='utf-8') as f:
            json.dump(settings, f)

    def test_on_unless_the_hub_turned_it_off(self):
        self.write({'user_name': 'Jose'})
        self.assertTrue(helpers.microphone_wanted(self.path))
        self.write({'user_name': 'Jose', 'microphone_on': False})
        self.assertFalse(helpers.microphone_wanted(self.path))

    def test_a_missing_or_broken_file_leaves_it_on(self):
        with open(self.path, 'w', encoding='utf-8') as f:
            f.write('{not json')
        self.assertTrue(helpers.microphone_wanted(self.path))
        self.assertTrue(helpers.microphone_wanted(self.path + '.missing'))


if __name__ == '__main__':
    unittest.main()
