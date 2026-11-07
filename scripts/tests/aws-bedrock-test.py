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

URL = 'https://bedrock.example.com/openai/v1'
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
        self.write_config('runner aws-bedrock\naws-bedrock.base_url %s\naws-bedrock.model anthropic.claude\n%s' % (URL, extra))
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


class LabelsTest(unittest.TestCase):
    """AC-1, AC-2: TUI labels and row order."""
    def setUp(self):
        self.source = (ROOT / 'uncle_tui.py').read_text(encoding='utf-8')

    def test_labels_present(self):
        for label in ('Bedrock URL', 'AWS Bedrock Token', 'AWS Bedrock', 'aws-bedrock-keys.json', 'HTTP_RUNNERS'):
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
        self.assertEqual(labels, ['Connection \u2014 Bedrock URL and AWS Bedrock Token', 'Refresh supported models ('])
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

    def test_bedrock_never_selects_ollama_format(self):
        self.bedrock_config()
        values = self.bedrock_values()
        modes = []

        def fake_final(v, messages, schema, name, mode, limit, effort, timeout):
            modes.append(mode)
            return '{}', 'stop', {}
        caps = {'modes': list(http.GRAMMAR_MODES) + ['prompt'], 'rejected': set()}
        with mock.patch.object(http, 'capabilities', return_value=caps), \
                mock.patch.object(http, '_final_call', fake_final):
            http.constrained_completion(values, [], SCHEMA, 'n', 10)
        self.assertNotIn('ollama_format', modes)

    def test_token_only_to_configured_url(self):
        self.bedrock_config()
        values = self.bedrock_values()
        seen = []

        def fake_post(url, key, body, timeout, what='model request'):
            seen.append((url, key))
            return {'choices': [{'message': {'content': '{}'}, 'finish_reason': 'stop'}], 'usage': {}}
        with mock.patch.object(http, 'post', fake_post):
            http.chat(values, [], [], 10)
        self.assertTrue(seen, 'no request reached post()')
        for url, key in seen:
            self.assertTrue(url.startswith(URL), url)
            self.assertEqual(key, TOKEN)

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

    def test_non_loopback_http_rejected_loopback_allowed(self):
        for host, ok in (('http://remote.example.com/v1', False), ('http://127.0.0.1:9/v1', True), ('http://localhost:9/v1', True)):
            self.write_config('runner aws-bedrock\naws-bedrock.base_url %s\naws-bedrock.model m\n' % host)
            os.environ['UNCLE_AWS_BEDROCK_API_KEY'] = TOKEN
            if ok:
                self.assertEqual(self_hosted.settings(str(self.config), 'implementation')['_profile'], 'aws-bedrock')
            else:
                with self.assertRaises(ValueError) as caught:
                    self_hosted.settings(str(self.config), 'implementation')
                self.assertIn('AWS Bedrock', str(caught.exception))
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
        self.write_config('runner aws-bedrock\naws-bedrock.base_url https://other.example.com/v1\naws-bedrock.model anthropic.claude\n')
        self.assertNotEqual(base, self.make_key(self.bedrock_values()), 'base URL must change the key')
        self.write_config('runner aws-bedrock\naws-bedrock.base_url %s\naws-bedrock.model other-model\n' % URL)
        self.assertNotEqual(base, self.make_key(self.bedrock_values()), 'model must change the key')
        sh = self.make_key(self.bedrock_values_as_self_hosted())
        self.assertNotEqual(base, sh, 'profile must change the key')

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

    def test_bedrock_url_rejected(self):
        # '#' starts a comment in the config file, so the fragment case goes through the env override.
        for bad in ('https://user:pw@h.example/v1', 'https://h.example/v1?x=1', 'https://h.example/v1#f'):
            self.write_config('runner aws-bedrock\naws-bedrock.base_url %s\naws-bedrock.model m\n' % URL)
            os.environ['UNCLE_AWS_BEDROCK_BASE_URL'] = bad
            os.environ['UNCLE_AWS_BEDROCK_API_KEY'] = TOKEN
            with self.assertRaises(ValueError) as caught:
                self_hosted.settings(str(self.config), 'implementation')
            self.assertIn('Bedrock', str(caught.exception))

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

    def test_exact_header_sets(self):
        import bedrock_protocols as bp
        self.assertEqual(bp.build_headers('openai', 'K'), {'Content-Type': 'application/json', 'Authorization': 'Bearer K'})
        self.assertEqual(bp.build_headers('converse', 'K'), {'Content-Type': 'application/json', 'Authorization': 'Bearer K'})
        self.assertEqual(bp.build_headers('anthropic', 'K'), {'Content-Type': 'application/json', 'x-api-key': 'K', 'anthropic-version': '2023-06-01'})

    def test_urls_and_unknown_protocol(self):
        import bedrock_protocols as bp
        self.assertEqual(bp.build_url('openai', 'http://h/', 'm'), 'http://h/chat/completions')
        self.assertEqual(bp.build_url('anthropic', 'http://h', 'm'), 'http://h/v1/messages')
        self.assertEqual(bp.build_url('converse', 'http://h', 'a/b'), 'http://h/model/a%2Fb/converse')
        with self.assertRaises(ValueError):
            bp.normalize_protocol('bogus')

    def test_bodies_have_no_temperature_and_shapes(self):
        import bedrock_protocols as bp
        for proto in bp.PROTOCOLS:
            body = bp.build_body(proto, 'm', self.MSGS, 50, self.TOOLS, self.SCHEMA)
            self.assertNotIn('temperature', json.dumps(body).lower(), proto)
        self.assertEqual(bp.build_body('openai', 'm', self.MSGS, 5, schema=self.SCHEMA)['response_format']['type'], 'json_schema')
        a = bp.build_body('anthropic', 'm', self.MSGS, 5, schema=self.SCHEMA)
        self.assertEqual((a['system'], a['tool_choice']['name']), ('sys', 'result'))
        c = bp.build_body('converse', 'm', self.MSGS, 5, schema=self.SCHEMA)
        self.assertEqual(c['inferenceConfig'], {'maxTokens': 5})
        self.assertEqual(c['toolConfig']['toolChoice'], {'tool': {'name': 'result'}})

    def test_parse_openai(self):
        import bedrock_protocols as bp
        r = bp.parse_response('openai', {'choices': [{'finish_reason': 'tool_calls', 'message': {'content': 'x', 'tool_calls': [
            {'id': '1', 'function': {'name': 't', 'arguments': '{"q":1}'}}]}}], 'usage': {'prompt_tokens': 3, 'completion_tokens': 4}})
        self.assertEqual((r['text'], r['tool_calls'][0]['arguments'], r['usage']), ('x', {'q': 1}, {'input': 3, 'output': 4}))

    def test_parse_anthropic_and_schema(self):
        import bedrock_protocols as bp
        d = {'content': [{'type': 'text', 'text': 'a'}, {'type': 'tool_use', 'id': '1', 'name': 'result', 'input': {'a': 'z'}},
                         {'type': 'tool_use', 'id': '2', 'name': 't', 'input': {}}], 'stop_reason': 'tool_use', 'usage': {'input_tokens': 1, 'output_tokens': 2}}
        r = bp.parse_response('anthropic', d, 'result')
        self.assertEqual(json.loads(r['text']), {'a': 'z'})
        self.assertEqual([c['name'] for c in r['tool_calls']], ['t'])
        self.assertEqual(r['usage'], {'input': 1, 'output': 2})

    def test_parse_converse(self):
        import bedrock_protocols as bp
        d = {'output': {'message': {'content': [{'text': 'hi'}, {'toolUse': {'toolUseId': '9', 'name': 't', 'input': {'k': 1}}}]}},
             'stopReason': 'tool_use', 'usage': {'inputTokens': 5, 'outputTokens': 6}}
        r = bp.parse_response('converse', d)
        self.assertEqual((r['text'], r['tool_calls'][0]['id'], r['usage']), ('hi', '9', {'input': 5, 'output': 6}))

    def test_malformed_responses_raise(self):
        import bedrock_protocols as bp
        for proto in bp.PROTOCOLS:
            with self.assertRaises(ValueError):
                bp.parse_response(proto, {})


class ApiCompatibilityFieldTests(unittest.TestCase):
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

    def test_bedrock_popup_fields_and_choices(self):
        mod, tui = self.make()
        self.assertEqual(mod.COMPAT_CHOICES, ['OpenAI compatible', 'Anthropic compatible', 'Converse API compatible'])
        self.assertEqual(tui.stage_fields('@bedrock'), ['base_url', 'api_key', 'api_compatibility'])
        self.assertEqual(tui.stage_fields('@connection'), ['base_url', 'api_key'])
        tui.picker_kind, tui.picker_target = 'api_compatibility', '@bedrock'
        self.assertEqual([t for _, t in tui._picker_rows()], mod.COMPAT_CHOICES)
        self.assertEqual(tui._picker_current(), 'OpenAI compatible')
        rows = tui._stage_items() if False else None
        self.assertIn('OpenAI compatible  (default)', tui._field_display('@bedrock', 'api_compatibility'))

    def test_choice_persists_in_bedrock_keys_only_and_rejects_others(self):
        mod, tui = self.make()
        tui._set_field('@bedrock', 'api_compatibility', 'Anthropic compatible')
        self.assertEqual(tui.bedrock_keys['__opencode_connection__']['api_compatibility'], 'Anthropic compatible')
        self.assertEqual(tui.stage_api_keys, {})
        tui._set_field('@bedrock', 'api_compatibility', 'bogus')
        self.assertEqual(tui.bedrock_keys['__opencode_connection__']['api_compatibility'], 'Anthropic compatible')
        self.assertIn('API Compatibility', tui.notice)


class NativeTransportTests(unittest.TestCase):
    def post(self, protocol, reply):
        import self_hosted_http as h
        seen = {}
        def fake(url, key, body=None, timeout=30, headers=None):
            seen.update(url=url, body=body, headers=headers)
            return reply
        values = {'_profile': 'aws-bedrock', '_protocol': protocol, 'api_key': 'TOK', 'model': 'm', 'base_url': 'https://h'}
        body = {'messages': [{'role': 'user', 'content': 'x'}], 'max_tokens': 9, 'temperature': 0.5}
        with mock.patch.object(h, '_request', fake):
            out = h.compatible_post(values, body, 5)
        return seen, out

    def test_anthropic_headers_url_no_temperature(self):
        seen, out = self.post('anthropic', {'content': [{'type': 'text', 'text': 'ok'}], 'usage': {'input_tokens': 1, 'output_tokens': 2}})
        self.assertEqual(seen['url'], 'https://h/v1/messages')
        self.assertEqual(seen['headers'], {'Content-Type': 'application/json', 'x-api-key': 'TOK', 'anthropic-version': '2023-06-01'})
        self.assertNotIn('temperature', json.dumps(seen['body']))
        self.assertEqual(out['choices'][0]['message']['content'], 'ok')

    def test_converse_headers_url(self):
        seen, out = self.post('converse', {'output': {'message': {'content': [{'text': 'hi'}]}}, 'usage': {'inputTokens': 1, 'outputTokens': 2}})
        self.assertEqual(seen['url'], 'https://h/model/m/converse')
        self.assertEqual(seen['headers']['Authorization'], 'Bearer TOK')
        self.assertNotIn('temperature', json.dumps(seen['body']))
        self.assertEqual(out['usage']['completion_tokens'], 2)

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
        self.profile_store({'base_url': URL, 'api_key': TOKEN})
        self.assertEqual(self_hosted.settings(str(self.config), 'implementation')['api_key'], TOKEN)
        for cleared in ({'base_url': URL, 'api_key': ''}, {'base_url': '', 'api_key': TOKEN}, {'base_url': '', 'api_key': ''}):
            self.profile_store(cleared)
            with self.assertRaisesRegex(ValueError, 'AWS Bedrock'):
                self_hosted.settings(str(self.config), 'implementation')

    def test_unknown_stored_protocol_runs_as_openai_with_one_notice(self):
        self.bedrock_config()
        self.profile_store({'base_url': URL, 'api_key': TOKEN, 'api_compatibility': 'Foo '})
        self.write_config('runner aws-bedrock\nimplementation.model local/anthropic.claude\n')
        self_hosted._BEDROCK_COMPAT_NOTICED = False
        before = (self.dir / 'aws-bedrock-keys.json').read_text()
        with mock.patch('sys.stderr') as err:
            first = self_hosted.settings(str(self.config), 'implementation')
            second = self_hosted.settings(str(self.config), 'implementation')
        self.assertEqual((first['_protocol'], second['_protocol']), ('openai', 'openai'))
        notices = [c.args[0] for c in err.write.call_args_list if 'Foo' in c.args[0]]
        self.assertEqual(len(notices), 1)
        self.assertEqual((self.dir / 'aws-bedrock-keys.json').read_text(), before)

    def test_openai_empty_choices_names_protocol(self):
        values = {'_profile': 'aws-bedrock', '_protocol': 'openai', 'api_key': 'T', 'model': 'm', 'base_url': 'https://h'}
        for reply in ({'choices': []}, {}):
            with mock.patch.object(http, '_compatible_output_post', lambda *a, **k: reply):
                for cap in (None, 5):
                    body = {'messages': [], **({} if cap is None else {'max_tokens': cap})}
                    with self.assertRaisesRegex(ValueError, 'AWS Bedrock OpenAI response has no choices'):
                        http.compatible_post(values, body, 5)

    def test_self_hosted_empty_choices_unchanged(self):
        values = {'api_key': 'T', 'model': 'm', 'base_url': 'http://h'}
        with mock.patch.object(http, '_compatible_output_post', lambda *a, **k: {'choices': []}):
            self.assertEqual(http.compatible_post(values, {'messages': []}, 5), {'choices': []})

    def test_malformed_responses_name_protocol(self):
        import bedrock_protocols as bp
        for proto, word in (('openai', 'OpenAI'), ('anthropic', 'Anthropic'), ('converse', 'Converse')):
            with self.assertRaisesRegex(ValueError, word):
                bp.parse_response(proto, {})

    def test_sampling_bedrock_empty_and_self_hosted_has_temperature(self):
        self.assertEqual(http.sampling({'_profile': 'aws-bedrock'}), {})
        self.assertIn('temperature', http.sampling({'_profile': 'self-hosted'}))

    def test_strip_temperature_keeps_user_property_named_temperature(self):
        body = {'temperature': 1, 'options': {'temperature': 2}, 'schema': {'properties': {'temperature': {'type': 'number'}}}}
        out = http._strip_temperature(body)
        self.assertNotIn('temperature', out)
        self.assertNotIn('temperature', out['options'])
        self.assertEqual(out['schema']['properties'], {'temperature': {'type': 'number'}})


if __name__ == '__main__':
    unittest.main()
