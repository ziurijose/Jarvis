# J.A.R.V.I.S for Mac and Windows

A voice assistant for your Mac or Windows PC. Say **"Hey"** and its name (the one you picked in
setup, or "Jarvis") and what you want, in one breath. Claude understands it, however you phrase
it, and acts on your computer.

Based on [gauravsingh9356/J.A.R.V.I.S](https://github.com/gauravsingh9356/J.A.R.V.I.S) (MIT licence).

## Two folders

**Mac** and **Windows** each hold a complete JARVIS: copy or download just the folder for your
computer and keep it somewhere you won't move it (it installs into that folder). Most files are
the same in both. After changing one of those, run `python sync_folders.py Mac` (or `Windows`) to
copy the change to the other folder; CI checks that they match.

## Start

In the **Mac** folder, double-click **Start JARVIS.command**. The first time, it installs what it needs into this folder
(a few minutes; no admin password or Homebrew). Then a setup window asks for your name, a name
for the assistant and its voice. Allow **microphone** access for Terminal when macOS asks.
"START HERE (Mac).txt" has the step-by-step version.

To run setup again (a new user), delete `user_settings.json` and start JARVIS.

## The hub

Every setting lives in one window: **Open hub** in the menu bar or tray menu, or double-click
**Open JARVIS Hub.bat** in the Windows folder (`python hub.py` in the Mac folder). On a Mac it also
opens by itself whenever Start JARVIS.command starts JARVIS. Home shows what JARVIS is doing
right now, with Start, Restart and Quit, and a **Microphone** switch: off closes the microphone
straight away (nothing is heard, not even its name, and the mic-in-use light goes out) until
you turn it back on. It needs no Save or restart, and stays as you left it next time. Settings has its name and yours, its voice (press play
to hear each one), the brain (the model, how hard it thinks),
listening, the face lock and start-up options. **Save** restarts JARVIS so the changes take
effect. It answers to any name you give it, short ones like "Max" included, and "Hey Jarvis"
keeps working too.

## Typing instead of talking

To type to JARVIS in a terminal, open one in its folder and run

    .venv\Scripts\python.exe jarvis.py --text      (Windows, in the Windows folder)
    .venv/bin/python jarvis.py --text              (Mac, in the Mac folder)

Type a request and press Enter; the answer prints as it's written. It's the same JARVIS (same
brain, tools, memory and quick commands), with no microphone, menu bar or orb. Add `--speak` to
hear the answers too. Ctrl+C stops an answer; `exit` quits. Run Start JARVIS once first, so it's
installed.

## The brain: Claude Code

JARVIS thinks with [Claude Code](https://claude.com/claude-code), signed in with your Claude
account, so it uses your Claude plan. No API key is needed, and JARVIS never asks for one. On a
Mac, setup installs Claude Code for you; on Windows, install it from that link. Either way, sign
in once ("START HERE" has the steps). Without it, JARVIS says so and doesn't start.

In the hub, pick Claude's model and how hard it thinks: Fast (the default, quickest to answer),
Balanced or Deep. By hand, these are `"claude_model"` and `"claude_effort"` (see Settings).

## On your phone

`phone/jarvis-phone.html` is a phone version, published as a claude.ai page: open it in your
phone's browser while signed in to claude.ai. Type, or tap the box and use your keyboard's
microphone; it answers out loud, sets timers, shows a button for searches and videos, and
remembers things about you. It uses your Claude plan, needs no API key, and can't control the
phone's own apps. Timers only ring while the page is open.

## On Windows

In the **Windows** folder, double-click **Start JARVIS.bat** ("START HERE (Windows).txt" has the steps). It installs the same
way (no admin password), and works the same, with these differences:

- **Hotkey:** Ctrl+Alt+J (Alt+Space opens every window's menu on Windows). JARVIS's icon sits in
  the system tray by the clock, with Open hub, Talk, Start when I sign in, Show log and Quit.
- **What it can do:** open and close apps (found through the Start menu), control whatever is
  playing (Spotify first) and the volume, look at the screen, screenshots, CPU and battery, web
  search, YouTube downloads and memory, as on a Mac. Notes are text files in Documents\JARVIS
  Notes; reminders are kept by JARVIS and said aloud when due (while it is running); emails open
  as a draft in your mail app for you to send. Windows has no general equivalent of Calendar,
  iMessage or Apple Shortcuts, so those aren't offered.
- **Microphone:** if Windows' default input is a silent virtual device (an unused Voicemeeter
  output, for example), JARVIS switches to a microphone that hears something and says which.

## Talking to it

- **Wake it:** "Hey Jarvinky, what's the weather tomorrow?" (its name, or "Jarvis"), or press
  Option+Space, or click Talk in the menu bar. Then just keep talking: after each answer it
  listens for 10 seconds, no wake word needed. The conversation ends when you go quiet for 10
  seconds or wrap up ("thanks, that's all", "ok bye"); a falling chime says it's waiting for its
  name again. Pausing to think is fine: it keeps listening through short pauses.
- **Memory that lasts:** its memory is your Obsidian vault (`Documents\JARVIS Vault` unless you
  pick another in the hub), kept only on this computer. When you mention something worth knowing
  later (people, plans, preferences), it saves it to `JARVIS/Memory.md` by itself, and every
  exchange goes into a day note in `JARVIS/Conversations`. Each conversation is forgotten when it
  ends, which keeps it fast, but nothing is lost: ask "what were we just talking about?", "what was
  that restaurant I mentioned?" or "what's in my pasta notes?" and it searches the whole vault,
  as it is now in Obsidian (your edits and your own notes included), however old. Its newest 60
  facts are in every request; it looks up older ones when they might matter. To quit JARVIS
  itself, say "shut down" or "go to sleep".
  - The first start downloads the search model (about 24 MB) in the background; until then it
    matches keywords.
  - "Forget that..." removes it from Memory.md and the day notes; deleting or editing lines in
    Obsidian works too. To clear all history, delete the `JARVIS` folder in the vault, and
    `conversations.jsonl` and `recall_index.npz`, while JARVIS is closed.
  - Anyone who calls JARVIS can ask about past conversations (the face lock, when it is on, only
    runs at start-up).
- **Calling it:** start or end the sentence with its name ("Hey Jarvis, ...", "OK Jarvis ...",
  "..., Jarvis?"). Its name in the middle of a sentence (on TV, in a song) is a mention, not a call.
- **Web pages:** before Claude opens a page, JARVIS checks it against the abuse.ch and OpenPhish
  lists of malware and phishing pages (`fetch_guard.py`) and blocks those, as well as addresses on
  this computer or the home network. Everything else stays open.
- **Interrupt it:** talk over it. It stops straight away, drops what it was doing, and listens to
  you instead. With headphones a word or two is enough; on the Mac's speakers, speak up (it has to
  tell your voice from its own), or say "Hey Jarvis" clearly, louder than its voice. If you pause
  and carry on while it is still thinking, it puts both parts together.
- **What it can do:** open and quit apps, control music and volume, look at your screen, take
  screenshots, check CPU and battery, run your Apple Shortcuts, read and add calendar events,
  reminders and notes, send iMessages and emails (it reads them back and only sends after you say
  yes; this is enforced in the code), search the web, download the YouTube video you copied, and
  remember facts about you (`JARVIS/Memory.md` in the vault). Websites open in Google Chrome unless you name
  another browser.
- **Mouse and keyboard:** it can use them like you do. Say "press enter", "scroll down", "type
  hello" and it just does it; say "click Send" or "open my last email" and it looks at the screen,
  clicks and types, and checks the result. It doesn't ask first, and long tasks keep going until
  they're done. To stop it mid-task, talk, press the hotkey, or push the mouse into a corner of
  the screen.
- **Your Chrome:** with `"chrome_browser"` in `user_settings.json` (the Claude in Chrome extension's
  device id), it reads and acts on web pages directly in your own Chrome, signed in as you: a
  whole page in one read, or many items in one step (every Unsubscribe link at once). For a click
  or two on the page in front of you it uses the screen, which is quicker for that.
- **Commands:** when it's quicker than clicking (files, folders, settings, installs), it runs a
  PowerShell command (zsh on a Mac) itself (`commands.py`). Commands that delete or overwrite
  files wait until it has said what they'll do and you've said yes; this is enforced in the
  code. Talking stops a running command, and a long wait, straight away.

## How it's fast

- **Hearing:** [Whisper](https://github.com/SYSTRAN/faster-whisper) speech recognition and the
  "Hey Jarvis" wake word run on your Mac. The name is spotted in the same sentence as the request,
  so "Hey Jarvinky, open Chrome" is heard once and acted on straight away.
- **Thinking:** Claude streams its answer, and JARVIS starts speaking at the first sentence.
  One Claude Code session is started when JARVIS starts and kept open, instead of a new one for
  every request. It loads only what JARVIS needs, not your own Claude Code plugins, hooks or
  CLAUDE.md, so it starts sooner and each request uses fewer tokens.
- **Simple commands skip Claude:** "pause", "next song", "volume 40", "open Spotify", "close
  Chrome", "google pasta recipes", "what time is it" and the like are done by JARVIS itself, at
  once and without using your Claude plan (`quick.py`). Anything more goes to Claude.
- **Voice:** [Kokoro](https://github.com/thewh1teagle/kokoro-onnx) speaks on your Mac, each sentence
  playing while the next is generated.

## Settings (`user_settings.json`)

| Setting | What it does |
| --- | --- |
| `"assistant_name"` | The assistant's name (the hub sets it); restart JARVIS after changing it by hand |
| `"claude_model"` | The Claude model, e.g. `"claude-haiku-5-5"` (Claude Code also takes `"haiku"`, `"sonnet"`, `"opus"`) |
| `"claude_effort"` | How hard Claude thinks: `"low"` (default, fastest) up to `"high"` |
| `"barge_in": false` | Talking over JARVIS no longer interrupts it; only "Hey Jarvis" and the hotkey do |
| `"wake_word": false` | Turn off the "Hey Jarvis" detector; JARVIS still wakes to its name |
| `"microphone"` | Part of a microphone's name, to use one other than the system default |
| `"language"` | e.g. `"es-ES"`, for speech in another language |
| `"hotkey"` | e.g. `"<cmd>+<shift>+j"` instead of Option+Space |
| `"face_lock": true` | Turn the face lock on (also in the hub): JARVIS scans your face at the next start and then starts only for you. `"face_lock_threshold"` (default 80) sets how strict |

`JARVIS_WHISPER_MODEL` (environment) picks the speech model: `small.en` on Apple silicon by
default, `tiny.en` or `base.en` for more speed, `medium.en` for more accuracy.
