"""Tests for quick.py: which requests JARVIS does itself, and which still go to Claude.
Run with:  python -m unittest test_quick"""
import datetime
import unittest

import quick


def done(text, is_mac=False):
    found = quick.match(text, is_mac, ['Jarbungus'])
    return found and (found.tool, found.args)


class Simple(unittest.TestCase):
    def test_music(self):
        self.assertEqual(done('Pause.'), ('music', {'action': 'pause'}))
        self.assertEqual(done('Okay, pause the music, please.'), ('music', {'action': 'pause'}))
        self.assertEqual(done('Stop the music'), ('music', {'action': 'pause'}))
        self.assertEqual(done('Resume.'), ('music', {'action': 'play'}))
        self.assertEqual(done('Play the music'), ('music', {'action': 'play'}))
        self.assertEqual(done('Next song.'), ('music', {'action': 'next'}))
        self.assertEqual(done('Skip this one'), ('music', {'action': 'next'}))
        self.assertEqual(done('Previous track'), ('music', {'action': 'previous'}))
        self.assertEqual(done('(I interrupted you.) Pause.'), ('music', {'action': 'pause'}))

    def test_volume(self):
        self.assertEqual(done('Volume 40.'), ('set_volume', {'percent': 40}))
        self.assertEqual(done('Set the volume to 75%.'), ('set_volume', {'percent': 75}))
        self.assertEqual(done('Turn the volume down to twenty five'), ('set_volume', {'percent': 25}))
        self.assertEqual(done('Volume max'), ('set_volume', {'percent': 100}))
        self.assertEqual(done('Set the volume to 30 percent.'), ('set_volume', {'percent': 30}))
        self.assertEqual(done('Volume fifty percent'), ('set_volume', {'percent': 50}))
        self.assertEqual(done('Turn the volume to twenty five percent'), ('set_volume', {'percent': 25}))

    def test_questions(self):
        self.assertEqual(done('What time is it?'), (None, {}))
        self.assertEqual(done("What's the date today?"), (None, {}))
        self.assertEqual(done("How's my battery?"), ('system_status', {}))
        self.assertEqual(done('Take a screenshot.'), ('take_screenshot', {}))

    def test_open_and_close(self):
        self.assertEqual(done('Open Spotify.'), ('open_app', {'name': 'Spotify'}))
        self.assertEqual(done('Open Chrome', is_mac=True), ('open_app', {'name': 'Google Chrome'}))
        self.assertEqual(done('Open Chrome'), ('open_app', {'name': 'Chrome'}))
        self.assertEqual(done('Open YouTube.'), ('open_website', {'url': 'https://www.youtube.com'}))
        self.assertEqual(done('Open nytimes.com'), ('open_website', {'url': 'nytimes.com'}))
        self.assertEqual(done('Close Spotify.'), ('quit_app', {'name': 'Spotify'}))
        self.assertEqual(done('Quit Google Chrome'), ('quit_app', {'name': 'Google Chrome'}))

    def test_search(self):
        self.assertEqual(done('Google pasta recipes.'), ('search', {'query': 'pasta recipes', 'site': 'google'}))
        self.assertEqual(done('Search YouTube for cat videos'), ('search', {'query': 'cat videos', 'site': 'youtube'}))
        self.assertEqual(done('Find lofi music on YouTube.'), ('search', {'query': 'lofi music', 'site': 'youtube'}))

    def test_left_to_claude(self):
        for text in ['Open Google Chrome and find me a funny video and play it.',
                     'Open my last email.', 'Open a new tab.', 'Close this window.', 'Close it.',
                     'Close Jarvis.', 'Close Jarbungus.', 'Play Bohemian Rhapsody.', 'Play some jazz.',
                     'What time is it in Tokyo?', "What's the weather tomorrow?", 'Turn it up.',
                     'Set the volume to 500.', 'Google chrome.', 'Pause and then open Spotify.',
                     'Search for the best pizza near me.', 'Can you make that full screen?', '']:
            self.assertIsNone(quick.match(text, False, ['Jarbungus']), text)


class Replies(unittest.TestCase):
    def test_music_reply(self):
        reply = quick.match('pause').reply
        self.assertEqual(reply('Spotify: pause.'), 'Paused.')
        self.assertEqual(reply('Nothing is playing.'), 'Nothing is playing.')

    def test_time_and_date(self):
        self.assertEqual(quick.spoken_time(datetime.datetime(2026, 10, 10, 15, 5)), "It's 3:05 PM.")
        self.assertEqual(quick.spoken_time(datetime.datetime(2026, 10, 10, 0, 0)), "It's 12 AM.")
        self.assertEqual(quick.spoken_date(datetime.datetime(2026, 10, 11)), "It's Sunday, October 11th.")
        self.assertEqual(quick.spoken_date(datetime.datetime(2026, 10, 22)), "It's Thursday, October 22nd.")

    def test_status_reply(self):
        reply = quick.match('battery level').reply
        self.assertEqual(reply('CPU 5%, battery 80%.'), 'CPU 5 percent, battery 80 percent.')

    def test_close_reply(self):
        reply = quick.match('quit spotify').reply
        self.assertEqual(reply('Quit Spotify.'), 'Closed Spotify.')
        self.assertEqual(reply('Spotify is not running.'), 'Spotify is not running.')


class ToldToClaude(unittest.TestCase):
    """A simple command is answered without Claude, and Claude hears about it next time."""

    def test_api_brain(self):
        import brain

        class Speech:
            def __init__(self):
                self.said = []

            def feed(self, text):
                self.said.append(text)

        class Sent(Exception):
            pass

        sent = []

        def stream(**request):
            sent.append(request)
            raise Sent  # stop before anything goes out

        claude = brain.ApiBrain('test-key', {'assistant_name': 'Jarbungus', 'city': 'Boston'})
        claude.client.beta.messages.stream = stream
        speech = Speech()
        said = claude.handle('What time is it?', speech, None)
        self.assertTrue(said.startswith("It's "))
        self.assertEqual(speech.said, [said])
        self.assertEqual(sent, [])
        with self.assertRaises(Sent):
            claude.handle('Tell me a joke.', Speech(), None)
        first = sent[0]['messages'][-1]['content']
        self.assertIn('What time is it?', first)
        self.assertTrue(first.endswith('Tell me a joke.'))
        with self.assertRaises(Sent):
            claude.handle('Another one.', Speech(), None)
        self.assertNotIn('What time is it?', sent[1]['messages'][-1]['content'])


if __name__ == '__main__':
    unittest.main()
