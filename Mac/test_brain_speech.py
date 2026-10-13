"""Tests for CliBrain._turn handing Claude's streamed reply to speech, with stand-in Claude Code
events. Run with:  python -m unittest test_brain_speech"""
import base64
import queue
import threading
import time
import unittest
from unittest import mock

import brain


def text(words):
    return {'type': 'stream_event', 'event': {'type': 'content_block_delta',
                                              'delta': {'type': 'text_delta', 'text': words}}}


BLOCK_END = {'type': 'stream_event', 'event': {'type': 'content_block_stop'}}


class Speech:
    def __init__(self):
        self.fed = []

    def feed(self, words):
        self.fed.append(words)

    def flush(self):
        self.fed.append(FLUSH)


FLUSH = '(flush)'


def fed_before_the_result(*events):
    """What _turn gave speech after these events, before Claude Code reported the result."""
    cli = brain.CliBrain.__new__(brain.CliBrain)
    cli._send = lambda message: None
    cli._supported = lambda: {'--include-partial-messages'}
    cli.events = queue.Queue()
    for event in events:
        cli.events.put(event)
    speech, done = Speech(), threading.Event()
    threading.Thread(target=lambda: (cli._turn('hi', speech, threading.Event()), done.set()),
                     daemon=True).start()
    deadline = time.monotonic() + 2
    while not cli.events.empty() and time.monotonic() < deadline:
        time.sleep(0.01)
    time.sleep(0.1)  # let _turn handle the last event
    fed = list(speech.fed)
    cli.events.put({'type': 'result'})
    assert done.wait(2), '_turn did not return'
    return fed


class BlockEndTest(unittest.TestCase):
    def test_a_finished_sentence_is_said_before_the_tool_runs(self):
        fed = fed_before_the_result(text('Let me look'), text(' that up.'), BLOCK_END)
        self.assertEqual(fed, ['Let me look', ' that up.', FLUSH])

    def test_a_block_that_stops_mid_sentence_is_not_cut(self):
        fed = fed_before_the_result(text('The forecast for tomorrow is'), BLOCK_END)
        self.assertNotIn(FLUSH, fed)

    def test_an_action_block_is_not_spoken(self):
        fed = fed_before_the_result(text('Opening Spotify. <do>{"tool": "open_app"}</do>'), BLOCK_END)
        self.assertEqual(fed, ['Opening Spotify. ', FLUSH])


class LongTaskTest(unittest.TestCase):
    def test_a_long_task_runs_every_round_until_claude_is_done(self):
        rounds = 40
        replies = ['<do>{"tool": "system_status", "args": {}}</do>'] * rounds + ['All done.']
        cli = brain.CliBrain.__new__(brain.CliBrain)
        cli.lock = threading.RLock()
        cli.unreported, cli.done_locally = [], ()
        cli._ready = lambda: None
        cli._turn = lambda prompt, speech, interrupted: (replies.pop(0), True)
        ran = []
        real_run_tool = brain.run_tool
        brain.run_tool = lambda name, args, heard='', interrupted=None: (ran.append(name), ('ok', False))[1]
        try:
            said = cli._handle('fill in the whole form', Speech(), threading.Event())
        finally:
            brain.run_tool = real_run_tool
        self.assertEqual(len(ran), rounds)
        self.assertEqual(said.strip(), 'All done.')


class LookTest(unittest.TestCase):
    def test_the_screenshot_goes_with_the_results_not_through_a_file(self):
        replies = ['<do>{"tool": "look_at_screen", "args": {}}</do>', 'It says hello.']
        prompts = []
        cli = brain.CliBrain.__new__(brain.CliBrain)
        cli.lock = threading.RLock()
        cli.unreported, cli.done_locally = [], ()
        cli._ready = lambda: None
        cli._turn = lambda prompt, speech, interrupted: (prompts.append(prompt), (replies.pop(0), True))[1]
        real, real_describe = brain.control.screenshot_png, brain.screen_text.describe
        brain.control.screenshot_png = lambda region=None: (b'fake png', (1280, 720))
        brain.screen_text.describe = lambda: None  # a window with no list of controls
        try:
            cli._handle('what does my screen say', Speech(), threading.Event())
        finally:
            brain.control.screenshot_png, brain.screen_text.describe = real, real_describe
        text, image = prompts[1]
        self.assertIn('look_at_screen', text['text'])
        self.assertNotIn('Read', text['text'])
        self.assertEqual(image['type'], 'image')
        self.assertEqual(base64.b64decode(image['source']['data']), b'fake png')


class SettleTest(unittest.TestCase):
    def test_opening_something_waits_for_it_to_settle_before_the_next_action(self):
        replies = ['<do>{"tool": "open_app", "args": {"name": "Calculator"}}</do>\n'
                   '<do>{"tool": "look_at_screen", "args": {}}</do>', 'Done.']
        order = []
        cli = brain.CliBrain.__new__(brain.CliBrain)
        cli.lock = threading.RLock()
        cli.unreported, cli.done_locally = [], ()
        cli._ready = lambda: None
        cli._turn = lambda prompt, speech, interrupted: (replies.pop(0), True)
        with mock.patch.object(brain, 'run_tool', lambda name, *a: (order.append(name), ('Opened.', False))[1]), \
                mock.patch.object(brain.control, 'wait_for_screen', lambda s, stop: order.append('settle') or 'ok'), \
                mock.patch.object(brain.CliBrain, '_look', staticmethod(lambda args: (order.append('look'), ('x', False, None))[1])):
            cli._handle('open calculator', Speech(), threading.Event())
        self.assertEqual(order, ['open_app', 'settle', 'look'])


class ChromeTest(unittest.TestCase):
    def command(self, settings):
        cli = brain.CliBrain.__new__(brain.CliBrain)
        cli.claude, cli.settings, cli.process, cli.rules = 'claude', settings, None, ''
        cli.lock = threading.RLock()
        cli._supported = lambda: {'--chrome', '--tools'}
        with mock.patch.object(brain.subprocess, 'Popen') as popen, mock.patch.object(brain.threading, 'Thread'), \
                mock.patch.object(brain, 'city', return_value=''), \
                mock.patch.object(brain, 'load_memory', return_value=[]):  # never the user's real notes
            cli._start(warm=False)
        return popen.call_args[0][0]

    def test_the_users_chrome_is_used_when_one_was_chosen(self):
        cmd = self.command({'user_name': 'Jose', 'chrome_browser': 'device-123'})
        self.assertIn('--chrome', cmd)
        self.assertIn('mcp__claude-in-chrome__*', cmd[cmd.index('--allowedTools') + 1])
        prompt = cmd[cmd.index('--system-prompt') + 1]
        self.assertIn('device-123', prompt)
        self.assertIn('javascript_tool', prompt)

    def test_no_chrome_without_a_chosen_browser(self):
        cmd = self.command({'user_name': 'Jose'})
        self.assertNotIn('--chrome', cmd)
        self.assertNotIn('chrome', cmd[cmd.index('--allowedTools') + 1])


class RunCommandTest(unittest.TestCase):
    def test_it_gets_what_the_user_said_and_the_interrupt(self):
        got = {}
        real = brain.TOOLS['run_command']
        brain.TOOLS['run_command'] = (lambda **kwargs: got.update(kwargs) or 'ok',) + real[1:]
        interrupted = threading.Event()
        try:
            result = brain.run_tool('run_command', {'command': 'Get-Process'}, 'yes do it', interrupted)
        finally:
            brain.TOOLS['run_command'] = real
        self.assertEqual(result, ('ok', False))
        self.assertEqual(got, {'command': 'Get-Process', 'heard': 'yes do it', 'interrupted': interrupted})


class WaitTest(unittest.TestCase):
    def test_a_full_wait_is_not_cut_short(self):
        asked = []

        class Event:
            def wait(self, seconds):
                asked.append(seconds)
                return False
        self.assertEqual(brain.CliBrain._wait({'seconds': 600, 'full': True}, Event()), ('Waited.', False))
        self.assertEqual(asked, [600])

    def test_talking_ends_a_long_wait_at_once(self):
        for full in (True, False):
            interrupted = threading.Event()
            threading.Timer(0.1, interrupted.set).start()
            started = time.monotonic()
            with mock.patch.object(brain.control, '_thumbnail', side_effect=lambda: object()):  # always changing
                content, error = brain.CliBrain._wait({'seconds': 600, 'full': full}, interrupted)
            self.assertLess(time.monotonic() - started, 2)
            self.assertFalse(error)
            self.assertIn('user', content)

    def test_a_plain_wait_watches_the_screen(self):
        with mock.patch.object(brain.control, 'wait_for_screen', return_value='Settled.') as watched:
            self.assertEqual(brain.CliBrain._wait({'seconds': 5}, threading.Event()), ('Settled.', False))
        self.assertEqual(watched.call_args[0][0], 5)


class Clock:
    """A stand-in for time and for the user-talked event: each wait moves time on."""

    def __init__(self, talk_at=None):
        self.t, self.talk_at = 0.0, talk_at

    def now(self):
        return self.t

    def wait(self, seconds):
        self.t += seconds
        return self.talk_at is not None and self.t >= self.talk_at


class WaitForScreenTest(unittest.TestCase):
    def watch(self, frames, seconds=10, talk_at=None):
        clock, frames = Clock(talk_at), list(frames)
        result = brain.control.wait_for_screen(seconds, clock, grab=lambda: frames.pop(0) if len(frames) > 1 else frames[0],
                                               differs=lambda a, b: a != b, now=clock.now)
        return result, round(clock.t, 2)

    def test_stops_soon_after_the_screen_settles(self):
        result, took = self.watch(['desk'] * 3 + ['opening', 'app'] + ['app'] * 100)
        self.assertIn('settled', result)
        self.assertLess(took, 1.5)

    def test_a_screen_that_never_changes_stops_early(self):
        result, took = self.watch(['desk'] * 100)
        self.assertIn('Nothing changed', result)
        self.assertLess(took, 2)

    def test_never_longer_than_asked(self):
        result, took = self.watch([n for n in range(1000)], seconds=3)  # a video: always changing
        self.assertIn('still changing', result)
        self.assertLessEqual(took, 3.2)

    def test_talking_stops_it(self):
        result, _took = self.watch([n for n in range(1000)], talk_at=0.5)
        self.assertIn('user', result)


class ProblemTest(unittest.TestCase):
    def problem(self, error):
        cli = brain.CliBrain.__new__(brain.CliBrain)
        cli.ended = cli.at_limit = False
        return cli.problem(error), cli.ended, cli.at_limit

    def test_the_usage_limit_is_said_briefly_and_ends_the_conversation(self):
        error = RuntimeError("You've hit your session limit \xb7 resets 6:50pm (America/New_York)")
        self.assertEqual(self.problem(error),
                         ("Sorry, you've hit your Claude usage limit. It resets at 6:50pm.", True, True))

    def test_other_wordings_of_the_limit(self):
        said, _, _ = self.problem(RuntimeError("You've hit your weekly limit \xb7 resets Oct 14, 9am (UTC)"))
        self.assertEqual(said, "Sorry, you've hit your Claude usage limit. It resets at Oct 14, 9am.")
        said, _, _ = self.problem(RuntimeError('Usage limit reached. Resets at 4:00 PM.'))
        self.assertEqual(said, "Sorry, you've hit your Claude usage limit. It resets at 4:00 PM.")

    def test_other_errors_are_unchanged(self):
        self.assertEqual(self.problem(RuntimeError('Claude Code stopped')),
                         ('Claude Code had a problem: Claude Code stopped', False, False))
        self.assertEqual(self.problem(KeyError('x')), (None, False, False))


if __name__ == '__main__':
    unittest.main()
