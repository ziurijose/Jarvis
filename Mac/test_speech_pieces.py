"""Tests for voices.Speech.feed: how a streamed reply is cut into pieces to speak.
Run with:  python -m unittest test_speech_pieces"""
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


if __name__ == '__main__':
    unittest.main()
