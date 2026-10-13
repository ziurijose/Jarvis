"""Tests for windows.quit_app: Store apps (Calculator) are closed through their window, only the
app's own windows are asked, and it says so when an app is still open.
Run with:  python -m unittest test_windows_apps"""
import types
import unittest
from unittest import mock

import windows


def process(pid, name):
    return types.SimpleNamespace(info={'pid': pid, 'name': name, 'exe': ''})


class QuitApp(unittest.TestCase):
    def quit(self, still_running, windows_open):
        asked = []
        with mock.patch.object(windows, 'find_app', return_value=('Calculator', 'x')), \
                mock.patch('psutil.process_iter', return_value=[process(7, 'CalculatorApp.exe'), process(8, 'chrome.exe')]), \
                mock.patch('psutil.pid_exists', side_effect=lambda pid: pid in still_running), \
                mock.patch.object(windows.subprocess, 'run'), \
                mock.patch.object(windows, '_app_windows', return_value=windows_open), \
                mock.patch.object(windows, '_ask_to_close', side_effect=asked.append), \
                mock.patch.object(windows.time, 'sleep'):
            return windows.quit_app('Calculator'), asked

    def test_a_store_app_is_closed_through_its_window(self):
        said, asked = self.quit(still_running=set(), windows_open=[101])
        self.assertEqual(said, 'Closed Calculator.')
        self.assertEqual(asked, [101])

    def test_it_says_so_when_the_app_is_still_open(self):
        said, _asked = self.quit(still_running={7}, windows_open=[101])
        self.assertIn('still open', said)

    def test_only_the_apps_own_windows_count(self):
        def window(title, cls, owner):
            return {'title': title, 'class': cls, 'pid': owner}
        found = [window('Calculator', 'ApplicationFrameWindow', 99),        # the Store app's frame
                 window('calculator - Google Search', 'Chrome_WidgetWin_1', 8),  # a browser tab: never
                 window('Settings', 'ApplicationFrameWindow', 99),           # another Store app
                 window('Untitled - Notepad', 'Notepad', 7)]                 # a window of the app itself
        with mock.patch.object(windows, '_visible_windows', return_value=[(n, w) for n, w in enumerate(found)]):
            self.assertEqual(windows._app_windows({7}, {'calculator'}), [0, 3])


if __name__ == '__main__':
    unittest.main()
