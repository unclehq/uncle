#!/usr/bin/env python3
"""Hermetic capture and SSE regressions: loopback only, no credentials or Git."""
import contextlib
import io
import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch
from urllib.parse import urlsplit

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'lib'))
import http_agent as agent
import self_hosted as hosted
import self_hosted_http as transport
from self_hosted_stream import StreamStopped

PLAN = '# Project plan\n\nKeep all the useful detail.\n\n## Verification commands\n```sh\npython3 tests/check.py\n```\n'
PATH = '.uncle/workflow/project-plan-investigation.md'
SCHEMA = {'type': 'object', 'required': ['ok'], 'properties': {'ok': {'type': 'boolean'}}}


def delta(content=None, calls=None, reason=None):
    value = {}
    if content is not None:
        value['content'] = content
    if calls is not None:
        value['tool_calls'] = calls
    return {'choices': [{'index': 0, 'delta': value, 'finish_reason': reason}]}


def call(name, **args):
    return {'id': 'c1', 'type': 'function', 'function': {'name': name, 'arguments': json.dumps(args)}}


def reply(text='', calls=()):
    return {'choices': [{'message': {'role': 'assistant', 'content': text, 'tool_calls': list(calls)},
                         'finish_reason': 'tool_calls' if calls else 'stop'}], 'usage': {'completion_tokens': 7}}


class Server:
    def __init__(self, events, reject=None):
        self.events, self.reject, self.requests, self.sent = events, reject, [], 0
        self.disconnected = threading.Event()
        outer = self
        class Handler(BaseHTTPRequestHandler):
            protocol_version = 'HTTP/1.1'
            def log_message(self, *args):
                pass
            def json(self, code, body):
                raw = json.dumps(body).encode()
                self.send_response(code)
                self.send_header('Content-Length', str(len(raw)))
                self.send_header('Content-Type', 'application/json')
                self.end_headers()
                self.wfile.write(raw)
            def do_GET(self):
                self.json(404, {})
            def do_POST(self):
                body = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
                outer.requests.append(body)
                if outer.reject == 'usage' and 'stream_options' in body:
                    return self.json(400, {'error': 'unsupported stream_options'})
                if outer.reject in ('stream', 'generic') and body.get('stream'):
                    return self.json(400, {'error': 'unsupported stream' if outer.reject == 'stream' else 'unsupported'})
                if outer.reject == 'schema' and 'response_format' in body:
                    return self.json(400, {'error': 'unsupported response_format'})
                if not body.get('stream'):
                    return self.json(200, reply('{"ok":true}'))
                self.send_response(200)
                self.send_header('Content-Type', 'text/event-stream; charset=utf-8')
                self.send_header('Connection', 'close')
                self.end_headers()
                self.close_connection = True
                events = outer.events(body) if callable(outer.events) else outer.events
                try:
                    for item in events:
                        raw = item if isinstance(item, str) else json.dumps(item, ensure_ascii=False)
                        self.wfile.write(('data: ' + raw + '\r\n\r\n').encode())
                        self.wfile.flush()
                        outer.sent += 1
                        time.sleep(0.001)
                except (BrokenPipeError, ConnectionResetError):
                    outer.disconnected.set()
        self.httpd = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        self.thread.start()
        self.values = {'base_url': 'http://127.0.0.1:%d/v1' % self.httpd.server_port, 'api_key': 'stub', 'model': 'stub'}
    def close(self):
        self.httpd.shutdown()
        self.httpd.server_close()
        self.thread.join()


class CaptureStream(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        env = patch.dict(os.environ, {'UNCLE_CONFIG': str(self.root / 'config'), 'UNCLE_PROJECT_ROOT': str(self.root),
                                     'WORKFLOW_SELF_HOSTED_HTTP2': 'off'}, clear=True)
        env.start()
        self.addCleanup(env.stop)
        self.output = io.StringIO()
        capture = contextlib.redirect_stdout(self.output)
        capture.__enter__()
        self.addCleanup(capture.__exit__, None, None, None)
        transport._request_features.clear()
        transport._capabilities.clear()
        self.addCleanup(transport.close_connections)
        request = transport._request
        def loopback_only(url, *args, **kwargs):
            if urlsplit(url).hostname not in ('127.0.0.1', '::1', 'localhost'):
                raise AssertionError('Unstubbed non-loopback request in test')
            return request(url, *args, **kwargs)
        guard = patch.object(transport, '_request', side_effect=loopback_only)
        guard.start()
        self.addCleanup(guard.stop)
        self.values = {'model': 'stub', 'base_url': 'http://unused.invalid/v1', 'api_key': 'stub'}

    def serve(self, events=None, **kwargs):
        server = Server(events or [delta('{"ok":true}', reason='stop'), '[DONE]'], **kwargs)
        self.addCleanup(server.close)
        return server

    def policy(self):
        return agent.Policy(self.root, write=True, drafts={PATH: lambda text: hosted.validate_plan(text, False)})

    def test_capture_beats_same_turn_stub_without_second_generation(self):
        policy = self.policy()
        with patch.object(agent, 'interruptible_chat', return_value=reply(PLAN, [call('write_file', path=PATH, content='# stub')])) as chat:
            text, turns = agent.run_agent(self.values, 'Plan', policy, 32768)
        self.assertEqual((turns, chat.call_count), (1, 1))
        self.assertEqual((self.root / PATH).read_text(), PLAN)
        event = next(json.loads(line) for line in self.output.getvalue().splitlines() if 'self_hosted_capture' in line)
        self.assertEqual(event['bytes'], len(PLAN.encode()))
        self.assertNotIn('useful detail', self.output.getvalue())

    def test_capture_replaces_previous_invalid_private_stub(self):
        policy = self.policy()
        agent.run_tool(policy, 'write_file', {'path': PATH, 'content': '# stub'})
        with patch.object(agent, 'interruptible_chat', return_value=reply(PLAN)) as chat:
            agent.run_agent(self.values, 'Plan', policy, 32768)
        self.assertEqual(chat.call_count, 1)
        self.assertEqual((self.root / PATH).read_text(), PLAN)

    def test_existing_invalid_file_loses_to_valid_fenced_chat(self):
        target = self.root / PATH
        target.parent.mkdir(parents=True)
        target.write_text('# stub\n')
        with patch.object(agent, 'interruptible_chat', return_value=reply('Here it is.\n```markdown\n' + PLAN + '```\nDone.')):
            agent.run_agent(self.values, 'Plan', self.policy(), 32768)
        self.assertEqual(target.read_text(), PLAN)

    def test_invalid_chat_cannot_replace_prior_valid_delivery(self):
        policy = self.policy()
        agent.run_tool(policy, 'write_file', {'path': PATH, 'content': PLAN})
        with patch.object(agent, 'interruptible_chat', return_value=reply('# Partial draft\n')):
            agent.run_agent(self.values, 'Plan', policy, 32768)
        self.assertEqual((self.root / PATH).read_text(), PLAN)

    def test_capture_does_not_skip_unrelated_tool_work(self):
        replies = [reply(PLAN, [call('write_file', path=PATH, content='# stub'),
                               call('write_file', path='required.txt', content='needed')]), reply('Done')]
        with patch.object(agent, 'interruptible_chat', side_effect=replies) as chat:
            agent.run_agent(self.values, 'Plan', self.policy(), 32768)
        self.assertEqual((self.root / 'required.txt').read_text(), 'needed')
        self.assertEqual(chat.call_count, 1)

    def test_capture_preserves_tool_failures_and_tells_model_what_is_retained(self):
        replies = [reply(PLAN, [call('edit_file', path='absent.txt', old_string='old', new_string='new')]), reply('Unresolved')]
        seen = []
        def chat(*args):
            seen.append(json.loads(json.dumps(args[2])))
            return replies.pop(0)
        with patch.object(agent, 'interruptible_chat', side_effect=chat):
            agent.run_agent(self.values, 'Plan', self.policy(), 32768)
        self.assertEqual(len(seen), 2)
        self.assertTrue(seen[1][-2]['content'].startswith('error:'))
        self.assertIn('already validated and published', seen[1][-1]['content'])
        self.assertEqual((self.root / PATH).read_text(), PLAN)

    def test_truncated_valid_looking_text_is_never_captured(self):
        data = reply(PLAN)
        data['choices'][0]['finish_reason'] = 'length'
        with patch.object(agent, 'interruptible_chat', return_value=data), patch.object(agent, 'save_truncated', return_value=''):
            with self.assertRaises(transport.OutputTruncated):
                agent.run_agent(self.values, 'Plan', self.policy(), 32768)
        self.assertFalse((self.root / PATH).exists())

    def test_capture_keeps_the_normal_symlink_write_guard(self):
        target = self.root / PATH
        target.parent.mkdir(parents=True)
        original = self.root / 'original.md'
        original.write_text('Do not touch')
        target.symlink_to(original)
        with patch.dict(os.environ, UNCLE_STATUS_STAGE='project-plan-investigate'):
            _, policy, _, _, _, _ = hosted._http_setup('agent', {}, 'Go', self.root, False, None)
            with patch.object(agent, 'interruptible_chat', return_value=reply(PLAN)), self.assertRaises(ValueError):
                agent.run_agent(self.values, 'Plan', policy, 32768)
        self.assertEqual(original.read_text(), 'Do not touch')

    def test_valid_chat_wins_same_turn_even_when_the_file_also_validates(self):
        file_plan = PLAN.replace('useful detail', 'newer file detail')
        with patch.object(agent, 'interruptible_chat', side_effect=[reply(PLAN, [call('write_file', path=PATH, content=file_plan)]), reply('Done')]):
            agent.run_agent(self.values, 'Plan', self.policy(), 32768)
        self.assertEqual((self.root / PATH).read_text(), PLAN)
        self.assertIn('self_hosted_capture', self.output.getvalue())

    def test_invalid_chat_gets_precise_private_repair_and_no_stub_overwrite(self):
        bad = PLAN.replace('python3 tests/check.py', '# TODO')
        replies = [reply(bad, [call('write_file', path=PATH, content='# stub')]),
                   reply('', [call('edit_file', path=PATH, old_string='# TODO', new_string='python3 tests/check.py')]), reply('Done')]
        seen = []
        def chat(*args):
            seen.append(json.loads(json.dumps(args[2])))
            if len(seen) == 2:
                self.assertFalse((self.root / PATH).exists())
            return replies.pop(0)
        with patch.object(agent, 'interruptible_chat', side_effect=chat):
            agent.run_agent(self.values, 'Plan', self.policy(), 32768)
        self.assertEqual((self.root / PATH).read_text(), PLAN)
        self.assertIn('verification commands', seen[1][-1]['content'])
        self.assertIn('unique old_string', seen[1][-1]['content'])

    def test_status_text_falls_back_to_normal_tools(self):
        replies = [reply('I will write it.', [call('write_file', path=PATH, content=PLAN)]), reply('Done')]
        with patch.object(agent, 'interruptible_chat', side_effect=replies):
            agent.run_agent(self.values, 'Plan', self.policy(), 32768)
        self.assertEqual((self.root / PATH).read_text(), PLAN)
        self.assertNotIn('self_hosted_capture', self.output.getvalue())

    def test_schema_packet_alongside_read_is_not_regenerated(self):
        with patch.object(agent, 'interruptible_chat', return_value=reply('{"ok":true}', [call('list_dir')])) as chat, \
                patch.object(agent, 'constrained_completion', side_effect=AssertionError('regenerated')):
            text, turns = agent.run_agent(self.values, 'Packet', agent.Policy(self.root), 32768, final_schema=SCHEMA)
        self.assertEqual((turns, chat.call_count), (1, 1))
        self.assertEqual(json.loads(text), {'ok': True})

    def test_invalid_packet_uses_anchored_repair(self):
        replies = [reply('{"ok":"wrong"}', [call('list_dir')]), reply('', [call('edit_file', path='.uncle/workflow/http-answer-repair.json',
                                                           old_string='"wrong"', new_string='true')]), reply('Done')]
        with patch.object(agent, 'interruptible_chat', side_effect=replies), \
                patch.object(agent, 'constrained_completion', side_effect=AssertionError('regenerated')):
            text, turns = agent.run_agent(self.values, 'Packet', agent.Policy(self.root), 32768,
                                          final_schema=SCHEMA, final_name='review_worker_packet')
        self.assertEqual(json.loads(text), {'ok': True})
        self.assertEqual(turns, 3)

    def test_packet_capture_publishes_through_driver_over_stub(self):
        packet = {'schema': 'uncle.artifact/v1', 'kind': 'adversarial-review-worker-packet', 'findings': []}
        delivery = '.uncle/workflow/artifact-delivery/review.json'
        with patch.dict(os.environ, UNCLE_ARTIFACT_DELIVERY=delivery), \
                patch.object(agent, 'interruptible_chat', return_value=reply(json.dumps(packet),
                    [call('write_file', path=delivery, content='{}')])) as chat:
            text, turns = hosted.run_opencode('agent', self.values, json.dumps(packet), self.root)
        self.assertEqual((turns, chat.call_count), (1, 1))
        self.assertEqual(json.loads((self.root / delivery).read_text()), packet)

    def test_schema_constrained_invalid_answer_is_also_repaired_without_rewrite(self):
        replies = [reply('', [call('edit_file', path='.uncle/workflow/http-answer-repair.json',
                                   old_string='"wrong"', new_string='true')]), reply('Done')]
        with patch.object(agent, 'constrained_completion', return_value=('{"ok":"wrong"}', 'stop', {}, 'json_schema')) as final, \
                patch.object(agent, 'interruptible_chat', side_effect=replies), \
                patch.object(agent, 'chat', return_value=reply('Done')):
            result, turns = agent.run_document(self.values, 'Go', self.root, SCHEMA, 'review_worker_packet',
                                               32768, explore_first=False)
        self.assertEqual((json.loads(result), turns, final.call_count), ({'ok': True}, 3, 1))

    def test_repair_chat_that_already_contains_valid_json_is_also_captured(self):
        with patch.object(agent, 'interruptible_chat', side_effect=[reply('{"ok":"wrong"}'), reply('{"ok":true}')]), \
                patch.object(agent, 'constrained_completion', side_effect=AssertionError('regenerated')):
            result, turns = agent.run_document(self.values, 'Go', self.root, SCHEMA, 'review_worker_packet', 32768)
        self.assertEqual((json.loads(result), turns), ({'ok': True}, 2))

    def test_exhausted_loop_closing_document_is_captured(self):
        with patch.object(agent, 'interruptible_chat', return_value=reply('', [call('list_dir')])), \
                patch.object(agent, 'chat', return_value=reply(PLAN)):
            _, turns = agent.run_agent(self.values, 'Go', self.policy(), 32768, turns=1)
        self.assertEqual(turns, 2)
        self.assertEqual((self.root / PATH).read_text(), PLAN)

    def test_stream_assembles_interleaved_tool_calls_unicode_and_usage(self):
        server = self.serve([
            delta('Hello 秘', [{'index': 1, 'id': 'b', 'type': 'function', 'function': {'name': 'read_', 'arguments': '{"path":'}},
                             {'index': 0, 'id': 'a', 'type': 'function', 'function': {'name': 'list_dir', 'arguments': '{'}}]),
            delta('密', [{'index': 0, 'function': {'arguments': '}'}},
                        {'index': 1, 'function': {'name': 'file', 'arguments': '"file.txt"}'}}], 'tool_calls'),
            {'choices': [], 'usage': {'prompt_tokens': 10, 'completion_tokens': 17}}, '[DONE]'])
        data = transport.chat(server.values, [{'role': 'user', 'content': 'go'}], agent.READ_TOOLS, 4096)
        message = data['choices'][0]['message']
        self.assertEqual(message['content'], 'Hello 秘密')
        self.assertEqual(message['tool_calls'], [call('list_dir') | {'id': 'a'},
                         {'id': 'b', 'type': 'function', 'function': {'name': 'read_file', 'arguments': '{"path":"file.txt"}'}}])
        self.assertEqual(data['usage']['completion_tokens'], 17)
        self.assertTrue(server.requests[0]['stream_options']['include_usage'])

    def test_whitespace_in_content_reasoning_and_arguments_stops_in_seconds(self):
        for channel in ('content', 'reasoning_content', 'arguments'):
            with self.subTest(channel=channel):
                item = delta(' ' * 100)
                if channel == 'reasoning_content':
                    item['choices'][0]['delta'] = {'reasoning_content': ' ' * 100}
                if channel == 'arguments':
                    item = delta(calls=[{'index': 0, 'function': {'arguments': ' ' * 100}}])
                server = self.serve([item] * 10000)
                started = time.monotonic()
                with self.assertRaisesRegex(StreamStopped, 'whitespace'):
                    transport.chat(server.values, [], None, 32768)
                self.assertLess(time.monotonic() - started, 2)
                self.assertTrue(server.disconnected.wait(1))
                self.assertLess(server.sent, 100)
        self.assertIn('self_hosted_stream_stop', self.output.getvalue())

    def test_repetition_independent_of_delta_boundaries(self):
        repeated = 'This is an obviously repeated line.\n' * 100
        server = self.serve([delta(repeated[i:i+7]) for i in range(0, len(repeated), 7)])
        with self.assertRaisesRegex(StreamStopped, 'repetition'):
            transport.chat(server.values, [], None, 32768)
        self.assertLess(server.sent, 100)
        compact = 'abcdefghijklmnopq' * 100
        server = self.serve([delta(compact[i:i+5]) for i in range(0, len(compact), 5)])
        with self.assertRaisesRegex(StreamStopped, 'repetition'):
            transport.chat(server.values, [], None, 32768)

    def test_configurable_threshold_and_nonrepeating_json(self):
        (self.root / 'config').write_text('self-hosted.stream-whitespace-chars 50\nself-hosted.stream-repetition-count 3\n')
        server = self.serve([delta(' ' * 50)])
        with self.assertRaisesRegex(StreamStopped, 'whitespace'):
            transport.chat(server.values, [], None, 32768)
        server = self.serve([delta(json.dumps({'rows': list(range(300))}), reason='stop'), '[DONE]'])
        result = transport.chat(server.values, [], None, 32768)
        self.assertEqual(len(json.loads(result['choices'][0]['message']['content'])['rows']), 300)

    def test_usage_fallback_remembered_and_stream_kept(self):
        server = self.serve(reject='usage')
        for _ in range(2):
            self.assertEqual(transport.chat(server.values, [], None, 4096)['choices'][0]['message']['content'], '{"ok":true}')
        self.assertEqual(len(server.requests), 3)
        self.assertTrue(all(body['stream'] for body in server.requests))
        self.assertNotIn('stream_options', server.requests[-1])

    def test_nonstream_fallback_remembered_per_server(self):
        for rejection in ('stream', 'generic'):
            server = self.serve(reject=rejection)
            for _ in range(2):
                transport.chat(server.values, [], None, 4096)
            self.assertEqual([body['stream'] for body in server.requests], [True, True, False, False])
        other = self.serve()
        transport.chat(other.values, [], None, 4096)
        self.assertTrue(other.requests[0]['stream'])

    def test_schema_rejection_does_not_disable_stream(self):
        server = self.serve(reject='schema')
        text, reason, usage, mode = transport.constrained_completion(server.values, [], SCHEMA, 'packet', 4096)
        self.assertEqual(json.loads(text), {'ok': True})
        self.assertEqual(mode, 'prompt')
        self.assertTrue(all(body['stream'] for body in server.requests))

    def test_incomplete_stream_is_never_accepted(self):
        server = self.serve([delta('{"ok":true}'), '[DONE]'])
        with self.assertRaisesRegex(StreamStopped, 'incomplete_stream'):
            transport.chat(server.values, [], None, 4096)

    def test_agent_retries_runaway_once_and_records_turn(self):
        count = [0]
        def script(body):
            count[0] += 1
            return [delta(' ' * 2000)] if count[0] == 1 else [delta('{"ok":true}', reason='stop'), '[DONE]']
        server = self.serve(script)
        answer, requests = agent.run_agent(server.values, 'Go', agent.Policy(self.root), 32768, final_schema=SCHEMA)
        self.assertEqual((json.loads(answer), requests), ({'ok': True}, 2))
        self.assertIn('early_stop:whitespace', self.output.getvalue())
        server = self.serve([delta(' ' * 2000)])
        with self.assertRaises(StreamStopped):
            agent.run_agent(server.values, 'Go', agent.Policy(self.root), 32768, final_schema=SCHEMA)
        self.assertEqual(len(server.requests), 2)

    def test_final_runaway_retries_without_grammar_and_validates(self):
        def script(body):
            return [delta(' ' * 2000)] if 'response_format' in body else [delta('{"ok":true}', reason='stop'), '[DONE]']
        server = self.serve(script)
        answer, requests = agent.run_document(server.values, 'Go', self.root, SCHEMA, 'review_worker_packet', 32768, explore_first=False)
        self.assertEqual((json.loads(answer), requests), ({'ok': True}, 2))
        self.assertNotIn('response_format', server.requests[-1])

    def test_caps_on_tools_and_final_with_stage_environment_and_config_overrides(self):
        with patch.dict(os.environ, UNCLE_STATUS_STAGE='updated-plan-worker-edits-1'):
            self.assertEqual(transport.turn_output_tokens(64512), 4096)
            (self.root / 'config').write_text('updated-plan.turn-output-tokens 2300\nupdated-plan.final-output-tokens 2400\n')
            self.assertEqual(transport.turn_output_tokens(64512), 2300)
            self.assertEqual(transport.output_cap(64512, 'final-output-tokens'), 2400)
            with patch.dict(os.environ, WORKFLOW_SELF_HOSTED_TURN_OUTPUT_TOKENS_UPDATED_PLAN_WORKER_EDITS_1='1200'):
                self.assertEqual(transport.turn_output_tokens(64512), 1200)
            server = self.serve()
            agent.run_document(server.values, 'Go', self.root, SCHEMA, 'updated_plan_edit_ops_packet', 64512)
            self.assertEqual(server.requests[-1]['max_tokens'], 2300 + 32768)
            agent.run_document(server.values, 'Go', self.root, SCHEMA, 'updated_plan_edit_ops_packet', 64512, explore_first=False)
            self.assertEqual(server.requests[-1]['max_tokens'], 2400 + 32768)
        self.assertEqual(transport.turn_output_tokens(64512), 32768)
        self.assertEqual(transport.turn_output_tokens(64512, 'review_worker_packet'), 32768)

    def test_requirements_investigation_uses_canonical_validator(self):
        headings = ('Required functionality', 'Optional functionality', 'Constraints', 'User-visible behaviors',
                    'System behaviors', 'Failure behaviors', 'Ambiguities', 'Assumptions', 'Explicit non-goals', 'Definition of done')
        text = '# Requirements\n' + ''.join('## %s\nDetails for %s.\n' % (h, h) for h in headings)
        with patch.dict(os.environ, UNCLE_STATUS_STAGE='requirements-investigate'):
            _, policy, _, _, _, _ = hosted._http_setup('agent', {}, 'Go', self.root, False, None)
            with patch.object(agent, 'interruptible_chat', return_value=reply(text)):
                agent.run_agent(self.values, 'Go', policy, 32768)
        self.assertEqual((self.root / '.uncle/workflow/requirements-investigation.md').read_text(), text)

    def test_review_investigation_probe_has_no_canonical_side_effects(self):
        text = '# Review\n\nNo findings.\n\n## Overall assessment\nThe plan is ready.\n'
        with patch.dict(os.environ, UNCLE_STATUS_STAGE='adversarial-review-investigate'):
            _, policy, _, _, _, _ = hosted._http_setup('reviewer', {}, 'Review', self.root, False, None)
            with patch.object(agent, 'interruptible_chat', return_value=reply(text)):
                agent.run_agent(self.values, 'Review', policy, 32768)
        self.assertEqual((self.root / '.uncle/workflow/adversarial-review-investigation.md').read_text(), text)
        self.assertFalse((self.root / '.uncle/workflow/documents').exists())
        with self.assertRaisesRegex(ValueError, 'Missing nonempty Overall assessment'):
            hosted.validate_investigation('ADVERSARIAL_REVIEW.md', '# Stub')

    def test_preflight_capture_keeps_acceptance_validation(self):
        text = '# Preflight\n\n## Acceptance gate\n| ID | Required | Status | Evidence |\n|---|---|---|---|\n| PF-1 | YES | PASS | Checked runtime |\n'
        hosted.validate_investigation('PREFLIGHT_REPORT.md', text)
        with self.assertRaises(ValueError):
            hosted.validate_investigation('PREFLIGHT_REPORT.md', text.replace('PASS', 'invented'))
        self.assertFalse((self.root / '.uncle/workflow/documents').exists())

    def test_implementation_and_repair_notes_use_same_checks_as_file_writes(self):
        headings = ('Changed files', 'Deviations', 'Unresolved concerns', 'Plan blockers', 'Findings not fixed')
        for stage in ('implementation-investigate', 'repair-investigate'):
            text = '# Notes\n' + ''.join('## %s\nNone.\n' % h for h in headings)
            with patch.dict(os.environ, UNCLE_STATUS_STAGE=stage):
                _, policy, _, _, _, _ = hosted._http_setup('agent', {}, 'Go', self.root, False, None)
                path = next(iter(policy.draft_checks))
                error = agent.run_tool(policy, 'write_file', {'path': str(path), 'content': '# Stub'})
                self.assertIn('Missing or empty investigation section', error)
                with patch.object(agent, 'interruptible_chat', return_value=reply(text)):
                    agent.run_agent(self.values, 'Go', policy, 32768)
                self.assertEqual(path.read_text(), text)


if __name__ == '__main__':
    unittest.main()
