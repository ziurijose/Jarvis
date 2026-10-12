"""The user's name and the assistant's name, chosen in first-run setup."""
import json
import os

SETTINGS_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'user_settings.json')
DEFAULT_ASSISTANT_NAME = 'JARVIS'


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


def update_settings(changes: dict, path: str = SETTINGS_PATH) -> dict:
    """Add or change settings, keeping everything else in the file."""
    try:
        with open(path, encoding='utf-8') as f:
            settings = json.load(f)
    except (OSError, ValueError):
        settings = {}
    settings.update(changes)
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(settings, f, indent=2)
    return settings


def save_settings(user_name: str, assistant_name: str, path: str = SETTINGS_PATH,
                  voice=None) -> dict:
    # Keeps what's already there (the installer may have saved the local model's engine).
    return update_settings({'user_name': user_name.strip(),
                            'assistant_name': assistant_name.strip() or DEFAULT_ASSISTANT_NAME,
                            'voice': voice}, path)
