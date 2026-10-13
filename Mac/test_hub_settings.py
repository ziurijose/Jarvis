"""Tests for the hub's settings (hub_api.HubApi).
Run with:  python -m unittest test_hub_settings"""
import json
import os
import tempfile
import unittest
from unittest import mock

import hub_api
import vault


class HubSettings(unittest.TestCase):
    def setUp(self):
        folder = tempfile.mkdtemp()
        self.folder = folder
        self.path = os.path.join(folder, 'user_settings.json')
        with open(self.path, 'w') as f:
            json.dump({'user_name': 'Jose', 'assistant_name': 'Jarbungus',
                       'vault': os.path.join(folder, 'vault')}, f)
        self.hub = hub_api.HubApi(settings_path=self.path, status_path=os.path.join(folder, 's.json'))
        patches = [mock.patch.object(hub_api, 'login_item_enabled', return_value=False),
                   mock.patch.object(vault, 'SETTINGS_PATH', self.path),
                   mock.patch.object(vault, 'OLD_MEMORY_PATH', os.path.join(folder, 'memory.json')),
                   mock.patch.object(vault, 'register_with_obsidian', return_value='added')]
        for patcher in patches:
            patcher.start()
            self.addCleanup(patcher.stop)

    def saved(self):
        with open(self.path) as f:
            return json.load(f)

    def test_the_microphone_switch_saves_at_once_and_save_keeps_it(self):
        self.assertTrue(self.hub.load()['microphone_on'])
        self.hub.set_microphone(False)
        self.assertIs(self.saved()['microphone_on'], False)
        self.assertFalse(self.hub.load()['microphone_on'])
        self.hub.save({'city': 'Boston'})  # saving the other settings leaves the switch alone
        self.assertIs(self.saved()['microphone_on'], False)
        self.hub.set_microphone(True)
        self.assertIs(self.saved()['microphone_on'], True)

    def test_offers_no_brain_choice(self):
        self.assertNotIn('brain', self.hub.load())
        self.hub.save({'brain': 'local'})  # an old page's choice: ignored
        self.assertNotIn('brain', self.saved())

    def test_clearing_a_setting_removes_it(self):
        self.hub.save({'city': 'Boston'})
        self.assertEqual(self.saved()['city'], 'Boston')
        self.hub.save({'city': ''})
        self.assertNotIn('city', self.saved())
        self.assertEqual(self.saved()['user_name'], 'Jose')  # the rest is kept

    def test_memory_is_the_vault_note(self):
        self.assertEqual(self.hub.add_memory('My cat is Tom'), {'ok': True})
        self.assertEqual(self.hub.add_memory('Likes tea'), {'ok': True})
        self.assertEqual([f['text'] for f in self.hub.list_memory()], vault.facts())
        self.assertEqual(self.hub.edit_memory(1, 'Likes coffee', 'Likes tea'), {'ok': True})
        self.assertFalse(self.hub.edit_memory(1, 'x', 'Likes tea')['ok'])  # changed meanwhile
        self.assertFalse(self.hub.edit_memory(1, '  ', 'Likes coffee')['ok'])  # blank
        self.assertEqual(self.hub.delete_memory(0, 'My cat is Tom'), {'ok': True})
        self.assertEqual(self.hub.add_memory('My cat is Tom', 0), {'ok': True})  # undo puts it back first
        self.assertEqual(vault.facts(), ['My cat is Tom', 'Likes coffee'])

    def test_changing_the_vault_moves_the_notes(self):
        self.hub.add_memory('x')
        new = os.path.join(self.folder, 'new vault')
        with mock.patch.object(self.hub, '_pick_folder', return_value=new):
            result = self.hub.choose_vault()
        self.assertTrue(result['ok'])
        self.assertEqual(self.saved()['vault'], new)
        self.assertEqual(self.hub.vault_path(), new)
        self.assertEqual(vault.facts(), ['x'])

    def test_choosing_a_vault_while_obsidian_runs_says_to_quit_it(self):
        new = os.path.join(self.folder, 'new vault')
        with mock.patch.object(self.hub, '_pick_folder', return_value=new),                 mock.patch.object(vault, 'register_with_obsidian', return_value='running'):
            result = self.hub.choose_vault()
        self.assertIn('Quit Obsidian', result['note'])

    def test_a_setting_that_cant_be_saved_is_reported(self):
        new = os.path.join(self.folder, 'new vault')
        with mock.patch.object(self.hub, '_pick_folder', return_value=new),                 mock.patch.object(hub_api.user_settings, 'update_settings', side_effect=OSError('locked')):
            result = self.hub.choose_vault()
        self.assertFalse(result['ok'])
        self.assertIn(new, result['error'])
        self.assertIn('locked', result['error'])

    def test_opening_the_vault_while_obsidian_runs_asks_to_quit_it(self):
        with mock.patch.object(vault, 'register_with_obsidian', return_value='running'),                 mock.patch.object(vault, 'open_in_obsidian') as opened:
            result = self.hub.open_vault()
        self.assertFalse(result['ok'])
        self.assertIn('Quit Obsidian', result['error'])
        opened.assert_not_called()

    def test_choosing_nothing_changes_nothing(self):
        with mock.patch.object(self.hub, '_pick_folder', return_value=None):
            self.assertIsNone(self.hub.choose_vault())


if __name__ == '__main__':
    unittest.main()
