"""JARVIS's Mac abilities: Calendar, Reminders, Notes, Contacts, Messages and Mail.

Most of it is AppleScript, so macOS asks once per app ("Terminal wants to control
Calendar"). Reading the calendar uses EventKit when it is available, because AppleScript
misses the repeats of recurring events (a weekly meeting only shows its first week).

Sending a message or an email needs the user's spoken "yes": the brain passes in what the
user last said, and send_* refuse unless it is a clear yes (see confirmed_by_user).
"""
import datetime
import re
import subprocess
import sys
import threading

IS_MAC = sys.platform == 'darwin'


class NotOnMac(RuntimeError):
    pass


def osascript(script: str, timeout: int = 30) -> str:
    if not IS_MAC:
        raise NotOnMac('This only works on a Mac.')
    out = subprocess.run(['osascript', '-e', script], capture_output=True, text=True, timeout=timeout)
    if out.returncode != 0:
        message = out.stderr.strip()
        if '-1743' in message or 'Not authorized' in message:
            raise RuntimeError('macOS blocked it. Allow it in System Settings > Privacy & Security > Automation.')
        raise RuntimeError(message or 'AppleScript failed')
    return out.stdout.strip()


def q(text) -> str:
    """A string as an AppleScript literal."""
    return '"' + str(text).replace('\\', '\\\\').replace('"', '\\"') + '"'


def as_date(name: str, when: datetime.datetime) -> str:
    """AppleScript lines that build a date variable from parts (date strings depend on locale)."""
    return (f'set {name} to current date\n'
            f'set day of {name} to 1\n'
            f'set year of {name} to {when.year}\n'
            f'set month of {name} to {when.month}\n'
            f'set day of {name} to {when.day}\n'
            f'set time of {name} to {when.hour * 3600 + when.minute * 60}\n')


def parse_when(text: str) -> datetime.datetime:
    """ISO 8601 time from the model, e.g. 2026-10-09T15:00, as this Mac's local time without a
    timezone (a time with an offset or a Z is converted; AppleScript dates have no timezone)."""
    try:
        when = datetime.datetime.fromisoformat(text.strip())
    except ValueError:
        raise ValueError(f'Give the time as ISO 8601, e.g. 2026-10-09T15:00 (got "{text}").')
    if when.tzinfo is not None:
        when = when.astimezone().replace(tzinfo=None)
    return when


def day_range(day: str, days: int):
    start = parse_when(day) if day else datetime.datetime.now()
    start = start.replace(hour=0, minute=0, second=0, microsecond=0)
    return start, start + datetime.timedelta(days=max(1, min(int(days or 1), 31)))


# ---- Calendar --------------------------------------------------------------------------

def _eventkit_store(entity):
    """An EKEventStore with access granted, or None (no pyobjc, or access denied)."""
    try:
        import EventKit
    except ImportError:
        return None
    store = EventKit.EKEventStore.alloc().init()
    answered, result = threading.Event(), {}

    def done(granted, _error):
        result['granted'] = bool(granted)
        answered.set()
    if entity == 0 and hasattr(store, 'requestFullAccessToEventsWithCompletion_'):
        store.requestFullAccessToEventsWithCompletion_(done)
    else:
        store.requestAccessToEntityType_completion_(entity, done)
    answered.wait(60)
    return store if result.get('granted') else None


def calendar_events(day: str = '', days: int = 1) -> str:
    """Events from the start of day (ISO date; default today) for that many days."""
    start, end = day_range(day, days)
    store = _eventkit_store(0) if IS_MAC else None
    if store is not None:
        from Foundation import NSDate
        predicate = store.predicateForEventsWithStartDate_endDate_calendars_(
            NSDate.dateWithTimeIntervalSince1970_(start.timestamp()),
            NSDate.dateWithTimeIntervalSince1970_(end.timestamp()), None)
        lines = []
        for event in sorted(store.eventsMatchingPredicate_(predicate), key=lambda e: e.startDate().timeIntervalSince1970()):
            begins = datetime.datetime.fromtimestamp(event.startDate().timeIntervalSince1970())
            when = begins.strftime('%a %d %b') + (' all day' if event.isAllDay() else begins.strftime(' %H:%M'))
            place = f' at {event.location()}' if event.location() else ''
            lines.append(f'{when}: {event.title()}{place} ({event.calendar().title()})')
        return '\n'.join(lines) or 'Nothing on the calendar then.'
    script = (as_date('startDate', start) + as_date('endDate', end) + '''
set out to ""
tell application "Calendar"
    repeat with c in calendars
        repeat with e in (every event of c whose start date is greater than or equal to startDate and start date is less than endDate)
            set out to out & ((start date of e) as string) & ": " & (summary of e) & " (" & (name of c) & ")" & linefeed
        end repeat
    end repeat
end tell
return out''')
    return osascript(script, timeout=60) or 'Nothing on the calendar then (repeating events may not show).'


def add_calendar_event(title: str, start: str, minutes: int = 60, calendar: str = '', location: str = '') -> str:
    begins = parse_when(start)
    ends = begins + datetime.timedelta(minutes=int(minutes or 60))
    target = f'calendar {q(calendar)}' if calendar else '(first calendar whose writable is true)'
    props = f'summary:{q(title)}, start date:startDate, end date:endDate' + (f', location:{q(location)}' if location else '')
    osascript(as_date('startDate', begins) + as_date('endDate', ends) +
              f'tell application "Calendar" to tell {target} to make new event with properties {{{props}}}')
    return f'Added "{title}" on {begins:%a %d %b at %H:%M}.'


# ---- Reminders and Notes --------------------------------------------------------------

def list_reminders(list_name: str = '') -> str:
    source = f'list {q(list_name)}' if list_name else 'default list'
    out = osascript(f'''tell application "Reminders"
    set out to ""
    repeat with r in (reminders of {source} whose completed is false)
        set out to out & name of r
        if due date of r is not missing value then set out to out & " (due " & ((due date of r) as string) & ")"
        set out to out & linefeed
    end repeat
    return out
end tell''', timeout=60)
    return out or 'No open reminders.'


def add_reminder(text: str, due: str = '', list_name: str = '') -> str:
    target = f'list {q(list_name)}' if list_name else 'default list'
    if due:
        when = parse_when(due)
        osascript(as_date('dueDate', when) +
                  f'tell application "Reminders" to tell {target} to make new reminder with properties '
                  f'{{name:{q(text)}, due date:dueDate, remind me date:dueDate}}')
        return f'Reminder set for {when:%a %d %b at %H:%M}.'
    osascript(f'tell application "Reminders" to tell {target} to make new reminder with properties {{name:{q(text)}}}')
    return 'Reminder added.'


def complete_reminder(text: str) -> str:
    done = osascript(f'''tell application "Reminders"
    set hits to (reminders whose completed is false and name contains {q(text)})
    repeat with r in hits
        set completed of r to true
    end repeat
    return count of hits
end tell''')
    return f'Marked {done} reminder(s) done.'


def add_note(title: str, body: str = '') -> str:
    html = '<h1>' + _html(title) + '</h1>' + ''.join(f'<div>{_html(line) or "<br>"}</div>' for line in body.splitlines())
    osascript(f'tell application "Notes" to make new note with properties {{body:{q(html)}}}')
    return f'Saved the note "{title}".'


def _html(text):
    return text.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')


# ---- Contacts, Messages and Mail ------------------------------------------------------

def find_contact(name: str, kind: str = 'phone') -> str:
    """The first phone number or email of the contact whose name contains name."""
    field = 'phones' if kind == 'phone' else 'emails'
    found = osascript(f'''tell application "Contacts"
    set hits to (people whose name contains {q(name)})
    if (count of hits) is 0 then return ""
    set p to item 1 of hits
    if (count of {field} of p) is 0 then return "NONE|" & name of p
    return (value of item 1 of {field} of p) & "|" & name of p
end tell''')
    if not found:
        raise ValueError(f'No contact matches "{name}".')
    value, full = found.split('|', 1)
    if value == 'NONE':
        raise ValueError(f'{full} has no {"phone number" if kind == "phone" else "email address"} in Contacts.')
    return value


YES = re.compile(r"\b(yes|yeah|yep|yup|sure|send it|go ahead|do it|correct|that's right|ok|okay|please do)\b", re.I)
NO = re.compile(r"\b(no|nope|don't|do not|cancel|wait|stop|change)\b", re.I)
_read_back = {}  # (kind, to, text) -> what the user had said when JARVIS read it back


def confirmed_by_user(heard: str) -> bool:
    return bool(YES.search(heard or '')) and not NO.search(heard or '')


def allowed_to_send(kind, to, text, confirmed, heard) -> bool:
    """True only when JARVIS read this exact message back earlier and the user has since
    answered with a clear yes. The first call always just records the read-back."""
    key = (kind, to.strip().lower(), text.strip())
    if confirmed and key in _read_back and heard != _read_back[key] and confirmed_by_user(heard):
        del _read_back[key]
        return True
    _read_back[key] = heard
    return False


ASK_FIRST = ('Not sent yet. Read the recipient and the exact text back to the user and ask if you should send it. '
             'Call again with confirmed=true only after they clearly say yes.')


def send_message(to: str, text: str, confirmed: bool = False, heard: str = '') -> str:
    """iMessage/SMS through Messages. to: a contact name, phone number or email."""
    if not allowed_to_send('message', to, text, confirmed, heard):
        return ASK_FIRST
    handle = to if re.fullmatch(r'[+\d][\d\s()-]{5,}|[^@\s]+@[^@\s]+', to.strip()) else find_contact(to, 'phone')
    osascript(f'''tell application "Messages"
    set svc to 1st account whose service type = iMessage
    send {q(text)} to participant {q(handle)} of svc
end tell''')
    return f'Sent to {to}.'


def send_email(to: str, subject: str, body: str, confirmed: bool = False, heard: str = '') -> str:
    """Sends through the Mail app, from its default account. to: a contact name or email."""
    if not allowed_to_send('email', to, subject + '\n' + body, confirmed, heard):
        return ASK_FIRST
    address = to if '@' in to else find_contact(to, 'email')
    osascript(f'''tell application "Mail"
    set m to make new outgoing message with properties {{subject:{q(subject)}, content:{q(body)}, visible:false}}
    tell m to make new to recipient at end of to recipients with properties {{address:{q(address)}}}
    send m
end tell''')
    return f'Email sent to {address}.'
