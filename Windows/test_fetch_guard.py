"""Tests for fetch_guard.py, the check Claude Code runs before opening a web page.
Run with:  python -m unittest test_fetch_guard"""
import base64
import contextlib
import io
import json
import unittest
from unittest import mock

import fetch_guard

LISTS = ({'malware-host.example'}, {'phish.example/login', 'files.example/bad.exe'})


class FetchGuard(unittest.TestCase):
    def setUp(self):
        patch = mock.patch.object(fetch_guard, '_lists', LISTS)
        patch.start()
        self.addCleanup(patch.stop)

    def test_ordinary_pages_are_allowed(self):
        for url in ('https://8.8.8.8/', 'https://1.1.1.1/search?q=weather+in+boston',
                    'https://files.example/good.pdf', 'https://phish.example/'):
            self.assertIsNone(fetch_guard.problem(url), url)

    def test_this_computer_and_the_home_network_are_blocked(self):
        for url in ('http://localhost:11434/api', 'http://127.0.0.1:6996/', 'http://192.168.1.1/admin',
                    'http://10.0.0.5/', 'http://[::1]/', 'http://printer.local/', 'http://169.254.169.254/'):
            self.assertIn('this computer', fetch_guard.problem(url), url)

    def test_listed_malware_and_phishing_pages_are_blocked(self):
        self.assertIn('malware', fetch_guard.problem('http://malware-host.example/x.exe'))
        self.assertIn('malware', fetch_guard.problem('http://cdn.malware-host.example/'))
        self.assertIn('phishing', fetch_guard.problem('https://PHISH.example/login/step2'))
        self.assertIn('phishing', fetch_guard.problem('http://files.example/bad.exe'))

    def test_links_smuggling_data_out_are_blocked(self):
        secret = base64.b64encode(b'my private notes ' * 40).decode()
        self.assertIn('encoded data', fetch_guard.problem(f'https://8.8.8.8/collect?d={secret}'))

    def test_other_kinds_of_link_are_blocked(self):
        self.assertIn('file:', fetch_guard.problem('file:///C:/Users/me/secrets.txt'))

    def test_the_hook_exit_code(self):
        def run(url):
            stdin = io.StringIO(json.dumps({'tool_name': 'WebFetch', 'tool_input': {'url': url}}))
            with mock.patch('sys.stdin', stdin), contextlib.redirect_stderr(io.StringIO()) as err:
                return fetch_guard.main(), err.getvalue()
        self.assertEqual(run('https://8.8.8.8/')[0], 0)
        code, message = run('http://127.0.0.1/')
        self.assertEqual(code, 2)
        self.assertIn('blocked', message)


if __name__ == '__main__':
    unittest.main()
