"""Tests for the Windows reminders (windows.py keeps them in reminders.json and says each when due).
Run with:  python -m unittest test_reminders"""
import datetime
import json
import os
import tempfile
import unittest
from unittest import mock

import windows


class Reminders(unittest.TestCase):
    def setUp(self):
        self.path = os.path.join(tempfile.mkdtemp(), 'reminders.json')
        patch = mock.patch.object(windows, 'REMINDERS_PATH', self.path)
        patch.start()
        self.addCleanup(patch.stop)

    def save(self, items):
        with open(self.path, 'w', encoding='utf-8') as f:
            json.dump(items, f)

    def test_a_time_with_an_offset_is_kept_in_local_time(self):
        an_hour_ago = (datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(hours=1))
        windows.add_reminder('call mum', an_hour_ago.isoformat())
        self.assertEqual(windows.due_reminders(), ['call mum'])

    def test_utc_z_times_are_utc(self):
        an_hour_ago = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(hours=1)
        windows.add_reminder('earlier', an_hour_ago.strftime('%Y-%m-%dT%H:%M:%SZ'))
        self.assertEqual(windows.due_reminders(), ['earlier'])

    def test_one_bad_reminder_does_not_stop_the_others(self):
        past = (datetime.datetime.now() - datetime.timedelta(minutes=5)).isoformat(timespec='minutes')
        self.save([{'text': 'broken', 'due': 'next tuesday-ish', 'done': False, 'alerted': False},
                   {'text': 'aware', 'due': '2020-01-01T09:00:00+02:00', 'done': False, 'alerted': False},
                   {'text': 'feed the cat', 'due': past, 'done': False, 'alerted': False}])
        self.assertEqual(sorted(windows.due_reminders()), ['aware', 'feed the cat'])
        self.assertIn('broken', windows.list_reminders())


if __name__ == '__main__':
    unittest.main()
