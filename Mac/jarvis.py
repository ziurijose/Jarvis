"""JARVIS: a voice assistant for your Mac or Windows PC.

Start-up: first-run setup (once) -> Claude key (asked once) -> face lock -> conversation.
The conversation: say "Hey Jarvis" (or press the hotkey, or click Talk in the menu bar),
then talk back and forth; no wake word is needed until the conversation ends (10 quiet
seconds, or you wrap up). Claude (brain.py) understands it and acts with JARVIS's tools, and
forgets each conversation when it ends (recall.py can look it up). While JARVIS answers, talk
over it (or say "Hey Jarvis") to stop it and say something new.
"""
import datetime
import faulthandler
import os
import sys
import threading
import time

LOG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'jarvis.log')


class _Tee:
    """Sends what JARVIS prints to the Terminal and to jarvis.log, so a failure can be read
    afterwards. (Started at login, the log already gets everything.)"""

    def __init__(self, stream, log):
        self.stream, self.log = stream, log

    def write(self, text):
        for out in (self.stream, self.log):
            try:
                out.write(text)
                out.flush()
            except Exception:
                pass
        return len(text)

    def flush(self):
        for out in (self.stream, self.log):
            try:
                out.flush()
            except Exception:
                pass

    def __getattr__(self, name):
        return getattr(self.stream, name)


def _start_log():
    if sys.stdout is None:  # started without a console (Windows "Start when I sign in"): log only
        log = open(LOG_PATH, 'w', encoding='utf-8', buffering=1)
        sys.stdout = sys.stderr = log
        faulthandler.enable(file=log, all_threads=True)
    elif sys.stdout.isatty():
        log = open(LOG_PATH, 'w', encoding='utf-8', buffering=1)
        sys.stdout, sys.stderr = _Tee(sys.stdout, log), _Tee(sys.stderr, log)
        faulthandler.enable(file=log, all_threads=True)  # even a hard crash leaves a trace
    else:
        faulthandler.enable(all_threads=True)
    print(f'JARVIS starting {datetime.datetime.now():%Y-%m-%d %H:%M:%S}, Python {sys.version.split()[0]}')


if __name__ == '__main__':
    _start_log()

import face_enroll
import helpers
import listen
import recall
import voices as voice_lib
from brain import Sleep, cli_brain, make_brain
from helpers import hud, speak
from platform_utils import open_camera
from user_settings import load_settings, update_settings


# ---- talking with Claude ----------------------------------------------------------------

STOP_WORDS = {'stop', 'stop it', 'stop talking', 'never mind', 'nevermind', 'cancel', 'quiet', 'be quiet',
              'shut up', 'jarvis stop', 'okay stop', 'ok stop', "that's enough", 'enough', 'thanks', 'thank you'}


FOLLOW_UP_SECONDS = 10  # after each answer, how long JARVIS waits for you to say more


def end_conversation(brain_) -> None:
    """Back to waiting for the wake word: a falling chime, and Claude forgets the
    conversation (recall.py still has it)."""
    print('Conversation over.')
    listen.end_chime()
    try:
        brain_.forget_conversation()
    except Exception as error:  # forgetting is housekeeping; JARVIS must keep listening
        print(f'Could not start a fresh conversation: {error}')


def greet(settings) -> None:
    hour = datetime.datetime.now().hour
    part = 'morning' if hour < 12 else 'afternoon' if hour < 18 else 'evening'
    name = (settings.get('assistant_name') or 'Jarvis').capitalize()
    speak(f"Good {part}, {settings.get('user_name', 'Sir')}. Say hey {name} whenever you need me.")


def respond(brain_, text, hear):
    """Has Claude answer text out loud. Talking over it, saying "Hey Jarvis" or pressing the
    hotkey stops it. Returns (interrupted, what was said, whether anything was said aloud yet);
    interrupted means the user is already saying something new."""
    def now_saying(piece):
        hud('show SPEAKING')
        hud('caption ' + piece)
    speech = voice_lib.Speech(helpers.VOICE, on_piece=now_saying)
    interrupted, done = threading.Event(), threading.Event()

    def watch_for_interruptions():
        if hear.wait_for_interrupt(stop=done):
            interrupted.set()
            speech.stop()
            print('(interrupted)')
    watcher = threading.Thread(target=watch_for_interruptions, daemon=True)
    watcher.start()
    hud('show THINKING')
    hud(f'caption “{text}”')
    sleeping, said = False, ''
    try:
        said = brain_.handle(text, speech, interrupted)
        if said:
            print(f'{brain_.name}: {said.strip()}\n')
    except Sleep:
        sleeping = True
    except Exception as error:
        message = brain_.problem(error)
        if message is None:
            import traceback
            traceback.print_exc()
            message = 'Sorry, something went wrong there.'
        print(message)
        speech.feed(message)
    speech.finish()
    speech.wait()
    hud('hide')
    done.set()
    watcher.join(timeout=1)  # so it can't take audio meant for the next request
    if sleeping:
        sys.exit()
    return interrupted.is_set(), said, speech.spoke


def converse(settings, brain_) -> None:
    """Wait to be called ("Hey Jarvinky"), then talk back and forth without the wake word.
    The conversation ends after FOLLOW_UP_SECONDS of quiet, when JARVIS says goodbye (Claude's
    end marker) or on a stop word; then Claude forgets it."""
    hear = helpers.hearing()
    talking, keep_audio, cut_off, last, conv = False, False, None, '', None
    while True:
        text = None
        if not talking:
            print('Waiting to be called...')
            text = hear.wait_for_wake()  # the request said with the name, or '' (it follows)
            keep_audio = True
            if not text:
                listen.chime()
        if not text:
            print('Listening...')
            hud('caption ')
            # Time to start talking: generous, so a pause to think doesn't lose the request.
            audio = hear.listen(on_listening=lambda: hud('show LISTENING'),
                                wait_seconds=FOLLOW_UP_SECONDS, fresh=not keep_audio)
            if audio:
                hud('show RECOGNIZING')
            text = hear.transcribe(audio) if audio else None
            hud('hide')
        if not text:
            if talking:  # nothing more to say
                end_conversation(brain_)
            talking, cut_off = False, None
            continue
        print(f'User said: {text}')
        if listen.clean(text) in STOP_WORDS:  # "Hey Jarvinky, stop": already quiet
            if talking:
                end_conversation(brain_)
            talking, cut_off = False, None
            continue
        if not talking:
            conv = recall.start_conversation()
            talking = True
        request = text
        if cut_off == 'thinking':  # they kept talking after a pause: it's all one request
            request = text = f'{last} {text}'
        elif cut_off == 'speaking':  # so Claude knows its answer was cut short, and changes course
            request = f'(I interrupted you.) {text}'
        interrupted, said, spoke = respond(brain_, request, hear)
        last = text
        if said or not interrupted:  # a request cut off before any answer is said again in full
            recall.record(conv, text, said)
        cut_off = ('speaking' if spoke else 'thinking') if interrupted else None
        if getattr(brain_, 'broken', False):
            fallback = cli_brain(settings)
            if fallback:
                brain_ = fallback
                helpers.BRAIN_NAME = brain_.name
                speak('I will use Claude Code instead for now.')
        keep_audio = bool(cut_off)
        if getattr(brain_, 'ended', False) and not cut_off:  # Claude said goodbye
            end_conversation(brain_)
            talking = False


def ask_for_claude_key(settings) -> dict:
    """Once: offer to save a Claude API key (the fastest brain). Enter skips."""
    if 'anthropic_api_key' in settings or not sys.stdin.isatty():
        return settings
    print('\nJARVIS can use Claude to understand anything you say.')
    print('Fastest: a Claude API key (with credit) from https://platform.claude.com/settings/keys')
    print('Or press Enter to use Claude Code with your Claude account, if it is installed.')
    import getpass
    key = getpass.getpass('Claude API key (hidden as you paste, Enter to skip): ').strip()
    if key:
        try:
            import anthropic
            anthropic.Anthropic(api_key=key).models.list(limit=1)
            print('Key works.')
        except Exception as error:
            print(f'That key did not work ({error}); skipping it. Add it to user_settings.json later.')
            key = ''
    return update_settings({'anthropic_api_key': key})


def wakeUpJARVIS(settings, brain_):
    print(f'Brain: {brain_.name}')
    if sys.platform == 'win32':  # Windows reminders are JARVIS's own: it says each one when due
        import windows
        windows.watch_reminders(lambda text: speak(f'Reminder: {text}'))
    greet(settings)
    converse(settings, brain_)


# ---- face lock ----------------------------------------------------------------------------

def face_check(settings) -> None:
    """Returns once the enrolled face has been recognised in 3 frames in a row.

    The model scores each face by distance (0 is a perfect match). The old check accepted
    anything under 100, which let other people in; 80 is stricter. If it keeps refusing you,
    lower lighting differences or set "face_lock_threshold" (e.g. 90) in user_settings.json,
    or "face_lock": false to turn it off.
    """
    import cv2
    if settings.get('face_lock') is False:
        return
    threshold = float(settings.get('face_lock_threshold', 80))
    recognizer = cv2.face.LBPHFaceRecognizer_create()  # Local Binary Patterns Histograms
    recognizer.read(face_enroll.model_path())
    detector = face_enroll.load_detector()
    def start_camera():
        camera = open_camera(0)
        camera.set(3, 640)
        camera.set(4, 480)
        return camera

    cam = start_camera()
    print('Looking for your face... face the camera.')
    streak, best, started, warned, last_print, failures = 0, None, time.time(), False, 0.0, 0
    unseen_warned = False
    try:
        while True:
            ok, img = cam.read()
            if not ok:
                failures += 1
                if failures <= 3:  # a camera that stopped once usually works when reopened
                    cam.release()
                    time.sleep(0.5)
                    cam = start_camera()
                    continue
                print('Could not read from the camera. Check it is connected and that this terminal is '
                      'allowed to use it (macOS: System Settings > Privacy & Security > Camera; '
                      'Windows: Settings > Privacy & security > Camera).')
                sys.exit(1)
            failures = 0
            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
            faces = face_enroll.find_faces(detector, gray)
            if not faces:
                streak = 0
                # Without this, a camera aimed away from the user waits in silence forever.
                if best is None and not unseen_warned and time.time() - started > 15:
                    unseen_warned = True
                    print("No face seen yet. Check the camera is pointing at you (and isn't covered), "
                          'or set "face_lock": false in user_settings.json.')
                    speak("I can't see a face. Check the camera is pointing at you.")
                continue
            x, y, w, h = faces[0]  # the largest face: the person at the computer
            _id, distance = recognizer.predict(gray[y:y + h, x:x + w])
            best = distance if best is None else min(best, distance)
            if time.time() - last_print > 1:
                print(f'Face distance {distance:.0f} (needs under {threshold:.0f})')
                last_print = time.time()
            streak = streak + 1 if distance < threshold else 0
            if streak >= 3:
                speak('Face recognised. Welcome back.')
                return
            if not warned and time.time() - started > 15:
                warned = True
                speak("I don't recognise you yet. Face the camera in good light.")
                if best is not None and best < threshold + 25:
                    print(f'Closest match so far: {best:.0f}. If this is you, set "face_lock_threshold": '
                          f'{int(best) + 10} in user_settings.json, or redo the face scan.')
    finally:
        cam.release()


if __name__ == '__main__':
    # First run on this computer (no user yet, or no face model): show the setup window.
    settings = load_settings()
    if settings is None or not os.path.exists(face_enroll.model_path()):
        from first_run import run_setup
        settings = run_setup()
        if settings is None:
            print('Setup was closed before it finished. Run JARVIS again to continue.')
            sys.exit(0)
    helpers.HUD_TITLE = settings['assistant_name']
    helpers.VOICE = settings.get('voice')
    settings = ask_for_claude_key(settings)
    brain_ = make_brain(settings)    # Claude Code starts in the background
    if brain_ is None:
        message = ('I need Claude to work. Install Claude Code from claude.com/claude-code and sign in, '
                   'or add a Claude API key to user_settings.json.')
        print(message)
        speak(message)
        sys.exit(1)
    helpers.BRAIN_NAME = brain_.name
    helpers.write_status()  # the hub can see JARVIS is running from now on
    helpers.start_hearing(settings)  # loads speech recognition while your face is checked
    voice_lib.warm_up()              # and the voice
    recall.warm_up()                 # and conversation search (downloads its model the first time)
    try:
        # Whisper brings its own copy of the Mac's camera code (PyAV). Loaded while the camera
        # is running, it breaks the camera, so it is loaded before the face check opens it.
        import faster_whisper  # noqa: F401
    except ImportError:
        pass
    face_check(settings)

    import menubar
    menubar.run(lambda: wakeUpJARVIS(settings, brain_), settings)
