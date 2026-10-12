"""Tests for mac.parse_when, the times the model gives for reminders and calendar events.
Run with:  python -m unittest test_mac_times"""
import datetime
import unittest

import mac


class Times(unittest.TestCase):
    def test_a_local_time_stays_as_it_is(self):
        self.assertEqual(mac.parse_when('2026-10-09T15:00'), datetime.datetime(2026, 10, 9, 15, 0))

    def test_offset_and_utc_times_become_local_time(self):
        moment = datetime.datetime(2026, 10, 9, 19, 0, tzinfo=datetime.timezone.utc)
        local = moment.astimezone().replace(tzinfo=None)
        self.assertEqual(mac.parse_when('2026-10-09T19:00Z'), local)
        self.assertEqual(mac.parse_when('2026-10-09T15:00-04:00'), local)
        self.assertIsNone(mac.parse_when('2026-10-09T15:00-04:00').tzinfo)

    def test_an_unreadable_time_explains_the_format(self):
        with self.assertRaises(ValueError):
            mac.parse_when('next tuesday-ish')


if __name__ == '__main__':
    unittest.main()
