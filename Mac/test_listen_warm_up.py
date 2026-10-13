"""Tests for listen.Hearing._warm_up: Whisper and its speech filter both run once on silence,
so the first real request isn't slower. Run with:  python -m unittest test_listen_warm_up"""
import unittest

import listen


class FakeWhisper:
    def __init__(self, fail=False):
        self.fail, self.calls, self.read = fail, [], []

    def transcribe(self, samples, **options):
        if self.fail:
            raise RuntimeError('broken model')
        self.calls.append(options)

        def segments():
            self.read.append(options['vad_filter'])
            yield from ()
        return segments(), None


def hearing(whisper):
    h = listen.Hearing.__new__(listen.Hearing)
    h.whisper, h.language, h.prompt = whisper, 'en-US', 'Jarvis.'
    return h


class WarmUpTest(unittest.TestCase):
    def test_runs_with_and_without_the_speech_filter(self):
        whisper = FakeWhisper()
        hearing(whisper)._warm_up()
        self.assertEqual([c['vad_filter'] for c in whisper.calls], [True, False])
        self.assertEqual(whisper.read, [True, False])  # segments are lazy: reading them does the work
        self.assertTrue(all(c['max_new_tokens'] for c in whisper.calls))

    def test_a_failure_is_ignored(self):
        hearing(FakeWhisper(fail=True))._warm_up()


if __name__ == '__main__':
    unittest.main()
