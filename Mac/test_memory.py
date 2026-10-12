"""Tests for brain.remember and brain.forget (the facts JARVIS keeps in memory.json).
Run with:  python -m unittest test_memory"""
import json
import os
import tempfile
import unittest
from unittest import mock

import brain


class Memory(unittest.TestCase):
    def setUp(self):
        folder = tempfile.mkdtemp()
        self.path = os.path.join(folder, 'memory.json')
        patches = [mock.patch.object(brain, 'MEMORY_PATH', self.path),
                   mock.patch.object(brain.recall, 'forget', return_value=0)]
        for patch in patches:
            patch.start()
            self.addCleanup(patch.stop)
        brain.remember('My cat is called Tom')
        brain.remember('I work at the bakery')

    def facts(self):
        with open(self.path, encoding='utf-8') as f:
            return json.load(f)

    def test_forget_removes_only_matching_facts(self):
        brain.forget('cat')
        self.assertEqual(self.facts(), ['I work at the bakery'])

    def test_forget_with_nothing_to_match_keeps_every_fact(self):
        for about in ('', '   '):
            answer = brain.forget(about)
            self.assertEqual(len(self.facts()), 2, about)
            self.assertIn('what', answer.lower())


if __name__ == '__main__':
    unittest.main()
