# Vault Memory Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** JARVIS keeps its facts and a readable copy of its conversations as notes in an Obsidian vault the user picks; the Mac setup installs Obsidian and graphify.

**Architecture:** A new shared module, `vault.py`, owns every read and write under `<vault>/JARVIS/`. `brain.py`, `recall.py`, `hub_api.py` and `jarvis.py` call it instead of touching `memory.json`. The vault folder is the `vault` setting in `user_settings.json` (default `~/Documents/JARVIS Vault`), read on every call, so a change in the hub applies at once. A new Mac-only script, `add_obsidian.sh`, installs Obsidian and graphify.

**Tech Stack:** Python 3.13 (standard library only), pywebview (the setup window and hub), bash (Mac setup), unittest.

**Spec:** `docs/superpowers/specs/2026-10-12-vault-memory-design.md`

## Global Constraints

- Work in `D:\Jarvis main v 1\Jarvis-main\Mac`. Files that exist in both `Mac` and `Windows` must stay identical: after each task, run `python sync_folders.py Mac` from `Jarvis-main`, and copy any **new** shared file (`vault.py`, `test_vault.py`) to `Windows` by hand (the sync script only copies files that already exist in both).
- This is not a git repository. Wherever a task says "Checkpoint", run `python check.py` from `Jarvis-main` instead of committing; it must print `ALL CHECKS PASSED`.
- Write files with Edit/Write or Python using `encoding="utf-8"`, never PowerShell. Keep each file's existing line endings: `.py`/`.html`/`.js` here are CRLF, `.sh`/`.command` are LF.
- Comments explain a non-obvious *why* in the code's own voice, matching the surrounding density. No history comments.
- Default vault: `os.path.join(os.path.expanduser('~'), 'Documents', 'JARVIS Vault')`. JARVIS writes only inside `<vault>/JARVIS/`.
- A fact is a top-level line matching `^[-*] (.*\S)\s*$`. Every other line in `Memory.md` is left as it was (apart from line endings).
- The 200-fact limit (`vault.MAX_FACTS = 200`) applies only to what `brain.load_memory()` returns. Lines are never deleted to make room.
- Vault errors never raise into a request. `vault` functions catch `OSError`, print once, and return a failure value.
- Tests must never write to the real vault: every test that can reach `vault` patches `vault.SETTINGS_PATH` (and `vault.OLD_MEMORY_PATH`) to temporary files.

## Review Focus

1. **Memory.md saved by an editor with a UTF-8 BOM or CRLF line endings** (Obsidian on Windows, Notepad): the first fact must still be read, and the user's lines kept. Test: `test_bom_and_crlf_are_read` (Task 1).
2. **A fact or reply with line breaks** (Claude's answers often have them, and the hub's editable text can send `\n`): it must be stored on one line, or it would split into a fact plus a user line. Tests: `test_add_puts_text_on_one_line` (Task 1), `test_exchange_text_on_one_line` (Task 2).
3. **"Forget Jose" when the user is called Jose**: forgetting must match what was said, not the speaker labels, or it wipes every conversation. Test: `test_forget_ignores_speaker_names` (Task 2).
4. **Obsidian is open while JARVIS registers the vault**: Obsidian rewrites `obsidian.json` when it quits, so JARVIS must not write then. Test: `test_register_waits_while_obsidian_runs` (Task 4).
5. **More than 200 facts**: none deleted, only the newest 200 go to Claude. Test: `test_more_than_200_facts_are_kept_but_only_200_loaded` (Task 5).

---

### Task 1: `vault.py` facts in Memory.md

**Files:**
- Create: `Mac/vault.py`
- Test: `Mac/test_vault.py`

**Interfaces:**
- Produces: `vault.SETTINGS_PATH: str`, `vault.OLD_MEMORY_PATH: str`, `vault.DEFAULT_VAULT: str`, `vault.MAX_FACTS = 200`, `vault.root() -> str`, `vault.folder() -> str`, `vault.memory_path() -> str`, `vault.facts() -> list[str]`, `vault.add_fact(text: str, index: int | None = None) -> bool`, `vault.forget_facts(about: str) -> int`, `vault.edit_fact(index: int, text: str, was: str) -> bool`, `vault.delete_fact(index: int, was: str) -> bool`; private helpers `_read`, `_write`, `_warn`, `_one_line`, `_lock`, `HEADER`.

- [ ] **Step 1: Write the failing tests**

`Mac/test_vault.py`:

```python
"""Tests for vault.py (JARVIS's notes in an Obsidian vault).
Run with:  python -m unittest test_vault"""
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
        self.write_memory('\ufeff- first\r\n# Mine\r\n- second\r\n', encoding='utf-8')
        self.assertEqual(vault.facts(), ['first', 'second'])
        vault.add_fact('third')
        self.assertEqual(self.memory(), '- first\n# Mine\n- second\n- third\n')

    def test_a_vault_that_cant_be_written_doesnt_raise(self):
        with mock.patch.object(vault, '_write', side_effect=PermissionError('read-only')), \
                mock.patch('builtins.print'):
            self.assertFalse(vault.add_fact('x'))
            self.assertEqual(vault.forget_facts('x'), 0)
        self.assertEqual(vault.facts(), [])

    def test_writes_leave_no_temporary_file(self):
        vault.add_fact('x')
        self.assertEqual(sorted(os.listdir(vault.folder())), ['Conversations', 'Memory.md'])


if __name__ == '__main__':
    unittest.main()
```

- [ ] **Step 2: Run the tests to see them fail**

Run (in `Mac`): `python -m unittest test_vault -v`
Expected: `ModuleNotFoundError: No module named 'vault'`

- [ ] **Step 3: Write `Mac/vault.py`**

```python
"""JARVIS's notes in an Obsidian vault: the facts it remembers (JARVIS/Memory.md) and a readable
copy of every conversation (JARVIS/Conversations/YYYY-MM-DD.md).

The vault is any folder the user picks ("vault" in user_settings.json), and their own notes can
live in it too: only the JARVIS folder inside it is touched. Memory.md is the memory itself.
Each top-level line starting with "- " is a fact; every other line is the user's and is left as
it is, so editing the note in Obsidian changes what JARVIS knows.
"""
import os
import re
import threading

import user_settings

HERE = os.path.dirname(os.path.abspath(__file__))
SETTINGS_PATH = user_settings.SETTINGS_PATH
OLD_MEMORY_PATH = os.path.join(HERE, 'memory.json')  # where facts were kept before the vault
DEFAULT_VAULT = os.path.join(os.path.expanduser('~'), 'Documents', 'JARVIS Vault')
FOLDER = 'JARVIS'
MAX_FACTS = 200  # how many go into Claude's instructions; the note itself can hold more
HEADER = ['# What JARVIS remembers', '',
          'JARVIS reads this note at the start of every conversation. Each line starting with "- " is one',
          'thing it remembers: add, change or delete lines as you like.', '']
FACT = re.compile(r'^[-*] (.*\S)\s*$')  # top level only: indented bullets belong to the user's own notes
_lock = threading.RLock()  # JARVIS and the hub can both write
_warned = set()


def root():
    """The vault folder, read each time so a change made in the hub applies at once."""
    return user_settings.read_settings(SETTINGS_PATH).get('vault') or DEFAULT_VAULT


def folder():
    path = os.path.join(root(), FOLDER)
    os.makedirs(os.path.join(path, 'Conversations'), exist_ok=True)
    return path


def memory_path():
    return os.path.join(folder(), 'Memory.md')


def _read(path):
    """The note's lines, or None if it doesn't exist. utf-8-sig: editors on Windows may add a BOM."""
    try:
        with open(path, encoding='utf-8-sig') as f:
            return f.read().splitlines()
    except FileNotFoundError:
        return None


def _write(path, lines):
    temporary = path + '.tmp'
    with open(temporary, 'w', encoding='utf-8', newline='\n') as f:
        f.write(''.join(line + '\n' for line in lines))
    os.replace(temporary, path)  # never left half-written


def _warn(error):
    message = f"The vault can't be written ({error}). Memory changes are not saved."
    if message not in _warned:
        _warned.add(message)
        print(message)


def _one_line(text):
    return ' '.join(str(text).split())


def _fact_rows(lines):
    return [i for i, line in enumerate(lines) if FACT.match(line)]


def _change_memory(change, failed):
    """Runs change(lines) on Memory.md's lines and saves them if they changed."""
    try:
        with _lock:
            path = memory_path()
            lines = _read(path)
            lines = list(HEADER) if lines is None else lines
            before = list(lines)
            result = change(lines)
            if lines != before:
                _write(path, lines)
            return result
    except OSError as error:
        _warn(error)
        return failed


def facts():
    """Every fact, oldest first ([] when the vault can't be read)."""
    try:
        with _lock:
            lines = _read(memory_path()) or []
    except OSError as error:
        _warn(error)
        return []
    return [FACT.match(lines[i]).group(1) for i in _fact_rows(lines)]


def add_fact(text, index=None):
    """Adds a fact at the end, or before the index-th fact (to put back one just deleted)."""
    text = _one_line(text)
    if not text:
        return False

    def change(lines):
        rows = _fact_rows(lines)
        if index is not None and 0 <= int(index) < len(rows):
            lines.insert(rows[int(index)], f'- {text}')
        else:
            lines.append(f'- {text}')
        return True
    return _change_memory(change, False)


def forget_facts(about):
    """Deletes every fact that mentions about (any capitals). Returns how many went."""
    needle = about.strip().lower()
    if not needle:
        return 0

    def change(lines):
        gone = [i for i in _fact_rows(lines) if needle in lines[i].lower()]
        for i in reversed(gone):
            del lines[i]
        return len(gone)
    return _change_memory(change, 0)


def _at(lines, index, was):
    """The line number of the index-th fact, if it is still the one the hub showed."""
    rows = _fact_rows(lines)
    if not 0 <= int(index) < len(rows):
        return None
    row = rows[int(index)]
    return row if FACT.match(lines[row]).group(1) == was else None


def edit_fact(index, text, was):
    text = _one_line(text)

    def change(lines):
        row = _at(lines, index, was)
        if row is None or not text:
            return False
        lines[row] = f'- {text}'
        return True
    return _change_memory(change, False)


def delete_fact(index, was):
    def change(lines):
        row = _at(lines, index, was)
        if row is None:
            return False
        del lines[row]
        return True
    return _change_memory(change, False)
```

- [ ] **Step 4: Run the tests to see them pass**

Run: `python -m unittest test_vault -v`
Expected: all `Facts` tests `ok`.

- [ ] **Step 5: Checkpoint**

Copy `vault.py` and `test_vault.py` to `Windows`, then from `Jarvis-main`: `python check.py`. Expected: `ALL CHECKS PASSED`.

---

### Task 2: Conversation notes

**Files:**
- Modify: `Mac/vault.py` (add after `delete_fact`)
- Test: `Mac/test_vault.py` (add class `Conversations` before `if __name__`)

**Interfaces:**
- Consumes: `vault.folder`, `_read`, `_write`, `_warn`, `_one_line`, `_lock`, `vault.SETTINGS_PATH` (Task 1).
- Produces: `vault.add_exchange(you: str, jarvis: str, when: datetime.datetime | None = None) -> None`, `vault.forget_exchanges(about: str) -> int`.

- [ ] **Step 1: Write the failing tests**

Add `import datetime` to the imports of `test_vault.py`, and this class:

```python
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

    def test_forget_ignores_speaker_names(self):
        vault.add_exchange('hello', 'Hi.', datetime.datetime(2026, 10, 12, 9, 0))
        self.assertEqual(vault.forget_exchanges('jose'), 0)
        self.assertEqual(vault.forget_exchanges('  '), 0)
        self.assertIn('hello', self.note())

    def test_cant_write_doesnt_raise(self):
        with mock.patch.object(vault, '_write', side_effect=PermissionError('read-only')), \
                mock.patch('builtins.print'):
            vault.add_exchange('hello', 'Hi.')
```

- [ ] **Step 2: Run them to see them fail**

Run: `python -m unittest test_vault.Conversations -v`
Expected: `AttributeError: module 'vault' has no attribute 'add_exchange'`

- [ ] **Step 3: Implement**

Add `import datetime` to `vault.py`'s imports, and after `delete_fact`:

```python
# ---- conversations: a readable copy (recall.py searches conversations.jsonl, not these) ----

def _day_path(day):
    return os.path.join(folder(), 'Conversations', f'{day:%Y-%m-%d}.md')


def add_exchange(you, jarvis, when=None):
    """Adds one exchange to the day's note. Never raises: an answer must not fail because of this."""
    when = when or datetime.datetime.now()
    settings = user_settings.read_settings(SETTINGS_PATH)
    user = settings.get('user_name') or 'You'
    assistant = settings.get('assistant_name') or user_settings.DEFAULT_ASSISTANT_NAME
    try:
        with _lock:
            path = _day_path(when)
            lines = _read(path) or [f'# {when:%A} {when.day} {when:%B %Y}', '']
            lines += [f'### {when:%H:%M}', f'**{user}:** {_one_line(you)}',
                      f'**{assistant}:** {_one_line(jarvis)}', '']
            _write(path, lines)
    except OSError as error:
        _warn(error)


def _blocks(lines):
    """(the lines before the first exchange, [each exchange's lines])"""
    head, blocks = [], []
    for line in lines:
        if line.startswith('### '):
            blocks.append([line])
        elif blocks:
            blocks[-1].append(line)
        else:
            head.append(line)
    return head, blocks


def _said(block):
    """What was said in an exchange, without the speakers' names (so forgetting "Jose" doesn't
    match every exchange Jose had)."""
    return ' '.join(line.split(':** ', 1)[-1] for line in block[1:]).lower()


def forget_exchanges(about):
    """Deletes every exchange that mentions about from the day notes. Returns how many went."""
    needle = about.strip().lower()
    if not needle:
        return 0
    removed = 0
    try:
        with _lock:
            notes = os.path.join(folder(), 'Conversations')
            for name in sorted(os.listdir(notes)):
                path = os.path.join(notes, name)
                if not name.endswith('.md') or not os.path.isfile(path):
                    continue
                head, blocks = _blocks(_read(path) or [])
                kept = [block for block in blocks if needle not in _said(block)]
                if len(kept) == len(blocks):
                    continue
                removed += len(blocks) - len(kept)
                if kept:
                    _write(path, head + [line for block in kept for line in block])
                else:
                    os.remove(path)
    except OSError as error:
        _warn(error)
    return removed
```

- [ ] **Step 4: Run all vault tests**

Run: `python -m unittest test_vault -v`
Expected: all `ok`.

- [ ] **Step 5: Checkpoint**

Copy `vault.py` and `test_vault.py` to `Windows`; `python check.py` → `ALL CHECKS PASSED`.

---

### Task 3: Moving the vault, migrating `memory.json`, preparing the folder

**Files:**
- Modify: `Mac/vault.py` (add after `forget_exchanges`)
- Test: `Mac/test_vault.py` (add class `Moving`)

**Interfaces:**
- Consumes: Task 1 and 2 functions.
- Produces: `vault.move_to(new_vault: str) -> str` (`'moved'`, `'kept'` or `'same'`; raises `OSError` when the move fails), `vault.migrate() -> bool`, `vault.ensure_memory() -> bool` (True when `Memory.md` was just created), `vault._same(a, b) -> bool`.

- [ ] **Step 1: Write the failing tests**

```python
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
```

- [ ] **Step 2: Run them to see them fail**

Run: `python -m unittest test_vault.Moving -v`
Expected: `AttributeError: module 'vault' has no attribute 'move_to'`

- [ ] **Step 3: Implement**

Add `import json` and `import shutil` to `vault.py`'s imports, and:

```python
# ---- the vault itself ----------------------------------------------------------------------

def _same(a, b):
    return os.path.normcase(os.path.abspath(a)) == os.path.normcase(os.path.abspath(b))


def move_to(new_vault):
    """Moves the JARVIS folder into new_vault. Call it before the setting changes. If new_vault
    already has a JARVIS folder, that one is used and the old one stays where it was."""
    with _lock:
        old = os.path.join(root(), FOLDER)
        new = os.path.join(new_vault, FOLDER)
        if _same(old, new):
            return 'same'
        if os.path.exists(new):
            return 'kept'
        os.makedirs(new_vault, exist_ok=True)
        if os.path.exists(old):
            shutil.move(old, new)
        return 'moved'


def ensure_memory():
    """Creates Memory.md with its header if it isn't there. True when it was just created."""
    try:
        with _lock:
            path = memory_path()
            if os.path.exists(path):
                return False
            _write(path, HEADER)
            return True
    except OSError as error:
        _warn(error)
        return False


def migrate():
    """Moves the facts older versions kept in memory.json into Memory.md, once."""
    try:
        with _lock:
            if not os.path.exists(OLD_MEMORY_PATH) or os.path.exists(memory_path()):
                return False
            with open(OLD_MEMORY_PATH, encoding='utf-8') as f:
                old = json.load(f)
            kept = [_one_line(fact) for fact in old if _one_line(fact)] if isinstance(old, list) else []
            _write(memory_path(), HEADER + [f'- {fact}' for fact in kept])
            os.replace(OLD_MEMORY_PATH, OLD_MEMORY_PATH + '.bak')
            return True
    except (OSError, ValueError) as error:
        print(f'Could not move the old memory into the vault: {error}')
        return False
```

- [ ] **Step 4: Run all vault tests**

Run: `python -m unittest test_vault -v` → all `ok`.

- [ ] **Step 5: Checkpoint**

Copy both files to `Windows`; `python check.py` → `ALL CHECKS PASSED`.

---

### Task 4: Registering with Obsidian and opening the vault

**Files:**
- Modify: `Mac/vault.py` (add at the end)
- Test: `Mac/test_vault.py` (add class `Obsidian`)

**Interfaces:**
- Consumes: `root`, `memory_path`, `ensure_memory`, `migrate`, `_same`, `_lock` (Tasks 1-3).
- Produces: `vault.obsidian_config_dir() -> str`, `vault.obsidian_installed() -> bool`, `vault.obsidian_running() -> bool`, `vault.register_with_obsidian(config_dir: str | None = None) -> str` (`'added'`, `'listed'`, `'running'`, `'no-obsidian'`, `'failed'`), `vault.open_in_obsidian() -> bool`, `vault.prepare(config_dir: str | None = None) -> None` (what `jarvis.py` calls at start).

- [ ] **Step 1: Check the vault-list format against the real Obsidian on this PC (read-only)**

Run: `python -c "import json,os;print(json.dumps(json.load(open(os.path.join(os.environ['APPDATA'],'obsidian','obsidian.json'),encoding='utf-8')),indent=1))"`
Expected: `{"vaults": {"<16 hex digits>": {"path": "...", "ts": <ms>, "open": true}}}` (seen on 2026-10-12). If it differs, stop and update the spec before going on.

- [ ] **Step 2: Write the failing tests**

```python
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
```

- [ ] **Step 3: Run them to see them fail**

Run: `python -m unittest test_vault.Obsidian -v`
Expected: `AttributeError: module 'vault' has no attribute 'register_with_obsidian'`

- [ ] **Step 4: Implement**

Add `import secrets`, `import subprocess`, `import sys`, `import time`, `import urllib.parse` to `vault.py`'s imports, and at the end:

```python
# ---- Obsidian ------------------------------------------------------------------------------

def obsidian_config_dir():
    """Where Obsidian keeps its list of vaults (obsidian.json)."""
    if sys.platform == 'darwin':
        return os.path.expanduser('~/Library/Application Support/obsidian')
    if sys.platform == 'win32':
        return os.path.join(os.environ.get('APPDATA', ''), 'obsidian')
    return os.path.expanduser('~/.config/obsidian')


def obsidian_installed():
    if sys.platform == 'darwin':
        return any(os.path.isdir(p) for p in ('/Applications/Obsidian.app',
                                               os.path.expanduser('~/Applications/Obsidian.app')))
    if sys.platform == 'win32':
        exe = os.path.join(os.environ.get('LOCALAPPDATA', ''), 'Programs', 'Obsidian', 'Obsidian.exe')
        return os.path.exists(exe) or os.path.isdir(obsidian_config_dir())
    return os.path.isdir(obsidian_config_dir())


def obsidian_running():
    try:
        if sys.platform == 'win32':
            out = subprocess.run(['tasklist', '/FI', 'IMAGENAME eq Obsidian.exe', '/NH'], capture_output=True,
                                 text=True, timeout=10, creationflags=0x08000000).stdout
            return 'obsidian.exe' in out.lower()
        return subprocess.run(['pgrep', '-x', 'Obsidian'], capture_output=True, timeout=10).returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


def register_with_obsidian(config_dir=None):
    """Adds the vault to Obsidian's vault list, so it is there when Obsidian opens. Not while
    Obsidian runs: it rewrites the list when it quits, and the vault would be dropped."""
    if not obsidian_installed():
        return 'no-obsidian'
    config_dir = config_dir or obsidian_config_dir()
    path = os.path.join(config_dir, 'obsidian.json')
    here = os.path.abspath(root())
    try:
        with _lock:
            try:
                with open(path, encoding='utf-8') as f:
                    data = json.load(f)
            except FileNotFoundError:
                data = {}
            vaults = data.setdefault('vaults', {})
            if any(_same(v.get('path', ''), here) for v in vaults.values() if isinstance(v, dict)):
                return 'listed'
            if obsidian_running():
                return 'running'
            vaults[secrets.token_hex(8)] = {'path': here, 'ts': int(time.time() * 1000), 'open': True}
            os.makedirs(config_dir, exist_ok=True)
            user_settings.save_json(path, data)
            return 'added'
    except (OSError, ValueError, AttributeError) as error:
        print(f"Could not add the vault to Obsidian's list: {error}")
        return 'failed'


def _open_url(url):
    try:
        if sys.platform == 'win32':
            os.startfile(url)
        else:
            subprocess.Popen(['open' if sys.platform == 'darwin' else 'xdg-open', url])
        return True
    except OSError:
        return False


def open_in_obsidian():
    """Opens Memory.md in Obsidian (in its vault)."""
    return _open_url('obsidian://open?path=' + urllib.parse.quote(memory_path()))


def prepare(config_dir=None):
    """At JARVIS's start: the vault is there, older memory is moved in, and Obsidian lists it.
    The first time (Memory.md just made), Obsidian opens on it so the user sees where it is."""
    fresh = migrate() or ensure_memory()
    state = register_with_obsidian(config_dir)
    if state == 'running':
        print('Quit Obsidian and start JARVIS again to add its vault to Obsidian.')
    if fresh and state in ('added', 'listed'):
        open_in_obsidian()
```

- [ ] **Step 5: Run all vault tests**

Run: `python -m unittest test_vault -v` → all `ok`.

- [ ] **Step 6: Checkpoint**

Copy both files to `Windows`; `python check.py` → `ALL CHECKS PASSED`.

---

### Task 5: JARVIS uses the vault (brain, recall, start-up)

**Files:**
- Modify: `Mac/brain.py:37` (`MEMORY_PATH` line), `Mac/brain.py:184-205` (`load_memory`, `remember`, `forget`)
- Modify: `Mac/recall.py:71-110` (`record`, `forget`)
- Modify: `Mac/jarvis.py` (after `helpers.VOICE = settings.get('voice')`, about line 419)
- Test: `Mac/test_memory.py` (rewrite)

**Interfaces:**
- Consumes: `vault.facts`, `vault.add_fact`, `vault.forget_facts`, `vault.add_exchange`, `vault.forget_exchanges`, `vault.prepare`, `vault.MAX_FACTS`.
- Produces: `brain.load_memory() -> list[str]` (the newest `MAX_FACTS` facts), `brain.remember(fact) -> str`, `brain.forget(about) -> str` (same messages as today).

- [ ] **Step 1: Rewrite `Mac/test_memory.py` (failing)**

```python
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

    def test_remember_says_so_when_the_vault_cant_be_written(self):
        with mock.patch.object(vault, 'add_fact', return_value=False):
            self.assertIn("couldn't", brain.remember('x').lower())


if __name__ == '__main__':
    unittest.main()
```

- [ ] **Step 2: Run it to see it fail**

Run: `python -m unittest test_memory -v`
Expected: `test_remember_writes_to_the_vault` FAILS (`[] != [...]`): brain still writes `memory.json`.

- [ ] **Step 3: Change `brain.py`**

Delete the `MEMORY_PATH = os.path.join(HERE, 'memory.json')` line. Add `import vault` to the local imports (after `import user_settings`). Replace `load_memory`, `remember` and `forget` with:

```python
def load_memory():
    return vault.facts()[-vault.MAX_FACTS:]


def remember(fact):
    if vault.add_fact(fact):
        return 'Remembered.'
    return "I couldn't save that: the vault folder can't be written."


def forget(about):
    if not about.strip():  # an empty search matches every fact
        return 'Forget what? Nothing was forgotten.'
    return f'Forgot {vault.forget_facts(about)} fact(s) and {recall.forget(about)} past exchange(s).'
```

Then run `grep -n "user_settings\|MEMORY_PATH" brain.py`. If `user_settings` is no longer used anywhere in `brain.py`, remove `import user_settings` (flake8 in `check.py` fails on unused imports).

- [ ] **Step 4: Change `recall.py`**

Add `import vault` after the standard imports. In `record`, after the `try`/`except` block (outside the lock), add:

```python
    vault.add_exchange(item['you'], item['jarvis'])  # the readable copy in the vault (never raises)
```

In `forget`, add one line after the empty-needle check, so the start of the function reads:

```python
    global _vectors
    needle = about.strip().lower()
    if not needle:
        return 0
    vault.forget_exchanges(about)
```

(The count `forget` returns stays the number of exchanges removed from `conversations.jsonl`, which is the same set.)

- [ ] **Step 5: Change `jarvis.py`**

Add `import vault` with the other local imports. After `helpers.VOICE = settings.get('voice')`:

```python
    threading.Thread(target=vault.prepare, daemon=True).start()  # the vault and Obsidian, without delaying the start
```

Check `threading` is imported in `jarvis.py` (`grep -n "^import threading" jarvis.py`); add it if not.

- [ ] **Step 6: Run the tests**

Run: `python -m unittest test_memory test_vault -v` → all `ok`.

- [ ] **Step 7: Checkpoint**

From `Jarvis-main`: `python sync_folders.py Mac`, then `python check.py` → `ALL CHECKS PASSED`.

---

### Task 6: The hub reads and edits the vault, and can change it

**Files:**
- Modify: `Mac/hub_api.py:20-21` (constants), `:83-88` (`__init__`), `:186-230` (memory section)
- Modify: `Mac/ui/hub.html` (Memory page, after the `.memory-head` block; CSS after the `.memory-head` rule)
- Modify: `Mac/ui/hub.js` (memory section)
- Test: `Mac/test_hub_settings.py`

**Interfaces:**
- Consumes: `vault.facts`, `vault.add_fact`, `vault.edit_fact`, `vault.delete_fact`, `vault.move_to`, `vault.register_with_obsidian`, `vault.open_in_obsidian`, `vault.root`, `vault.ensure_memory`.
- Produces (page API): `list_memory()`, `add_memory(text, index=None)`, `edit_memory(index, text, was)`, `delete_memory(index, was)` (unchanged signatures), new `vault_path() -> str`, `choose_vault() -> dict | None` (`{'ok': True, 'path': str, 'note': str}` or `{'ok': False, 'error': str}`), `open_vault() -> dict`.

- [ ] **Step 1: Update `Mac/test_hub_settings.py` (failing)**

Add `import vault` to the imports. Replace `setUp` and add these tests (keep the existing ones):

```python
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

    def test_choosing_nothing_changes_nothing(self):
        with mock.patch.object(self.hub, '_pick_folder', return_value=None):
            self.assertIsNone(self.hub.choose_vault())
```

- [ ] **Step 2: Run it to see it fail**

Run: `python -m unittest test_hub_settings -v`
Expected: `AttributeError` (`HubApi` has no `vault_path`, `_pick_folder`, ...) or failing memory assertions.

- [ ] **Step 3: Change `hub_api.py`**

Delete the `MEMORY_PATH` and `MAX_FACTS` lines. Add `import vault` after `import voices`. In `__init__`, remove the `memory_path=MEMORY_PATH` parameter and the `self._memory_path = memory_path` line. Replace the whole memory section (from `# ---- memory:` to just before `# ---- JARVIS itself`) with:

```python
    # ---- memory: the vault's JARVIS/Memory.md (JARVIS rereads it every conversation) -----

    def list_memory(self):
        return [{'index': i, 'text': text} for i, text in enumerate(vault.facts())]

    def add_memory(self, text, index=None):
        """Adds a fact at the end, or at index (to put back one that was just deleted)."""
        if not _clean(text):
            return {'ok': False, 'error': 'Type something for it to remember.'}
        if not vault.add_fact(_clean(text), None if index is None else int(index)):
            return {'ok': False, 'error': "The vault folder can't be written."}
        return {'ok': True}

    def edit_memory(self, index, text, was):
        """was is the fact as the page showed it: if it changed since, nothing is touched."""
        if not _clean(text):
            return {'ok': False, 'error': 'A fact can\'t be blank. Delete it instead.'}
        if not vault.edit_fact(int(index), _clean(text), was):
            return {'ok': False, 'error': 'That changed while you were editing. Have another look.'}
        return {'ok': True}

    def delete_memory(self, index, was):
        if not vault.delete_fact(int(index), was):
            return {'ok': False, 'error': 'That changed in the meantime. Have another look.'}
        return {'ok': True}

    def vault_path(self):
        return vault.root()

    def _pick_folder(self):
        import webview
        kind = webview.FileDialog.FOLDER if hasattr(webview, 'FileDialog') else webview.FOLDER_DIALOG
        chosen = self._window.create_file_dialog(kind, directory=vault.root())
        return chosen[0] if chosen else None

    def choose_vault(self):
        """Lets the user pick another vault folder, and takes JARVIS's notes there."""
        new = self._pick_folder()
        if not new:
            return None
        try:
            moved = vault.move_to(new)
        except OSError as error:
            return {'ok': False, 'error': f"Couldn't move the notes there: {error}"}
        user_settings.update_settings({'vault': new}, self._settings_path)
        vault.ensure_memory()
        vault.register_with_obsidian()
        note = {'moved': 'Its notes moved to the new vault.', 'same': 'That is already its vault.',
                'kept': 'That vault already had a JARVIS folder, so it uses that one now.'}[moved]
        return {'ok': True, 'path': new, 'note': note}

    def open_vault(self):
        vault.ensure_memory()
        if vault.register_with_obsidian() == 'no-obsidian':
            return {'ok': False, 'error': 'Obsidian isn\'t installed. Get it from obsidian.md.'}
        return {'ok': True} if vault.open_in_obsidian() else {'ok': False, 'error': 'Obsidian didn\'t open.'}
```

Run `grep -n "_memory_path\|MEMORY_PATH\|MAX_FACTS" hub_api.py` → no output expected.

- [ ] **Step 4: Change `ui/hub.html`**

After the `.memory-head { ... }` CSS rule, add:

```css
  .vault-row { display: flex; flex-wrap: wrap; align-items: center; gap: 10px 14px; margin: -12px 0 28px; color: var(--muted); }
  .vault-row code { color: var(--text); font-family: inherit; overflow-wrap: anywhere; flex: 1 1 240px; }
```

In the Memory page, right after the closing `</div>` of `.memory-head`, add:

```html
      <div class="vault-row">
        <span>Kept as notes in</span>
        <code id="vault-path"></code>
        <button class="btn ghost" id="vault-choose" type="button">Change folder</button>
        <button class="btn ghost" id="vault-open" type="button">Open in Obsidian</button>
      </div>
```

Change the Memory page's lead text to: `What it knows about you, kept in Memory.md in your Obsidian vault. It reads it at the start of every conversation.`

- [ ] **Step 5: Change `ui/hub.js`**

As the first line inside `loadMemory()`, add:

```js
  $('vault-path').textContent = await api().vault_path();
```

After the `loadMemory` function, add:

```js
$('vault-choose').addEventListener('click', async () => {
  const result = await api().choose_vault();
  if (!result) return;  // closed without choosing
  toast(result.ok ? result.note : result.error);
  await loadMemory();
});

$('vault-open').addEventListener('click', async () => {
  const result = await api().open_vault();
  if (!result.ok) toast(result.error);
});
```

- [ ] **Step 6: Run the tests**

Run: `python -m unittest test_hub_settings test_vault test_memory -v` → all `ok`.

- [ ] **Step 7: See it in the hub (on this PC, Windows folder)**

`python sync_folders.py Mac`. Back up `Windows/user_settings.json` to the scratchpad, then run `Windows/.venv/Scripts/python.exe Windows/hub.py` and open Memory. Expected: the "Kept as notes in" row shows `C:\Users\luzno\Documents\JARVIS Vault`; adding "test fact for the hub" shows it in the list and in `JARVIS Vault/JARVIS/Memory.md`; deleting it removes the line. Take a screenshot and look at the row's layout. **Ask the user before** clicking "Open in Obsidian" or "Change folder" (both touch their Obsidian vault list). Restore `user_settings.json` afterwards if it changed.

- [ ] **Step 8: Checkpoint**

`python check.py` → `ALL CHECKS PASSED`.

---

### Task 7: The setup window asks where to keep the memory

**Files:**
- Modify: `Mac/first_run.py` (`import vault`; `defaults`; new `choose_vault`)
- Modify: `Mac/ui/setup.html` (new `s-vault` screen, a fourth progress dot, step list, `ORB_STATE`, `chooseVoice`, start handler)

**Interfaces:**
- Consumes: `vault.DEFAULT_VAULT`, `user_settings.update_settings`.
- Produces: `SetupApi.defaults()` now also returns `'vault': str`; `SetupApi.choose_vault() -> str | None` (saves `vault` to settings when chosen).

- [ ] **Step 1: Change `first_run.py`**

Add `import vault` after `import user_settings`. Replace `defaults`:

```python
    def defaults(self):
        settings = user_settings.read_settings(self._settings_path)
        return {'assistant': user_settings.DEFAULT_ASSISTANT_NAME, 'face_lock': user_settings.face_lock_on(settings),
                'vault': settings.get('vault') or vault.DEFAULT_VAULT}
```

Add after `save_choices`:

```python
    def choose_vault(self):
        """Lets the user pick the vault folder (JARVIS uses a JARVIS folder inside it)."""
        import webview
        kind = webview.FileDialog.FOLDER if hasattr(webview, 'FileDialog') else webview.FOLDER_DIALOG
        chosen = self._window.create_file_dialog(kind)
        if not chosen:
            return None
        user_settings.update_settings({'vault': chosen[0]}, self._settings_path)
        return chosen[0]
```

- [ ] **Step 2: Change `ui/setup.html`**

Progress: change `<div class="progress" aria-hidden="true"><span></span><span></span><span></span></div>` to four `<span></span>`.

Add after the voice screen's closing `</section>`:

```html
      <!-- memory -->
      <section class="screen" id="s-vault">
        <h1 data-split>Where it<br>remembers</h1>
        <p class="lead">It keeps what it learns about you as notes in an Obsidian vault. Any folder works, even one with your own notes: it only uses a JARVIS folder inside it.</p>
        <label>Vault folder</label>
        <div class="field" id="vault-path"></div>
        <div class="note" id="vault-note" role="status"></div>
        <div class="actions">
          <button class="btn" id="vault-continue">Continue</button>
          <button class="btn ghost" id="vault-choose">Choose another</button>
        </div>
      </section>
```

Add CSS next to the other `#s-...` rules: `#vault-path { overflow-wrap: anywhere; }`

Script changes. Replace the `STEPS` line:

```js
let STEPS = ['s-names', 's-voice', 's-vault', 's-face', 's-hello'];  // without s-face when the face lock is off
```

In `ORB_STATE`, after the `'s-voice'` line: `  's-vault': { energy: 0.5, spread: 0.04, scale: 1, shift: 0 },`

Replace `chooseVoice` (and keep the two `voice-continue` / `voice-refresh` listener lines that follow it, unchanged), then add the vault handlers after them:

```js
async function chooseVoice() {
  await api().set_choices(state.user, state.assistant, state.selected);
  show('s-vault');
}
```

```js
/* ---- memory ----------------------------------------------------------------------------- */
document.getElementById('vault-choose').addEventListener('click', async () => {
  const path = await api().choose_vault();
  if (path) document.getElementById('vault-path').textContent = path;
});
document.getElementById('vault-continue').addEventListener('click', async () => {
  if (STEPS.includes('s-face')) { show('s-face'); startCamera(); return; }
  await api().save_choices();
  sayHello();
});
```

In the `pywebviewready` handler, after `assistantInput.value = d.assistant;`:

```js
  document.getElementById('vault-path').textContent = d.vault;
```

- [ ] **Step 3: See it work (Windows folder, real window)**

`python sync_folders.py Mac`. From `Windows`, run `.venv/Scripts/python.exe -c "import first_run, tempfile, os; d=tempfile.mkdtemp(); print(first_run.run_setup(os.path.join(d,'s.json'), os.path.join(d,'faces')))"`. Expected: names → voice → "Where it remembers" showing `C:\Users\luzno\Documents\JARVIS Vault` → "Choose another" opens a folder picker and the path updates → Continue → hello; the caption counts 3 steps (face lock off). Take a screenshot of the vault screen and look at it. The printed settings include `vault` only if one was chosen.

- [ ] **Step 4: Checkpoint**

`python check.py` → `ALL CHECKS PASSED`.

---

### Task 8: Mac setup installs Obsidian and graphify; notes for the user

**Files:**
- Create: `Mac/add_obsidian.sh` (LF line endings)
- Modify: `Mac/setup_mac.sh` (after `bash add_claude_code.sh`)
- Modify: `Mac/Start JARVIS.command` (after the Claude Code check)
- Modify: `Mac/START HERE (Mac).txt`, `Windows/START HERE (Windows).txt`

**Interfaces:** none (shell and text only).

- [ ] **Step 1: Check the Obsidian release assets (read-only)**

Run: `curl -fsSL https://api.github.com/repos/obsidianmd/obsidian-releases/releases/latest | python -c "import json,sys;print([a['name'] for a in json.load(sys.stdin)['assets'] if a['name'].endswith('.dmg')])"`
Expected: exactly one name like `Obsidian-1.x.y.dmg` (a universal build). If there are several, change the script's filter below to pick the one matching the Mac's chip (`uname -m`).

- [ ] **Step 2: Write `Mac/add_obsidian.sh`**

```bash
#!/bin/bash
# Adds Obsidian, where JARVIS keeps its memory as notes you can read and edit, and graphify,
# which maps those notes as a graph (/graphify in Claude Code). Setup runs this; "Start
# JARVIS.command" runs it once for older installs. Each part can fail without stopping JARVIS,
# which keeps writing its notes either way. To try again later:  bash add_obsidian.sh
cd "$(dirname "$0")"
export PATH="$HOME/.local/bin:$PATH"
ok=1

if [ -d /Applications/Obsidian.app ] || [ -d "$HOME/Applications/Obsidian.app" ]; then
    echo "Obsidian is already installed."
else
    echo "Adding Obsidian, where JARVIS keeps its memory (about 300 MB, once)..."
    url=$(curl -fsSL https://api.github.com/repos/obsidianmd/obsidian-releases/releases/latest | .venv/bin/python -c '
import json, sys
names = [a["browser_download_url"] for a in json.load(sys.stdin).get("assets", []) if a["name"].endswith(".dmg")]
print(names[0] if names else "")')
    mount=$(mktemp -d)
    if [ -n "$url" ] && curl -fL --progress-bar "$url" -o .obsidian.dmg \
            && hdiutil attach -nobrowse -quiet -mountpoint "$mount" .obsidian.dmg \
            && mkdir -p "$HOME/Applications" \
            && cp -R "$mount/Obsidian.app" "$HOME/Applications/"; then
        echo "Obsidian added."
    else
        echo "Obsidian couldn't be added. To add it by hand: https://obsidian.md/download"
        ok=0
    fi
    hdiutil detach -quiet "$mount" 2>/dev/null
    rmdir "$mount" 2>/dev/null
    rm -f .obsidian.dmg
fi

if command -v graphify >/dev/null 2>&1; then
    echo "graphify is already installed."
elif uv tool install graphifyy && graphify install --platform claude; then
    echo "graphify added: in Claude Code, /graphify maps a folder of notes."
else
    echo "graphify couldn't be added. To add it later:  uv tool install graphifyy && graphify install --platform claude"
    ok=0
fi

if [ "$ok" = 1 ]; then rm -f .venv/.no-obsidian; else touch .venv/.no-obsidian; fi
exit 0
```

- [ ] **Step 3: Call it from setup and the start script**

`setup_mac.sh`: after the line `bash add_claude_code.sh`, add `bash add_obsidian.sh`.

`Start JARVIS.command`: after the `fi` that closes the Claude Code check, add:

```bash
# Older installs: add Obsidian and graphify once (skipped after a failed try; run add_obsidian.sh to retry).
if { { [ ! -d /Applications/Obsidian.app ] && [ ! -d "$HOME/Applications/Obsidian.app" ]; } \
     || ! command -v graphify >/dev/null 2>&1; } && [ ! -f .venv/.no-obsidian ]; then
    bash add_obsidian.sh
fi
```

- [ ] **Step 4: Check the scripts**

Run: `bash -n Mac/add_obsidian.sh && bash -n Mac/setup_mac.sh && bash -n "Mac/Start JARVIS.command" && file Mac/add_obsidian.sh`
Expected: no syntax errors; `file` shows no `CRLF`. Then read `add_obsidian.sh` line by line against the spec (it can't run on this PC: `hdiutil` is Mac-only).

- [ ] **Step 5: Update the user notes**

`START HERE (Mac).txt`: in step 2, after "...and Claude Code, which it thinks with.", add ` It also adds Obsidian, where it keeps its memory, and graphify.` Then add this section before `Talking to JARVIS`:

```
Your memory in Obsidian
-----------------------
  JARVIS keeps what it remembers about you in Obsidian, as notes you can read and change:
  the vault folder you picked in setup (Documents > JARVIS Vault unless you chose another),
  in its JARVIS folder. Memory.md holds the facts, one per line starting with "- ": add,
  change or delete lines and JARVIS knows it from the next conversation. Conversations has
  a note for each day you talked. The hub's Memory page shows the same facts, and can move
  them to another vault.
  To see how it all connects, open Claude Code in Terminal and type:
    /graphify "~/Documents/JARVIS Vault/JARVIS" --obsidian
  That uses your Claude plan, so run it when you want a fresh picture, not all the time.
```

`START HERE (Windows).txt`: after step 4, add (indented like the other steps):

```
   JARVIS keeps what it remembers as notes in Documents\JARVIS Vault\JARVIS (Memory.md, and a
   note per day of conversations). Open the folder in Obsidian (obsidian.md) to read and edit
   them; the hub's Memory page can move them to another folder.
```

- [ ] **Step 6: Checkpoint**

`python check.py` → `ALL CHECKS PASSED`.

---

### Task 9: End-to-end check on this PC

**Files:** none changed (verification only).

- [ ] **Step 1: Ask the user first.** This task creates `C:\Users\luzno\Documents\JARVIS Vault`, adds it to their Obsidian vault list (Obsidian must be closed for that), and uses a few Claude requests.

- [ ] **Step 2: Run JARVIS in text mode (Windows folder)**

```bash
cd "/d/Jarvis main v 1/Jarvis-main/Windows"
printf 'remember that my favourite colour is teal\nwhat is my favourite colour\nexit\n' | timeout 300 .venv/Scripts/python.exe -W ignore jarvis.py --text
```

Expected: a short "remembered" reply, then an answer mentioning teal. `Documents/JARVIS Vault/JARVIS/Memory.md` ends with a line about teal; today's note in `Conversations` has both exchanges; `obsidian.json` lists the vault; Obsidian opened on `Memory.md` (take a screenshot and look).

- [ ] **Step 3: Edit by hand, then ask again**

Change the teal line in `Memory.md` to `- My favourite colour is orange`, then run JARVIS again with `what is my favourite colour`. Expected: orange.

- [ ] **Step 4: Forget**

Run with `forget my favourite colour`. Expected: the line is gone from `Memory.md`, and the exchanges mentioning it are gone from the day note.

- [ ] **Step 5: Clean up and report**

Ask the user whether to keep the test vault. Report what was run and seen, including anything that didn't match.
