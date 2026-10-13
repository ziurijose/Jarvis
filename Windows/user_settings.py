"""The user's name and the assistant's name, chosen in first-run setup."""
import json
import os

SETTINGS_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'user_settings.json')
DEFAULT_ASSISTANT_NAME = 'JARVIS'


def save_json(path: str, data, **options) -> None:
    """Writes data as JSON to path all at once: into a temporary file that then replaces path,
    so a crash or a forced quit part way through leaves the old file whole, never half of one."""
    temporary = path + '.tmp'
    with open(temporary, 'w', encoding='utf-8') as f:
        json.dump(data, f, **options)
    os.replace(temporary, path)


def load_settings(path: str = SETTINGS_PATH):
    """Return {'user_name', 'assistant_name', 'voice'}, or None if setup hasn't been done yet.
    'voice' is None when no voice was chosen (the system default voice is used)."""
    try:
        with open(path, encoding='utf-8') as f:
            settings = json.load(f)
    except (OSError, ValueError):
        return None
    if not settings.get('user_name'):
        return None
    settings.setdefault('assistant_name', DEFAULT_ASSISTANT_NAME)
    settings.setdefault('voice', None)
    return settings


def read_settings(path: str = SETTINGS_PATH) -> dict:
    """Everything in the settings file, even before setup is finished ({} if there is none)."""
    try:
        with open(path, encoding='utf-8') as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def face_lock_on(settings) -> bool:
    """The face lock is off unless it was turned on (in the hub, or "face_lock": true)."""
    return bool(settings) and settings.get('face_lock') is True


def update_settings(changes: dict, path: str = SETTINGS_PATH) -> dict:
    """Add or change settings, keeping everything else in the file."""
    settings = read_settings(path)
    settings.update(changes)
    save_json(path, settings, indent=2)
    return settings


def write_settings(settings: dict, path: str = SETTINGS_PATH) -> dict:
    """Replace the whole file with settings (so a setting left out is removed)."""
    save_json(path, settings, indent=2)
    return settings


def save_settings(user_name: str, assistant_name: str, path: str = SETTINGS_PATH,
                  voice=None) -> dict:
    # Keeps what's already there (settings made in the hub).
    return update_settings({'user_name': user_name.strip(),
                            'assistant_name': assistant_name.strip() or DEFAULT_ASSISTANT_NAME,
                            'voice': voice}, path)
