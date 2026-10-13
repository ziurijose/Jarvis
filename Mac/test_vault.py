"""Tests for vault.py (JARVIS's notes in an Obsidian vault).
Run with:  python -m unittest test_vault"""
import datetime
import json
import os
import tempfile
import unittest
from unittest import mock

import vault


class VaultTest(unittest.TestCase):
    """Every test gets its own vault and settings file, never the real ones."""

    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.vault = os.path.join(self.dir, 'My Vault')
        self.settings = os.path.join(self.dir, 'user_settings.json')
        with open(self.settings, 'w', encoding='utf-8') as f:
            json.dump({'user_name': 'Jose', 'assistant_name': 'Jarbungus', 'vault': self.vault}, f)
        for name, value in (('SETTINGS_PATH', self.settings),
                            ('OLD_MEMORY_PATH', os.path.join(self.dir, 'memory.json'))):
            patcher = mock.patch.object(vault, name, value)
            patcher.start()
            self.addCleanup(patcher.stop)

    def memory(self):
        with open(vault.memory_path(), encoding='utf-8') as f:
            return f.read()

    def write_memory(self, text, encoding='utf-8'):
        with open(vault.memory_path(), 'w', encoding=encoding, newline='') as f:
            f.write(text)


class Facts(VaultTest):
    def test_no_note_yet(self):
        self.assertEqual(vault.facts(), [])

    def test_add_creates_the_note_with_its_header(self):
        self.assertTrue(vault.add_fact('I take my coffee black'))
        text = self.memory()
        self.assertTrue(text.startswith('# What JARVIS remembers\n'))
        self.assertTrue(text.endswith('\n- I take my coffee black\n'))
        self.assertEqual(vault.facts(), ['I take my coffee black'])
        self.assertTrue(os.path.isdir(os.path.join(self.vault, 'JARVIS', 'Conversations')))

    def test_only_top_level_bullets_are_facts(self):
        self.write_memory('# Mine\n\nSome text.\n- one\n  - a sub-point\n* two\n-not a bullet\n')
        self.assertEqual(vault.facts(), ['one', 'two'])

    def test_user_lines_are_kept(self):
        self.write_memory('# Mine\n\n## Family\n- Sister is Ana\n\n## Food\n- Likes tacos\n')
        vault.add_fact('Hates olives')
        vault.forget_facts('ana')
        self.assertEqual(self.memory(), '# Mine\n\n## Family\n\n## Food\n- Likes tacos\n- Hates olives\n')

    def test_add_at_index_goes_before_that_fact(self):
        self.write_memory('- a\n- c\n')
        vault.add_fact('b', index=1)
        self.assertEqual(vault.facts(), ['a', 'b', 'c'])
        vault.add_fact('d', index=99)
        self.assertEqual(vault.facts(), ['a', 'b', 'c', 'd'])

    def test_add_puts_text_on_one_line(self):
        vault.add_fact('line one\nline two  ')
        self.assertEqual(vault.facts(), ['line one line two'])

    def test_add_nothing(self):
        self.assertFalse(vault.add_fact('   '))
        self.assertFalse(os.path.exists(vault.memory_path()))

    def test_forget_is_case_blind_and_counts(self):
        self.write_memory('- My cat is Tom\n- I work at the bakery\n- CAT food is in the shed\n')
        self.assertEqual(vault.forget_facts('cat'), 2)
        self.assertEqual(vault.facts(), ['I work at the bakery'])

    def test_forget_nothing_keeps_everything(self):
        self.write_memory('- a\n- b\n')
        for about in ('', '   '):
            self.assertEqual(vault.forget_facts(about), 0)
        self.assertEqual(vault.facts(), ['a', 'b'])

    def test_edit_and_delete_check_what_was_shown(self):
        self.write_memory('- a\n- b\n')
        self.assertFalse(vault.edit_fact(1, 'B', was='not b'))
        self.assertFalse(vault.delete_fact(5, was='b'))
        self.assertEqual(vault.facts(), ['a', 'b'])
        self.assertTrue(vault.edit_fact(1, 'B\nB', was='b'))
        self.assertEqual(vault.facts(), ['a', 'B B'])
        self.assertTrue(vault.delete_fact(0, was='a'))
        self.assertEqual(vault.facts(), ['B B'])

    def test_bom_and_crlf_are_read(self):
        self.write_memory('﻿- first\r\n# Mine\r\n- second\r\n', encoding='utf-8')
        self.assertEqual(vault.facts(), ['first', 'second'])
        vault.add_fact('third')
        self.assertEqual(self.memory(), '- first\n# Mine\n- second\n- third\n')

    def test_a_vault_that_cant_be_written_doesnt_raise(self):
        with mock.patch.object(vault, '_write', side_effect=PermissionError('read-only')), \
                mock.patch('builtins.print'):
            self.assertFalse(vault.add_fact('x'))
            self.assertEqual(vault.forget_facts('x'), 0)
        self.assertEqual(vault.facts(), [])

    def test_forget_matches_the_fact_not_its_dash(self):
        self.write_memory('- a\n- b-c\n')
        self.assertEqual(vault.forget_facts('-'), 1)
        self.assertEqual(vault.facts(), ['a'])

    def test_the_temporary_name_is_per_process(self):
        used = []
        real = os.replace
        with mock.patch.object(vault.os, 'replace', side_effect=lambda a, b: (used.append(a), real(a, b))):
            vault.add_fact('x')
        self.assertIn(f'.{os.getpid()}.', used[0])

    def test_header_explanation_is_one_line(self):
        vault.add_fact('x')
        self.assertIn('Each line starting with "- " is one thing it remembers: add, change or delete lines as you like.',
                      self.memory().splitlines()[2])

    def test_writes_leave_no_temporary_file(self):
        vault.add_fact('x')
        self.assertEqual(sorted(os.listdir(vault.folder())), ['Conversations', 'Memory.md'])

    def test_a_note_that_isnt_utf8_is_left_alone(self):
        with open(vault.memory_path(), 'wb') as f:
            f.write(b'- caf\xe9\n')
        with mock.patch('builtins.print'):
            self.assertEqual(vault.facts(), [])
            self.assertFalse(vault.add_fact('x'))
        with open(vault.memory_path(), 'rb') as f:
            self.assertEqual(f.read(), b'- caf\xe9\n')


class Conversations(VaultTest):
    def note(self, day='2026-10-12'):
        with open(os.path.join(vault.folder(), 'Conversations', f'{day}.md'), encoding='utf-8') as f:
            return f.read()

    def test_a_day_note_per_day(self):
        vault.add_exchange("what's the weather", 'Sunny.', datetime.datetime(2026, 10, 12, 14, 52))
        vault.add_exchange('thanks', 'Any time.', datetime.datetime(2026, 10, 12, 14, 53))
        self.assertEqual(self.note(), '# Monday 12 October 2026\n\n'
                                      "### 14:52\n**Jose:** what's the weather\n**Jarbungus:** Sunny.\n\n"
                                      '### 14:53\n**Jose:** thanks\n**Jarbungus:** Any time.\n\n')

    def test_exchange_text_on_one_line(self):
        vault.add_exchange('one\ntwo', 'First.\n\nSecond.', datetime.datetime(2026, 10, 12, 9, 0))
        self.assertIn('**Jose:** one two\n**Jarbungus:** First. Second.\n', self.note())

    def test_forget_removes_matching_exchanges_and_empty_notes(self):
        vault.add_exchange('my cat is Tom', 'Nice.', datetime.datetime(2026, 10, 11, 9, 0))
        vault.add_exchange('hello', 'Hi.', datetime.datetime(2026, 10, 12, 9, 0))
        vault.add_exchange('feed the CAT', 'Done.', datetime.datetime(2026, 10, 12, 9, 5))
        self.assertEqual(vault.forget_exchanges('cat'), 2)
        self.assertFalse(os.path.exists(os.path.join(vault.folder(), 'Conversations', '2026-10-11.md')))
        self.assertEqual(self.note(), '# Monday 12 October 2026\n\n### 09:00\n**Jose:** hello\n**Jarbungus:** Hi.\n\n')

    def test_an_unreadable_note_doesnt_stop_the_pass(self):
        vault.add_exchange('my cat is Tom', 'Nice.', datetime.datetime(2026, 10, 12, 9, 0))
        with open(os.path.join(vault.folder(), 'Conversations', '2026-10-01.md'), 'wb') as f:
            f.write(b'### 09:00\n\xe9\n')
        with mock.patch('builtins.print'):
            self.assertEqual(vault.forget_exchanges('cat'), 1)

    def test_forget_ignores_speaker_names(self):
        vault.add_exchange('hello', 'Hi.', datetime.datetime(2026, 10, 12, 9, 0))
        self.assertEqual(vault.forget_exchanges('jose'), 0)
        self.assertEqual(vault.forget_exchanges('  '), 0)
        self.assertIn('hello', self.note())

    def test_cant_write_doesnt_raise(self):
        with mock.patch.object(vault, '_write', side_effect=PermissionError('read-only')), \
                mock.patch('builtins.print'):
            vault.add_exchange('hello', 'Hi.')

    def test_copy_in_adds_only_missing_exchanges_in_time_order(self):
        vault.add_exchange('hello', 'Hi.', datetime.datetime(2026, 10, 12, 10, 0))
        log = [{'t': '2026-10-11T08:30:00', 'you': 'my cat is Tom', 'jarvis': 'Nice.'},
               {'t': '2026-10-12T09:00:05', 'you': 'good  morning', 'jarvis': 'Morning!'},
               {'t': '2026-10-12T10:00:40', 'you': 'hello', 'jarvis': 'Hi.'}]  # already there
        self.assertEqual(vault.copy_in_exchanges(log), 2)
        self.assertEqual(self.note(), '# Monday 12 October 2026\n\n'
                                      '### 09:00\n**Jose:** good morning\n**Jarbungus:** Morning!\n\n'
                                      '### 10:00\n**Jose:** hello\n**Jarbungus:** Hi.\n\n')
        self.assertIn('**Jose:** my cat is Tom', self.note('2026-10-11'))
        self.assertEqual(vault.copy_in_exchanges(log), 0)  # running it again changes nothing

    def test_copy_in_skips_items_it_cant_read(self):
        self.assertEqual(vault.copy_in_exchanges([{'t': 'not a time', 'you': 'x', 'jarvis': 'y'}, {}]), 0)


class Moving(VaultTest):
    def set_vault(self, path):
        with open(self.settings, 'w', encoding='utf-8') as f:
            json.dump({'user_name': 'Jose', 'vault': path}, f)

    def test_move_takes_the_jarvis_folder_along(self):
        vault.add_fact('x')
        new = os.path.join(self.dir, 'Other Vault')
        self.assertEqual(vault.move_to(new), 'moved')
        self.assertFalse(os.path.exists(os.path.join(self.vault, 'JARVIS')))
        self.set_vault(new)
        self.assertEqual(vault.facts(), ['x'])

    def test_move_to_a_vault_with_its_own_jarvis_folder_keeps_both(self):
        vault.add_fact('old')
        new = os.path.join(self.dir, 'Other Vault')
        os.makedirs(os.path.join(new, 'JARVIS'))
        self.assertEqual(vault.move_to(new), 'kept')
        self.assertTrue(os.path.exists(os.path.join(self.vault, 'JARVIS', 'Memory.md')))

    def test_move_to_the_same_vault(self):
        self.assertEqual(vault.move_to(self.vault + os.sep), 'same')

    def test_migrate_moves_memory_json_once(self):
        with open(vault.OLD_MEMORY_PATH, 'w', encoding='utf-8') as f:
            json.dump(['My cat is Tom', '  ', 'Two\nlines'], f)
        self.assertTrue(vault.migrate())
        self.assertEqual(vault.facts(), ['My cat is Tom', 'Two lines'])
        self.assertFalse(os.path.exists(vault.OLD_MEMORY_PATH))
        self.assertTrue(os.path.exists(vault.OLD_MEMORY_PATH + '.bak'))
        self.assertFalse(vault.migrate())

    def test_migrate_never_overwrites_the_note(self):
        vault.add_fact('mine')
        with open(vault.OLD_MEMORY_PATH, 'w', encoding='utf-8') as f:
            json.dump(['old'], f)
        self.assertFalse(vault.migrate())
        self.assertEqual(vault.facts(), ['mine'])

    def test_ensure_memory_creates_the_note_once(self):
        self.assertTrue(vault.ensure_memory())
        self.assertFalse(vault.ensure_memory())
        self.assertEqual(vault.facts(), [])


class Obsidian(VaultTest):
    def setUp(self):
        super().setUp()
        self.config = os.path.join(self.dir, 'obsidian')
        os.makedirs(self.config)
        self.list_path = os.path.join(self.config, 'obsidian.json')
        with open(self.list_path, 'w', encoding='utf-8') as f:
            json.dump({'vaults': {'0e48d7d250155236': {'path': 'D:\\Notes', 'ts': 1, 'open': True}},
                       'other': 'kept'}, f)
        for name, value in (('obsidian_installed', True), ('obsidian_running', False)):
            patcher = mock.patch.object(vault, name, return_value=value)
            patcher.start()
            self.addCleanup(patcher.stop)

    def vaults(self):
        with open(self.list_path, encoding='utf-8') as f:
            return json.load(f)

    def test_register_adds_the_vault_and_keeps_the_rest(self):
        self.assertEqual(vault.register_with_obsidian(self.config), 'added')
        data = self.vaults()
        self.assertEqual(data['other'], 'kept')
        self.assertEqual(len(data['vaults']), 2)
        added = [(i, v) for i, v in data['vaults'].items() if i != '0e48d7d250155236'][0]
        self.assertRegex(added[0], r'^[0-9a-f]{16}$')
        self.assertEqual(added[1]['path'], os.path.abspath(self.vault))
        self.assertTrue(added[1]['open'])
        self.assertEqual(vault.register_with_obsidian(self.config), 'listed')

    def test_register_with_no_list_yet(self):
        os.remove(self.list_path)
        self.assertEqual(vault.register_with_obsidian(self.config), 'added')
        self.assertEqual(len(self.vaults()['vaults']), 1)

    def test_register_waits_while_obsidian_runs(self):
        with mock.patch.object(vault, 'obsidian_running', return_value=True):
            self.assertEqual(vault.register_with_obsidian(self.config), 'running')
        self.assertEqual(len(self.vaults()['vaults']), 1)

    def test_register_without_obsidian(self):
        with mock.patch.object(vault, 'obsidian_installed', return_value=False):
            self.assertEqual(vault.register_with_obsidian(self.config), 'no-obsidian')

    def test_a_broken_list_is_left_alone(self):
        with open(self.list_path, 'w', encoding='utf-8') as f:
            f.write('{not json')
        with mock.patch('builtins.print'):
            self.assertEqual(vault.register_with_obsidian(self.config), 'failed')
        with open(self.list_path, encoding='utf-8') as f:
            self.assertEqual(f.read(), '{not json')

    def test_an_entry_without_a_text_path_is_skipped(self):
        with open(self.list_path, 'w', encoding='utf-8') as f:
            json.dump({'vaults': {'aaaaaaaaaaaaaaaa': {'path': None}, 'bbbbbbbbbbbbbbbb': {'path': 5}}}, f)
        self.assertEqual(vault.register_with_obsidian(self.config), 'added')
        self.assertIn('aaaaaaaaaaaaaaaa', self.vaults()['vaults'])

    def test_a_mac_opens_the_link_through_obsidian(self):
        with mock.patch.object(vault.sys, 'platform', 'darwin'),                 mock.patch.object(vault.subprocess, 'Popen') as popen:
            self.assertTrue(vault._open_url('obsidian://x'))
        self.assertEqual(popen.call_args.args[0], ['open', '-a', 'Obsidian', 'obsidian://x'])

    def test_open_uses_an_obsidian_link_to_memory(self):
        with mock.patch.object(vault, '_open_url', return_value=True) as opened:
            self.assertTrue(vault.open_in_obsidian())
        url = opened.call_args.args[0]
        self.assertTrue(url.startswith('obsidian://open?path='))
        self.assertIn('My%20Vault', url)
        self.assertTrue(url.endswith('Memory.md'))

    def test_prepare_opens_obsidian_only_the_first_time(self):
        with mock.patch.object(vault, 'open_in_obsidian') as opened:
            vault.prepare(self.config)
            vault.prepare(self.config)
        self.assertEqual(opened.call_count, 1)


if __name__ == '__main__':
    unittest.main()
