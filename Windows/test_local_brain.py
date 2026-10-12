"""Tests for brain.LocalBrain against a fake LM Studio / Ollama server on this computer: it
streams answers and tool calls the way their OpenAI-style API does.
Run with:  python -m unittest test_local_brain"""
import json
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest import mock

import brain


class FakeServer:
    """Answers /v1/models, and /v1/chat/completions with the next scripted list of chunks."""

    def __init__(self, scripts):
        self.scripts = list(scripts)
        self.requests = []  # the chat requests JARVIS sent (not the warm-up)
        server = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_GET(self):
                self._json({'data': [{'id': 'text-embedding-small'}, {'id': 'test-model'}]})

            def do_POST(self):
                body = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
                if body.get('max_tokens') == 1:  # the warm-up
                    self._json({'choices': [{'message': {'role': 'assistant', 'content': 'H'}}]})
                    return
                server.requests.append(body)
                chunks = server.scripts.pop(0)
                self.send_response(200)
                self.send_header('Content-Type', 'text/event-stream')
                self.end_headers()
                for delta in chunks:
                    self.wfile.write(b'data: ' + json.dumps({'choices': [{'index': 0, 'delta': delta}]}).encode() + b'\n\n')
                self.wfile.write(b'data: [DONE]\n\n')

            def _json(self, data):
                raw = json.dumps(data).encode()
                self.send_response(200)
                self.send_header('Content-Type', 'application/json')
                self.send_header('Content-Length', str(len(raw)))
                self.end_headers()
                self.wfile.write(raw)

        self.httpd = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        self.url = f'http://127.0.0.1:{self.httpd.server_address[1]}/v1'
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()

    def close(self):
        self.httpd.shutdown()
        self.httpd.server_close()


class Speech:
    def __init__(self):
        self.said = ''

    def feed(self, text):
        self.said += text


def local_brain(url, **settings):
    return brain.LocalBrain({'brain': 'local', 'local_url': url, 'assistant_name': 'Jarbungus',
                             'user_name': 'Jose', 'city': 'Boston', **settings})


class LocalBrainTests(unittest.TestCase):
    def test_streams_an_answer_without_its_thinking(self):
        server = FakeServer([[{'role': 'assistant', 'content': '<think>They want a joke.'},
                              {'content': '</think>\n\nWhy did the'}, {'content': ' chicken cross the road? '},
                              {'content': 'To get to the other side.'}]])
        try:
            claude = local_brain(server.url)
            speech = Speech()
            said = claude.handle('Tell me a joke', speech, threading.Event())
        finally:
            server.close()
        self.assertEqual(said.strip(), 'Why did the chicken cross the road? To get to the other side.')
        self.assertNotIn('think', speech.said)
        self.assertIn('chicken cross the road', speech.said)
        sent = server.requests[0]
        self.assertEqual(sent['model'], 'test-model')  # the first loaded model that isn't for embeddings
        self.assertEqual(sent['messages'][0]['role'], 'system')
        self.assertTrue(sent['messages'][-1]['content'].endswith('Tell me a joke'))
        names = {t['function']['name'] for t in sent['tools']}
        self.assertTrue({'search', 'look_at_screen', 'click', 'type_text', 'set_volume'} <= names)
        self.assertNotIn('web_search', names)  # it searches on screen, like a person
        self.assertIn('look_at_screen to read them', sent['messages'][0]['content'])
        self.assertEqual(claude.messages[-1], {'role': 'assistant', 'content': said.strip()})

    def test_runs_a_tool_call_streamed_in_pieces(self):
        ran = []
        fake = (lambda level: ran.append(level) or f'Set to {level}.', 'Test tool.',
                brain._schema({'level': brain.I}, ['level']))
        server = FakeServer([
            [{'role': 'assistant', 'content': 'Turning it down. '},
             {'tool_calls': [{'index': 0, 'id': 'call_1', 'type': 'function',
                              'function': {'name': 'fake_volume', 'arguments': '{"lev'}}]},
             {'tool_calls': [{'index': 0, 'function': {'arguments': 'el": 20}'}}]}],
            [{'role': 'assistant', 'content': 'Done, it is at twenty.'}],
        ])
        try:
            with mock.patch.dict(brain.TOOLS, {'fake_volume': fake}):
                claude = local_brain(server.url)
                speech = Speech()
                said = claude.handle('Make it quieter', speech, threading.Event())
        finally:
            server.close()
        self.assertEqual(ran, [20])
        self.assertIn('Turning it down.', said)
        self.assertIn('Done, it is at twenty.', said)
        second = server.requests[1]['messages']
        self.assertEqual(second[-2]['tool_calls'][0]['function'], {'name': 'fake_volume', 'arguments': '{"level": 20}'})
        self.assertEqual(second[-1], {'role': 'tool', 'tool_call_id': 'call_1', 'content': 'Set to 20.'})

    def test_bad_arguments_go_back_to_the_model(self):
        server = FakeServer([
            [{'tool_calls': [{'index': 0, 'function': {'name': 'set_volume', 'arguments': '{"percent": '}}]}],
            [{'content': 'Sorry, try that again.'}],
        ])
        try:
            claude = local_brain(server.url)
            claude.handle('Volume', Speech(), threading.Event())
        finally:
            server.close()
        tool_reply = server.requests[1]['messages'][-1]
        self.assertEqual(tool_reply['role'], 'tool')
        self.assertIn('not valid JSON', tool_reply['content'])
        self.assertTrue(tool_reply['tool_call_id'])  # one was made up for it

    def test_not_running_is_reported_and_marks_it_broken(self):
        claude = local_brain('http://127.0.0.1:9/v1')  # nothing listens there
        with self.assertRaises(Exception) as caught:
            claude.handle('Tell me a joke', Speech(), threading.Event())
        message = claude.problem(caught.exception)
        self.assertIn("can't reach the local model", message)
        self.assertTrue(claude.broken)

    def test_searches_by_reading_the_screen(self):
        shot = [{'type': 'text', 'text': 'Screenshot, 1280x720 pixels.'},
                {'type': 'image', 'source': {'type': 'base64', 'media_type': 'image/png', 'data': 'iVBORw0KGgo='}}]
        server = FakeServer([
            [{'tool_calls': [{'index': 0, 'id': 'a', 'function': {'name': 'search',
                                                               'arguments': '{"query": "boston weather"}'}}]}],
            [{'tool_calls': [{'index': 0, 'id': 'b', 'function': {'name': 'look_at_screen', 'arguments': '{}'}}]}],
            [{'content': 'Sunny and sixty-eight tomorrow.'}],
        ])
        searched = []
        fakes = {'search': (lambda query, site='google', browser='': searched.append(query) or 'Showing results.',
                            *brain.TOOLS['search'][1:]),
                 'look_at_screen': (lambda region=None: shot, *brain.TOOLS['look_at_screen'][1:])}
        try:
            with mock.patch.dict(brain.TOOLS, fakes):
                said = local_brain(server.url).handle("What's the weather tomorrow?", Speech(), threading.Event())
        finally:
            server.close()
        self.assertEqual(searched, ['boston weather'])
        self.assertEqual(said, 'Sunny and sixty-eight tomorrow.')
        last = server.requests[2]['messages']
        self.assertEqual(last[-2]['role'], 'tool')
        self.assertIn('Screenshot, 1280x720 pixels.', last[-2]['content'])
        self.assertEqual(last[-1]['role'], 'user')  # the screenshot itself, as an image
        self.assertEqual(last[-1]['content'][1]['image_url']['url'], 'data:image/png;base64,iVBORw0KGgo=')

    def test_without_eyes_it_offers_no_screen_tool(self):
        server = FakeServer([[{'content': 'Hi.'}]])
        try:
            local_brain(server.url, local_vision=False).handle('Hello', Speech(), threading.Event())
        finally:
            server.close()
        sent = server.requests[0]
        self.assertNotIn('look_at_screen', {t['function']['name'] for t in sent['tools']})
        self.assertIn("can't see the screen", sent['messages'][0]['content'])

    def test_thinking_is_held_back_while_it_arrives(self):
        self.assertEqual(brain._without_thinking('<think>hmm', final=False), '')
        self.assertEqual(brain._without_thinking('Hello <thi', final=False), 'Hello ')
        self.assertEqual(brain._without_thinking('<think>a</think>Hi.', final=True), 'Hi.')


if __name__ == '__main__':
    unittest.main()
