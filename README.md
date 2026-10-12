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
(a few minutes; no admin password or Homebrew). Then a setup window asks for your name and a name
for the assistant, and scans your face for the face lock. Allow **camera** and **microphone**
access for Terminal when macOS asks. "START HERE (Mac).txt" has the step-by-step version.

To run setup again (new user or new face), delete `user_settings.json` and start JARVIS.

## The hub

Every setting lives in one window: **Open hub** in the menu bar or tray menu, or double-click
**Open JARVIS Hub.bat** in the Windows folder (`python hub.py` in the Mac folder). Home shows what JARVIS is doing
right now, with Start, Restart and Quit. Settings has its name and yours, its voice (press play
to hear each one), the brain (Claude Code or an API key, the model, how hard it thinks),
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

## The brain: a free model on your computer, Claude when needed

JARVIS thinks with a free model running on your own computer, through
[TurboLLM](https://github.com/mohitsoni48/TurboLLM). Claude Code (signed in with your Claude
account) takes over only when it has to: while the local model is getting ready, if it stops or
fails, or when a request is beyond it (long tasks on the screen, careful reasoning, code), which
it decides itself. You can't hear the difference: both get the same personality and rules,
JARVIS's own voice speaks for both, nothing announces a switch, and each one knows what the other
said.

**First start** (needs [Node.js](https://nodejs.org) 22.13 or newer): JARVIS starts TurboLLM in
the background, checks your graphics card's memory, and downloads the fastest model it runs well
that can also see the screen and use JARVIS's tools:

| Graphics memory | Model | |
| --- | --- | --- |
| 22 GB or more | Gemma 4 26B-A4B (4-bit) | only 4B of its 26B run per word: fast, and smarter |
| 7 to 22 GB | Gemma 4 E4B (4-bit) | about 4.5B: very fast |
| less, or none | Gemma 4 E4B (3-bit) | |

On an AMD Radeon it times both of TurboLLM's engines, ROCm and Vulkan, and keeps the quicker
(not every Radeon runs ROCm well). This takes a few minutes once (the model is 5 to 7 GB); Claude
Code answers in the meantime. Later starts take seconds.

To look something up, the local model opens the search results in your browser and reads them
off the screen, scrolling and clicking like you would.

**Choosing:** `"brain"` in `user_settings.json` is `"auto"` (the default, as above), `"local"`
(only the local model, never Claude) or `"claude"` (only Claude: Claude Code, or the API with
`anthropic_api_key`). For one run, start JARVIS with `--local` or `--claude`. Other optional
settings: `"local_model"` (a model by name instead), `"local_url"` (another server, such as LM
Studio's `http://localhost:1234/v1` or Ollama's `http://localhost:11434/v1`), `"local_vision":
false` for a model that can't see images, and `"local_api_key"` if the server is shared with a
key. JARVIS writes `"local_backend"` (the engine it chose); delete it to time the engines again.

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
- **Forgetting and remembering:** each conversation is forgotten when it ends, which keeps it fast.
  Ask "what were we just talking about?" or "what was that restaurant I mentioned?" and it looks
  back through past conversations (kept only on this computer, in `conversations.jsonl`). To quit
  JARVIS itself, say "shut down" or "go to sleep".
  - The first start downloads the search model (about 24 MB) in the background; until then it
    matches keywords.
  - "Forget that..." also removes it from past conversations. To clear all history, delete
    `conversations.jsonl` and `recall_index.npy` while JARVIS is closed.
  - Anyone who calls JARVIS can ask about past conversations (the face lock only runs at start-up).
- **Interrupt it:** talk over it. It stops straight away, drops what it was doing, and listens to
  you instead. With headphones a word or two is enough; on the Mac's speakers, speak up (it has to
  tell your voice from its own), or say "Hey Jarvis", which always works. If you pause and carry on
  while it is still thinking, it puts both parts together.
- **What it can do:** open and quit apps, control music and volume, look at your screen, take
  screenshots, check CPU and battery, run your Apple Shortcuts, read and add calendar events,
  reminders and notes, send iMessages and emails (it reads them back and only sends after you say
  yes; this is enforced in the code), search the web, download the YouTube video you copied, and
  remember facts about you (`memory.json`). Websites open in Google Chrome unless you name
  another browser.
- **Mouse and keyboard:** it can use them like you do. Say "press enter", "scroll down", "type
  hello" and it just does it; say "click Send" or "open my last email" and it looks at the screen,
  clicks and types, and checks the result. It doesn't ask first. To stop it mid-task, talk, press
  the hotkey, or push the mouse into a corner of the screen.

## How it's fast

- **Hearing:** [Whisper](https://github.com/SYSTRAN/faster-whisper) speech recognition and the
  "Hey Jarvis" wake word run on your Mac. The name is spotted in the same sentence as the request,
  so "Hey Jarvinky, open Chrome" is heard once and acted on straight away.
- **Thinking:** Claude streams its answer, and JARVIS starts speaking at the first sentence.
  With Claude Code, one session is started when JARVIS starts and kept open, instead of a new one
  for every request.
- **Simple commands skip Claude:** "pause", "next song", "volume 40", "open Spotify", "close
  Chrome", "google pasta recipes", "what time is it" and the like are done by JARVIS itself, at
  once and without using your Claude plan or credit (`quick.py`). Anything more goes to Claude.
- **Voice:** [Kokoro](https://github.com/thewh1teagle/kokoro-onnx) speaks on your Mac, each sentence
  playing while the next is generated.

## Claude

When JARVIS needs Claude (see "The brain" above), it uses [Claude Code](https://claude.com/claude-code)
signed in with your Claude account, or a Claude API key if you saved one and Claude Code isn't
installed (`anthropic_api_key` in `user_settings.json`; API use is billed to your Console account).

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
| `"face_lock": false` | Turn the face lock off (or set `"face_lock_threshold"`, default 80) |

`JARVIS_WHISPER_MODEL` (environment) picks the speech model: `small.en` on Apple silicon by
default, `tiny.en` or `base.en` for more speed, `medium.en` for more accuracy.
