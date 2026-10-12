"""Tests for voices.Speech.feed: how a streamed reply is cut into pieces to speak.
Run with:  python -m unittest test_speech_pieces"""
import threading
import time
import unittest
from unittest import mock

import voices


def pieces_before_finish(reply, chunk=6):
    """The pieces queued while reply streams in chunk characters at a time (before finish())."""
    queued = []
    with mock.patch.object(voices.Speech, '_queue', lambda self, text: (queued.append(text),
                                                                        setattr(self, 'queued', True))):
        speech = voices.Speech()
        for start in range(0, len(reply), chunk):
            speech.feed(reply[start:start + chunk])
    return queued


class Pieces(unittest.TestCase):
    def test_a_short_opening_does_not_hold_back_the_rest(self):
        queued = pieces_before_finish('Sure, I can check that. It is a quarter past three. Anything else you need? ')
        self.assertTrue(queued, 'nothing was queued until the reply finished')
        self.assertEqual(queued[0], 'Sure, I can check that. It is a quarter past three.')

    def test_a_short_sentence_later_in_the_reply_does_not_stall_it(self):
        queued = pieces_before_finish('The lights in the kitchen are now off. Done. The hall lights are off too. ')
        self.assertEqual(''.join(queued).split(), 'The lights in the kitchen are now off. Done. The hall lights are off too.'.split())

    def test_tiny_pieces_still_wait_for_more(self):
        self.assertEqual(pieces_before_finish('Sure. '), [])


class Interrupting(unittest.TestCase):
    def test_both_threads_end_when_speech_is_stopped(self):
        started = threading.Event()

        def speak_slowly(voice, text):
            started.set()
            time.sleep(0.2)

        with mock.patch.object(voices, '_kokoro_engine', return_value=None), \
                mock.patch.object(voices, 'say_isolated', side_effect=speak_slowly), \
                mock.patch.object(voices, 'IS_MAC', False):
            speech = voices.Speech()
            for n in range(5):
                speech.feed(f'This is sentence number {n}, long enough to be spoken alone. ')
            self.assertTrue(started.wait(2))
            speech.stop()
            speech._player.join(2)
            speech._maker.join(2)
        self.assertFalse(speech._player.is_alive())
        self.assertFalse(speech._maker.is_alive(), 'the generator thread is stuck after stop()')

    def test_stopping_while_the_next_sentence_is_being_made(self):
        making = threading.Event()

        def make_slowly(engine, voice, text):
            making.set()
            time.sleep(0.3)
            return [0.0], 24000

        with mock.patch.object(voices, '_kokoro_engine', return_value=object()), \
                mock.patch.object(voices, '_synthesize', side_effect=make_slowly):
            speech = voices.Speech()
            speech.feed('This is the first sentence, long enough to be spoken alone. ')
            self.assertTrue(making.wait(2))
            speech.stop()  # the player is waiting for this sentence
            speech._player.join(2)
            speech._maker.join(2)
        self.assertFalse(speech._player.is_alive(), 'the player thread is stuck after stop()')
        self.assertFalse(speech._maker.is_alive())


if __name__ == '__main__':
    unittest.main()
