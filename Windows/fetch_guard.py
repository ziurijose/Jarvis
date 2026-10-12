"""Checks each web page Claude is about to open (its WebFetch tool) and blocks the dangerous ones.

brain.py gives Claude Code this file as a PreToolUse hook: Claude Code runs it before every
WebFetch with the request as JSON on stdin. Exit code 2 refuses the fetch, and what is printed to
stderr tells Claude why. Everything else is allowed: there is no list of permitted sites.

Blocked:
  - pages on the abuse.ch URLhaus (malware) and OpenPhish (phishing) lists, refreshed every few
    hours in the background (refresh(), started with JARVIS) and kept in malicious_urls.cache;
  - this computer and the home network (localhost, 192.168.x.x, ...), where a page could steer
    Claude at the router or at JARVIS's own local model server;
  - addresses carrying a long run of encoded data, the way a page could get Claude to smuggle a
    file's contents out in a link.
When the lists can't be downloaded, the other checks still run and the fetch goes ahead.
"""
import ipaddress
import json
import os
import re
import socket
import sys
import threading
import time
import urllib.request
from urllib.parse import unquote, urlsplit

HERE = os.path.dirname(os.path.abspath(__file__))
CACHE_PATH = os.path.join(HERE, 'malicious_urls.cache')
REFRESH_SECONDS = 6 * 3600
HOST_FEEDS = ['https://urlhaus.abuse.ch/downloads/hostfile/']  # hosts that only serve malware
URL_FEEDS = ['https://urlhaus.abuse.ch/downloads/text_online/', 'https://openphish.com/feed.txt']
LONG_DATA = re.compile(r'[A-Za-z0-9+/=_%-]{400,}')  # e.g. a base64-encoded file in a link

_lists = None


def _download(url) -> str:
    request = urllib.request.Request(url, headers={'User-Agent': 'JARVIS fetch guard'})
    with urllib.request.urlopen(request, timeout=30) as response:
        return response.read().decode('utf-8', 'replace')


def refresh(force=False) -> bool:
    """Downloads the lists again when the cached copy is older than REFRESH_SECONDS. Returns
    whether the cache is up to date. Never raises: JARVIS works on without fresh lists."""
    try:
        if not force and time.time() - os.path.getmtime(CACHE_PATH) < REFRESH_SECONDS:
            return True
    except OSError:
        pass
    try:
        hosts, urls = set(), set()
        for feed in HOST_FEEDS:
            for line in _download(feed).splitlines():
                parts = line.split()
                if len(parts) == 2 and not line.startswith('#'):
                    hosts.add(parts[1].lower())
        for feed in URL_FEEDS:
            for line in _download(feed).splitlines():
                if line.startswith(('http://', 'https://')):
                    urls.add(_normal(line.strip()))
        temporary = CACHE_PATH + '.tmp'
        with open(temporary, 'w', encoding='utf-8') as f:
            json.dump({'hosts': sorted(hosts), 'urls': sorted(urls)}, f)
        os.replace(temporary, CACHE_PATH)
        return True
    except Exception as error:
        print(f'Could not refresh the list of dangerous web pages ({error}).')
        return False


def refresh_in_background() -> None:
    threading.Thread(target=refresh, daemon=True).start()


def _normal(url: str) -> str:
    """url lower-cased up to its path, without a trailing slash, for comparing."""
    parts = urlsplit(url)
    return f'{parts.netloc.lower()}{parts.path}'.rstrip('/') + (f'?{parts.query}' if parts.query else '')


def _load_lists():
    global _lists
    if _lists is None:
        try:
            with open(CACHE_PATH, encoding='utf-8') as f:
                data = json.load(f)
            _lists = set(data['hosts']), set(data['urls'])
        except (OSError, ValueError, KeyError):
            _lists = set(), set()
    return _lists


def _private(host: str) -> bool:
    """Whether host is this computer or on the local network (checking where its name points)."""
    if host in ('localhost', '') or host.endswith(('.local', '.localhost', '.internal', '.lan', '.home.arpa')):
        return True
    try:
        addresses = [ipaddress.ip_address(host.strip('[]'))]
    except ValueError:
        try:
            addresses = [ipaddress.ip_address(info[4][0].split('%')[0])
                         for info in socket.getaddrinfo(host, None)]
        except (OSError, ValueError, UnicodeError):
            return False  # can't be looked up: the fetch itself will fail
    return any(a.is_private or a.is_loopback or a.is_link_local or a.is_reserved or a.is_unspecified
               for a in addresses)


def problem(url: str):
    """Why fetching url is refused, or None when it's fine."""
    parts = urlsplit(url.strip())
    if parts.scheme not in ('http', 'https'):
        return f'only web pages (http or https) can be opened, not "{parts.scheme}:" links'
    host = (parts.hostname or '').lower().rstrip('.')
    if _private(host):
        return 'it points at this computer or the home network, which web pages must not reach'
    if LONG_DATA.search(unquote(parts.path + '?' + parts.query)):
        return 'the address carries a long block of encoded data, the way information gets smuggled out'
    hosts, urls = _load_lists()
    if host in hosts or any(host.endswith('.' + bad) for bad in hosts if '.' in bad):
        return 'the site is on the abuse.ch list of sites that spread malware'
    wanted = _normal(url.strip())
    if any(wanted == bad or wanted.startswith(bad + '/') for bad in urls):
        return 'the page is on a list of live malware and phishing pages (abuse.ch, OpenPhish)'
    return None


def main() -> int:
    try:
        request = json.load(sys.stdin)
        url = (request.get('tool_input') or {}).get('url') or ''
    except ValueError:
        return 0
    reason = problem(url)
    if reason:
        print(f'JARVIS blocked this page: {reason}. Do not try to open it another way; '
              f'tell the user it was blocked and why.', file=sys.stderr)
        return 2
    return 0


if __name__ == '__main__':
    sys.exit(main())
