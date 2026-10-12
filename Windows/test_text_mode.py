"""Tests for typing to JARVIS in a terminal (python jarvis.py --text), with a stand-in brain.
Run with:  python -m unittest test_text_mode"""
import contextlib
import io
import unittest
from unittest import mock

import jarvis


class FakeBrain:
    name = 'Fake'
    broken = False
    ended = False

    def __init__(self):
        self.heard, self.forgot = [], 0

    def handle(self, text, speech, interrupted):
        self.heard.append(text)
        if text == 'shut down':
            raise jarvis.Sleep()
        if text == 'break':
            raise RuntimeError('boom')
        self.ended = text == 'bye'
        for piece in ('Hello ', 'there.'):
            speech.feed(piece)
        return 'Hello there.'

    def problem(self, error):
        return f'Fake had a problem: {error}'

    def forget_conversation(self):
        self.forgot += 1


def type_lines(*lines):
    brain = FakeBrain()
    out = io.StringIO()
    with mock.patch('builtins.input', side_effect=[*lines, EOFError()]), \
            mock.patch.object(jarvis.recall, 'start_conversation', return_value=1), \
            mock.patch.object(jarvis.recall, 'record') as record, contextlib.redirect_stdout(out):
        jarvis.type_to_jarvis({'assistant_name': 'jarbungus'}, brain)
    return brain, out.getvalue(), record


class TextMode(unittest.TestCase):
    def test_prints_the_answer_and_keeps_it(self):
        brain, shown, record = type_lines('hi', '', 'exit')
        self.assertEqual(brain.heard, ['hi'])
        self.assertIn('Jarbungus: Hello there.\n', shown)
        record.assert_called_once_with(1, 'hi', 'Hello there.')

    def test_a_goodbye_starts_a_new_conversation(self):
        brain, shown, _record = type_lines('bye', 'hi again', 'quit')
        self.assertEqual(brain.forgot, 1)
        self.assertIn('Conversation over', shown)
        self.assertEqual(brain.heard, ['bye', 'hi again'])

    def test_problems_are_explained_and_it_carries_on(self):
        brain, shown, _record = type_lines('break', 'hi', 'exit')
        self.assertIn('Fake had a problem: boom', shown)
        self.assertEqual(brain.heard, ['break', 'hi'])

    def test_shut_down_and_end_of_input_quit(self):
        brain, _shown, _record = type_lines('shut down', 'never read')
        self.assertEqual(brain.heard, ['shut down'])
        brain, _shown, _record = type_lines()  # Ctrl+D: input() raises EOFError
        self.assertEqual(brain.heard, [])


if __name__ == '__main__':
    unittest.main()
