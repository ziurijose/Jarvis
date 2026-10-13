"""Tests for brain.remember, brain.forget and brain.load_memory (the facts JARVIS keeps in the
vault's Memory.md). Run with:  python -m unittest test_memory"""
import json
import os
import tempfile
import unittest
from unittest import mock

import brain
import vault


class Memory(unittest.TestCase):
    def setUp(self):
        folder = tempfile.mkdtemp()
        settings = os.path.join(folder, 'user_settings.json')
        with open(settings, 'w', encoding='utf-8') as f:
            json.dump({'user_name': 'Jose', 'vault': os.path.join(folder, 'vault')}, f)
        patches = [mock.patch.object(vault, 'SETTINGS_PATH', settings),
                   mock.patch.object(vault, 'OLD_MEMORY_PATH', os.path.join(folder, 'memory.json')),
                   mock.patch.object(brain.recall, 'forget', return_value=0)]
        for patch in patches:
            patch.start()
            self.addCleanup(patch.stop)
        brain.remember('My cat is called Tom')
        brain.remember('I work at the bakery')

    def test_remember_writes_to_the_vault(self):
        self.assertEqual(vault.facts(), ['My cat is called Tom', 'I work at the bakery'])
        self.assertEqual(brain.load_memory(), vault.facts())

    def test_forget_removes_only_matching_facts(self):
        self.assertIn('Forgot 1 fact', brain.forget('cat'))
        self.assertEqual(vault.facts(), ['I work at the bakery'])

    def test_forget_with_nothing_to_match_keeps_every_fact(self):
        for about in ('', '   '):
            answer = brain.forget(about)
            self.assertEqual(len(vault.facts()), 2, about)
            self.assertIn('what', answer.lower())

    def test_more_than_200_facts_are_kept_but_only_200_loaded(self):
        for n in range(205):
            vault.add_fact(f'fact {n}')
        self.assertEqual(len(vault.facts()), 207)
        loaded = brain.load_memory()
        self.assertEqual(len(loaded), 200)
        self.assertEqual(loaded[-1], 'fact 204')

    def test_the_newest_facts_are_in_the_instructions_and_older_ones_are_searchable(self):
        for n in range(70):
            vault.add_fact(f'Fact number {n} is about topic{n}')
        with mock.patch.object(brain, 'city', return_value=''):
            prompt = brain.system_prompt({'user_name': 'Jose', 'assistant_name': 'Jarbungus'})
        self.assertIn('topic69', prompt)
        self.assertNotIn('topic0 ', prompt + ' ')
        self.assertIn('recall', prompt)  # it is told the older ones are there to find
        with mock.patch.object(brain.recall, '_model', None):
            self.assertIn('topic0', brain.recall.search('topic0'))

    def test_few_facts_need_no_note_about_older_ones(self):
        with mock.patch.object(brain, 'city', return_value=''):
            prompt = brain.system_prompt({'user_name': 'Jose', 'assistant_name': 'Jarbungus'})
        self.assertIn('My cat is called Tom', prompt)
        self.assertNotIn('older', prompt)

    def test_remember_says_so_when_the_vault_cant_be_written(self):
        with mock.patch.object(vault, 'add_fact', return_value=False):
            self.assertIn("couldn't", brain.remember('x').lower())


class Restart(unittest.TestCase):
    """CliBrain._ready restarts Claude Code for changed facts, but only between conversations."""

    def setUp(self):
        self.brain = brain.CliBrain.__new__(brain.CliBrain)
        self.brain.starter = mock.Mock()
        self.brain.lock = brain.threading.RLock()
        self.brain.process = mock.Mock(poll=mock.Mock(return_value=None))
        self.brain.pending = 0
        self.brain.facts_seen = ['a']
        self.start = mock.patch.object(brain.CliBrain, '_start').start()
        self.addCleanup(mock.patch.stopall)

    def test_facts_changed_before_the_first_request_restart(self):
        self.brain.last_used = 0.0
        with mock.patch.object(brain, 'load_memory', return_value=['a', 'b']):
            self.brain._ready()
        self.start.assert_called_once_with(warm=False)

    def test_facts_changed_mid_conversation_do_not_restart(self):
        self.brain.last_used = brain.time.time()
        with mock.patch.object(brain, 'load_memory', return_value=['a', 'b']):
            self.brain._ready()
        self.start.assert_not_called()

    def test_same_facts_do_not_restart(self):
        self.brain.last_used = 0.0
        with mock.patch.object(brain, 'load_memory', return_value=['a']):
            self.brain._ready()
        self.start.assert_not_called()


if __name__ == '__main__':
    unittest.main()
