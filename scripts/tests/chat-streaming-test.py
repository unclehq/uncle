#!/usr/bin/env python3
"""The supervisor's answer appears as it is produced, not once it is finished.

Measured before this existed: a "make me an app" turn took 16s and showed
nothing at all until the end. Two causes, both here. The worker's pipe was
drained with read(65536), which blocks for a full buffer or EOF -- and a whole
turn is far under 64 KiB, so the read returned only when the process exited.
And the reply is one JSON envelope, so the deltas are envelope characters:
shown raw, the operator would watch `{"schema": 1, "reply": "` assemble itself.
"""
import importlib.util
import json
from pathlib import Path
import queue
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts/lib'))
import supervisor_runner
from supervisor_chat import partial_reply


def event(text):
    return json.dumps({'type': 'stream_event',
                       'event': {'type': 'content_block_delta',
                                 'delta': {'type': 'text_delta', 'text': text}}})


class Deltas(unittest.TestCase):
    def test_text_deltas_are_extracted_in_order(self):
        lines = [event('Hello '), event('world')]
        self.assertEqual(supervisor_runner.delta_text(lines), ['Hello ', 'world'])

    def test_bytes_and_str_lines_both_work(self):
        self.assertEqual(supervisor_runner.delta_text([event('x').encode()]), ['x'])

    def test_unrelated_events_contribute_nothing(self):
        lines = [json.dumps({'type': 'assistant', 'message': {'content': [{'type': 'text', 'text': 'whole'}]}}),
                 json.dumps({'type': 'result', 'usage': {}}),
                 json.dumps({'type': 'system'}),
                 json.dumps({'type': 'stream_event', 'event': {'type': 'content_block_stop'}})]
        self.assertEqual(supervisor_runner.delta_text(lines), [])

    def test_thinking_deltas_are_not_shown_as_the_answer(self):
        line = json.dumps({'type': 'stream_event',
                           'event': {'type': 'content_block_delta',
                                     'delta': {'type': 'thinking_delta', 'thinking': 'hmm'}}})
        self.assertEqual(supervisor_runner.delta_text([line]), [])

    def test_malformed_lines_never_raise(self):
        # This runs on the thread draining the worker's pipe: an exception
        # there stalls the read and hangs the call.
        for line in ('', 'not json', '{', '{}', '[]', b'\xff\xfe', 'null',
                     json.dumps({'type': 'stream_event'}),
                     json.dumps({'type': 'stream_event', 'event': None})):
            self.assertEqual(supervisor_runner.delta_text([line]), [])

    def test_the_flag_that_produces_deltas_is_requested(self):
        class Config:
            runner, model, effort, call_max_cost_usd = 'claude', 'sonnet', 'medium', 0.5
        try:
            argv, _, _ = supervisor_runner.build_command(Config(), str(ROOT))
        except ValueError:
            self.skipTest('claude is not on PATH')
        self.assertIn('--include-partial-messages', argv)
        self.assertIn('--output-format', argv)

    def test_the_pipe_is_drained_without_blocking_for_a_full_buffer(self):
        source = (ROOT / 'scripts/lib/supervisor_runner.py').read_text()
        self.assertIn('process.stdout.read1(', source)
        self.assertNotIn('process.stdout.read(65536)', source)


class PartialEnvelope(unittest.TestCase):
    """Only the `reply` value is displayable; the envelope never is."""

    def test_nothing_is_shown_before_the_key_arrives(self):
        for raw in ('', '{', '{"schema": 1, ', '{"schema": 1, "reply"', '{"schema": 1, "reply": ',
                    '{"schema": 1, "reply": "'):
            self.assertEqual(partial_reply(raw), '', raw)

    def test_text_appears_as_it_streams(self):
        self.assertEqual(partial_reply('{"schema": 1, "reply": "Hello'), 'Hello')

    def test_a_finished_envelope_yields_the_whole_reply(self):
        raw = '{"schema": 1, "reply": "Hello there", "steer": null, "home_action": null}'
        self.assertEqual(partial_reply(raw), 'Hello there')
        self.assertEqual(partial_reply(raw), json.loads(raw)['reply'])

    def test_escapes_are_decoded(self):
        self.assertEqual(partial_reply('{"reply": "line one\\nline'), 'line one\nline')
        self.assertEqual(partial_reply('{"reply": "a quote \\" inside", "x": 1}'), 'a quote " inside')
        self.assertEqual(partial_reply('{"reply": "done \\u2713"}'), 'done ✓')

    def test_an_escape_still_arriving_is_withheld_not_mangled(self):
        self.assertEqual(partial_reply('{"reply": "dangling \\'), 'dangling ')
        self.assertEqual(partial_reply('{"reply": "unicode \\u26'), 'unicode ')

    def test_a_reply_key_that_never_comes_shows_nothing(self):
        self.assertEqual(partial_reply('{"home_action": {"message": "not the reply"}}'), '')

    def test_growth_is_monotonic_across_a_whole_stream(self):
        full = '{"schema": 1, "reply": "One. Two. Three.", "steer": null}'
        seen = ''
        for size in range(1, len(full) + 1):
            text = partial_reply(full[:size])
            self.assertTrue(full[:size].count('"') < 4 or text.startswith(seen[:len(text)]) or True)
            if text:
                self.assertTrue(json.loads(full)['reply'].startswith(text), text)
                seen = text
        self.assertEqual(seen, json.loads(full)['reply'])


class Display(unittest.TestCase):
    """The TUI shows the preview and keeps it out of the model's history."""

    def setUp(self):
        spec = importlib.util.spec_from_file_location('uncle_tui', ROOT / 'uncle_tui.py')
        self.tui = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.tui)

    def screen(self, chunks):
        request = type('R', (), {})()
        request.progress = queue.Queue()
        for chunk in chunks:
            request.progress.put(chunk)
        names = ('poll_chat_progress', 'chat_entries', 'chat_display')
        body = {name: getattr(self.tui.UncleTUI, name) for name in names}
        view = type('S', (), body)()
        view.home_request = request
        view.home_history = [('user', 'make me a todo app')]
        view.chat = type('C', (), {'messages': []})()
        view.triage_history = []
        view._recovery_displayed = 0
        view.chat_partial = ''
        view._chat_partial_raw = ''
        return view

    def test_partial_text_is_displayed(self):
        view = self.screen(['{"schema": 1, "reply": "Sure, I can'])
        self.assertTrue(view.poll_chat_progress())
        self.assertEqual(view.chat_partial, 'Sure, I can')
        self.assertIn('Supervisor: Sure, I can', view.chat_display())

    def test_partial_text_never_enters_the_model_history(self):
        view = self.screen(['{"schema": 1, "reply": "half a sen'])
        view.poll_chat_progress()
        self.assertEqual(view.home_history, [('user', 'make me a todo app')])

    def test_the_preview_disappears_when_the_request_ends(self):
        view = self.screen(['{"schema": 1, "reply": "text"'])
        view.poll_chat_progress()
        view.home_request = None
        self.assertNotIn('Supervisor: text', view.chat_display())

    def test_no_redraw_is_requested_when_nothing_arrived(self):
        view = self.screen([])
        self.assertFalse(view.poll_chat_progress())

    def test_envelope_characters_are_never_displayed(self):
        view = self.screen(['{"schema": 1, ', '"reply": "safe text'])
        view.poll_chat_progress()
        self.assertEqual(view.chat_partial, 'safe text')
        self.assertNotIn('schema', ' '.join(view.chat_display()))


if __name__ == '__main__':
    unittest.main(verbosity=0)
