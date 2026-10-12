"""Finding a microphone by name (sounddevice ships PortAudio, so no extra install is needed)."""
SAMPLE_RATE = 16000  # what speech recognition expects; the OS resamples from the device


def find_input_device(name_part):
    """Index of the first input device whose name contains name_part and can record at
    SAMPLE_RATE, or None for the system default."""
    if not name_part:
        return None
    import sounddevice as sd
    for index, device in enumerate(sd.query_devices()):
        if device['max_input_channels'] > 0 and name_part.lower() in device['name'].lower():
            try:
                sd.check_input_settings(device=index, samplerate=SAMPLE_RATE,
                                        channels=1, dtype='int16')
                return index
            except Exception:
                continue  # this host API can't do 16 kHz mono; try the same mic via another
    return None


SILENT_LEVEL = 2.0  # loudness (RMS) below which an input is dead: real mics hear the room
# Inputs that carry what the computer plays, not what the user says.
LOOPBACK_WORDS = ('voicemeeter', 'stereo mix', 'what u hear', 'loopback', 'cable output', 'wave out')


def find_live_input(seconds=0.4):
    """(index, name) of the first real microphone that picks up sound, or None.

    For when the default input is dead quiet: that is a virtual or disconnected device (e.g.
    an unused Voicemeeter output), never a real microphone in a real room. Loopback inputs
    are skipped, since they would hear the computer's own sound instead of the user."""
    import numpy as np
    import sounddevice as sd
    tried = set()
    for index, device in enumerate(sd.query_devices()):
        name = device['name']
        if (device['max_input_channels'] < 1 or name in tried
                or any(word in name.lower() for word in LOOPBACK_WORDS)):
            continue
        tried.add(name)  # each device appears once per Windows audio system; one try is enough
        try:
            audio = sd.rec(int(SAMPLE_RATE * seconds), samplerate=SAMPLE_RATE, channels=1,
                           dtype='int16', device=index)
            sd.wait()
        except Exception:
            continue
        samples = audio.astype(np.float32).ravel()
        if np.sqrt((samples * samples).mean()) >= SILENT_LEVEL:
            return index, name
    return None
