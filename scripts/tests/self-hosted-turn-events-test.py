#!/usr/bin/env python3
"""Offline HTTP turn metadata contracts; no model or signer."""
import contextlib
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts/lib'))
import http_agent as agent
import self_hosted_http as transport

class TurnEvents(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        env = patch.dict(os.environ, {'UNCLE_CONFIG': str(self.root / 'absent'),
                                     'UNCLE_PROJECT_ROOT': str(self.root)}, clear=True)
        env.start()
        self.addCleanup(env.stop)
        self.output = io.StringIO()
        capture = contextlib.redirect_stdout(self.output)
        capture.__enter__()
        self.addCleanup(capture.__exit__, None, None, None)
        self.values = {'model': 'stub', 'base_url': 'http://unused.invalid/v1', 'api_key': 'never-used'}

    def call(self, name, **args):
        return {'id': 'stub', 'type': 'function', 'function': {'name': name, 'arguments': json.dumps(args, ensure_ascii=False)}}

    def reply(self, text='done', calls=(), tokens=1, reason='stop'):
        return {'choices': [{'message': {'role': 'assistant', 'content': text, 'tool_calls': list(calls)},
                             'finish_reason': reason}], 'usage': {'prompt_tokens': 10, 'completion_tokens': tokens}}

    def events(self):
        return [json.loads(line) for line in self.output.getvalue().splitlines() if line.startswith('{')]

    def test_turn_metadata_bytes_raw_arguments_no_contents_or_double_usage(self):
        calls = [self.call('write_file', path='private.txt', content='秘密'),
                 self.call('read_file', path='private.txt')]
        calls.append({'id': 'bad', 'function': {'name': 'edit_file', 'arguments': '{malformed-private'}})
        replies = [self.reply(calls=calls, tokens=21), self.reply(tokens=4)]
        with patch.object(agent, 'interruptible_chat', side_effect=replies):
            usage = {}
            agent.run_agent(self.values, 'go', agent.Policy(self.root, write=True), 4096, usage=usage)
        events = self.events()
        self.assertEqual([e['output_tokens'] for e in events], [21, 4])
        self.assertEqual([e['turn'] for e in events], [1, 2])
        self.assertEqual(len({e['request_group'] for e in events}), 1)
        self.assertEqual(events[0]['tools'], [dict(name=c['function']['name'], argument_bytes=len(c['function']['arguments'].encode())) for c in calls])
        self.assertEqual(events[1]['tools'], [])
        for secret in ('秘密', 'private.txt', 'malformed-private', 'never-used'):
            self.assertNotIn(secret, self.output.getvalue())
        self.assertTrue(all('usage' not in e and e['type'] == 'self_hosted_turn' for e in events))
        self.assertEqual(usage['output_tokens'], 25)

    def test_turn_records_text_and_reasoning_sizes_not_contents(self):
        first = self.reply(calls=[self.call('read_file', path='a.txt')], tokens=9)
        first['choices'][0]['message'].update(content='Draft plan ✓', reasoning_content='thinking-secret')
        second = self.reply(tokens=3)
        second['choices'][0]['message'].update(content='done', reasoning='more-secret')
        with patch.object(agent, 'interruptible_chat', side_effect=[first, second]):
            agent.run_agent(self.values, 'go', agent.Policy(self.root, write=True), 4096, usage={})
        events = self.events()
        self.assertEqual([e['text_bytes'] for e in events], [len('Draft plan ✓'.encode()), 4])
        self.assertEqual([e['reasoning_bytes'] for e in events], [len('thinking-secret'), len('more-secret')])
        for secret in ('Draft plan', 'thinking-secret', 'more-secret'):
            self.assertNotIn(secret, self.output.getvalue())

    def test_final_fallback_and_truncated_turn_are_logged(self):
        schema = {'type': 'object', 'required': ['ok'], 'properties': {'ok': {'type': 'boolean'}}}
        with patch.object(agent, 'interruptible_chat', return_value=self.reply('ready', tokens=2)), \
                patch.object(agent, 'constrained_completion', return_value=('{"ok":true}', 'stop', {'completion_tokens': 7}, 'json_schema')):
            _, count = agent.run_agent(self.values, 'go', agent.Policy(self.root), 4096, final_schema=schema)
        self.assertEqual(count, 2)
        self.assertEqual([(e['phase'], e['output_tokens']) for e in self.events()], [('tools', 2), ('final', 7)])
        self.output.seek(0); self.output.truncate()
        with patch.object(agent, 'interruptible_chat', return_value=self.reply(tokens=4096, reason='length')), \
                patch.object(agent, 'save_truncated', return_value=None):
            with self.assertRaises(transport.OutputTruncated):
                agent.run_agent(self.values, 'go', agent.Policy(self.root), 4096)
        self.assertEqual(self.events()[0]['finish_reason'], 'length')


if __name__ == '__main__':
    unittest.main()
