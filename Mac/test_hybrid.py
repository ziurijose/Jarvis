"""Tests for brain.HybridBrain (the local model first, Claude only when needed) and
brain.TurboSetup (the model and engine for this computer's graphics card).
Run with:  python -m unittest test_hybrid"""
import threading
import unittest
from unittest import mock

import brain
from test_local_brain import FakeServer, Speech


class FakeClaude:
    """Stands in for Claude Code."""

    def __init__(self):
        self.asked, self.done_locally, self.ended, self.forgot = [], (), False, 0

    def handle(self, text, speech, interrupted):
        self.asked.append(text)
        speech.feed('Here you go.')
        return 'Here you go.'

    def forget_conversation(self):
        self.forgot += 1

    def problem(self, error):
        return None


def hybrid(url, claude):
    settings = {'local_url': url, 'assistant_name': 'Jarbungus', 'user_name': 'Jose', 'city': 'Boston'}
    made = brain.HybridBrain(settings, backup=claude)
    made.local.ready.wait(5)
    return made


class HybridBrainTests(unittest.TestCase):
    def test_the_local_model_answers_and_claude_hears_about_it(self):
        server, claude = FakeServer([[{'content': 'Paris is the capital.'}]]), FakeClaude()
        try:
            jarvis = hybrid(server.url, claude)
            speech = Speech()
            said = jarvis.handle('Capital of France?', speech, threading.Event())
        finally:
            server.close()
        self.assertEqual(said, 'Paris is the capital.')
        self.assertEqual(claude.asked, [])
        self.assertEqual(claude.done_locally, ('"Capital of France?" (you answered "Paris is the capital.")',))
        tools = {t['function']['name'] for t in server.requests[0]['tools']}
        self.assertIn('ask_claude', tools)
        self.assertIn('call ask_claude straight away', server.requests[0]['messages'][0]['content'])

    def test_claude_answers_while_the_local_model_isnt_ready(self):
        claude = FakeClaude()
        with mock.patch.object(brain, 'LOCAL_SERVERS', (('TurboLLM', 'http://127.0.0.1:9/v1'),)), \
                mock.patch.object(brain, 'start_turbollm', return_value=None):
            jarvis = hybrid('', claude)
            speech = Speech()
            said = jarvis.handle('Tell me a joke', speech, threading.Event())
        self.assertEqual((said, speech.said), ('Here you go.', 'Here you go.'))
        self.assertEqual(claude.asked, ['Tell me a joke'])  # nothing added: it's an ordinary request
        self.assertEqual(jarvis.local.messages[-1], {'role': 'assistant', 'content': 'Here you go.'})

    def test_a_handover_carries_on_in_the_same_voice(self):
        server, claude = FakeServer([[{'content': 'Let me look at that. '},
                                      {'tool_calls': [{'index': 0, 'id': 'h', 'function': {
                                          'name': 'ask_claude', 'arguments': '{"reason": "long task"}'}}]}]]), FakeClaude()
        try:
            jarvis = hybrid(server.url, claude)
            speech = Speech()
            said = jarvis.handle('Reorganise my desktop', speech, threading.Event())
        finally:
            server.close()
        self.assertEqual(speech.said, 'Let me look at that. Here you go.')
        self.assertEqual(said, 'Let me look at that. Here you go.')
        self.assertTrue(claude.asked[0].endswith('Reorganise my desktop'))
        self.assertIn('never mention a handover', claude.asked[0])
        self.assertIn('You have already said: "Let me look at that."', claude.asked[0])
        # the local model's unfinished try is replaced by the finished exchange
        self.assertEqual([m['role'] for m in jarvis.local.messages], ['user', 'assistant'])
        self.assertEqual(jarvis.local.messages[-1]['content'], said)

    def test_talk_of_handing_over_is_never_heard(self):
        server, claude = FakeServer([[{'content': 'Sure. That is a bit too complex for me, so I will hand it '},
                                      {'content': 'over to a stronger assistant.'},
                                      {'tool_calls': [{'index': 0, 'id': 'h', 'function': {
                                          'name': 'ask_claude', 'arguments': '{}'}}]}]]), FakeClaude()
        try:
            jarvis = hybrid(server.url, claude)
            speech = Speech()
            jarvis.handle('Write me a sorting algorithm', speech, threading.Event())
        finally:
            server.close()
        self.assertEqual(speech.said, 'Sure. Here you go.')
        self.assertIn('You have already said: "Sure."', claude.asked[0])

    def test_sentences_are_checked_whole(self):
        speech = Speech()
        heard = brain._Heard(speech)
        for piece in ('Paris is the cap', 'ital. Claude would ', 'say so too. It has ', 'two million people'):
            heard.feed(piece)
        self.assertEqual(speech.said, 'Paris is the capital. ')  # the rest waits for its sentence to end
        heard.flush()
        self.assertEqual(speech.said, 'Paris is the capital. It has two million people')

    def test_a_local_failure_goes_to_claude(self):
        server, claude = FakeServer([500]), FakeClaude()
        try:
            jarvis = hybrid(server.url, claude)
            said = jarvis.handle('What is two plus two?', Speech(), threading.Event())
        finally:
            server.close()
        self.assertEqual(said, 'Here you go.')
        self.assertEqual(len(claude.asked), 1)
        self.assertFalse(jarvis.broken)

    def test_forgetting_reaches_both(self):
        server, claude = FakeServer([]), FakeClaude()
        try:
            jarvis = hybrid(server.url, claude)
            jarvis.local.messages.append({'role': 'user', 'content': 'hi'})
            jarvis.forget_conversation()
        finally:
            server.close()
        self.assertEqual((jarvis.local.messages, claude.forgot), ([], 1))


class FakeTurbo(brain.TurboSetup):
    """TurboSetup against a pretend TurboLLM: graphics card, library, downloads and engines."""

    def __init__(self, gpus, library=(), speeds=None, backends=('rocm', 'vulkan', 'cpu'), vendor='amd', settings=None):
        self.saved, self.used, self.asked_download = [], [], None
        super().__init__('http://turbo/v1', settings or {}, save=self.saved.append)
        self.gpus, self.library, self.speeds = gpus, list(library), speeds or {}
        self.offered, self.vendor, self.active = backends, vendor, 'cpu'
        self.polls = 0

    def _call(self, method, path, body=None, timeout=30):
        if path == '/api/v1/sysinfo':
            return {'ramMB': 32768, 'gpus': self.gpus}
        if path == '/v1/models':
            return {'data': [{'id': i} for i in self.library]}
        if path == '/api/v1/downloads' and method == 'POST':
            self.asked_download = body
            return {'downloads': [{'id': 'd1'}, {'id': 'd2'}]}
        if path == '/api/v1/downloads':
            self.polls += 1
            done = self.polls > 1
            if done:
                self.library.append('gemma-4-e4b-it|Q4_K_M|4977171584')
            return {'downloads': [{'id': i, 'status': 'done' if done else 'downloading', 'received': 1, 'total': 2}
                                  for i in ('d1', 'd2')]}
        if path == '/api/v1/engines/backends':
            return {'vendor': self.vendor, 'recommended': 'rocm' if self.vendor == 'amd' else 'cuda',
                    'backends': [{'id': b, 'installed': True, 'active': b == self.active} for b in self.offered]}
        raise AssertionError(path)

    def _use(self, backend, wait=0):
        self.used.append(backend)
        self.active = backend

    def _speed(self, backend, model):
        return self.speeds.get(backend, 0)


RX_6750_XT = [{'vendor': 'amd', 'name': 'AMD Radeon RX 6750 XT', 'vramMb': 12272}]


class TurboSetupTests(unittest.TestCase):
    def test_picks_the_model_for_the_graphics_memory(self):
        self.assertEqual(brain.graphics_memory({'gpus': RX_6750_XT}), 12272)
        self.assertEqual(brain.graphics_memory({'ramMB': 16384, 'gpus': [{'vramMb': 16384, 'unified': True}]}), 10649)
        self.assertEqual(brain.graphics_memory({'ramMB': 16384, 'gpus': []}), 0)
        self.assertEqual(brain.model_for(12272)[1], 'gemma-4-E4B-it-Q4_K_M.gguf')
        self.assertEqual(brain.model_for(24576)[1], 'gemma-4-26B-A4B-it-UD-Q4_K_M.gguf')
        self.assertEqual(brain.model_for(0)[1], 'gemma-4-E4B-it-Q3_K_M.gguf')
        self.assertTrue(brain._matches('gemma-4-e4b-it|Q4_K_M|4977171584', 'gemma-4-E4B-it-Q4_K_M.gguf'))
        self.assertFalse(brain._matches('gemma-4-e4b-it|Q3_K_M|4058137728', 'gemma-4-E4B-it-Q4_K_M.gguf'))
        self.assertTrue(brain._matches('gemma-4-26b-a4b-it|UD-Q4_K_M|1', 'gemma-4-26B-A4B-it-UD-Q4_K_M.gguf'))
        self.assertEqual(brain.model_size('gemma-4-e4b-it|Q4_K_M|4977171584'), 4)

    def test_downloads_the_model_then_keeps_the_faster_engine(self):
        turbo = FakeTurbo(RX_6750_XT, speeds={'rocm': 0, 'vulkan': 48})  # ROCm doesn't run on this card
        with mock.patch('time.sleep'):
            model = turbo.run()
        self.assertEqual(model, 'gemma-4-e4b-it|Q4_K_M|4977171584')
        self.assertEqual(turbo.asked_download, {'repo': 'unsloth/gemma-4-E4B-it-GGUF',
                                                'rfilename': 'gemma-4-E4B-it-Q4_K_M.gguf'})
        self.assertEqual(turbo.saved, [{'local_backend': 'vulkan'}])
        self.assertEqual(turbo.active, 'vulkan')

    def test_rocm_wins_when_it_is_faster(self):
        turbo = FakeTurbo(RX_6750_XT, library=['gemma-4-e4b-it|Q4_K_M|4977171584'], speeds={'rocm': 61, 'vulkan': 48})
        turbo.run()
        self.assertIsNone(turbo.asked_download)  # already downloaded
        self.assertEqual((turbo.saved, turbo.active), ([{'local_backend': 'rocm'}], 'rocm'))

    def test_later_starts_reuse_the_choice(self):
        turbo = FakeTurbo(RX_6750_XT, library=['gemma-4-e4b-it|Q4_K_M|4977171584'],
                          speeds={'rocm': 99, 'vulkan': 1}, settings={'local_backend': 'vulkan'})
        turbo.run()
        self.assertEqual((turbo.saved, turbo.used), ([], ['vulkan']))  # no timing again

    def test_other_cards_take_turbollms_engine(self):
        nvidia = [{'vendor': 'nvidia', 'name': 'RTX 4070', 'vramMb': 12282}]
        turbo = FakeTurbo(nvidia, library=['gemma-4-e4b-it|Q4_K_M|4977171584'], vendor='nvidia',
                          backends=('cuda', 'vulkan', 'cpu'))
        turbo.run()
        self.assertEqual((turbo.saved, turbo.active), ([{'local_backend': 'cuda'}], 'cuda'))


if __name__ == '__main__':
    unittest.main()
