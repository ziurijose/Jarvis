"""Tests for the hub's brain choice (hub_api.HubApi): local + Claude, local only, Claude only.
Run with:  python -m unittest test_hub_brain"""
import json
import os
import tempfile
import unittest
from unittest import mock

import hub_api


class BrainChoice(unittest.TestCase):
    def setUp(self):
        folder = tempfile.mkdtemp()
        self.path = os.path.join(folder, 'user_settings.json')
        with open(self.path, 'w') as f:
            json.dump({'user_name': 'Jose', 'assistant_name': 'Jarbungus'}, f)
        self.hub = hub_api.HubApi(settings_path=self.path, status_path=os.path.join(folder, 's.json'),
                                  memory_path=os.path.join(folder, 'm.json'))
        patcher = mock.patch.object(hub_api, 'login_item_enabled', return_value=False)
        patcher.start()
        self.addCleanup(patcher.stop)

    def saved(self):
        with open(self.path) as f:
            return json.load(f)

    def test_defaults_to_local_with_claude(self):
        self.assertEqual(self.hub.load()['brain'], 'auto')
        self.assertNotIn('has_key', self.hub.load())

    def test_saves_each_choice(self):
        for choice in ('local', 'claude'):
            self.assertEqual(self.hub.save({'brain': choice}), {'ok': True})
            self.assertEqual((self.saved()['brain'], self.hub.load()['brain']), (choice, choice))
        self.hub.save({'brain': 'auto'})
        self.assertNotIn('brain', self.saved())  # the default isn't written down
        self.hub.save({'brain': 'api'})  # an old page's choice: ignored, no key is ever asked for
        self.assertEqual(self.hub.load()['brain'], 'auto')

    def test_clearing_a_setting_removes_it(self):
        self.hub.save({'city': 'Boston'})
        self.assertEqual(self.saved()['city'], 'Boston')
        self.hub.save({'city': ''})
        self.assertNotIn('city', self.saved())
        self.assertEqual(self.saved()['user_name'], 'Jose')  # the rest is kept


if __name__ == '__main__':
    unittest.main()
