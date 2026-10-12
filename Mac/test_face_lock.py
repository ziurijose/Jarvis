"""Tests that the face lock stays off unless it was turned on.
Run with:  python -m unittest test_face_lock"""
import unittest
from unittest import mock

import jarvis
import user_settings


class FaceLock(unittest.TestCase):
    def test_off_unless_turned_on(self):
        self.assertFalse(user_settings.face_lock_on(None))
        self.assertFalse(user_settings.face_lock_on({'user_name': 'Jose'}))
        self.assertFalse(user_settings.face_lock_on({'face_lock': False}))
        self.assertTrue(user_settings.face_lock_on({'face_lock': True}))

    def test_start_up_does_not_open_the_camera_when_it_is_off(self):
        with mock.patch.object(jarvis, 'open_camera', side_effect=AssertionError('camera opened')):
            jarvis.face_check({'user_name': 'Jose'})


if __name__ == '__main__':
    unittest.main()
