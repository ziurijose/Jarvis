"""Tests for screen_text (the active window's controls as text) and for look_at_screen choosing
between that list and a screenshot. Run with:  python -m unittest test_screen_text"""
import unittest
from unittest import mock

import brain
import screen_text


def control(kind, name, left, top, width=20, height=10, offscreen=False):
    return {'kind': kind, 'name': name, 'rect': (left, top, width, height), 'offscreen': offscreen}


class Describe(unittest.TestCase):
    def describe(self, found, seconds=0.05, scale=1.0):
        with mock.patch.object(screen_text, '_read', return_value=('Calculator', found, seconds)), \
                mock.patch.object(screen_text.control, 'from_screen', lambda x, y: (round(x * scale), round(y * scale))):
            return screen_text.describe()

    def test_named_controls_with_their_centres_in_screenshot_pixels(self):
        found = [control(50000, '7', 100, 200), control(50000, '8', 140, 200), control(50004, 'Display', 0, 0),
                 control(50000, '9', 180, 200), control(50000, 'Equals', 220, 260)]
        text = self.describe(found, scale=0.5)
        self.assertTrue(text.startswith('Window "Calculator"'))
        self.assertIn('button "7" at 55,102', text)
        self.assertIn('edit "Display" at 5,2', text)

    def test_unnamed_offscreen_and_unclickable_items_are_left_out(self):
        found = [control(50000, f'b{n}', n, n) for n in range(5)] + [
            control(50000, '', 1, 1), control(50000, 'hidden', 1, 1, offscreen=True), control(50033, 'a pane', 1, 1)]
        text = self.describe(found)
        self.assertNotIn('hidden', text)
        self.assertNotIn('pane', text)
        self.assertEqual(text.count('\n'), 5)  # the title line and five buttons

    def test_a_window_that_shows_too_little_gets_a_screenshot(self):
        self.assertIsNone(self.describe([control(50000, 'OK', 1, 1)] * 4))  # e.g. Voicemeeter, a game

    def test_a_list_too_big_or_too_slow_gets_a_screenshot(self):
        many = [control(50000, 'x' * 70 + str(n), n, n) for n in range(400)]
        self.assertIsNone(self.describe(many))
        few = [control(50000, f'b{n}', n, n) for n in range(10)]
        self.assertIsNone(self.describe(few, seconds=2.0))

    def test_no_accessibility_means_a_screenshot(self):
        with mock.patch.object(screen_text, '_read', side_effect=OSError('no UI Automation')):
            self.assertIsNone(screen_text.describe())


class Look(unittest.TestCase):
    def look(self, args, listing):
        with mock.patch.object(screen_text, 'describe', return_value=listing), \
                mock.patch.object(brain.control, 'screenshot_png', return_value=(b'png', (1280, 720))):
            return brain.CliBrain._look(args)

    def test_the_list_is_used_when_there_is_one(self):
        content, error, png = self.look({}, 'Window "Calculator"\nbutton "7" at 60,251')
        self.assertIn('button "7" at 60,251', content)
        self.assertIsNone(png)
        self.assertFalse(error)

    def test_a_screenshot_when_there_is_no_list_or_claude_asks_for_a_picture(self):
        self.assertEqual(self.look({}, None)[2], b'png')
        self.assertEqual(self.look({'picture': True}, 'Window "Calculator"')[2], b'png')
        self.assertEqual(self.look({'region': [0, 0, 10, 10]}, 'Window "Calculator"')[2], b'png')


if __name__ == '__main__':
    unittest.main()
