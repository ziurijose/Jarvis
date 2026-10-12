"""Simple commands JARVIS does itself, without asking Claude: "pause", "next song", "volume
40", "open Spotify", "close Chrome", "google pasta recipes", "what time is it". They happen at
once and cost nothing; anything else, or anything said with more to it ("open Chrome and find
a funny video"), goes to Claude as before.

match() only reads the words; brain.py runs the tool it names. It has to match the whole
request, so a command inside a longer sentence is left to Claude.
"""
import datetime
import re
from typing import Callable, NamedTuple, Optional


class Match(NamedTuple):
    tool: Optional[str]           # a tool in brain.TOOLS, or None for an answer with no action
    args: dict
    reply: Callable[[str], str]   # the tool's result -> what JARVIS says


# Said around a command without changing it: "okay, pause the music please".
LEADING = re.compile(r'^(okay|ok|alright|all right|so|um|uh|hey|please|just|now|and|then|'
                     r'can you|could you|would you|will you|go ahead and)\s+')
TRAILING = re.compile(r'\s+(please|for me|now|right now|thanks|thank you)$')

MUSIC = [
    (r'(pause|stop)( the| my)?( music| song| track| spotify| playback)?', 'pause'),
    (r'(play|resume|unpause|continue)( the| my)? (music|song|spotify|playback)|resume|unpause|play', 'play'),
    (r'(play )?(the )?next( song| track| one)?|skip( it| this| the)?( song| track| one)?', 'next'),
    (r'(play )?(the )?previous( song| track| one)?|(play )?(the )?last (song|track)|'
     r'go back (a|one) (song|track)', 'previous'),
]
SAID_MUSIC = {'play': 'Playing.', 'pause': 'Paused.', 'next': 'Next song.', 'previous': 'Previous song.'}

VOLUME = re.compile(r'((set|turn|put|change|make)( the)? volume( up| down)?( to| at)?|volume( to| at)?|'
                    r'(set|turn|put) (it|the sound)( up| down)? to) (?P<n>\w+( \w+)?)( percent|%)?')
NUMBER_WORDS = {'zero': 0, 'ten': 10, 'twenty': 20, 'thirty': 30, 'forty': 40, 'fifty': 50, 'sixty': 60,
                'seventy': 70, 'eighty': 80, 'ninety': 90, 'one': 1, 'two': 2, 'three': 3, 'four': 4,
                'five': 5, 'six': 6, 'seven': 7, 'eight': 8, 'nine': 9, 'fifteen': 15, 'twelve': 12,
                'hundred': 100, 'max': 100, 'maximum': 100, 'full': 100, 'half': 50}

TIME = re.compile(r"(what's|whats|what is) the time( right now)?|what time is it( right now)?|"
                  r"(do you know |tell me )?what time it is")
DATE = re.compile(r"(what's|whats|what is) (the date|today's date|the date today|today)|"
                  r"what day is (it|today)( today)?|(what's|whats|what is) the day today")
STATUS = re.compile(r"(how's|hows|how is|what's|whats|what is|check)( my| the)? battery"
                    r"( level| at| status| percentage| life)?|how much battery (do i have|is left|have i got)"
                    r"( left)?|battery( level| status| percentage)|system status")
SCREENSHOT = re.compile(r'(take|grab|save|capture) (a |the )?screenshot|screenshot')

OPEN = re.compile(r'(open|launch)( up)? (?P<what>.+)')
CLOSE = re.compile(r'(quit|close|exit)( out of)? (?P<what>.+)')
# Words that make "open ..." something other than an app ("open my last email", "open a new
# tab", "open Chrome and go to YouTube"); Claude handles those.
NOT_AN_APP = {'my', 'a', 'an', 'this', 'that', 'these', 'those', 'it', 'its', 'new', 'last', 'first',
              'next', 'previous', 'recent', 'another', 'some', 'any', 'all', 'and', 'with', 'in', 'on',
              'for', 'to', 'from', 'about', 'of', 'file', 'files', 'folder', 'tab', 'tabs', 'window',
              'link', 'page', 'video', 'song', 'photo', 'picture', 'email', 'document', 'everything',
              'you', 'yourself', 'jarvis', 'up', 'down', 'out'}
SITES = {'youtube': ('YouTube', 'https://www.youtube.com'), 'google': ('Google', 'https://www.google.com'),
         'gmail': ('Gmail', 'https://mail.google.com'), 'netflix': ('Netflix', 'https://www.netflix.com'),
         'amazon': ('Amazon', 'https://www.amazon.com'), 'facebook': ('Facebook', 'https://www.facebook.com'),
         'instagram': ('Instagram', 'https://www.instagram.com'), 'reddit': ('Reddit', 'https://www.reddit.com'),
         'wikipedia': ('Wikipedia', 'https://www.wikipedia.org'), 'github': ('GitHub', 'https://github.com'),
         'twitter': ('Twitter', 'https://x.com'), 'youtube music': ('YouTube Music', 'https://music.youtube.com')}
DOMAIN = re.compile(r'[a-z0-9-]+(\.[a-z0-9-]+)*\.(com|org|net|io|co|tv|edu|gov|ai|app|dev|me|us|uk)')
# The names a Mac's `open -a` needs (Windows finds apps by any part of their name itself).
MAC_APPS = {'chrome': 'Google Chrome', 'vs code': 'Visual Studio Code', 'vscode': 'Visual Studio Code',
            'word': 'Microsoft Word', 'excel': 'Microsoft Excel', 'powerpoint': 'Microsoft PowerPoint',
            'outlook': 'Microsoft Outlook', 'teams': 'Microsoft Teams', 'settings': 'System Settings',
            'system preferences': 'System Settings'}

SEARCH = [
    re.compile(r'google (?P<q>.+)'),
    re.compile(r'(search|look up)( on)? (?P<site>google|youtube|amazon|wikipedia) for (?P<q>.+)'),
    re.compile(r'(search for|search|look up|look for|find) (?P<q>.+) on (?P<site>google|youtube|amazon|wikipedia)'),
]
SITE_NAMES = {'google': 'Google', 'youtube': 'YouTube', 'amazon': 'Amazon', 'wikipedia': 'Wikipedia'}


def normalize(text: str) -> str:
    text = text.lower().replace('(i interrupted you.)', ' ')
    text = re.sub(r"[^\w\s'.%-]", ' ', text)   # dots stay for "youtube.com", % for "50%"
    text = re.sub(r'\.(?!\w)', ' ', text)        # but not the one ending a sentence
    text = re.sub(r'\s+', ' ', text).strip()
    before = None
    while before != text:
        before = text
        text = TRAILING.sub('', LEADING.sub('', text))
    return text


def number(words: str) -> Optional[int]:
    if words.isdigit():
        return int(words) if int(words) <= 100 else None
    parts = words.replace('a hundred', 'hundred').replace('one hundred', 'hundred').split()
    if not parts or any(p not in NUMBER_WORDS for p in parts):
        return None
    total = sum(NUMBER_WORDS[p] for p in parts)
    return total if total <= 100 else None


def app_name(words: str, own_names) -> Optional[str]:
    """The app in "open ..." / "close ...", or None when it doesn't sound like one."""
    words = re.sub(r'^the ', '', words)
    if not words or len(words.split()) > 3 or words in own_names:
        return None
    if any(w in NOT_AN_APP for w in words.split()) or not re.fullmatch(r"[\w .'-]+", words):
        return None
    return words


def spoken_time(now: datetime.datetime) -> str:
    hour = now.hour % 12 or 12
    when = 'AM' if now.hour < 12 else 'PM'
    return f"It's {hour} {when}." if now.minute == 0 else f"It's {hour}:{now.minute:02d} {when}."


def spoken_date(now: datetime.datetime) -> str:
    day = now.day
    suffix = 'th' if 10 <= day % 100 <= 20 else {1: 'st', 2: 'nd', 3: 'rd'}.get(day % 10, 'th')
    return f"It's {now.strftime('%A, %B')} {day}{suffix}."


def _same(result):
    return result


def match(text: str, is_mac: bool = False, own_names=()) -> Optional[Match]:
    """The command in text, if it is one JARVIS can do itself. own_names: what the assistant
    is called, so "close Jarvis" goes to Claude (which knows to shut down)."""
    said = normalize(text)
    own = {'jarvis'} | {n.lower() for n in own_names if n}
    if not said:
        return None

    for pattern, action in MUSIC:
        if re.fullmatch(pattern, said):
            def music_reply(result, action=action):
                # "Spotify: pause." means it worked; otherwise ("Nothing is playing.") say what happened.
                return SAID_MUSIC[action] if re.fullmatch(r'.+: (play|pause|next|previous|playing)\.', result) else result
            return Match('music', {'action': action}, music_reply)

    found = VOLUME.fullmatch(said)
    if found:
        level = number(found['n'])
        if level is not None:
            return Match('set_volume', {'percent': level}, lambda _r, level=level: f'Volume {level}.')

    if TIME.fullmatch(said):
        return Match(None, {}, lambda _r: spoken_time(datetime.datetime.now()))
    if DATE.fullmatch(said):
        return Match(None, {}, lambda _r: spoken_date(datetime.datetime.now()))
    if STATUS.fullmatch(said):
        return Match('system_status', {}, lambda r: r.replace('%', ' percent'))
    if SCREENSHOT.fullmatch(said):
        return Match('take_screenshot', {}, lambda _r: 'Screenshot saved.')

    for pattern in SEARCH:
        found = pattern.fullmatch(said)
        if found and found['q'] != 'chrome':  # "google chrome" is the app
            site = found.groupdict().get('site') or 'google'
            query = found['q']
            return Match('search', {'query': query, 'site': site},
                         lambda _r, s=SITE_NAMES[site], q=query: f'Searching {s} for {q}.')

    found = OPEN.fullmatch(said)
    if found:
        what = re.sub(r'^the ', '', found['what'])
        if what in SITES:
            name, url = SITES[what]
            return Match('open_website', {'url': url}, lambda _r, n=name: f'Opening {n}.')
        if DOMAIN.fullmatch(what):
            return Match('open_website', {'url': what}, lambda _r, w=what: f'Opening {w}.')
        app = app_name(what, own)
        if app:
            name = MAC_APPS.get(app, app.title()) if is_mac else app.title()
            return Match('open_app', {'name': name}, _same)

    found = CLOSE.fullmatch(said)
    if found:
        app = app_name(found['what'], own)
        if app:
            name = MAC_APPS.get(app, app.title()) if is_mac else app.title()
            return Match('quit_app', {'name': name}, lambda r: 'Closed ' + r[5:] if r.startswith('Quit ') else r)
    return None
