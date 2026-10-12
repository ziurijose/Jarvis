"""First-run setup window: choose names, pick a voice, scan the user's face, then say hello.

The window is an HTML page (ui/setup.html) in a native window via pywebview, which uses
the system's own web engine (Edge WebView2 on Windows, WebKit on macOS) - that is what
gives it real typography and smooth animation. This module is its Python side: the page
calls the SetupApi methods, and Python pushes camera frames and results back by calling
JavaScript functions (onFrame, onScanProgress, ...).

JARVIS opens this automatically when no user has been set up yet. It can also be run
on its own:  python first_run.py
"""
import base64
import json
import os
import threading
import time

import cv2

import face_enroll
import user_settings
import voices
from platform_utils import IS_MAC, open_camera

UI_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'ui', 'setup.html')
SAMPLE_GAP_SECONDS = 0.25  # spread the photos out so they aren't ten copies of one frame
FRAME_SECONDS = 1 / 20     # preview frame rate sent to the page
PREVIEW_WIDTH = 640


class SetupApi:
    """Methods the page calls through window.pywebview.api. Attributes starting with an
    underscore are hidden from the page (pywebview only exposes public members)."""

    def __init__(self, settings_path, face_dir, speak):
        self._settings_path = settings_path
        self._face_dir = face_dir
        self._speak = speak  # None = speak aloud; tests pass a stand-in
        self._window = None
        self._voices = []
        self._user = ''
        self._assistant = user_settings.DEFAULT_ASSISTANT_NAME
        self._voice = None
        self._camera_stop = threading.Event()
        self._camera_thread = None
        self._scanning = False
        self._count = 0
        self.result = None

    # ---- talking to the page -----------------------------------------------------------

    def _push(self, function, *args):
        try:
            self._window.evaluate_js(f'{function}({", ".join(json.dumps(a) for a in args)})')
        except Exception:
            pass  # window is closing

    def _say(self, text, voice, on_done=None):
        if self._speak is not None:
            self._speak(text)
            if on_done:
                on_done(None)
            return
        voices.say_in_background(voice, text, on_done)

    # ---- names and voice ---------------------------------------------------------------

    def defaults(self):
        face_lock = user_settings.face_lock_on(user_settings.read_settings(self._settings_path))
        return {'assistant': user_settings.DEFAULT_ASSISTANT_NAME, 'face_lock': face_lock}

    def list_voices(self):
        self._voices = voices.all_voices()
        return {'voices': [{'name': v['name'], 'source': v['source']} for v in self._voices],
                'voicebox_count': sum(v['source'] == 'voicebox' for v in self._voices)}

    def preview_voice(self, index, user, assistant):
        voice = self._voices[index]
        self._say(f"Hello, {user}. I'm {assistant}.", voice,
                  on_done=lambda error: self._push('onPreviewDone', error))

    def set_choices(self, user, assistant, index):
        self._user = user.strip()
        self._assistant = assistant.strip() or user_settings.DEFAULT_ASSISTANT_NAME
        self._voice = self._voices[index] if self._voices else None
        return True

    def save_choices(self):
        """Saves the names and voice. Setup ends here when the face lock is off (no face scan)."""
        self.result = user_settings.save_settings(self._user, self._assistant, self._settings_path,
                                                  voice=self._voice)
        return True

    # ---- face scan ---------------------------------------------------------------------

    def start_camera(self):
        self._stop_camera()
        self._camera_stop = threading.Event()
        self._scanning = False
        self._camera_thread = threading.Thread(target=self._camera_loop,
                                               args=(self._camera_stop,), daemon=True)
        self._camera_thread.start()
        return {'needed': face_enroll.SAMPLES_NEEDED}

    def start_scan(self):
        face_enroll.clear_samples(self._face_dir)
        self._count = 0
        self._scanning = True

    def _stop_camera(self):
        self._camera_stop.set()
        if self._camera_thread and self._camera_thread is not threading.current_thread():
            self._camera_thread.join(timeout=2)

    def _camera_loop(self, stop):
        cam = open_camera(0)
        cam.set(3, 640)
        cam.set(4, 480)
        detector = face_enroll.load_detector(self._face_dir)
        last_sample = last_frame = 0.0
        try:
            while not stop.is_set():
                ok, img = cam.read()
                if not ok or img is None:
                    hint = (' On a Mac, allow it in System Settings > Privacy & Security > Camera,'
                            ' then press Retry.') if IS_MAC else \
                           ' Check that a camera is connected and not used by another app.'
                    self._push('onCameraError', "Can't see the camera." + hint)
                    return
                gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
                faces = face_enroll.find_faces(detector, gray)
                height, width = gray.shape
                face = None
                if faces:
                    x, y, w, h = (int(v) for v in faces[0])
                    face = [(width - x - w) / width, y / height, w / width, h / height]  # mirrored
                    now = time.time()
                    if self._scanning and now - last_sample >= SAMPLE_GAP_SECONDS:
                        last_sample = now
                        self._count += 1
                        face_enroll.save_sample(gray[y:y + h, x:x + w], self._count, self._face_dir)
                        self._push('onScanProgress', self._count)
                        if self._count >= face_enroll.SAMPLES_NEEDED:
                            self._scanning = False
                            self._finish_scan()
                            return
                now = time.time()
                if now - last_frame >= FRAME_SECONDS:
                    last_frame = now
                    small = cv2.resize(cv2.flip(img, 1), (PREVIEW_WIDTH, PREVIEW_WIDTH * height // width))
                    ok, jpeg = cv2.imencode('.jpg', small, [cv2.IMWRITE_JPEG_QUALITY, 72])
                    if ok:
                        self._push('onFrame', {'jpeg': 'data:image/jpeg;base64,' +
                                               base64.b64encode(jpeg.tobytes()).decode(), 'face': face})
                else:
                    time.sleep(0.005)
        finally:
            cam.release()

    def _finish_scan(self):
        if face_enroll.train(self._face_dir) == 0:
            self._push('onScanDone', False, 'The photos could not be saved. Press Start scan to try again.')
            return
        self.result = user_settings.save_settings(self._user, self._assistant, self._settings_path,
                                                  voice=self._voice)
        self._push('onScanDone', True, '')

    # ---- hello -------------------------------------------------------------------------

    def say_hello(self):
        self._say(f'Hello, {self._user}', self._voice)

    def finish(self):
        self._stop_camera()
        self._window.destroy()


def run_setup(settings_path: str = user_settings.SETTINGS_PATH,
              face_dir: str = face_enroll.FACE_DIR, speak=None):
    """Show the setup window. Returns the saved settings, or None if it was closed early."""
    import webview
    api = SetupApi(settings_path, face_dir, speak)
    window = webview.create_window('Assistant setup', url=UI_FILE, js_api=api, width=1040,
                                   height=680, min_size=(900, 620), background_color='#0F1113')
    api._window = window
    window.events.closed += api._stop_camera
    webview.start()
    return api.result


if __name__ == '__main__':
    print(run_setup())
