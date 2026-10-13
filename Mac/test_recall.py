"""Tests for recall.search reading the Obsidian vault: facts, conversations (as edited in
Obsidian) and the user's own notes. Run with:  python -m unittest test_recall"""
import datetime
import json
import os
import tempfile
import unittest
from unittest import mock

import numpy as np

import recall
import vault


class RecallTest(unittest.TestCase):
    """Each test gets its own vault, settings and conversation log; search is by keywords
    unless a test gives it a stand-in model."""

    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.vault = os.path.join(self.dir, 'Vault')
        settings = os.path.join(self.dir, 'user_settings.json')
        with open(settings, 'w', encoding='utf-8') as f:
            json.dump({'user_name': 'Jose', 'assistant_name': 'Jarbungus', 'vault': self.vault}, f)
        patcher = mock.patch.object(vault, 'SETTINGS_PATH', settings)
        patcher.start()
        self.addCleanup(patcher.stop)
        recall.use_folder(self.dir, model_dir=os.path.join(self.dir, 'no-model'))
        self.addCleanup(recall.use_folder, recall.HERE)

    def note(self, relative, text):
        path = os.path.join(self.vault, relative)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, 'w', encoding='utf-8') as f:
            f.write(text)
        return path


class Search(RecallTest):
    def test_finds_a_remembered_fact(self):
        vault.add_fact('My sister Ana lives in Lisbon')
        self.assertIn('[Remembered] My sister Ana lives in Lisbon', recall.search('where does Ana live'))

    def test_finds_the_users_own_notes(self):
        self.note('Recipes/Pasta.md', '# Pasta\n\nCarbonara needs guanciale and pecorino.\n\nBoil the water first.')
        found = recall.search('what goes in carbonara')
        self.assertIn('[Note: Recipes/Pasta] Carbonara needs guanciale and pecorino.', found)
        self.assertNotIn('Boil the water', found)

    def test_an_exchange_edited_in_obsidian_is_found_as_edited(self):
        vault.add_exchange('my dentist is Dr Lee', 'Got it.', datetime.datetime(2026, 10, 12, 9, 0))
        path = os.path.join(vault.folder(), 'Conversations', '2026-10-12.md')
        with open(path, encoding='utf-8') as f:
            text = f.read().replace('Dr Lee', 'Dr Park')
        with open(path, 'w', encoding='utf-8') as f:
            f.write(text)
        found = recall.search('who is my dentist')
        self.assertIn('Dr Park', found)
        self.assertIn('[Mon 12 Oct, 09:00]', found)
        self.assertNotIn('Dr Lee', found)

    def test_obsidian_settings_and_trash_are_skipped(self):
        self.note('.obsidian/workspace.md', 'dentist settings')
        self.note('.trash/old.md', 'my old dentist')
        self.assertEqual(recall.search('dentist'), 'Nothing found in your memory.')

    def test_since_and_until_keep_only_dated_exchanges(self):
        vault.add_fact('My dentist is Dr Lee')
        vault.add_exchange('dentist on Friday', 'Noted.', datetime.datetime(2026, 10, 11, 9, 0))
        vault.add_exchange('dentist moved to Monday', 'Okay.', datetime.datetime(2026, 10, 12, 9, 0))
        found = recall.search('dentist', since='2026-10-12')
        self.assertIn('Monday', found)
        self.assertNotIn('Friday', found)
        self.assertNotIn('Dr Lee', found)

    def test_a_long_paragraph_is_split(self):
        self.note('Journal.md', ' '.join(f'word{n}' for n in range(400)) + ' zebra')
        found = recall.search('zebra')
        self.assertIn('zebra', found)
        self.assertLess(len(found), recall.MAX_CHARS)


class Meaning(RecallTest):
    def test_vectors_are_made_once_per_piece_and_kept(self):
        vault.add_fact('I take my coffee black')
        self.note('Ideas.md', 'Build a birdhouse.')
        made = []

        def embed(texts):
            made.extend(texts)
            return np.ones((len(texts), recall.DIMENSIONS), dtype=np.float32) / np.sqrt(recall.DIMENSIONS)
        with mock.patch.object(recall, '_model', object()), mock.patch.object(recall, '_embed', embed):
            recall.search('coffee')
            first = len(made)
            recall.search('birdhouse')
            self.assertEqual(len(made), first + 1)  # only the new question; the pieces are cached
            recall._piece_vectors.clear()
            recall._load_piece_vectors()
            recall.search('coffee')
            self.assertEqual(len(made), first + 2)  # read back from the saved index


class CopyLogOnce(RecallTest):
    def test_the_log_is_copied_into_the_vault_once(self):
        with open(recall.LOG_PATH, 'w', encoding='utf-8') as f:
            f.write(json.dumps({'t': '2026-10-10T08:00:00', 'conv': 1, 'you': 'my cat is Tom',
                                'jarvis': 'Nice.'}) + '\n')
        recall.copy_log_to_vault()
        path = os.path.join(vault.folder(), 'Conversations', '2026-10-10.md')
        self.assertTrue(os.path.exists(path))
        os.remove(path)  # the user deleted it in Obsidian: it must stay deleted
        recall.copy_log_to_vault()
        self.assertFalse(os.path.exists(path))


if __name__ == '__main__':
    unittest.main()
