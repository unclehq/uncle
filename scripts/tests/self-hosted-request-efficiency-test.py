#!/usr/bin/env python3
"""Hermetic request effort, reasoning hygiene and batched tool-loop regressions."""
import importlib.util
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
from urllib.error import HTTPError

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts/lib'))
import self_hosted_http as transport
import http_agent
from read_cache import ReadCache

spec = importlib.util.spec_from_file_location('http_fixture', Path(__file__).with_name('self-hosted-http-test.py'))
fixture = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fixture)


class Efficiency(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.config = self.root / 'config'
        env = patch.dict(os.environ, {'UNCLE_CONFIG': str(self.config), 'UNCLE_PROJECT_ROOT': str(self.root)}, clear=True)
        env.start()
        self.addCleanup(env.stop)
        transport._request_features.clear()
        transport._capabilities.clear()
        transport.close_connections()
        self.addCleanup(transport.close_connections)
        self.values = {'base_url': 'http://fixture.invalid/v1', 'api_key': 'fixture', 'model': 'any-model'}

    def server(self, **kwargs):
        server = fixture.Server(fixture.PLAN, **kwargs)
        self.addCleanup(server.close)
        self.values['base_url'] = server.url
        return server

    def call(self, name, args, identity):
        return {'id': identity, 'type': 'function', 'function': {'name': name, 'arguments': json.dumps(args)}}

    def response(self, content='done', **fields):
        return {'choices': [{'message': {'role': 'assistant', 'content': content, **fields}, 'finish_reason': 'stop'}]}

    def test_effort_defaults_mapping_and_parent_config(self):
        self.assertEqual(transport.reasoning_effort(), 'low')
        for source, expected in [('none', 'low'), ('minimal', 'low'), ('low', 'low'),
                                 ('medium', 'medium'), ('high', 'high'), ('xhigh', 'high'), ('max', 'high')]:
            self.assertEqual(transport.reasoning_effort({'effort': source}), expected)
        self.config.write_text('project-plan.effort medium\neffort high\n')
        for stage in ('requirements', 'project-plan-investigate', 'project-plan-section-outline'):
            with patch.dict(os.environ, {'UNCLE_STATUS_STAGE': stage}):
                self.assertEqual(transport.reasoning_effort(), 'medium')
        with patch.dict(os.environ, {'UNCLE_STATUS_STAGE': 'adversarial-review-worker-security'}):
            self.config.write_text('adversarial-review.effort high\n')
            self.assertEqual(transport.reasoning_effort(), 'high')
        with self.assertRaisesRegex(ValueError, 'Unsupported'):
            transport.reasoning_effort({'effort': 'huge'})

    def test_effort_precedence_and_off_switch(self):
        self.config.write_text('repair.effort high\nself-hosted.reasoning-effort off\n')
        with patch.dict(os.environ, {'UNCLE_STATUS_STAGE': 'repair', 'WORKFLOW_EFFORT_REPAIR': 'medium'}):
            self.assertIsNone(transport.reasoning_effort({'effort': 'high'}))
            with patch.dict(os.environ, {'WORKFLOW_SELF_HOSTED_REASONING_EFFORT': 'on'}):
                self.assertEqual(transport.reasoning_effort({'effort': 'high'}), 'medium')
            with patch.dict(os.environ, {'WORKFLOW_SELF_HOSTED_REASONING_EFFORT': 'bad'}):
                with self.assertRaisesRegex(ValueError, 'on or off'):
                    transport.reasoning_effort()
        self.config.write_text('repair.effort high\n')
        with patch.dict(os.environ, {'UNCLE_STATUS_STAGE': 'repair'}):
            self.assertEqual(transport.reasoning_effort({'effort': 'low'}), 'low')

    def test_tool_and_final_requests_send_effort(self):
        server = self.server(tool_script=[{'role': 'assistant', 'content': 'ready'}])
        self.values['effort'] = 'medium'
        http_agent.run_document(self.values, 'Plan', self.root, fixture.artifact_schema('plan'), 'plan', 4096)
        self.assertTrue(all(body['reasoning_effort'] == 'medium' for _, body in server.requests))
        self.assertEqual(len(server.requests), 2)

    def test_off_omits_field_from_tool_and_schema_requests(self):
        server = self.server(tool_script=[{'role': 'assistant', 'content': 'ready'}])
        with patch.dict(os.environ, {'WORKFLOW_SELF_HOSTED_REASONING_EFFORT': 'off'}):
            http_agent.run_document(self.values, 'Plan', self.root, fixture.artifact_schema('plan'), 'plan', 4096)
        self.assertTrue(all('reasoning_effort' not in body for _, body in server.requests))

    def test_effort_rejection_is_remembered_without_downgrading_schema(self):
        server = self.server(reject={'reasoning_effort'})
        for _ in range(2):
            result = transport.constrained_completion(self.values, [], fixture.artifact_schema('plan'), 'plan', 4096)
            self.assertEqual(result[3], 'json_schema')
        transport.chat(self.values, [], [], 4096)
        self.assertEqual(len(server.requests), 4)
        self.assertEqual(sum('reasoning_effort' in body for _, body in server.requests), 1)
        self.assertEqual(transport.capabilities(server.url, 'fixture')['rejected'], set())
        other = self.server()
        transport.chat(self.values, [], [], 4096)
        self.assertEqual(other.requests[-1][1]['reasoning_effort'], 'low')

    def test_tool_rejection_does_not_disable_effort(self):
        server = self.server(reject={'tools'})
        self.assertIsNone(transport.chat(self.values, [], http_agent.READ_TOOLS, 4096))
        result = transport.constrained_completion(self.values, [], fixture.artifact_schema('plan'), 'plan', 4096)
        self.assertEqual(result[3], 'json_schema')
        self.assertEqual(server.requests[-1][1]['reasoning_effort'], 'low')

    def test_schema_rejection_does_not_disable_effort(self):
        bodies = []
        def post(url, key, body, timeout):
            bodies.append(body)
            if body.get('response_format', {}).get('type') == 'json_schema':
                raise HTTPError(url, 400, 'bad', {}, io.BytesIO(b'unsupported response_format json_schema'))
            return self.response(json.dumps(fixture.PLAN))
        with patch.object(transport, 'detect_flavor', return_value='generic'), patch.object(transport, 'post', side_effect=post):
            self.assertEqual(transport.constrained_completion(self.values, [], {}, 'x', 100)[3], 'json_object')
        self.assertEqual(len(bodies), 2)
        self.assertTrue(all(b['reasoning_effort'] == 'low' for b in bodies))

    def test_non_capability_errors_are_not_retried(self):
        for status in (401, 429, 500):
            with patch.object(transport, 'post', side_effect=HTTPError('x', status, 'bad', {}, io.BytesIO())) as post:
                with self.assertRaisesRegex(ValueError, 'HTTP %d' % status):
                    transport.chat(self.values, [], [], 100)
                self.assertEqual(post.call_count, 1)

    def test_thinking_is_removed_without_editing_artifact_strings(self):
        for prefix in ('<think>private</think>', '  <think>private</think>\n<think>again</think>\n',
                       'private analysis\n</think>\n', 'The file has been written. Let me verify it.</think>'):
            self.assertEqual(transport.strip_reasoning(prefix + '{"ok":true}'), '{"ok":true}')
        for text in ('{"example":"<think>literal</think>"}', '```xml\n<think>literal</think>\n```',
                     'The literal </think> is part of this sentence.'):
            self.assertEqual(transport.strip_reasoning(text), text)
        self.assertEqual(transport.strip_reasoning('<think>unfinished'), '')
        self.assertEqual(transport.strip_reasoning(None), '')

    def test_reasoning_is_not_replayed_or_used_as_answer(self):
        call = self.call('list_dir', {}, 'one')
        server = self.server(tool_script=[{'role': 'assistant', 'content': '<think>private</think>inspect',
                             'reasoning_content': 'secret trace', 'reasoning': 'another trace', 'tool_calls': [call]},
                            {'role': 'assistant', 'content': '<think>private</think>' + json.dumps(fixture.PLAN)}])
        result, turns = http_agent.run_document(self.values, 'Plan', self.root, fixture.artifact_schema('plan'), 'plan', 4096)
        self.assertEqual(json.loads(result), fixture.PLAN)
        self.assertEqual(turns, 2)
        history = server.requests[1][1]['messages']
        self.assertNotIn('<think>', json.dumps(history))
        self.assertEqual(next(m['content'] for m in history if m['role'] == 'assistant'), 'inspect')
        self.assertNotIn('secret trace', json.dumps(history))
        self.assertNotIn('another trace', json.dumps(history))
        self.assertFalse(any(k in m for m in history for k in ('reasoning_content', 'reasoning')))

    def test_explicit_required_reasoning_field_is_replayed_only_to_that_server(self):
        for field in ('reasoning_content', 'reasoning'):
            transport._request_features.clear()
            bodies = []
            def post(url, key, body, timeout):
                bodies.append(body)
                if field not in body['messages'][0]:
                    raise HTTPError(url, 400, 'bad', {}, io.BytesIO(('Missing required ' + field).encode()))
                return self.response()
            messages = [{'role': 'assistant', 'content': 'inspect', field: 'private'}]
            with patch.object(transport, 'post', side_effect=post):
                transport.chat(self.values, messages, [], 100)
                transport.chat(self.values, messages, [], 100)
            self.assertEqual(len(bodies), 3)
            self.assertNotIn(field, bodies[0]['messages'][0])
            self.assertEqual(bodies[1]['messages'][0][field], 'private')
            with patch.object(transport, 'post', return_value=self.response()) as post:
                transport.chat(dict(self.values, base_url='http://other.invalid'), messages, [], 100)
                self.assertNotIn(field, post.call_args.args[2]['messages'][0])

    def test_schema_completion_strips_leading_reasoning(self):
        server = self.server()
        server.reply = fixture.Raw('<think>private</think>' + json.dumps(fixture.PLAN))
        text, _ = http_agent.run_document(self.values, 'Plan', self.root, fixture.artifact_schema('plan'), 'plan', 4096,
                                        explore_first=False)
        self.assertEqual(json.loads(text), fixture.PLAN)

    def test_all_calls_run_before_next_request_and_errors_do_not_skip_later_calls(self):
        (self.root / 'a').write_text('A')
        (self.root / 'b').write_text('B')
        calls = [self.call('read_file', {'path': 'a'}, 'a'), self.call('read_file', {'path': '../outside'}, 'bad'),
                 self.call('read_file', {'path': 'b'}, 'b'),
                 self.call('write_file', {'path': 'c', 'content': 'C'}, 'write'),
                 self.call('read_file', {'path': 'c'}, 'after-write')]
        server = self.server(tool_script=[{'role': 'assistant', 'content': '', 'tool_calls': calls},
                                         {'role': 'assistant', 'content': 'done'}])
        text, turns = http_agent.run_agent(self.values, 'Go', http_agent.Policy(self.root, write=True), 4096, turns=1)
        self.assertEqual(turns, 2)  # one budgeted tool turn, one closing turn
        results = [m for m in server.requests[1][1]['messages'] if m['role'] == 'tool']
        self.assertEqual([r['tool_call_id'] for r in results], ['a', 'bad', 'b', 'write', 'after-write'])
        self.assertEqual(results[0]['content'], '1\tA')
        self.assertTrue(results[1]['content'].startswith('error:'))
        self.assertEqual(results[2]['content'], '1\tB')
        self.assertEqual(results[4]['content'], '1\tC')

    def test_thinking_before_tool_arguments_is_stripped(self):
        call = self.call('read_file', {'path': 'a'}, 'a')
        call['function']['arguments'] = '<think>private</think>' + call['function']['arguments']
        cleaned = transport.clean_message({'tool_calls': [call], 'content': None})
        self.assertEqual(json.loads(cleaned['tool_calls'][0]['function']['arguments']), {'path': 'a'})
        self.assertTrue(call['function']['arguments'].startswith('<think>'))

    def test_reasoning_only_response_is_not_success(self):
        server = self.server(tool_script=[{'role': 'assistant', 'content': None, 'reasoning_content': 'not an answer'},
                                         {'role': 'assistant', 'content': '<think>still thinking'}])
        with self.assertRaisesRegex(ValueError, 'no final text'):
            http_agent.run_agent(self.values, 'Go', http_agent.Policy(self.root), 100)
        self.assertEqual(len(server.requests), 2)

    def test_ollama_native_effort_fallback_retains_format(self):
        server = self.server(version=('/api/version',), reject={'reasoning_effort'})
        for _ in range(2):
            result = transport.constrained_completion(self.values, [], {}, 'x', 100, effort='medium')
            self.assertEqual(result[3], 'ollama_format')
        self.assertEqual(len(server.requests), 3)
        self.assertEqual(server.requests[0][1]['reasoning_effort'], 'medium')
        self.assertTrue(all(path == '/api/chat' and 'format' in body for path, body in server.requests))

    def test_opencode_artifact_recovery_ignores_hidden_draft(self):
        from self_hosted import canonical_response_from_texts, response_from_events
        draft = json.dumps(fixture.PLAN)
        self.assertIsNone(canonical_response_from_texts(['<think>' + draft + '</think>done'], 'plan'))
        path = self.root / 'events.jsonl'
        path.write_text(json.dumps({'type': 'text', 'part': {'text': '<think>private</think>done'}}) + '\n' +
                        json.dumps({'type': 'step_finish', 'part': {'reason': 'stop'}}))
        self.assertEqual(response_from_events(path), ('done', 1))

    def test_prefetch_requested_sources_and_generated_json_on_first_request(self):
        path = self.root / '.uncle/workflow/documents/REQUIREMENTS_INTERPRETATION.json'
        path.parent.mkdir(parents=True)
        path.write_text('{"requirements":"all gates"}')
        (self.root / 'a.md').write_text('hello')
        server = self.server(tool_script=[{'role': 'assistant', 'content': 'done'}])
        prompt = 'Read only `.uncle/workflow/documents/REQUIREMENTS_INTERPRETATION.json`.\nRead `a.md`.\n'
        _, turns = http_agent.run_agent(self.values, prompt, http_agent.Policy(self.root), 100)
        self.assertEqual(turns, 1)
        supplied = server.requests[0][1]['messages'][1]['content']
        self.assertIn('all gates', supplied)
        self.assertIn('hello', supplied)
        self.assertIn('never verification evidence', supplied)

    def test_prefetch_does_not_read_negative_output_secret_or_symlink_paths(self):
        (self.root / 'a.md').write_text('source')
        (self.root / '.env').write_text('secret')
        (self.root / 'link.md').symlink_to(self.root / 'a.md')
        policy = http_agent.Policy(self.root)
        for prompt in ('Do not read `a.md`.', 'Write `a.md`.', 'Read `link.md`.', 'Read `.env`.',
                       'Do not read files.\nRead `a.md`.', '```text\nRead `a.md`.\n```'):
            self.assertEqual(http_agent.prefetch_context(prompt, policy), '')
        with patch.object(Path, 'read_bytes', side_effect=AssertionError('must not open credentials')):
            self.assertEqual(http_agent.prefetch_context('Read `self-hosted-keys.json`.', policy), '')

    def test_prefetch_bounds_disable_duplicate_and_freshness(self):
        (self.root / 'a.md').write_text('first')
        policy = http_agent.Policy(self.root)
        prompt = 'Read `a.md`.'
        self.assertIn('first', http_agent.prefetch_context(prompt, policy))
        (self.root / 'a.md').write_text('changed')
        self.assertIn('changed', http_agent.prefetch_context(prompt, policy))
        cache = ReadCache(self.root)
        existing = cache.context(prompt)
        self.assertEqual(http_agent.prefetch_context(prompt + existing, policy), '')
        for env in ({'WORKFLOW_SELF_HOSTED_PREFETCH': 'off'}, {'WORKFLOW_READ_CACHE': '0'}):
            with patch.dict(os.environ, env):
                self.assertEqual(http_agent.prefetch_context(prompt, policy), '')
        self.config.write_text('self-hosted.prefetch off\n')
        self.assertEqual(http_agent.prefetch_context(prompt, policy), '')
        self.config.write_text('')
        (self.root / 'a.md').write_text('x' * (ReadCache.RESULT_LIMIT + 1))
        self.assertEqual(http_agent.prefetch_context(prompt, policy), '')

    def test_cached_read_preserves_ranges_and_invalidates_after_change(self):
        (self.root / 'a.md').write_text('first\nsecond\nthird')
        cache = ReadCache(self.root)
        server = self.server(tool_script=[{'role': 'assistant', 'content': '', 'tool_calls': [
            self.call('read_file', {'path': 'a.md', 'offset': 1, 'limit': 1}, 'read')]},
            {'role': 'assistant', 'content': 'done'}])
        http_agent.run_agent(self.values, 'Go', http_agent.Policy(self.root), 100, read_cache=cache)
        context = cache.context('Read a.md')
        self.assertIn('second', context)
        self.assertIn('"offset": 1', context)
        self.assertIn('"limit": 1', context)
        (self.root / 'a.md').write_text('new')
        self.assertEqual(cache.context('Read a.md'), '')

    def test_denied_reads_never_enter_cache_snapshot(self):
        cache = ReadCache(self.root)
        server = self.server(tool_script=[{'role': 'assistant', 'content': '', 'tool_calls': [
            self.call('read_file', {'path': 'self-hosted-keys.json'}, 'secret')]},
            {'role': 'assistant', 'content': 'done'}])
        with patch.object(cache, 'snapshot', side_effect=AssertionError('must not open credentials')) as snapshot:
            http_agent.run_agent(self.values, 'Go', http_agent.Policy(self.root), 100, read_cache=cache)
            snapshot.assert_not_called()
        results = [m for m in server.requests[1][1]['messages'] if m['role'] == 'tool']
        self.assertEqual(results[0]['content'], 'error: path is not readable')


if __name__ == '__main__':
    unittest.main()
