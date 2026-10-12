"""Tests for jarvis.converse starting the conversation loop again after an unexpected error.
Run with:  python -m unittest test_recovery"""
import contextlib
import io
import unittest
from unittest import mock

import jarvis


class Recovery(unittest.TestCase):
    def run_converse(self, loop):
        said = []
        with mock.patch.object(jarvis, '_converse', side_effect=loop), \
                mock.patch.object(jarvis, 'speak', side_effect=said.append), \
                mock.patch.object(jarvis, 'hud'), mock.patch.object(jarvis.time, 'sleep'), \
                contextlib.redirect_stderr(io.StringIO()):
            jarvis.converse({}, None)
        return said

    def test_a_passing_error_is_survived(self):
        loop = [OSError('microphone went away'), RuntimeError('transcription failed'), None]
        said = self.run_converse(loop)
        self.assertEqual(len(said), 2)
        self.assertIn('still listening', said[0])

    def test_an_error_that_keeps_coming_back_is_passed_on(self):
        with self.assertRaises(OSError):
            self.run_converse(OSError('no microphone'))


if __name__ == '__main__':
    unittest.main()
