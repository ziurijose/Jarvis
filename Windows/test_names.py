"""Tests for listen.split_at_name: which sentences call the assistant, and what the request is.
Run with:  python -m unittest test_names"""
import unittest

import listen

NAMES = ['jarvis']


class CallingByName(unittest.TestCase):
    def test_the_name_at_the_start_calls_it(self):
        self.assertEqual(listen.split_at_name("Hey Jarvis, what's the time?", NAMES), "what's the time")
        self.assertEqual(listen.split_at_name('Jarvis open Spotify', NAMES), 'open Spotify')
        self.assertEqual(listen.split_at_name('OK Jarvis.', NAMES), '')
        self.assertEqual(listen.split_at_name('Please Jarvis, pause the music', NAMES), 'pause the music')

    def test_the_name_at_the_end_calls_it(self):
        self.assertEqual(listen.split_at_name("What's the weather tomorrow, Jarvis?", NAMES),
                         "What's the weather tomorrow")

    def test_a_close_spelling_still_counts(self):
        self.assertEqual(listen.split_at_name('Hey Jarvys, stop', NAMES), 'stop')

    def test_a_mention_in_the_middle_does_not(self):
        for text in ('And then Jarvis said open the pod bay doors', 'I think Jarvis is the best AI in the movies',
                     'Tony asked Jarvis to scan the suit for damage'):
            self.assertIsNone(listen.split_at_name(text, NAMES), text)
            self.assertTrue(listen.mentions_name(text, NAMES), text)

    def test_no_name_at_all(self):
        self.assertIsNone(listen.split_at_name("What's the time?", NAMES))
        self.assertFalse(listen.mentions_name("What's the time?", NAMES))


if __name__ == '__main__':
    unittest.main()
