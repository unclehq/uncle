"""AWS Bedrock profile of the self-hosted runner (AC-1..7).

Real settings() -> builder paths are used; only the network post and the
config/env are controlled.
"""
import json
import os
import re
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts' / 'lib'))
sys.path.insert(0, str(ROOT))

import self_hosted  # noqa: E402
import self_hosted_http as http  # noqa: E402

REGION = 'us-east-1'
RUNTIME = 'https://bedrock-runtime.us-east-1.amazonaws.com'
URL = RUNTIME  # legacy base_url form
TOKEN = 'bedrock-secret-token-xyz'
SH_TOKEN = 'selfhosted-secret-token-abc'
SCHEMA = {'type': 'object', 'properties': {'a': {'type': 'string'}}}
ENV_KEYS = ('UNCLE_CONFIG', 'UNCLE_STATUS_STAGE', 'WORKFLOW_SELF_HOSTED_TEMPERATURE')


def clean_env():
    env = {k: v for k, v in os.environ.items()
           if not (k.startswith('UNCLE_SELF_HOSTED_') or k.startswith('UNCLE_AWS_BEDROCK_')
                   or k.startswith('WORKFLOW_SELF_HOSTED') or k in ENV_KEYS
                   or k.startswith('WORKFLOW_AWS_BEDROCK'))}
    return env


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.dir = Path(self.tmp.name) / '.uncle'
        self.dir.mkdir()
        self.config = self.dir / 'config'
        patcher = mock.patch.dict(os.environ, clean_env(), clear=True)
        patcher.start()
        self.addCleanup(patcher.stop)
        os.environ['UNCLE_CONFIG'] = str(self.config)

    def write_config(self, text):
        self.config.write_text(text, encoding='utf-8')

    def bedrock_config(self, extra=''):
        self.write_config('runner aws-bedrock\naws-bedrock.region %s\naws-bedrock.model anthropic.claude\n%s' % (REGION, extra))
        os.environ['UNCLE_AWS_BEDROCK_API_KEY'] = TOKEN

    def self_hosted_config(self, extra=''):
        self.write_config('runner self-hosted\nself-hosted.base_url http://localhost:8000/v1\nself-hosted.model m1\n%s' % extra)
        os.environ['UNCLE_SELF_HOSTED_API_KEY'] = SH_TOKEN

    def bedrock_values(self, stage='implementation'):
        values = self_hosted.settings(str(self.config), stage)
        self.assertEqual(values.get('_profile'), 'aws-bedrock')
        return values


def has_key(obj, key):
    if isinstance(obj, dict):
        return key in obj or any(has_key(v, key) for v in obj.values())
    if isinstance(obj, list):
        return any(has_key(v, key) for v in obj)
    return False


class Capture:
    def __init__(self, reply=None):
        self.calls = []
        self.reply = reply

    def __call__(self, values, body, timeout, url=None):
        self.calls.append((body, url))
        if self.reply is not None:
            return self.reply
        return {'choices': [{'message': {'content': '{}'}, 'finish_reason': 'stop'}], 'usage': {},
                'message': {'content': '{}'}}


CONVERSE_OK = {'output': {'message': {'content': [{'text': '{}'}]}}, 'stopReason': 'end_turn', 'usage': {}}


class RequestCapture:
    """Stands in for self_hosted_http._request (the Bedrock transport seam)."""
    def __init__(self, reply=None, error=None):
        self.calls = []
        self.reply = CONVERSE_OK if reply is None else reply
        self.error = error

    def __call__(self, url, key, body=None, timeout=30, headers=None):
        self.calls.append({'url': url, 'key': key, 'body': body, 'headers': headers})
        if self.error:
            raise self.error
        return self.reply


class LabelsTest(unittest.TestCase):
    """AC-1, AC-2: TUI labels and row order."""
    def setUp(self):
        self.source = (ROOT / 'uncle_tui.py').read_text(encoding='utf-8')

    def test_labels_present(self):
        for label in ('Region', 'AWS Bedrock Token', 'AWS Bedrock', 'aws-bedrock-keys.json', 'HTTP_RUNNERS'):
            self.assertIn(label, self.source)

    def test_second_key_store(self):
        self.assertIn('bedrock_keys', self.source)
        self.assertIn('read_keys(CONFIG_PATH, profile="aws-bedrock")', self.source)

    def _items(self, section):
        body = self.source[self.source.index('def _config_items'):]
        body = body[:body.index('def ', 20)]
        if section is None:
            m = re.search(r'if not section:\s*return (\[[^\n]*\])', body)
        else:
            m = re.search(r'if section == "%s":\s*return (\[.*?\])\n\s*(?:if section|return|""")' % section, body, re.S)
        self.assertIsNotNone(m, section)
        return m.group(1)

    def test_row_order_bedrock_after_self_hosted(self):
        top = re.findall(r'"([^"]+)"', self._items(None))
        self.assertEqual(top, ['1. Configure stages', '2. Configure self hosting', '3. Configure AWS Bedrock',
                               '4. Miscellaneous', '5. Supervision', '6. Recovery'])
        self.assertEqual(top.index('3. Configure AWS Bedrock'), top.index('2. Configure self hosting') + 1)

    def test_bedrock_submenu_exact_and_no_temperature_entry(self):
        items = self._items('bedrock')
        labels = re.findall(r'(?:^\[|, )"([^"%]+)', items)
        self.assertEqual(labels, ['Connection \u2014 Region and AWS Bedrock Token', 'Refresh supported models ('])
        self.assertNotIn('emperature', items)
        self.assertNotIn('emperature', self._items(None))


class BuilderTest(Base):
    """AC-3: no temperature field in any Bedrock request body."""
    def test_chat_omits_temperature(self):
        self.bedrock_config()
        values = self.bedrock_values()
        post = Capture()
        with mock.patch.object(http, 'compatible_post', post):
            http.chat(values, [{'role': 'user', 'content': 'x'}], [{'type': 'function'}], 100)
        self.assertEqual(len(post.calls), 1)
        self.assertFalse(has_key(post.calls[0][0], 'temperature'))

    def test_agent_path_omits_temperature(self):
        self.bedrock_config()
        values = self.bedrock_values('implementation-step-1')
        post = Capture()
        with mock.patch.object(http, 'compatible_post', post):
            http.chat(values, [{'role': 'user', 'content': 'x'}], [{'type': 'function', 'function': {'name': 't'}}], 50, effort='low')
        self.assertFalse(has_key(post.calls[0][0], 'temperature'))

    def test_final_call_json_schema_omits_temperature(self):
        self.bedrock_config()
        values = self.bedrock_values()
        post = Capture()
        with mock.patch.object(http, 'compatible_post', post):
            http._final_call(values, [{'role': 'user', 'content': 'x'}], SCHEMA, 'n', 'json_schema', 100, None, 10)
        self.assertFalse(has_key(post.calls[0][0], 'temperature'))

    def test_final_call_ollama_format_omits_temperature(self):
        self.bedrock_config()
        values = self.bedrock_values()
        post = Capture({'message': {'content': '{}'}, 'done_reason': 'stop'})
        with mock.patch.object(http, 'compatible_post', post):
            http._final_call(values, [{'role': 'user', 'content': 'x'}], SCHEMA, 'n', 'ollama_format', 100, None, 10)
        self.assertFalse(has_key(post.calls[0][0], 'temperature'))

    def test_missing_profile_never_sends_temperature(self):
        self.bedrock_config()
        values = self.bedrock_values()
        stripped = {k: v for k, v in values.items() if k != '_profile'}
        os.environ['UNCLE_STATUS_STAGE'] = 'implementation'
        calls = (lambda: http.chat(stripped, [], [], 10),
                 lambda: http._final_call(stripped, [], SCHEMA, 'n', 'json_schema', 10, None, 10),
                 lambda: http._final_call(stripped, [], SCHEMA, 'n', 'ollama_format', 10, None, 10))
        self.assertEqual(len(calls), 3)
        for call in calls:
            post = Capture({'message': {'content': '{}'}, 'choices': [{'message': {'content': '{}'}}]})
            with mock.patch.object(http, 'compatible_post', post):
                with self.assertRaises(ValueError) as caught:
                    call()
            self.assertIn('AWS Bedrock', str(caught.exception))
            self.assertEqual(post.calls, [], 'a request was sent despite the missing profile')

    def test_invalid_temperature_env_ignored(self):
        self.bedrock_config('aws-bedrock.temperature abc\nimplementation.temperature abc\n')
        for bad in ('1.5', 'abc'):
            os.environ['WORKFLOW_SELF_HOSTED_TEMPERATURE'] = bad
            values = self.bedrock_values()
            post = Capture()
            with mock.patch.object(http, 'compatible_post', post):
                http.chat(values, [], [], 10)
            self.assertFalse(has_key(post.calls[0][0], 'temperature'))

    def test_request_options_temperature_stripped(self):
        options = json.dumps({'temperature': 0.3, 'top_p': 0.9, 'extra_body': {'temperature': 0.1, 'x': 1}})
        self.bedrock_config('implementation.request-options %s\n' % options)
        values = self.bedrock_values()
        for run in (lambda v, p: http.chat(v, [], [], 10),
                    lambda v, p: http._final_call(v, [], SCHEMA, 'n', 'json_schema', 10, None, 10),
                    lambda v, p: http._final_call(v, [], SCHEMA, 'n', 'ollama_format', 10, None, 10)):
            post = Capture({'message': {'content': '{}'}, 'choices': [{'message': {'content': '{}'}}]})
            with mock.patch.object(http, 'compatible_post', post):
                run(http.configure_request_options(values, 'implementation'), post)
            for body, _ in post.calls:
                self.assertFalse(has_key(body, 'temperature'), body)

    def test_self_hosted_temperature_unchanged(self):
        self.self_hosted_config()
        values = self_hosted.settings(str(self.config), 'implementation')
        self.assertNotEqual(values.get('_profile'), 'aws-bedrock')
        post = Capture()
        with mock.patch.object(http, 'compatible_post', post):
            http.chat(values, [], [], 10)
            http._final_call(values, [], SCHEMA, 'n', 'json_schema', 10, None, 10)
        for body, _ in post.calls:
            self.assertIn('temperature', body)

    def test_self_hosted_ollama_options_keep_temperature(self):
        self.self_hosted_config()
        values = self_hosted.settings(str(self.config), 'implementation')
        post = Capture({'message': {'content': '{}'}, 'done_reason': 'stop'})
        with mock.patch.object(http, 'compatible_post', post):
            http._final_call(values, [], SCHEMA, 'n', 'ollama_format', 10, None, 10)
        self.assertIn('temperature', post.calls[0][0]['options'])

    def test_bedrock_constrained_uses_only_json_schema_without_probe(self):
        self.bedrock_config()
        values = self.bedrock_values()
        modes = []

        def fake_final(v, messages, schema, name, mode, limit, effort, timeout):
            modes.append(mode)
            return '{}', 'stop', {}
        with mock.patch.object(http, 'capabilities', side_effect=AssertionError('capabilities probed')), \
                mock.patch.object(http, '_final_call', fake_final):
            http.constrained_completion(values, [], SCHEMA, 'n', 10)
        self.assertEqual(modes, ['json_schema'])

    def test_token_only_to_region_runtime_host(self):
        self.bedrock_config()
        values = self.bedrock_values()
        cap = RequestCapture()
        with mock.patch.object(http, '_request', cap):
            http.chat(values, [{'role': 'user', 'content': 'x'}], [], 10)
        self.assertEqual(len(cap.calls), 1)
        for call in cap.calls:
            self.assertTrue(call['url'].startswith(RUNTIME + '/model/'), call['url'])
            self.assertEqual(call['key'], TOKEN)
            self.assertEqual(call['headers']['Authorization'], 'Bearer ' + TOKEN)
            self.assertNotIn(TOKEN, call['url'])
            self.assertNotIn(TOKEN, json.dumps(call['body']))

    def test_redirect_not_followed_token_not_forwarded(self):
        import http.server as server_lib
        import threading
        hits = {'target': [], 'origin': []}

        class Target(server_lib.BaseHTTPRequestHandler):
            def do_POST(self):
                hits['target'].append(self.headers.get('Authorization'))
                self.send_response(200)
                self.end_headers()
            do_GET = do_POST

            def log_message(self, *a):
                pass
        target = server_lib.HTTPServer(('127.0.0.1', 0), Target)
        where = 'http://127.0.0.1:%d/stolen' % target.server_port

        class Origin(server_lib.BaseHTTPRequestHandler):
            def do_POST(self):
                hits['origin'].append(self.headers.get('Authorization'))
                self.send_response(307)
                self.send_header('Location', where)
                self.send_header('Content-Length', '0')
                self.end_headers()

            def log_message(self, *a):
                pass
        origin = server_lib.HTTPServer(('127.0.0.1', 0), Origin)
        for server in (target, origin):
            threading.Thread(target=server.serve_forever, daemon=True).start()
            self.addCleanup(server.server_close)
            self.addCleanup(server.shutdown)
        error = None
        try:
            http._request('http://127.0.0.1:%d/v1/chat' % origin.server_port, TOKEN, {'a': 1}, 5)
        except Exception as caught:  # noqa: BLE001 -- the 307 must surface as an error
            error = caught
        self.assertEqual(hits['origin'], ['Bearer ' + TOKEN])
        self.assertEqual(hits['target'], [], 'the redirect was followed')
        self.assertIsNotNone(error, 'a 307 must not be treated as success')


GOLDEN_SELF_HOSTED = json.loads(r'''[{"max_tokens": 100, "messages": [{"content": "x", "role": "user"}], "model": "m1", "stream": false, "temperature": 0.0, "tools": [{"type": "function"}]}, {"max_tokens": 100, "messages": [{"content": "x", "role": "user"}], "model": "m1", "response_format": {"json_schema": {"name": "n", "schema": {"properties": {"a": {"type": "string"}}, "type": "object"}}, "type": "json_schema"}, "stream": false, "temperature": 0.0}, {"format": {"properties": {"a": {"type": "string"}}, "type": "object"}, "messages": [{"content": "[user]\nx", "role": "user"}], "model": "m1", "options": {"num_predict": 100, "temperature": 0.0}, "stream": false}]''')


class SelfHostedGoldenTest(Base):
    """R-5/AR-007: Self Hosted payloads are byte-identical to the pre-change (HEAD) payloads."""
    def test_golden_payloads(self):
        self.self_hosted_config()
        values = self_hosted.settings(str(self.config), 'implementation')
        post = Capture({'choices': [{'message': {'content': '{}'}, 'finish_reason': 'stop'}], 'usage': {},
                        'message': {'content': '{}'}, 'done_reason': 'stop'})
        msg = [{'role': 'user', 'content': 'x'}]
        with mock.patch.object(http, 'compatible_post', post):
            http.chat(values, msg, [{'type': 'function'}], 100)
            http._final_call(values, msg, SCHEMA, 'n', 'json_schema', 100, None, 10)
            http._final_call(values, msg, SCHEMA, 'n', 'ollama_format', 100, None, 10)
        got = [body for body, _ in post.calls]
        self.assertEqual(json.dumps(got, sort_keys=True), json.dumps(GOLDEN_SELF_HOSTED, sort_keys=True))


class BuilderIntrospectionTest(unittest.TestCase):
    """AR-020: every self_hosted_http builder that sets sampling is covered by a registered Bedrock test."""
    COVERED = {'chat': 'test_chat_omits_temperature', '_final_call': 'test_final_call_json_schema_omits_temperature'}

    def test_all_builders_covered(self):
        import ast
        src = (ROOT / 'scripts' / 'lib' / 'self_hosted_http.py').read_text(encoding='utf-8')
        found = set()
        for node in ast.walk(ast.parse(src)):
            if isinstance(node, ast.FunctionDef) and node.name not in ('sampling', 'temperature', '_parse_temperature', '_strip_temperature', 'compatible_post'):
                text = ast.get_source_segment(src, node)
                if 'sampling(' in text or "'temperature'" in text or '"temperature"' in text:
                    found.add(node.name)
        self.assertEqual(found, set(self.COVERED), 'new or uncovered request builder: add a Bedrock no-temperature test')
        for name in self.COVERED.values():
            self.assertTrue(hasattr(BuilderTest, name), name)


class RedactionAndSchemeTest(Base):
    def test_error_body_and_reason_never_echo_token(self):
        import http.server as server_lib
        import threading

        class Echo(server_lib.BaseHTTPRequestHandler):
            def do_POST(self):
                body = ('bad auth ' + (self.headers.get('Authorization') or '') + ' ' + 'z' * 9000).encode()
                self.send_response(401, 'denied ' + TOKEN)
                self.send_header('Content-Length', str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, *a):
                pass
        server = server_lib.HTTPServer(('127.0.0.1', 0), Echo)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        with self.assertRaises(Exception) as caught:
            http._request('http://127.0.0.1:%d/v1/chat' % server.server_port, TOKEN, {'a': 1}, 5)
        error = caught.exception
        text = str(error) + repr(error) + error.read().decode('utf-8', 'replace')
        self.assertNotIn(TOKEN, text)
        self.assertLess(len(text), 5000)

    def test_http_and_non_aws_hosts_have_no_region(self):
        for host in ('http://127.0.0.1:9/v1', 'http://localhost:9/v1', 'http://remote.example.com/v1'):
            self.write_config('runner aws-bedrock\naws-bedrock.base_url %s\naws-bedrock.model m\n' % host)
            os.environ['UNCLE_AWS_BEDROCK_API_KEY'] = TOKEN
            with self.assertRaises(ValueError) as caught:
                self_hosted.settings(str(self.config), 'implementation')
            self.assertIn('Region', str(caught.exception))
            self.assertNotIn(TOKEN, str(caught.exception))


class SupervisorPathTest(Base):
    """AC-3: the supervisor's interruptible_chat path adds no temperature either."""
    def run_path(self, stage, config_extra=''):
        import http_agent
        self.bedrock_config(config_extra)
        values = self.bedrock_values()
        post = Capture()
        with mock.patch.object(http, 'compatible_post', post):
            http_agent.interruptible_chat(stage, values, [{'role': 'user', 'content': 'x'}],
                                          [{'type': 'function', 'function': {'name': 't'}}], 50, 'low', 10)
        self.assertEqual(len(post.calls), 1)
        return post.calls[0][0]

    def test_direct_and_threaded_paths(self):
        self.assertFalse(has_key(self.run_path(None), 'temperature'))
        channel = Path(self.tmp.name) / 'inbox'
        channel.mkdir()
        self.assertFalse(has_key(self.run_path(mock.Mock(channel=str(channel))), 'temperature'))

    def test_self_hosted_supervisor_path_keeps_temperature(self):
        import http_agent
        self.self_hosted_config()
        values = self_hosted.settings(str(self.config), 'implementation')
        post = Capture()
        with mock.patch.object(http, 'compatible_post', post):
            http_agent.interruptible_chat(None, values, [], [], 50, None, 10)
        self.assertIn('temperature', post.calls[0][0])


class ReuseTest(Base):
    def reuse_class(self):
        import self_hosted_performance as perf
        return perf

    def make_key(self, values):
        perf = self.reuse_class()
        policy = mock.Mock(root=Path(self.tmp.name), write=False, shell=False)
        policy.tools.return_value = []
        with mock.patch.object(perf, 'snapshot', return_value=[]):
            reuse = perf.Reuse(values, 'prompt', policy, SCHEMA, 'n', 10, 1, 10, None)
        return reuse.key

    def test_unknown_explicit_profile_raises_in_reuse(self):
        self.bedrock_config()
        values = dict(self.bedrock_values(), _profile='bogus')
        with self.assertRaises(ValueError):
            self.make_key(values)

    def test_bedrock_reuse_ignores_temperature(self):
        perf = self.reuse_class()
        self.bedrock_config()
        values = self.bedrock_values()
        keys = set()
        for bad in (None, '0', '1.5', 'abc'):
            if bad is None:
                os.environ.pop('WORKFLOW_SELF_HOSTED_TEMPERATURE', None)
            else:
                os.environ['WORKFLOW_SELF_HOSTED_TEMPERATURE'] = bad
            with mock.patch.object(http, 'temperature', side_effect=AssertionError('temperature() called')):
                keys.add(self.make_key(values))
        self.assertEqual(len(keys), 1)
        key = keys.pop()
        self.assertIsNotNone(key, 'Reuse must be eligible for Bedrock regardless of temperature')
        self.assertNotIn(TOKEN, key)

    def test_bedrock_reuse_key_sensitivity(self):
        self.bedrock_config()
        base = self.make_key(self.bedrock_values())
        self.assertIsNotNone(base)
        self.assertEqual(base, self.make_key(self.bedrock_values()))
        os.environ['UNCLE_AWS_BEDROCK_API_KEY'] = 'another-token'
        self.assertEqual(base, self.make_key(self.bedrock_values()), 'token must not enter the key')
        os.environ['UNCLE_AWS_BEDROCK_API_KEY'] = TOKEN
        self.write_config('runner aws-bedrock\naws-bedrock.region eu-west-1\naws-bedrock.model anthropic.claude\n')
        self.assertNotEqual(base, self.make_key(self.bedrock_values()), 'region must change the key')
        self.write_config('runner aws-bedrock\naws-bedrock.region %s\naws-bedrock.model other-model\n' % REGION)
        self.assertNotEqual(base, self.make_key(self.bedrock_values()), 'model must change the key')
        sh = self.make_key(self.bedrock_values_as_self_hosted())
        self.assertNotEqual(base, sh, 'profile must change the key')

    def test_reuse_key_identical_across_temperature_sources_and_changes_with_region(self):
        self.bedrock_config()
        base = self.make_key(self.bedrock_values())
        self.assertIsNotNone(base)
        os.environ['WORKFLOW_AWS_BEDROCK_TEMPERATURE'] = '0.77'
        self.assertEqual(base, self.make_key(self.bedrock_values()), 'global env temperature')
        del os.environ['WORKFLOW_AWS_BEDROCK_TEMPERATURE']
        self.bedrock_config('implementation.temperature 0.9\n')
        self.assertEqual(base, self.make_key(self.bedrock_values()), 'per-stage temperature')
        self.bedrock_config('implementation.request-options %s\n' % json.dumps({'top_p': 0.9}))
        without_temp = self.make_key(self.bedrock_values())
        self.bedrock_config('implementation.request-options %s\n' % json.dumps({'temperature': 0.3, 'top_p': 0.9}))
        with_temp = self.make_key(self.bedrock_values())
        self.assertIsNotNone(without_temp)
        self.assertEqual(without_temp, with_temp, 'temperature in request-options must not alter the Reuse key')
        self.write_config('runner aws-bedrock\naws-bedrock.region eu-west-1\naws-bedrock.model anthropic.claude\n')
        self.assertNotEqual(base, self.make_key(self.bedrock_values()), 'region change')

    def bedrock_values_as_self_hosted(self):
        self.bedrock_config()
        values = dict(self.bedrock_values())
        values['_profile'] = 'self-hosted'
        return values


class StorageTest(Base):
    """AC-5, AC-6: separate stores, 0600, gitignore, URL validation."""
    def test_disjoint_stores(self):
        self_hosted.save_keys(str(self.config), {'implementation': SH_TOKEN})
        self_hosted.save_keys(str(self.config), {'implementation': TOKEN}, profile='aws-bedrock')
        self.assertEqual(self_hosted.read_keys(str(self.config))['implementation'], SH_TOKEN)
        self.assertEqual(self_hosted.read_keys(str(self.config), profile='aws-bedrock')['implementation'], TOKEN)
        self.assertTrue((self.dir / 'aws-bedrock-keys.json').exists())
        self.assertNotIn(TOKEN, (self.dir / 'self-hosted-keys.json').read_text())
        self.assertNotIn(SH_TOKEN, (self.dir / 'aws-bedrock-keys.json').read_text())

    def test_file_mode_0600_and_gitignored(self):
        self_hosted.save_keys(str(self.config), {'implementation': TOKEN}, profile='aws-bedrock')
        mode = stat.S_IMODE((self.dir / 'aws-bedrock-keys.json').stat().st_mode)
        self.assertEqual(mode, 0o600)
        self.assertIn('/aws-bedrock-keys.json', (self.dir / '.gitignore').read_text().splitlines())
        self.assertEqual([p.name for p in self.dir.iterdir() if p.name.startswith('.') and p.name != '.gitignore'], [])

    def test_failed_write_leaves_no_token_or_temp_file(self):
        self_hosted.save_keys(str(self.config), {'implementation': 'old-token'}, profile='aws-bedrock')
        target = self.dir / 'aws-bedrock-keys.json'
        with mock.patch.object(self_hosted.os, 'replace', side_effect=OSError('injected')):
            with self.assertRaises(OSError):
                self_hosted.save_keys(str(self.config), {'implementation': TOKEN}, profile='aws-bedrock')
        self.assertIn('old-token', target.read_text())
        self.assertNotIn(TOKEN, target.read_text())
        self.assertEqual([p.name for p in self.dir.iterdir() if p.name.startswith('.') and p.name != '.gitignore'], [])
        self.assertEqual(stat.S_IMODE(target.stat().st_mode), 0o600)

    def test_save_refused_without_gitignore(self):
        (self.dir / '.gitignore').mkdir()   # cannot be read or appended as a file
        with self.assertRaises(Exception):
            self_hosted.save_keys(str(self.config), {'implementation': TOKEN}, profile='aws-bedrock')
        self.assertFalse((self.dir / 'aws-bedrock-keys.json').exists())

    def test_region_validation_and_precedence(self):
        self.write_config('runner aws-bedrock\naws-bedrock.model m\n')
        os.environ['UNCLE_AWS_BEDROCK_API_KEY'] = TOKEN
        os.environ['UNCLE_AWS_BEDROCK_REGION'] = ' us-east-1 '
        values = self_hosted.settings(str(self.config), 'implementation')
        self.assertEqual((values['region'], values['base_url']), ('us-east-1', RUNTIME))
        for bad in ('US-EAST-1', 'us_east_1', 'us-east', 'x.y-1', 'us-east-1.evil.com/'):
            os.environ['UNCLE_AWS_BEDROCK_REGION'] = bad
            with self.assertRaises(ValueError) as caught:
                self_hosted.settings(str(self.config), 'implementation')
            self.assertIn('Region', str(caught.exception))
            self.assertNotIn(TOKEN, str(caught.exception))
        os.environ['UNCLE_AWS_BEDROCK_REGION'] = '   '
        with self.assertRaises(ValueError) as caught:
            self_hosted.settings(str(self.config), 'implementation')
        self.assertIn('Region is not set', str(caught.exception))

    def test_invalid_env_region_does_not_fall_through_to_stored(self):
        self.bedrock_config()
        self.assertEqual(self.bedrock_values()['region'], REGION)
        self_hosted.save_keys(str(self.config), {'__opencode_connection__': {'region': 'eu-west-1', 'api_key': TOKEN}}, profile='aws-bedrock')
        os.environ['UNCLE_AWS_BEDROCK_REGION'] = 'US-EAST-1'
        with self.assertRaises(ValueError) as caught:
            self_hosted.settings(str(self.config), 'implementation')
        self.assertIn('Region', str(caught.exception))

    def test_region_precedence_order(self):
        self.write_config('runner aws-bedrock\naws-bedrock.region ap-south-1\nimplementation.region sa-east-1\naws-bedrock.model m\n')
        self_hosted.save_keys(str(self.config), {'__opencode_connection__': {'region': 'eu-west-1', 'api_key': TOKEN}}, profile='aws-bedrock')
        self.assertEqual(self_hosted.settings(str(self.config), 'implementation')['region'], 'sa-east-1')
        self.assertEqual(self_hosted.settings(str(self.config), 'requirements')['region'], 'ap-south-1')
        os.environ['UNCLE_AWS_BEDROCK_REGION'] = 'us-west-2'
        self.assertEqual(self_hosted.settings(str(self.config), 'implementation')['region'], 'us-west-2')
        del os.environ['UNCLE_AWS_BEDROCK_REGION']
        self.write_config('runner aws-bedrock\naws-bedrock.model m\n')
        self.assertEqual(self_hosted.settings(str(self.config), 'implementation')['region'], 'eu-west-1')

    def test_legacy_base_url_migration(self):
        os.environ['UNCLE_AWS_BEDROCK_API_KEY'] = TOKEN
        for url in ('https://bedrock-runtime.eu-west-1.amazonaws.com', 'https://bedrock.eu-west-1.amazonaws.com'):
            self.write_config('runner aws-bedrock\naws-bedrock.base_url %s\naws-bedrock.api_compatibility converse\naws-bedrock.model m\n' % url)
            values = self_hosted.settings(str(self.config), 'implementation')
            self.assertEqual(values['region'], 'eu-west-1')
            self.assertEqual(values['base_url'], 'https://bedrock-runtime.eu-west-1.amazonaws.com')
        for url in ('http://bedrock-runtime.eu-west-1.amazonaws.com', 'https://bedrock-runtime.eu-west-1.example.com',
                    'https://user:pw@bedrock-runtime.eu-west-1.amazonaws.com', 'https://bedrock-runtime.eu-west-1.amazonaws.com:8443',
                    'https://example.com/bedrock-runtime.eu-west-1.amazonaws.com'):
            self.write_config('runner aws-bedrock\naws-bedrock.base_url %s\naws-bedrock.api_compatibility converse\naws-bedrock.model m\n' % url)
            with self.assertRaises(ValueError) as caught:
                self_hosted.settings(str(self.config), 'implementation')
            self.assertIn('Region', str(caught.exception), url)
            self.assertNotIn(TOKEN, str(caught.exception))

    def test_token_validation(self):
        self.bedrock_config()
        for bad in ('line1\nline2', 'has space', 'ctrl\x01char', ''):
            os.environ['UNCLE_AWS_BEDROCK_API_KEY'] = bad
            if not bad:
                del os.environ['UNCLE_AWS_BEDROCK_API_KEY']
            with self.assertRaises(ValueError) as caught:
                self_hosted.settings(str(self.config), 'implementation')
            self.assertIn('token', str(caught.exception))
            for part in ('line1', 'line2', 'has', 'ctrl'):
                self.assertNotIn(part, str(caught.exception))
        for bad in ('a\nb', 'a b', ''):
            with self.assertRaises(ValueError):
                self_hosted.validate_bedrock_token(bad)
        self.assertEqual(self_hosted.validate_bedrock_token(TOKEN), TOKEN)

    def test_settings_never_read_self_hosted_store(self):
        self_hosted.save_keys(str(self.config), {'implementation': SH_TOKEN})
        self.write_config('runner aws-bedrock\naws-bedrock.base_url %s\naws-bedrock.model m\n' % URL)
        os.environ['UNCLE_SELF_HOSTED_API_KEY'] = SH_TOKEN
        with self.assertRaises(ValueError) as caught:
            self_hosted.settings(str(self.config), 'implementation')
        self.assertIn('Bedrock', str(caught.exception))

    def test_missing_fields_bedrock_worded(self):
        self.write_config('runner aws-bedrock\n')
        with self.assertRaises(ValueError) as caught:
            self_hosted.settings(str(self.config), 'implementation')
        self.assertIn('Bedrock', str(caught.exception))
        self.assertNotIn('Self hosted', str(caught.exception))


class ProfileTest(Base):
    """AC-6: profile derivation from config only."""
    def profile(self, stage):
        try:
            return self_hosted.settings(str(self.config), stage).get('_profile', 'self-hosted')
        except ValueError:
            self.fail('settings raised for %s' % stage)

    def full(self, runner_lines):
        self.write_config(runner_lines +
                          'aws-bedrock.base_url %s\naws-bedrock.model bm\n'
                          'self-hosted.base_url http://localhost:8000/v1\nself-hosted.model sm\n' % URL)
        os.environ['UNCLE_AWS_BEDROCK_API_KEY'] = TOKEN
        os.environ['UNCLE_SELF_HOSTED_API_KEY'] = SH_TOKEN

    def test_mixed_cases(self):
        self.full('runner self-hosted\nimplementation.runner aws-bedrock\n')
        self.assertEqual(self.profile('implementation'), 'aws-bedrock')
        self.assertEqual(self.profile('requirements'), 'self-hosted')
        self.full('runner aws-bedrock\nimplementation.runner self-hosted\n')
        self.assertEqual(self.profile('implementation'), 'self-hosted')
        self.assertEqual(self.profile('requirements'), 'aws-bedrock')
        self.full('')
        self.assertEqual(self.profile('implementation'), 'self-hosted')

    def test_inherited_stage_names(self):
        self.full('implementation.runner aws-bedrock\nadversarial-review.runner aws-bedrock\n')
        for stage in ('implementation-step-2', 'implementation-report', 'implementation-worker-1',
                      'adversarial-review-worker-scope', 'implementation-investigate'):
            self.assertEqual(self.profile(stage), 'aws-bedrock', stage)

    def test_cmd_override_does_not_change_profile(self):
        self.full('runner aws-bedrock\n')
        os.environ['WORKFLOW_AGENT_CMD'] = 'echo'
        self.assertEqual(self.profile('implementation'), 'aws-bedrock')

    def test_unset_stage_uses_global(self):
        self.full('runner aws-bedrock\n')
        self.assertEqual(self.profile(''), 'aws-bedrock')

    def test_self_hosted_has_no_bedrock_profile(self):
        self.self_hosted_config()
        self.assertNotEqual(self_hosted.settings(str(self.config), 'implementation').get('_profile'), 'aws-bedrock')


class ShellTest(Base):
    """AC-7: shell accepts aws-bedrock and keeps the Bedrock model sources apart."""
    LIB = str(ROOT / 'scripts' / 'lib' / 'stage-config.sh')

    def sh(self, script, extra_env=None):
        env = clean_env()
        env['UNCLE_CONFIG'] = str(self.config)
        env['ROOT'] = str(ROOT)
        env.update(extra_env or {})
        return subprocess.run(['bash', '-c', '. "%s"; %s' % (self.LIB, script)], env=env,
                              capture_output=True, text=True, timeout=60)

    def test_validator_accepts_any_case_and_rejects_unknown(self):
        for name in ('aws-bedrock', 'AWS-Bedrock'):
            self.write_config('runner %s\n' % name)
            self.assertEqual(self.sh('uncle_validate_config_runners').returncode, 0, name)
        self.write_config('runner not-a-runner\n')
        self.assertNotEqual(self.sh('uncle_validate_config_runners').returncode, 0)

    def test_resolvers_normalize_and_effort_none(self):
        self.write_config('implementation.runner aws-bedrock\n')
        self.assertEqual(self.sh('uncle_stage_runner implementation').stdout, 'self-hosted')
        self.assertEqual(self.sh('uncle_stage_effort implementation').stdout, 'none')
        resolved = self.sh('uncle_resolve_stage_runner implementation AGENT; printf %s "$UNCLE_RESOLVED_RUNNER"',
                           {'WORKFLOW_AGENT_CMD': 'echo'})
        self.assertEqual(resolved.stdout, 'self-hosted')
        self.assertNotEqual(self.sh('uncle_runner_cmd aws-bedrock agent').returncode, 0)
        self.assertIn('self-hosted.sh', self.sh('uncle_runner_cmd self-hosted agent').stdout)

    def model(self, config, env=None):
        self.write_config(config)
        return self.sh('uncle_stage_model implementation', env).stdout

    def test_model_lookup_bedrock_sources_only(self):
        both = 'implementation.runner aws-bedrock\nself-hosted.model SHM\n'
        sh_env = {'UNCLE_SELF_HOSTED_MODEL': 'SHENV'}
        self.assertEqual(self.model(both + 'aws-bedrock.model BGLOBAL\nimplementation.model BSTAGE\n',
                                    dict(sh_env, UNCLE_AWS_BEDROCK_MODEL='BENV')), 'BENV')
        self.assertEqual(self.model(both + 'aws-bedrock.model BGLOBAL\nimplementation.model BSTAGE\n', sh_env), 'BSTAGE')
        self.assertEqual(self.model(both + 'aws-bedrock.model BGLOBAL\n', sh_env), 'BGLOBAL')
        self.assertEqual(self.model(both, sh_env), '')

    def test_self_hosted_model_lookup_unchanged(self):
        self.assertEqual(self.model('implementation.runner self-hosted\nself-hosted.model SHM\n'), 'SHM')
        self.assertEqual(self.model('implementation.runner self-hosted\nself-hosted.model SHM\n',
                                    {'UNCLE_SELF_HOSTED_MODEL': 'SHENV'}), 'SHENV')


class ProtocolAdapterTests(unittest.TestCase):
    MSGS = [{'role': 'system', 'content': 'sys'}, {'role': 'user', 'content': 'hi'}]
    SCHEMA = {'type': 'object', 'properties': {'a': {'type': 'string'}}}
    TOOLS = [{'type': 'function', 'function': {'name': 't', 'description': 'd', 'parameters': {'type': 'object'}}}]

    def test_exact_header_set(self):
        import bedrock_protocols as bp
        self.assertEqual(bp.build_headers('K'), {'Content-Type': 'application/json', 'Authorization': 'Bearer K'})

    def test_urls(self):
        import bedrock_protocols as bp
        self.assertEqual(bp.runtime_url('us-east-1'), RUNTIME)
        self.assertEqual(bp.control_url('eu-west-1'), 'https://bedrock.eu-west-1.amazonaws.com')
        self.assertEqual(bp.build_url('us-east-1', 'anthropic.claude-3:0'), RUNTIME + '/model/anthropic.claude-3%3A0/converse')
        self.assertEqual(bp.build_url('us-east-1', 'a/b'), RUNTIME + '/model/a%2Fb/converse')
        self.assertFalse(hasattr(bp, 'normalize_protocol'))

    def test_body_has_no_temperature_and_shape(self):
        import bedrock_protocols as bp
        body = bp.build_body(self.MSGS, 50, self.TOOLS, self.SCHEMA)
        self.assertNotIn('temperature', json.dumps(body).lower())
        c = bp.build_body(self.MSGS, 5, schema=self.SCHEMA)
        self.assertEqual(c['inferenceConfig'], {'maxTokens': 5})
        self.assertEqual(c['toolConfig']['toolChoice'], {'tool': {'name': 'result'}})
        self.assertEqual(c['system'], [{'text': 'sys'}])

    def test_parse_converse_and_schema(self):
        import bedrock_protocols as bp
        d = {'output': {'message': {'content': [{'text': 'hi'}, {'toolUse': {'toolUseId': '9', 'name': 't', 'input': {'k': 1}}}]}},
             'stopReason': 'tool_use', 'usage': {'inputTokens': 5, 'outputTokens': 6}}
        r = bp.parse_response(d)
        self.assertEqual((r['text'], r['tool_calls'][0]['id'], r['usage']), ('hi', '9', {'input': 5, 'output': 6}))
        d['output']['message']['content'].append({'toolUse': {'toolUseId': '2', 'name': 'result', 'input': {'a': 'z'}}})
        r = bp.parse_response(d, 'result')
        self.assertEqual(json.loads(r['text']), {'a': 'z'})
        self.assertEqual([c['name'] for c in r['tool_calls']], ['t'])

    def test_malformed_responses_raise(self):
        import bedrock_protocols as bp
        for bad in ({}, [], {'output': {}}):
            with self.assertRaises(ValueError):
                bp.parse_response(bad)


class RegionFieldTests(unittest.TestCase):
    def make(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location('uncle_tui_under_test', ROOT / 'uncle_tui.py')
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        tui = object.__new__(mod.UncleTUI)
        tui.bedrock_keys, tui.stage_api_keys, tui.notice = {}, {}, ''
        tui.stage_runners = {}
        tui.save_config = lambda: None
        tui.maybe_reload = lambda: None
        return mod, tui

    def test_bedrock_popup_fields_have_no_compatibility_or_url(self):
        mod, tui = self.make()
        self.assertFalse(hasattr(mod, 'COMPAT_CHOICES'))
        self.assertEqual(tui.stage_fields('@bedrock'), ['region', 'api_key'])
        self.assertEqual(tui.stage_fields('@connection'), ['base_url', 'api_key'])
        self.assertNotIn('api_compatibility', (ROOT / 'uncle_tui.py').read_text(encoding='utf-8'))

    def test_failed_discovery_leaves_connection_and_catalog_untouched(self):
        import copy
        mod, tui = self.make()
        seed = {'__opencode_connection__': {'region': 'us-east-1', 'api_key': 'OLDTOKEN'},
                '__opencode_models__': {'local/m': {'region': 'us-east-1', 'api_key': 'OLDTOKEN', 'model': 'm'}}}
        tui.bedrock_keys = copy.deepcopy(seed)
        saved = []
        tui.save_config = lambda: saved.append(1)
        def boom(keys, region, key):
            raise ValueError('AWS Bedrock model discovery failed (HTTP 401); check the Region and token')
        for field, value in (('region', 'eu-west-1'), ('api_key', 'NEWTOKEN999')):
            with mock.patch.object(mod, 'refresh_bedrock_models', boom):
                tui._set_field('@bedrock', field, value)
            self.assertEqual(tui.bedrock_keys, seed)
            self.assertEqual(saved, [])
            self.assertIn('check the Region', tui.notice)


class NativeTransportTests(unittest.TestCase):
    def post(self, reply, **extra):
        import self_hosted_http as h
        seen = {}
        def fake(url, key, body=None, timeout=30, headers=None):
            seen.update(url=url, body=body, headers=headers)
            return reply
        values = dict({'_profile': 'aws-bedrock', 'api_key': 'TOK', 'model': 'anthropic.claude-3:0', 'region': 'us-east-1',
                       'base_url': RUNTIME}, **extra)
        body = {'messages': [{'role': 'user', 'content': 'x'}], 'max_tokens': 9, 'temperature': 0.5}
        with mock.patch.object(h, '_request', fake):
            out = h.compatible_post(values, body, 5)
        return seen, out

    def test_converse_headers_url_and_reasons(self):
        for reason, want in (('end_turn', 'stop'), ('max_tokens', 'length'), ('tool_use', 'tool_calls')):
            seen, out = self.post({'output': {'message': {'content': [{'text': 'hi'}]}}, 'stopReason': reason,
                                   'usage': {'inputTokens': 1, 'outputTokens': 2}})
            self.assertEqual(out['choices'][0]['finish_reason'], want)
        self.assertEqual(seen['url'], RUNTIME + '/model/anthropic.claude-3%3A0/converse')
        self.assertEqual(seen['headers'], {'Content-Type': 'application/json', 'Authorization': 'Bearer TOK'})
        self.assertNotIn('temperature', json.dumps(seen['body']))
        self.assertEqual(seen['body']['inferenceConfig'], {'maxTokens': 9})
        self.assertEqual(out['usage']['completion_tokens'], 2)

    def test_missing_content_names_converse_and_model(self):
        for reply in ({}, {'output': {}}):
            with self.assertRaises(ValueError) as caught:
                self.post(reply)
            self.assertIn('Converse', str(caught.exception))
            self.assertIn('anthropic.claude-3:0', str(caught.exception))

    def test_http_errors_and_redirects_do_not_leak_token(self):
        from urllib.error import HTTPError
        import self_hosted_http as h
        for code in (401, 403, 500, 302, 307):
            err = HTTPError(RUNTIME, code, 'denied TOK', {}, None)
            values = {'_profile': 'aws-bedrock', 'api_key': 'TOK', 'model': 'm', 'region': 'us-east-1', 'base_url': RUNTIME}
            with mock.patch.object(h, '_request', RequestCapture(error=err)):
                with self.assertRaises(ValueError) as caught:
                    h.compatible_post(values, {'messages': []}, 5)
            self.assertNotIn('TOK', str(caught.exception))
            self.assertIn(str(code), str(caught.exception))
            if code < 400:
                self.assertIn('not followed', str(caught.exception))

    def test_redactor_scrubs_text_and_bytes(self):
        import self_hosted
        self.assertEqual(self_hosted.redact_token('bad TOK here', 'TOK'), 'bad [redacted] here')
        self.assertEqual(self_hosted.redact_token(b'bad TOK', 'TOK'), b'bad [redacted]')


class RepairRegressionTests(Base):
    """Verification defects MC-103, MC-105, MC-303 plus per-defect guards for INV-1."""
    def profile_store(self, connection):
        keys = {'__opencode_connection__': connection,
                '__opencode_models__': {'local/anthropic.claude': {'model': 'anthropic.claude', 'base_url': URL, 'api_key': TOKEN}}}
        self_hosted.save_keys(str(self.config), keys, profile='aws-bedrock')

    def test_cleared_connection_does_not_keep_profile_credentials(self):
        self.write_config('runner aws-bedrock\nimplementation.model local/anthropic.claude\n')
        self.profile_store({'region': REGION, 'api_key': TOKEN})
        self.assertEqual(self_hosted.settings(str(self.config), 'implementation')['api_key'], TOKEN)
        for cleared in ({'region': REGION, 'api_key': ''}, {'region': '', 'api_key': TOKEN}, {'region': '', 'api_key': ''}):
            self.profile_store(cleared)
            with self.assertRaisesRegex(ValueError, 'AWS Bedrock'):
                self_hosted.settings(str(self.config), 'implementation')

    def test_legacy_stored_connection_migrates_region_without_rewrite(self):
        self.write_config('runner aws-bedrock\nimplementation.model local/anthropic.claude\n')
        self.profile_store({'base_url': 'https://bedrock-runtime.eu-west-1.amazonaws.com', 'api_key': TOKEN, 'api_compatibility': 'Foo '})
        before = (self.dir / 'aws-bedrock-keys.json').read_text()
        values = self_hosted.settings(str(self.config), 'implementation')
        self.assertEqual((values['region'], values['_profile']), ('eu-west-1', 'aws-bedrock'))
        self.assertNotIn('_protocol', values)
        self.assertEqual((self.dir / 'aws-bedrock-keys.json').read_text(), before)

    def test_compatibility_env_is_ignored(self):
        self.bedrock_config()
        os.environ['WORKFLOW_AWS_BEDROCK_API_COMPATIBILITY'] = 'anthropic'
        self.assertNotIn('_protocol', self.bedrock_values())

    def test_self_hosted_empty_choices_unchanged(self):
        values = {'api_key': 'T', 'model': 'm', 'base_url': 'http://h'}
        with mock.patch.object(http, '_compatible_output_post', lambda *a, **k: {'choices': []}):
            self.assertEqual(http.compatible_post(values, {'messages': []}, 5), {'choices': []})

    def test_malformed_response_names_converse(self):
        import bedrock_protocols as bp
        with self.assertRaisesRegex(ValueError, 'Converse'):
            bp.parse_response({})

    def test_sampling_bedrock_empty_and_self_hosted_has_temperature(self):
        self.assertEqual(http.sampling({'_profile': 'aws-bedrock'}), {})
        self.assertIn('temperature', http.sampling({'_profile': 'self-hosted'}))

    def test_strip_temperature_keeps_user_property_named_temperature(self):
        body = {'temperature': 1, 'options': {'temperature': 2}, 'schema': {'properties': {'temperature': {'type': 'number'}}}}
        out = http._strip_temperature(body)
        self.assertNotIn('temperature', out)
        self.assertNotIn('temperature', out['options'])
        self.assertEqual(out['schema']['properties'], {'temperature': {'type': 'number'}})


class DiscoveryTest(Base):
    CONTROL = 'https://bedrock.us-east-1.amazonaws.com'

    def run_discovery(self, responder, keys=None):
        calls = []

        def fake(url, headers):
            calls.append((url, headers))
            out = responder(url, len(calls))
            if isinstance(out, BaseException):
                raise out
            return out if isinstance(out, bytes) else json.dumps(out).encode()
        keys = {} if keys is None else keys
        with mock.patch.object(self_hosted, '_discovery_get', fake):
            try:
                return calls, self_hosted.refresh_bedrock_models(keys, REGION, TOKEN), keys
            except ValueError as exc:
                return calls, exc, keys

    def test_paginates_both_lists_and_unions_ids(self):
        def responder(url, n):
            if url == self.CONTROL + '/foundation-models':
                return {'modelSummaries': [{'modelId': 'amazon.a:0'}], 'nextToken': 'a/b+c='}
            if url == self.CONTROL + '/foundation-models?nextToken=a%2Fb%2Bc%3D':
                return {'modelSummaries': [{'modelId': 'amazon.b'}]}
            if url == self.CONTROL + '/inference-profiles?maxResults=100':
                return {'inferenceProfileSummaries': [{'inferenceProfileId': 'us.amazon.a:0'}, {'inferenceProfileId': 'amazon.b'}]}
            raise AssertionError(url)
        calls, names, keys = self.run_discovery(responder)
        self.assertEqual([u for u, _ in calls], [
            self.CONTROL + '/foundation-models', self.CONTROL + '/foundation-models?nextToken=a%2Fb%2Bc%3D',
            self.CONTROL + '/inference-profiles?maxResults=100'])
        for _, headers in calls:
            self.assertEqual(headers['Authorization'], 'Bearer ' + TOKEN)
        self.assertEqual(sorted(names), ['local/amazon.a:0', 'local/amazon.b', 'local/us.amazon.a:0'])
        self.assertEqual(keys['__opencode_connection__'], {'region': REGION, 'api_key': TOKEN})
        self.assertEqual(set(keys['__opencode_models__']), set(names))

    PRIOR = {'__opencode_connection__': {'region': 'eu-west-1', 'api_key': 'old'},
             '__opencode_models__': {'local/old': {'model': 'old', 'region': 'eu-west-1', 'api_key': 'old'}}}

    def assert_kept(self, responder, **kw):
        import copy
        prior = copy.deepcopy(self.PRIOR)
        calls, exc, keys = self.run_discovery(responder, copy.deepcopy(prior))
        self.assertIsInstance(exc, ValueError)
        self.assertEqual(keys, prior)
        self.assertNotIn(TOKEN, str(exc))
        return exc

    def test_repeated_next_token_errors_and_keeps_prior(self):
        self.assert_kept(lambda url, n: {'modelSummaries': [{'modelId': 'a.b'}], 'nextToken': 'same'})

    def test_101_pages_errors(self):
        counter = []

        def responder(url, n):
            counter.append(n)
            return {'modelSummaries': [{'modelId': 'a.b'}], 'nextToken': 'tok%d' % n}
        self.assert_kept(responder)
        self.assertLessEqual(len(counter), 101)

    def test_failures_keep_prior_catalog_and_hide_token(self):
        from urllib.error import HTTPError, URLError
        good = {'modelSummaries': [{'modelId': 'a.b'}]}
        cases = (
            lambda url, n: HTTPError(url, 403, 'denied ' + TOKEN, {}, None),
            lambda url, n: HTTPError(url, 302, 'moved', {}, None),
            lambda url, n: URLError('dns ' + TOKEN),
            lambda url, n: b'{not json ' + TOKEN.encode(),
            lambda url, n: b'[1, 2]',
            lambda url, n: good if n == 1 else HTTPError(url, 500, 'boom', {}, None),
            lambda url, n: dict(good, nextToken='p2') if n == 1 else b'garbage',
        )
        for responder in cases:
            self.assert_kept(responder)

    def test_unsafe_ids_skipped_and_empty_union_errors(self):
        def responder(url, n):
            if 'foundation' in url:
                return {'modelSummaries': [{'modelId': 'ok.model'}, {'modelId': 'has space'}, {'modelId': 'bad#frag'},
                                           {'modelId': '/leading'}, {'modelId': 'new\nline'}]}
            return {'inferenceProfileSummaries': []}
        _, names, _ = self.run_discovery(responder)
        self.assertEqual(names, ['local/ok.model'])
        exc = self.assert_kept(lambda url, n: {'modelSummaries': [{'modelId': 'has space'}, {'modelId': '#x'}]})
        self.assertIn('no usable models', str(exc))
        self.assert_kept(lambda url, n: {})

    def test_invalid_region_or_token_makes_no_request(self):
        calls = []
        with mock.patch.object(self_hosted, '_discovery_get', lambda u, h: calls.append(u)):
            for region, token in (('US-EAST-1', TOKEN), (REGION, 'bad token'), (REGION, '')):
                with self.assertRaises(ValueError):
                    self_hosted.discover_bedrock_models(region, token)
        self.assertEqual(calls, [])


class ConverseTemperatureTest(Base):
    """Every temperature source: the real settings() -> chat/final-call path posts a Converse body without it."""
    SOURCES = {
        'global-env': ('', {'WORKFLOW_AWS_BEDROCK_TEMPERATURE': '0.4242'}),
        'self-hosted-env': ('', {'WORKFLOW_SELF_HOSTED_TEMPERATURE': '0.4242'}),
        'per-stage': ('implementation.temperature 0.4242\naws-bedrock.temperature 0.4242\n', {}),
        'request-options': ('implementation.request-options %s\n' % json.dumps({'temperature': 0.4242, 'extra_body': {'temperature': 0.4242}}), {}),
    }

    def test_no_temperature_and_max_tokens_preserved(self):
        for name, (extra, env) in self.SOURCES.items():
            self.bedrock_config(extra)
            with mock.patch.dict(os.environ, env):
                values = http.configure_request_options(self.bedrock_values(), 'implementation')
                cap = RequestCapture()
                with mock.patch.object(http, '_request', cap):
                    http.chat(values, [{'role': 'system', 'content': 's'}, {'role': 'user', 'content': 'x'}], [], 321)
                    http.constrained_completion(values, [{'role': 'user', 'content': 'x'}], SCHEMA, 'n', 123)
            self.assertEqual(len(cap.calls), 2, name)
            for call in cap.calls:
                self.assertFalse(has_key(call['body'], 'temperature'), name)
                self.assertNotIn('0.4242', json.dumps(call['body']), name)
                self.assertTrue(call['url'].endswith('/converse'), name)
            self.assertEqual(cap.calls[0]['body']['inferenceConfig']['maxTokens'], 321, name)
            self.assertEqual(cap.calls[1]['body']['inferenceConfig']['maxTokens'], 123, name)
            self.assertEqual(cap.calls[1]['body']['toolConfig']['toolChoice'], {'tool': {'name': 'n'}}, name)


if __name__ == '__main__':
    unittest.main()
