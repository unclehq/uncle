#!/usr/bin/env python3
"""Hermetic request-options contracts; all inference and discovery are stubbed."""
import copy
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
from urllib.error import HTTPError

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts/lib'))
import http_agent
import self_hosted
import self_hosted_http as transport

ENV = 'WORKFLOW_SELF_HOSTED_REQUEST_OPTIONS'
EXTRA = {'chat_template_kwargs': {'thinking': False}}


class RequestOptions(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory(prefix='uncle-request-options-')
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.config = self.root / 'config'
        env = patch.dict(os.environ, {'UNCLE_CONFIG': str(self.config),
                                     'WORKFLOW_SELF_HOSTED_REASONING_EFFORT': 'on',  # opt-in hint under test
                                     'UNCLE_STATUS_STAGE': 'project-plan',
                                     'UNCLE_PROJECT_ROOT': str(self.root)}, clear=True)
        env.start()
        self.addCleanup(env.stop)
        transport._request_features.clear()
        transport._capabilities.clear()
        self.values = {'model': 'arbitrary-model', 'api_key': 'fixture', 'base_url': 'http://fixture.invalid/v1'}
        self.bodies = []
        self.reply = 'done'
        self.reject = lambda body: None
        self.logs = io.StringIO()
        for patcher in (patch.object(transport, 'post', side_effect=self.post),
                        patch.object(transport, 'detect_flavor', return_value='generic'),
                        patch.object(transport, '_request', side_effect=AssertionError('no network')),
                        patch('sys.stderr', self.logs)):
            patcher.start()
            self.addCleanup(patcher.stop)

    def post(self, url, key, body, timeout):
        self.bodies.append(copy.deepcopy(body))
        rejection = self.reject(body)
        if rejection:
            status, detail = rejection
            raise HTTPError(url, status, 'fixture', {}, io.BytesIO(detail.encode()))
        return {'choices': [{'message': {'role': 'assistant', 'content': self.reply}, 'finish_reason': 'stop'}]}

    def configure(self, options=EXTRA):
        self.config.write_text('self-hosted.request-options ' + json.dumps(options) + '\n')

    def chat(self, values=None):
        return transport.chat(values or self.values, [], http_agent.READ_TOOLS, 100)

    def final(self):
        return transport.constrained_completion(self.values, [], {}, 'fixture', 100)

    def test_default_is_empty_and_preserves_original_body(self):
        self.assertEqual(transport.request_options(), {})
        self.chat()
        self.assertEqual(set(self.bodies[0]), {'model', 'messages', 'tools', 'max_tokens', 'stream', 'stream_options',
                                              'temperature', 'reasoning_effort'})
        self.assertTrue(self.bodies[0]['stream'])
        self.assertEqual(self.bodies[0]['stream_options'], {'include_usage': True})
        self.assertEqual(self.logs.getvalue(), '')

    def test_precedence_and_replacement(self):
        self.config.write_text('self-hosted.request-options {"global":true}\n'
                               'project-plan.request-options {"stage":true}\n')
        self.assertEqual(transport.request_options(), {'stage': True})
        with patch.dict(os.environ, {ENV: '{"env_global":true}'}):
            self.assertEqual(transport.request_options(), {'env_global': True})
            with patch.dict(os.environ, {ENV + '_PROJECT_PLAN': '{"env_stage":true}'}):
                self.assertEqual(transport.request_options(), {'env_stage': True})
            with patch.dict(os.environ, {ENV + '_PROJECT_PLAN': '{}'}):
                self.assertEqual(transport.request_options(), {})
        self.config.write_text('self-hosted.request-options {"global":true}\nproject-plan.request-options {}\n')
        self.assertEqual(transport.request_options(), {})

    def test_parent_mapping_for_config_and_environment(self):
        cases = {
            'project-plan-section-outline': 'project-plan',
            'project-plan-investigate': 'project-plan',
            'requirements': 'project-plan', 'requirements-investigate': 'project-plan',
            'adversarial-review-worker-security': 'adversarial-review',
            'test-review-worker-tests': 'test-review',
            'updated-plan-review-worker-scope': 'updated-plan',
            'execute-checklist-worker-MC-001': 'execute-checklist',
            'implementation-step-2': 'implementation',
            'manual-checklist-base': 'manual-checklist', 'manual-checklist-delta': 'manual-checklist',
            'repair-investigate': 'repair', 'final-audit-investigate': 'final-audit',
            'preview-build': 'project-plan', 'preview-build-part-script': 'project-plan',
        }
        for stage, parent in cases.items():
            with self.subTest(stage=stage):
                self.config.write_text('project-plan.model any\n%s.request-options {"parent":true}\n' % parent)
                self.assertEqual(transport.request_options(stage), {'parent': True})
                var = ENV + '_' + parent.upper().replace('-', '_')
                with patch.dict(os.environ, {var: '{"env_parent":true}', ENV: '{"global":true}'}):
                    self.assertEqual(transport.request_options(stage), {'env_parent': True})
                    own = ENV + '_' + stage.upper().replace('-', '_')
                    with patch.dict(os.environ, {own: '{}'}):
                        self.assertEqual(transport.request_options(stage), {})

    def test_explicit_stage_config_beats_inherited_config(self):
        self.config.write_text('project-plan.request-options {"parent":true}\nrequirements.request-options {}\n')
        self.assertEqual(transport.request_options('requirements'), {})

    def test_empty_malformed_nonobject_and_nonfinite_values(self):
        for value in ('', '[1]', 'null', 'true', '42', '"x"', '{', '{"x":}', '{"x":1,}',
                      '{"x":NaN}', '{"x":Infinity}', '{"x":1e999}', '{}\n{}', '{\n"x":1}', '{}\r'):
            with self.subTest(value=value), patch.dict(os.environ, {ENV: value}):
                with self.assertRaisesRegex(ValueError, 'REQUEST_OPTIONS.*JSON object'):
                    transport.request_options()
        self.config.write_text('project-plan.request-options\n')
        with self.assertRaisesRegex(ValueError, 'project-plan.request-options'):
            transport.request_options()

    def test_size_limit_counts_utf8_bytes(self):
        for value in ('{"x":"' + 'a' * 4088 + '"}', '{"x":"' + 'é' * 2044 + '"}'):
            self.assertEqual(len(value.encode()), 4096)
            with patch.dict(os.environ, {ENV: value}):
                self.assertIn('x', transport.request_options())
            with patch.dict(os.environ, {ENV: value + ' '}):
                with self.assertRaisesRegex(ValueError, '4096 bytes'):
                    transport.request_options()

    def test_config_hash_quotes_comments_and_first_key_win(self):
        options = {'text': 'a  # b " c \\ # d', '#key': {'hash': '#'}}
        self.config.write_text('  # ordinary comment\nproject-plan.request-options ' + json.dumps(options) +
                               ' # trailing comment\nproject-plan.request-options {}\nmodel any # old parser\n')
        self.assertEqual(transport.request_options(), options)
        self.assertEqual(transport._config_values()['model'], 'any')
        with patch.dict(os.environ, {ENV: json.dumps(options)}):
            self.assertEqual(transport.request_options(), options)
        self.config.write_text('project-plan.request-options {\n"x":true\n}\n')
        with self.assertRaisesRegex(ValueError, 'valid JSON object'):
            transport.request_options()

    def test_all_protected_keys_fail_before_credentials_or_transport(self):
        for key in transport.PROTECTED_REQUEST_KEYS:
            with self.subTest(key=key):
                self.configure({key: {}})
                with patch.object(self_hosted, 'read_keys', side_effect=AssertionError('no credentials')):
                    with self.assertRaisesRegex(ValueError, 'protected request key ' + key):
                        self_hosted.settings(self.config, 'project-plan')
                with self.assertRaisesRegex(ValueError, 'protected request key ' + key):
                    self.final()
        self.assertEqual(self.bodies, [])

    def test_bad_options_fail_before_discovery_prefetch_or_tools(self):
        self.config.write_text('self-hosted.request-options nope\n')
        with patch.object(http_agent, 'prefetch_context', side_effect=AssertionError('no file reads')):
            with self.assertRaisesRegex(ValueError, 'request-options'):
                http_agent.run_agent(self.values, 'Go', http_agent.Policy(self.root), 100)
        with patch.object(transport, 'capabilities', side_effect=AssertionError('no discovery')):
            with self.assertRaisesRegex(ValueError, 'request-options'):
                self.final()
        self.assertEqual(self.bodies, [])

    def test_explicit_config_path_options_travel_with_connection(self):
        for options in (EXTRA, {}):
            self.configure(options)
            with patch.dict(os.environ, {'UNCLE_SELF_HOSTED_API_KEY': 'fixture',
                                        'UNCLE_SELF_HOSTED_MODEL': 'any',
                                        'UNCLE_SELF_HOSTED_BASE_URL': 'http://fixture.invalid/v1'}), \
                    patch.object(self_hosted, 'read_keys', return_value={}):
                values = self_hosted.settings(self.config, 'project-plan')
            with patch.dict(os.environ, {ENV: '{"different":true}'}):
                self.chat(values)
            self.assertNotIn('different', self.bodies[-1])
            self.assertEqual('chat_template_kwargs' in self.bodies[-1], bool(options))

    def test_merge_is_one_level_and_does_not_mutate_inputs(self):
        body = {'temperature': 0, 'chat_template_kwargs': {'existing': True, 'nested': {'old': 1}}}
        extras = {'temperature': 2, 'chat_template_kwargs': {'thinking': False, 'nested': {'new': 2}},
                  'other': [1, 2]}
        before = copy.deepcopy((body, extras))
        merged, applied = transport.merge_request_options(body, extras)
        self.assertEqual(merged, {'temperature': 0, 'chat_template_kwargs':
                                {'existing': True, 'thinking': False, 'nested': {'new': 2}}, 'other': [1, 2]})
        self.assertEqual(set(applied), {'chat_template_kwargs', 'other'})
        self.assertEqual((body, extras), before)
        for existing, supplied in ((None, {}), ({'a': 1}, False), ([], {}), (False, True)):
            self.assertEqual(transport.merge_request_options({'x': existing}, {'x': supplied}), ({'x': existing}, {}))

    def test_options_in_tool_closing_schema_reviewer_and_retry_requests(self):
        self.configure()
        call = {'id': 'one', 'type': 'function', 'function': {'name': 'list_dir', 'arguments': '{}'}}
        reply = {'choices': [{'message': {'role': 'assistant', 'content': '', 'tool_calls': [call]},
                              'finish_reason': 'tool_calls'}]}
        original_post = self.post
        def scripted(*args):
            result = original_post(*args)
            return reply if len(self.bodies) == 1 else result
        with patch.object(transport, 'post', side_effect=scripted):
            http_agent.run_agent(self.values, 'Go', http_agent.Policy(self.root), 100, turns=1)
        self.assertEqual(len(self.bodies), 2)
        self.assertIn('tools', self.bodies[0])
        self.assertNotIn('tools', self.bodies[1])
        self.reply = '{}'
        with patch.dict(os.environ, {'UNCLE_STATUS_STAGE': 'final-audit'}):
            http_agent.run_agent(self.values, 'Review', http_agent.Policy(self.root), 100,
                                 turns=0, final_schema={'type': 'object'}, side='reviewer')
        self.reject = lambda b: (400, 'unsupported response_format json_schema') if 'response_format' in b else None
        self.assertEqual(self.final()[3], 'prompt')
        self.assertTrue(all(b['chat_template_kwargs'] == EXTRA['chat_template_kwargs'] for b in self.bodies))
        self.assertIn('[final-audit]', self.logs.getvalue())

    def test_every_schema_mode_and_native_request_keeps_options_and_limits(self):
        self.configure()
        for flavor in ('generic', 'vllm', 'ollama'):
            for mode in transport.MODE_ORDER[flavor]:
                with self.subTest(mode=mode):
                    def post(url, key, body, timeout):
                        self.bodies.append(body)
                        if mode == 'ollama_format':
                            return {'message': {'content': '{}'}}
                        return {'choices': [{'message': {'content': '{}'}, 'finish_reason': 'stop'}]}
                    with patch.object(transport, 'post', side_effect=post):
                        transport._final_call(self.values, [], {}, 'fixture', mode, 123, 'medium', 30)
                    body = self.bodies[-1]
                    self.assertEqual(body['chat_template_kwargs'], EXTRA['chat_template_kwargs'])
                    self.assertEqual(body.get('max_tokens', body.get('options', {}).get('num_predict')), 123)

    def test_stage_snapshot_and_names_only_observability(self):
        self.configure({'custom': 'private-value', 'temperature': 2})
        values = transport.configure_request_options(self.values)
        self.configure({'changed': True})
        self.chat(values)
        self.chat(values)
        self.assertEqual(self.bodies[0]['custom'], 'private-value')
        log = self.logs.getvalue()
        self.assertIn('[project-plan]', log)
        self.assertIn('"custom"', log)
        self.assertNotIn('private-value', log)
        self.assertNotIn('temperature', log)
        self.assertEqual(log.count('request options applied:'), 1)

    def test_named_rejection_retry_memory_and_base_url_isolation(self):
        self.configure()
        for status, detail in ((400, 'unsupported chat_template_kwargs'), (422, 'unknown thinking'),
                               (409, 'chat_template_kwargs not supported')):
            with self.subTest(status=status):
                transport._request_features.clear()
                self.bodies.clear()
                self.logs.seek(0)
                self.logs.truncate()
                self.reject = lambda b: (status, detail) if 'chat_template_kwargs' in b else None
                self.assertIsNotNone(self.chat())
                self.assertEqual(self.final()[3], 'json_schema')
                self.chat(dict(self.values, base_url=self.values['base_url'] + '/'))
                self.assertEqual(sum('chat_template_kwargs' in b for b in self.bodies), 1)
                self.assertEqual(len(self.bodies), 4)
                self.assertEqual(self.logs.getvalue().count('server rejected request options'), 1)
                self.assertIn('[project-plan]', self.logs.getvalue())
                self.assertIn('"chat_template_kwargs"', self.logs.getvalue())
                self.assertNotIn('False', self.logs.getvalue())
                self.assertNotIn('effort', transport._request_features[self.values['base_url']])
                self.assertEqual(transport._capabilities[self.values['base_url']]['rejected'], set())
                self.reject = lambda b: None
                self.chat(dict(self.values, base_url='http://second.invalid/v1'))
                self.assertIn('chat_template_kwargs', self.bodies[-1])

    def test_generic_400_only_disables_options_after_success_without_them(self):
        self.configure()
        self.reject = lambda b: (400, 'bad request') if 'chat_template_kwargs' in b else None
        self.chat()
        self.chat()
        self.assertEqual(len(self.bodies), 3)  # one retry, then remembered
        self.assertNotIn('chat_template_kwargs', self.bodies[-1])
        self.assertTrue(all(b['reasoning_effort'] == 'low' for b in self.bodies if 'chat_template_kwargs' not in b))
        self.assertNotIn('effort', transport._request_features[self.values['base_url']])
        transport._request_features.clear()
        self.reject = lambda b: (400, 'bad request')
        self.assertIsNone(self.chat())
        self.assertNotIn('request_options', transport._request_features[self.values['base_url']])
        self.assertNotIn('effort', transport._request_features[self.values['base_url']])

    def test_generic_effort_rejection_does_not_get_misattributed_to_options(self):
        self.configure()
        self.reject = lambda b: (400, 'bad request') if 'reasoning_effort' in b else None
        self.assertEqual(self.final()[3], 'json_schema')
        features = transport._request_features[self.values['base_url']]
        self.assertNotIn('request_options', features)
        self.assertIs(features['effort'], False)
        self.assertIn('chat_template_kwargs', self.bodies[-1])

    def test_combined_generic_rejections_preserve_schema(self):
        self.configure()
        self.reject = lambda b: (400, 'bad request') if 'reasoning_effort' in b or 'chat_template_kwargs' in b else None
        self.assertEqual(self.final()[3], 'json_schema')
        features = transport._request_features[self.values['base_url']]
        self.assertIs(features['request_options'], False)
        self.assertIs(features['effort'], False)
        self.assertEqual(transport._capabilities[self.values['base_url']]['rejected'], set())

    def test_option_fallback_restores_uncles_original_object(self):
        self.configure()
        self.reject = lambda b: (422, 'unknown thinking') if 'thinking' in b.get('chat_template_kwargs', {}) else None
        body = {'model': 'any', 'messages': [], 'chat_template_kwargs': {'owned': True}}
        transport.compatible_post(self.values, body, 30)
        self.assertEqual(self.bodies[-1]['chat_template_kwargs'], {'owned': True})

    def test_tui_save_preserves_option_lines_without_reading_credentials(self):
        sys.path.insert(0, str(ROOT))
        self.addCleanup(lambda: sys.path.remove(str(ROOT)))
        import uncle_tui as tui
        raw = '{"text":"a  # b"} # comment'
        self.config.write_text('self-hosted.request-options ' + raw + '\n'
                               'project-plan.request-options {}\n'
                               'requirements.request-options invalid\n')
        ui = tui.UncleTUI.__new__(tui.UncleTUI)
        with patch.object(tui, 'CONFIG_PATH', str(self.config)), \
                patch.object(tui, 'read_keys', return_value={}), patch.object(tui, 'save_keys'), \
                patch.object(tui, '_ensure_uncle_gitignored'):
            ui.load_config()
            ui.save_config()
        rewritten = self.config.read_text()
        self.assertIn('self-hosted.request-options ' + raw + '\n', rewritten)
        self.assertIn('requirements.request-options invalid\n', rewritten)
        self.assertEqual(transport.request_options(), {})
        self.assertEqual(transport.request_options('repair'), {'text': 'a  # b'})

    def test_effort_rejection_keeps_options_and_schema(self):
        self.configure()
        self.reject = lambda b: (400, 'unsupported reasoning_effort') if 'reasoning_effort' in b else None
        self.assertEqual(self.final()[3], 'json_schema')
        self.chat()
        self.assertTrue(all('chat_template_kwargs' in b for b in self.bodies))
        self.assertNotIn('reasoning_effort', self.bodies[-1])
        self.assertNotIn('request_options', transport._request_features[self.values['base_url']])

    def test_combined_effort_and_option_rejections_in_either_order(self):
        self.configure()
        for first in ('reasoning_effort', 'chat_template_kwargs'):
            with self.subTest(first=first):
                transport._request_features.clear()
                transport._capabilities.clear()
                def reject(body):
                    for key in (first, 'reasoning_effort', 'chat_template_kwargs'):
                        if key in body:
                            return 400, 'unsupported ' + key
                self.reject = reject
                self.assertEqual(self.final()[3], 'json_schema')
                self.assertEqual(transport._capabilities[self.values['base_url']]['rejected'], set())
                features = transport._request_features[self.values['base_url']]
                self.assertIs(features['effort'], False)
                self.assertIs(features['request_options'], False)
                self.chat()
                self.assertNotIn('chat_template_kwargs', self.bodies[-1])
                self.assertNotIn('reasoning_effort', self.bodies[-1])

    def test_schema_rejection_keeps_options_and_effort(self):
        self.configure()
        self.reject = lambda b: (400, 'unsupported response_format json_schema') if b.get('response_format', {}).get('type') == 'json_schema' else None
        self.assertEqual(self.final()[3], 'json_object')
        self.assertEqual(len(self.bodies), 2)
        self.assertTrue(all('chat_template_kwargs' in b and 'reasoning_effort' in b for b in self.bodies))
        self.assertNotIn('request_options', transport._request_features[self.values['base_url']])

    def test_non_option_failures_do_not_disable_options(self):
        self.configure()
        for status in (401, 403, 429, 500):
            with self.subTest(status=status):
                self.bodies.clear()
                self.reject = lambda b: (status, 'unavailable')
                with self.assertRaisesRegex(ValueError, 'HTTP %d' % status):
                    self.chat()
                self.assertEqual(len(self.bodies), 1)
                self.assertNotIn('request_options', transport._request_features[self.values['base_url']])

    def test_hosted_runner_resolution_ignores_invalid_options(self):
        # Execute the existing shared shell resolver; no git repositories or
        # fixture commits, external CLIs, credentials, or network are needed.
        script = 'source scripts/lib/stage-config.sh\n' + '\n'.join(
            'uncle_stage_runner implementation\nuncle_stage_model implementation %s\nuncle_stage_effort implementation' % runner
            for runner in ('claude', 'codex', 'kimi'))
        for runner in ('claude', 'codex', 'kimi'):
            self.config.write_text('implementation.runner %s\nimplementation.model fixture-model\n'
                                   'implementation.effort medium\n' % runner)
            base = subprocess.run(['bash', '-c', script], cwd=ROOT, env=dict(os.environ),
                                  text=True, capture_output=True, check=True)
            with self.config.open('a') as stream:
                stream.write('self-hosted.request-options malformed\nimplementation.request-options malformed\n')
            configured = subprocess.run(['bash', '-c', script], cwd=ROOT,
                                        env=dict(os.environ, **{ENV: 'malformed'}),
                                        text=True, capture_output=True, check=True)
            self.assertEqual((base.stdout, base.stderr), (configured.stdout, configured.stderr))


if __name__ == '__main__':
    unittest.main()
