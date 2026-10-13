# JARVIS memory in an Obsidian vault

Date: 2026-10-12. Status: awaiting review.

## Goal

JARVIS's memory (the facts it remembers about the user, and its past conversations) lives as
notes in an Obsidian vault the user can open, read and edit. The Mac setup installs Obsidian and
graphify. Token use stays where it is today.

Success means:
- On a fresh Mac, after setup and the setup window, Obsidian opens a vault with a `JARVIS` folder.
- "Remember that ..." adds a line to `JARVIS/Memory.md`. "Forget ..." removes the matching lines.
- Adding, editing or deleting a fact in Obsidian changes what JARVIS knows from the next conversation on.
- Every exchange also appears in a daily note, `JARVIS/Conversations/YYYY-MM-DD.md`.
- Tokens per request are unchanged: facts still go into the instructions (read from cache), and
  there is no extra lookup round.

## Decisions already made

- Storage option A: the vault notes *are* the memory. There is no second copy of the facts.
- The vault is any folder the user picks. The user may keep their own notes in it. JARVIS reads
  and writes only its `JARVIS/` subfolder.
- Each Mac has its own data. Nothing syncs with the Windows PC.
- The Mac setup installs Obsidian and graphify. The Windows setup installs neither, but the
  memory code is the same (shared files stay identical, see `sync_folders.py`).
- JARVIS never runs graphify. The user runs `/graphify` on the vault when they want a map of it.

## Out of scope

- JARVIS reading the user's other notes in the vault.
- Trimming the per-request token base (the next spec).
- Running graphify from JARVIS, or on every change.

## The vault

Setting `vault` in `user_settings.json`: the vault folder. The default is `~/Documents/JARVIS Vault`
on both platforms (on Windows, `%USERPROFILE%\Documents\JARVIS Vault`).

```
<vault>/
  (the user's own notes, untouched)
  JARVIS/
    Memory.md
    Conversations/
      2026-10-12.md
```

### Memory.md

```markdown
# What JARVIS remembers

JARVIS reads this note at the start of every conversation. Each line starting with "- " is one
thing it remembers: add, change or delete lines as you like.

- My sister's birthday is June 3rd
- I take my coffee black
```

- A fact is a top-level line starting with `- ` (also `* `). Every other line (headings, text,
  indented sub-bullets) belongs to the user and is never changed.
- Remember: appends `- <fact>` at the end of the file.
- Forget "about": deletes every fact line containing `about` (ignoring capitals), in place.
- Hub edit and delete: change or remove the n-th fact line, in place. The hub's existing "was"
  check stays: if the line changed since the page loaded, the edit is refused.
- The 200 limit (`MAX_FACTS`) applies only to what goes into the instructions: the last 200 facts.
  Lines are never deleted to make room.
- When the file is missing, it is created with the header above.

### Conversation notes

One note per day, `JARVIS/Conversations/YYYY-MM-DD.md`, one block per exchange:

```markdown
### 14:52
**Jose:** what's the weather tomorrow
**Jarbungus:** Sunny, high of 84.
```

- Written whenever `recall.record` writes an exchange (the same moment, the same text).
- `conversations.jsonl` and its search index stay as they are: `recall` keeps searching them.
  The daily notes are the readable copy.
- Forget "about" also deletes the matching blocks from every daily note. A note left with no
  blocks is deleted.
- Editing a daily note in Obsidian doesn't change what recall finds.

### Writing safely

- Every write goes to a temporary file first, then `os.replace` (never left half-written).
- One lock covers all vault writes (the hub and JARVIS can write at the same time).
- A vault error never breaks a request: it is printed and the request carries on, the same as
  `recall.record` today. If the vault folder can't be written (for example a removed drive),
  JARVIS says so once in the log and keeps working without memory changes.

## Code

### New shared module: `vault.py`

One clear job: reading and writing JARVIS's notes in the vault.

- `folder()`: `<vault>/JARVIS`, created if missing.
- `facts()`: every fact line, in order.
- `add_fact(text)`, `forget_facts(about)` returns how many went, `edit_fact(index, text, was)`,
  `delete_fact(index, was)`.
- `add_exchange(user_name, assistant_name, you, jarvis, when)`.
- `forget_exchanges(about)` returns how many went.
- `move_to(new_vault)`: moves `JARVIS/` into the new vault. If the new vault already has a
  `JARVIS/` folder, that one is used and the old one is left where it was.
- `migrate()`: on first start, when `memory.json` exists and `Memory.md` doesn't, writes its
  facts into `Memory.md` and renames `memory.json` to `memory.json.bak`.
- `register_with_obsidian()`: adds the vault to Obsidian's vault list so it shows up in
  Obsidian's vault switcher. The list is `obsidian.json` in Obsidian's settings folder
  (`~/Library/Application Support/obsidian/` on a Mac, `%APPDATA%\obsidian\` on Windows): an
  entry `{"path": ..., "ts": <ms>, "open": true}` under a new 16-hex-digit id. It is written only
  when Obsidian is installed and the vault isn't already listed, and only while Obsidian isn't
  running (Obsidian rewrites the file when it quits). The first implementation step checks this
  format against a real Obsidian install.
- `open_in_obsidian()`: opens the vault (`obsidian://open?path=...`).

### Changes to existing files (all shared unless noted)

- `brain.py`: `load_memory`, `remember` and `forget` use `vault`. The tool descriptions don't change.
- `recall.py`: `record` also calls `vault.add_exchange`. `forget` also calls `vault.forget_exchanges`.
- `hub_api.py`: the memory list, add, edit and delete use `vault`. A new `vault` setting has a
  "Choose..." folder picker. Saving a new folder calls `vault.move_to`, then `register_with_obsidian`.
- `ui/hub.html`, `ui/hub.js`: a "Vault folder" row in the Memory section, with Choose... and Open in Obsidian.
- `first_run.py` and the setup page in `ui/`: a "Vault folder" row with the default and Choose....
  When setup finishes: create the folder, `migrate`, `register_with_obsidian`, `open_in_obsidian`.
- `jarvis.py`: at start, `vault.migrate()` (for existing installs).
- `user_settings.py`: default for `vault`.
- Mac only: new `add_obsidian.sh`, run by `setup_mac.sh` (and once by `Start JARVIS.command` for
  existing installs, unless `.venv/.no-obsidian` is there):
  - Obsidian: skipped if `Obsidian.app` is in `/Applications` or `~/Applications`. Otherwise it
    finds the latest Mac `.dmg` among the releases of github.com/obsidianmd/obsidian-releases,
    downloads it, mounts it (`hdiutil attach -nobrowse`), copies `Obsidian.app` to `~/Applications`
    (no password needed) and unmounts it.
  - graphify: `uv tool install graphifyy`, then `graphify install --platform claude` (adds the
    `/graphify` skill to Claude Code).
  - Each part can fail without stopping setup. It prints what to do by hand, and writes
    `.venv/.no-obsidian` so the start script doesn't retry every time.
- Mac only: `START HERE (Mac).txt` gets a "Your memory in Obsidian" section: where the vault is,
  that it can be edited, and how to map it with `/graphify "<vault>/JARVIS" --obsidian` in Claude Code.

The install script can't create the vault, because it runs before the setup window where the
folder is chosen. The vault is created when the setup window finishes.

## Testing

- `test_vault.py` (new): reading fact lines; leaving the user's other lines alone; append; forget
  in place; edit and delete with the "was" check; the 200 limit only on what is loaded; daily note
  blocks; forgetting across daily notes and deleting empty ones; `move_to` both ways; migration;
  writes are atomic; a vault that can't be written doesn't raise; registering with Obsidian against
  a temporary `obsidian.json`.
- `test_memory.py` and `test_hub_settings.py`: updated to use a temporary vault.
- `python check.py` passes (folders match, compile, flake8, all tests).
- On this PC: JARVIS in text mode. Say "remember ...", see the line in `Memory.md`. Edit the line
  by hand and ask about it in a new conversation. "Forget ...", see it gone from `Memory.md` and
  the daily note. The hub's memory list shows the same lines. Change the vault in the hub and see
  the folder move. If Obsidian is installed here, the vault appears in its vault list.
- The Mac script can't be run from this PC. It is read through line by line, and the user runs it
  once on the Mac; its messages say what happened.
