#!/usr/bin/env python3
"""The Anthropic API runner: a profile of the Self Hosted class that speaks the Messages API to api.anthropic.com."""
import copy
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock
from urllib.error import HTTPError

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts' / 'lib'))
import anthropic_protocols as ap  # noqa: E402
import self_hosted  # noqa: E402
import self_hosted_http as http  # noqa: E402

KEY = 'sk-ant-test-0123456789'
MSGS = [{'role': 'system', 'content': 'be brief'}, {'role': 'user', 'content': 'hi'}]
TOOLS = [{'type': 'function', 'function': {'name': 'read_file', 'description': 'read', 'parameters': {
    'type': 'object', 'properties': {'path': {'type': 'string'}}}}}]
SCHEMA = {'type': 'object', 'properties': {'a': {'type': 'string'}}}


def clean_env():
    return {k: v for k, v in os.environ.items()
            if not k.startswith(('UNCLE_', 'WORKFLOW_', 'ANTHROPIC_', 'AWS_', 'OPENAI_', 'SEREN_'))}


class Protocol(unittest.TestCase):
    def test_endpoint_and_headers_are_fixed(self):
        self.assertEqual(ap.messages_url(), 'https://api.anthropic.com/v1/messages')
        self.assertEqual(ap.models_url(), 'https://api.anthropic.com/v1/models?limit=1000')
        self.assertTrue(ap.models_url('m1').endswith('&after_id=m1'))
        headers = ap.build_headers(KEY)
        self.assertEqual(headers['x-api-key'], KEY)
        self.assertEqual(headers['anthropic-version'], '2023-06-01')
        self.assertNotIn('Authorization', headers)

    def test_key_validation_never_echoes_the_key(self):
        self.assertEqual(ap.validate_key(KEY), KEY)
        for bad in ('', None, 'two words', 'new\nline', 'tab\tbed', 'ünï'):
            with self.assertRaises(ValueError) as caught:
                ap.validate_key(bad)
            if isinstance(bad, str) and bad:
                self.assertNotIn(bad, str(caught.exception))

    def test_body_system_tools_and_no_temperature(self):
        body = ap.build_body('claude-x', MSGS, 100, TOOLS)
        self.assertEqual((body['model'], body['max_tokens'], body['system']), ('claude-x', 100, 'be brief'))
        self.assertEqual(body['messages'], [{'role': 'user', 'content': [{'type': 'text', 'text': 'hi'}]}])
        self.assertEqual(body['tools'], [{'name': 'read_file', 'description': 'read',
                                          'input_schema': TOOLS[0]['function']['parameters']}])
        self.assertNotIn('tool_choice', body)
        self.assertNotIn('temperature', body)

    def test_schema_becomes_one_forced_tool(self):
        body = ap.build_body('m', MSGS, 50, None, SCHEMA, 'answer')
        self.assertEqual(body['tool_choice'], {'type': 'tool', 'name': 'answer'})
        self.assertEqual(body['tools'][-1]['name'], 'answer')
        self.assertEqual(body['tools'][-1]['input_schema'], SCHEMA)

    def test_tool_history_maps_to_tool_use_and_tool_result_and_merges_turns(self):
        turns = MSGS + [
            {'role': 'assistant', 'content': 'looking', 'tool_calls': [
                {'id': 'c1', 'type': 'function', 'function': {'name': 'read_file', 'arguments': '{"path": "a"}'}}]},
            {'role': 'tool', 'tool_call_id': 'c1', 'content': 'file text'},
            {'role': 'user', 'content': 'and now?'},
        ]
        body = ap.build_body('m', turns, 50)
        roles = [m['role'] for m in body['messages']]
        self.assertEqual(roles, ['user', 'assistant', 'user'])          # tool result and the next user turn merged
        self.assertEqual(body['messages'][1]['content'][1], {'type': 'tool_use', 'id': 'c1', 'name': 'read_file', 'input': {'path': 'a'}})
        self.assertEqual(body['messages'][2]['content'][0],
                         {'type': 'tool_result', 'tool_use_id': 'c1', 'content': 'file text'})
        # History with tool_use and no tools offered still declares them: the API rejects it otherwise.
        self.assertEqual([t['name'] for t in body['tools']], ['read_file'])

    def test_response_parsing(self):
        data = {'content': [{'type': 'text', 'text': 'ok'},
                            {'type': 'tool_use', 'id': 't1', 'name': 'read_file', 'input': {'path': 'x'}}],
                'stop_reason': 'tool_use', 'usage': {'input_tokens': 3, 'output_tokens': 4}}
        parsed = ap.parse_response(data)
        self.assertEqual(parsed['text'], 'ok')
        self.assertEqual(parsed['tool_calls'], [{'id': 't1', 'name': 'read_file', 'arguments': {'path': 'x'}}])
        self.assertEqual((parsed['usage'], parsed['reason']), ({'input': 3, 'output': 4}, 'tool_use'))
        answer = ap.parse_response({'content': [{'type': 'tool_use', 'id': 't', 'name': 'result', 'input': {'a': 'b'}}],
                                    'stop_reason': 'tool_use'}, 'result')
        self.assertEqual((json.loads(answer['text']), answer['tool_calls']), ({'a': 'b'}, []))
        for bad in (None, [], {}, {'content': 'x'}):
            with self.assertRaises(ValueError):
                ap.parse_response(bad)

    def test_model_list(self):
        pages = [{'data': [{'id': 'claude-b'}, {'id': 'claude-a'}, {'id': 'bad id'}, {'x': 1}]}, {'data': [{'id': 'claude-a'}]}]
        self.assertEqual(ap.parse_models(pages), ['claude-a', 'claude-b'])
        with self.assertRaises(ValueError):
            ap.parse_models([{'data': 'nope'}])


class Reply:
    """Stands in for self_hosted_http._request: records calls, replays scripted answers or errors."""

    def __init__(self, *answers):
        self.answers, self.calls = list(answers), []

    def __call__(self, url, api_key, body=None, timeout=30, headers=None):
        self.calls.append(dict(url=url, key=api_key, body=copy.deepcopy(body), headers=headers))
        answer = self.answers.pop(0)
        if isinstance(answer, Exception):
            raise answer
        return answer


def http_error(code, message='', headers=None):
    payload = json.dumps({'type': 'error', 'error': {'type': 'x', 'message': message}}).encode()
    return HTTPError('https://api.anthropic.com/v1/messages', code, 'x', headers or {}, io.BytesIO(payload))


VALUES = {'_profile': 'anthropic-api', 'api_key': KEY, 'model': 'claude-x', 'base_url': 'https://api.anthropic.com'}
OK = {'content': [{'type': 'text', 'text': 'hello'}], 'stop_reason': 'end_turn', 'usage': {'input_tokens': 5, 'output_tokens': 2}}


class Transport(unittest.TestCase):
    def post(self, reply, body=None, values=VALUES):
        with mock.patch.object(http, '_request', reply), mock.patch('time.sleep'):
            return http.compatible_post(values, body or {'messages': MSGS, 'max_tokens': 64, 'temperature': 0.7}, 5)

    def test_request_goes_to_the_fixed_endpoint_with_the_key_header_and_no_temperature(self):
        reply = Reply(OK)
        out = self.post(reply)
        call = reply.calls[0]
        self.assertEqual(call['url'], 'https://api.anthropic.com/v1/messages')
        self.assertEqual(call['headers']['x-api-key'], KEY)
        self.assertNotIn('temperature', call['body'])
        self.assertEqual(call['body']['model'], 'claude-x')
        self.assertEqual(out['choices'][0]['message'], {'role': 'assistant', 'content': 'hello'})
        self.assertEqual(out['choices'][0]['finish_reason'], 'stop')
        self.assertEqual(out['usage'], {'prompt_tokens': 5, 'completion_tokens': 2, 'total_tokens': 7})

    def test_the_endpoint_does_not_come_from_the_values(self):
        reply = Reply(OK)
        self.post(reply, values=dict(VALUES, base_url='https://evil.example'))
        self.assertTrue(reply.calls[0]['url'].startswith('https://api.anthropic.com/'))

    def test_tool_calls_and_length_are_translated(self):
        reply = Reply({'content': [{'type': 'tool_use', 'id': 'a', 'name': 'read_file', 'input': {'path': 'p'}}],
                       'stop_reason': 'tool_use', 'usage': {}})
        message = self.post(reply, {'messages': MSGS, 'max_tokens': 9, 'tools': TOOLS})['choices'][0]
        self.assertEqual(message['finish_reason'], 'tool_calls')
        call = message['message']['tool_calls'][0]
        self.assertEqual((call['id'], call['function']['name'], json.loads(call['function']['arguments'])),
                         ('a', 'read_file', {'path': 'p'}))
        reply = Reply(dict(OK, stop_reason='max_tokens'))
        self.assertEqual(self.post(reply)['choices'][0]['finish_reason'], 'length')

    def test_schema_answer_is_a_finished_stop(self):
        reply = Reply({'content': [{'type': 'tool_use', 'id': 'a', 'name': 'result', 'input': {'a': 'b'}}],
                       'stop_reason': 'tool_use', 'usage': {}})
        body = {'messages': MSGS, 'max_tokens': 64, 'response_format': {'type': 'json_schema', 'json_schema': {'name': 'result', 'schema': SCHEMA}}}
        choice = self.post(reply, body)['choices'][0]
        self.assertEqual(json.loads(choice['message']['content']), {'a': 'b'})
        self.assertEqual(choice['finish_reason'], 'stop')
        self.assertEqual(reply.calls[0]['body']['tool_choice'], {'type': 'tool', 'name': 'result'})

    def test_overload_and_rate_limit_are_retried(self):
        reply = Reply(http_error(529), http_error(429, headers={'retry-after': '1'}), OK)
        self.assertEqual(self.post(reply)['choices'][0]['message']['content'], 'hello')
        self.assertEqual(len(reply.calls), 3)

    def test_a_refused_forced_tool_falls_back_to_plain_text(self):
        reply = Reply(http_error(400, 'tool_choice is not supported with this model'), OK)
        body = {'messages': MSGS, 'max_tokens': 64, 'response_format': {'type': 'json_schema', 'json_schema': {'name': 'r', 'schema': SCHEMA}}}
        self.assertEqual(self.post(reply, body)['choices'][0]['message']['content'], 'hello')
        self.assertNotIn('tool_choice', reply.calls[1]['body'])

    def test_too_many_output_tokens_retries_at_the_common_ceiling(self):
        reply = Reply(http_error(400, 'max_tokens: 64000 > 8192, which is the maximum allowed'), OK)
        self.post(reply, {'messages': MSGS, 'max_tokens': 64000})
        self.assertEqual([c['body']['max_tokens'] for c in reply.calls], [64000, 4096])

    def test_errors_name_the_status_and_never_the_key(self):
        reply = Reply(http_error(401, 'invalid x-api-key'))
        with self.assertRaises(ValueError) as caught:
            self.post(reply)
        text = str(caught.exception)
        self.assertIn('HTTP 401', text)
        self.assertIn('invalid x-api-key', text)
        self.assertNotIn(KEY, text)

    def test_redirect_is_refused(self):
        with self.assertRaisesRegex(ValueError, 'redirected'):
            self.post(Reply(http_error(307)))

    def test_no_temperature_is_ever_sampled(self):
        with mock.patch.dict(os.environ, {'WORKFLOW_SELF_HOSTED_USE_TEMPERATURE': 'on', 'WORKFLOW_SELF_HOSTED_TEMPERATURE': '0.9'}):
            self.assertEqual(http.sampling({'_profile': 'anthropic-api'}), {})


class Profile(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        patcher = mock.patch.dict(os.environ, clean_env(), clear=True)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.uncle = Path(self.tmp.name) / '.uncle'
        self.uncle.mkdir()
        self.config = self.uncle / 'config'

    def write(self, text, keys=None):
        self.config.write_text(text)
        if keys is not None:
            (self.uncle / 'anthropic-api-keys.json').write_text(json.dumps(keys))

    def test_runner_resolves_to_the_profile(self):
        self.assertEqual(self_hosted.resolve_profile({'implementation.runner': 'anthropic-api'}, 'implementation'), 'anthropic-api')
        self.assertEqual(self_hosted.resolve_profile({'runner': 'Anthropic-API'}), 'anthropic-api')
        self.assertEqual(self_hosted.resolve_profile({'implementation.runner': 'self-hosted'}, 'implementation'), 'self-hosted')

    def test_settings_use_the_fixed_endpoint_stored_key_and_model(self):
        self.write('implementation.runner anthropic-api\nimplementation.model claude-sonnet-x\n',
                   {'__opencode_connection__': {'api_key': KEY}, '__opencode_models__': {'claude-sonnet-x': {'api_key': KEY, 'model': 'claude-sonnet-x'}}})
        values = self_hosted.settings(str(self.config), 'implementation')
        self.assertEqual((values['model'], values['base_url'], values['api_key'], values['_profile']),
                         ('claude-sonnet-x', 'https://api.anthropic.com', KEY, 'anthropic-api'))

    def test_environment_overrides_and_the_anthropic_key_fallback(self):
        self.write('implementation.runner anthropic-api\n')
        with mock.patch.dict(os.environ, {'ANTHROPIC_API_KEY': KEY, 'UNCLE_ANTHROPIC_API_MODEL': 'claude-env'}):
            values = self_hosted.settings(str(self.config), 'implementation')
        self.assertEqual((values['model'], values['api_key']), ('claude-env', KEY))
        with mock.patch.dict(os.environ, {'UNCLE_ANTHROPIC_API_KEY': 'sk-ant-explicit', 'ANTHROPIC_API_KEY': KEY, 'UNCLE_ANTHROPIC_API_MODEL': 'm'}):
            self.assertEqual(self_hosted.settings(str(self.config), 'implementation')['api_key'], 'sk-ant-explicit')

    def test_missing_key_or_model_is_an_anthropic_error_not_a_self_hosted_fallback(self):
        self.write('implementation.runner anthropic-api\nimplementation.model m\n')
        with mock.patch.dict(os.environ, {'UNCLE_SELF_HOSTED_API_KEY': 'k', 'UNCLE_SELF_HOSTED_BASE_URL': 'http://h/v1', 'OPENAI_API_KEY': 'o'}):
            with self.assertRaisesRegex(ValueError, 'Anthropic API requires an API key'):
                self_hosted.settings(str(self.config), 'implementation')
        self.write('implementation.runner anthropic-api\n')
        with mock.patch.dict(os.environ, {'ANTHROPIC_API_KEY': KEY}):
            with self.assertRaisesRegex(ValueError, 'Anthropic API requires a model name'):
                self_hosted.settings(str(self.config), 'implementation')

    def test_the_tests_authors_run_under_the_implementation_row(self):
        # tests-harness, tests-unit, tests-mutation ... are one stage; the shell resolves them through `implementation`.
        self.write('implementation.runner anthropic-api\nimplementation.model claude-sonnet-x\n',
                   {'__opencode_connection__': {'api_key': KEY}, '__opencode_models__': {'claude-sonnet-x': {'api_key': KEY, 'model': 'claude-sonnet-x'}}})
        for stage in ('tests', 'tests-harness', 'tests-unit', 'tests-mutation'):
            values = self_hosted.settings(str(self.config), stage)
            self.assertEqual((values['_profile'], values['base_url'], values['model']),
                             ('anthropic-api', 'https://api.anthropic.com', 'claude-sonnet-x'), stage)
            self.assertEqual(self_hosted.resolve_profile({'implementation.runner': 'aws-bedrock'}, stage), 'aws-bedrock')

    def test_repair_inherits_what_it_leaves_unset_from_implementation(self):
        # The shell does this for every key (uncle_stage_key); the profile lookup did not, so repair-investigate came out as plain
        # self-hosted and asked for a Base URL although the shell had routed it through the configured anthropic-api runner.
        keys = {'__opencode_connection__': {'api_key': KEY}, '__opencode_models__': {'claude-impl': {'api_key': KEY, 'model': 'claude-impl'}, 'claude-fix': {'api_key': KEY, 'model': 'claude-fix'}}}
        self.write('implementation.runner anthropic-api\nimplementation.model claude-impl\nrepair.model claude-fix\n', keys)
        for stage in ('repair', 'repair-investigate'):
            values = self_hosted.settings(str(self.config), stage)
            self.assertEqual((values['_profile'], values['base_url'], values['model']),
                             ('anthropic-api', 'https://api.anthropic.com', 'claude-fix'), stage)   # its own model, inherited runner
        self.write('implementation.runner anthropic-api\nimplementation.model claude-impl\n', keys)
        self.assertEqual(self_hosted.settings(str(self.config), 'repair-investigate')['model'], 'claude-impl')

    def test_an_explicit_repair_runner_is_not_overridden_by_implementation(self):
        self.write('implementation.runner anthropic-api\nrepair.runner self-hosted\nrepair.model m\nrepair.base_url http://localhost:8000/v1\n')
        with mock.patch.dict(os.environ, {'UNCLE_SELF_HOSTED_API_KEY': 'local'}):
            values = self_hosted.settings(str(self.config), 'repair-investigate')
        self.assertNotIn('_profile', values)
        self.assertEqual(values['base_url'], 'http://localhost:8000/v1')

    def test_self_hosted_stages_are_unchanged(self):
        self.write('implementation.runner self-hosted\nimplementation.model local/x\nimplementation.base_url http://localhost:8000/v1\n')
        with mock.patch.dict(os.environ, {'UNCLE_SELF_HOSTED_API_KEY': 'local'}):
            values = self_hosted.settings(str(self.config), 'implementation')
        self.assertNotIn('_profile', values)
        self.assertEqual(values['base_url'], 'http://localhost:8000/v1')

    def test_key_file_is_private_gitignored_and_separate(self):
        keys = {'__opencode_connection__': {'api_key': KEY}}
        self_hosted.save_keys(str(self.config), keys, 'anthropic-api')
        path = self.uncle / 'anthropic-api-keys.json'
        self.assertEqual(path.stat().st_mode & 0o777, 0o600)
        self.assertIn('/anthropic-api-keys.json', (self.uncle / '.gitignore').read_text().splitlines())
        self.assertFalse((self.uncle / 'self-hosted-keys.json').exists())
        self.assertEqual(self_hosted.read_keys(str(self.config), 'anthropic-api'), keys)

    def test_discovery_paginates_and_keeps_the_old_catalog_on_failure(self):
        pages = [json.dumps({'data': [{'id': 'claude-b'}], 'has_more': True, 'last_id': 'claude-b'}).encode(),
                 json.dumps({'data': [{'id': 'claude-a'}], 'has_more': False, 'last_id': 'claude-a'}).encode()]
        seen = []

        def get(url, headers):
            seen.append((url, headers))
            return pages.pop(0)
        keys = {'__opencode_models__': {'old': {}}}
        with mock.patch.object(self_hosted, '_discovery_get', get):
            names = self_hosted.refresh_anthropic_models(keys, KEY)
        self.assertEqual(names, ['claude-a', 'claude-b'])
        self.assertTrue(all(h['x-api-key'] == KEY for _, h in seen))
        self.assertTrue(seen[1][0].endswith('after_id=claude-b'))
        self.assertEqual(sorted(keys['__opencode_models__']), ['claude-a', 'claude-b'])
        self.assertEqual(keys['__opencode_connection__'], {'api_key': KEY})
        broken = {'__opencode_models__': {'keep': {}}}
        with mock.patch.object(self_hosted, '_discovery_get', side_effect=http_error(401)):
            with self.assertRaises(ValueError) as caught:
                self_hosted.refresh_anthropic_models(broken, KEY)
        self.assertNotIn(KEY, str(caught.exception))
        self.assertEqual(broken, {'__opencode_models__': {'keep': {}}})

    def test_profile_validation_accepts_both_vendor_profiles(self):
        self.assertEqual(self_hosted.validate_profile('anthropic-api'), 'anthropic-api')
        self.assertEqual(self_hosted.validate_profile('aws-bedrock'), 'aws-bedrock')
        self.assertIsNone(self_hosted.validate_profile('openai'))


class ShellConfig(unittest.TestCase):
    def run_sh(self, config, expr):
        with tempfile.TemporaryDirectory() as directory:
            Path(directory, 'config').write_text(config)
            env = dict(clean_env(), UNCLE_CONFIG=str(Path(directory, 'config')), PATH=os.environ['PATH'])
            return subprocess.run(['bash', '-c', '. "%s/scripts/lib/stage-config.sh"; %s' % (ROOT, expr)], env=env,
                                  capture_output=True, text=True, timeout=30).stdout.strip()

    def test_runner_dispatches_through_self_hosted_with_its_own_model(self):
        config = 'implementation.runner anthropic-api\nimplementation.model claude-x\nself-hosted.model local-y\n'
        out = self.run_sh(config, 'echo "$(uncle_stage_runner implementation)|$(uncle_stage_model implementation)"')
        self.assertEqual(out, 'self-hosted|claude-x')

    def test_the_model_falls_back_to_its_own_default_never_the_self_hosted_one(self):
        config = 'implementation.runner anthropic-api\nanthropic-api.model claude-default\nself-hosted.model local-y\n'
        self.assertEqual(self.run_sh(config, 'uncle_stage_model implementation'), 'claude-default')

    def test_the_runner_name_is_accepted_by_config_validation(self):
        self.assertEqual(self.run_sh('implementation.runner anthropic-api\n', 'uncle_validate_config_runners >/dev/null 2>&1; echo $?'), '0')
        self.assertEqual(self.run_sh('implementation.runner nonsense\n', 'uncle_validate_config_runners >/dev/null 2>&1; echo $?'), '1')


class Wiring(unittest.TestCase):
    def test_supervisor_and_tui_know_the_runner(self):
        import supervisor
        self.assertIn('anthropic-api', supervisor.SUPPORTED_RUNNERS)
        text = (ROOT / 'uncle_tui.py').read_text()
        self.assertIn('HTTP_RUNNERS = ("self-hosted", "aws-bedrock", "anthropic-api")', text)
        self.assertIn('"anthropic-api": shim("agent-self-hosted.sh")', text)
        self.assertIn('"anthropic-api": shim("reviewer-self-hosted.sh")', text)

    def test_the_launcher_offers_it_in_the_fallback_configure(self):
        launcher = (ROOT / 'uncle').read_text()
        self.assertIn("printf 'anthropic-api\\n'", launcher)
        self.assertIn('4) python3 "$ROOT/scripts/lib/self_hosted.py" models "$UNCLE_CONFIG" anthropic-api', launcher)


if __name__ == '__main__':
    unittest.main()
