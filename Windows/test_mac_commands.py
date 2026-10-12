"""Tests for the commands JARVIS builds for macOS (AppleScript and say), checked on any computer.
Run with:  python -m unittest test_mac_commands"""
import unittest
from unittest import mock

import brain
import voices


class AppleScript(unittest.TestCase):
    def quit_script(self, name):
        scripts = []
        with mock.patch.object(brain, 'IS_WINDOWS', False), mock.patch.object(brain, 'IS_MAC', True), \
                mock.patch.object(brain, '_osascript', side_effect=scripts.append):
            brain.quit_app(name)
        return scripts[0]

    def test_an_ordinary_app_name(self):
        self.assertEqual(self.quit_script('Safari'), 'tell application "Safari" to quit')

    def test_quotes_in_a_name_cannot_end_the_string(self):
        script = self.quit_script('x" to quit\ndo shell script "touch /tmp/owned')
        self.assertEqual(script, 'tell application "x\\" to quit\ndo shell script \\"touch /tmp/owned" to quit')


class Say(unittest.TestCase):
    def test_text_is_the_last_argument(self):
        self.assertEqual(voices.say_command('Daniel', 'Hello there'),
                         ['say', '-v', 'Daniel', '-r', '195', 'Hello there'])
        self.assertEqual(voices.say_command(None, 'Hi'), ['say', '-r', '195', 'Hi'])

    def test_text_starting_with_a_dash_is_not_an_option(self):
        self.assertEqual(voices.say_command(None, '-o /tmp/x hello')[-1], ' -o /tmp/x hello')


if __name__ == '__main__':
    unittest.main()
