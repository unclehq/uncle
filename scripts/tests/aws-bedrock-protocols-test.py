#!/usr/bin/env python3
"""AWS Bedrock protocol adapters, temperature stripping and redaction (new file; existing suites untouched)."""
import json
import os
import sys
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts' / 'lib'))
import bedrock_protocols as bp  # noqa: E402
import self_hosted  # noqa: E402
import self_hosted_http as http  # noqa: E402

MSGS = [{'role': 'system', 'content': 's'}, {'role': 'user', 'content': 'u'}]
TOOLS = [{'type': 'function', 'function': {'name': 'set', 'description': 'd', 'parameters': {
    'type': 'object', 'properties': {'temperature': {'type': 'number'}}, 'required': ['temperature']}}}]
SCHEMA = {'type': 'object', 'properties': {'a': {'type': 'string'}}}


class TemperatureTests(unittest.TestCase):
    def test_env_sentinels_absent_from_all_bodies(self):
        env = {'WORKFLOW_AWS_BEDROCK_TEMPERATURE': '0.12345', 'WORKFLOW_SELF_HOSTED_TEMPERATURE': '0.67890'}
        with mock.patch.dict(os.environ, env):
            for proto in bp.PROTOCOLS:
                text = json.dumps(http._strip_temperature(bp.build_body(proto, 'm', MSGS, 5, None, SCHEMA)))
                self.assertNotIn('0.12345', text)
                self.assertNotIn('0.67890', text)
                self.assertNotIn('temperature', text)
            self.assertEqual(http.sampling({'_profile': 'aws-bedrock'}), {})

    def test_schema_property_named_temperature_survives_strip(self):
        body = {'temperature': 0.4, 'tools': TOOLS}
        out = http._strip_temperature(body)
        self.assertNotIn('temperature', {k for k in out})
        params = out['tools'][0]['function']['parameters']
        self.assertIn('temperature', params['properties'])
        self.assertEqual(params['required'], ['temperature'])

    def test_self_hosted_still_carries_temperature(self):
        self.assertIn('temperature', http.sampling({'_profile': 'self-hosted'}))
        seen = {}
        def fake(values, body, timeout, url=None):
            seen['body'] = body
            return {'choices': [{'message': {'content': 'x'}}], 'usage': {}}
        body = {'messages': MSGS, 'temperature': 0.3}
        with mock.patch.object(http, '_compatible_output_post', fake):
            http.compatible_post({'_profile': 'self-hosted', 'base_url': 'http://h'}, body, 5)
        self.assertEqual(seen['body'], body)


class AdapterTests(unittest.TestCase):
    def test_protocol_normalization(self):
        for raw, want in (('  OpenAI Compatible ', 'openai'), ('ANTHROPIC', 'anthropic'), ('', 'openai'), (None, 'openai'),
                          ('Converse API compatible', 'converse')):
            self.assertEqual(bp.normalize_protocol(raw), want)
        with self.assertRaises(ValueError):
            bp.normalize_protocol('grpc')

    def test_missing_usage_is_zeros(self):
        replies = {'openai': {'choices': [{'message': {'content': 'x'}}]},
                   'anthropic': {'content': [{'type': 'text', 'text': 'x'}]},
                   'converse': {'output': {'message': {'content': [{'text': 'x'}]}}}}
        for proto, data in replies.items():
            self.assertEqual(bp.parse_response(proto, data)['usage'], {'input': 0, 'output': 0}, proto)

    def test_missing_required_keys_error_names_protocol(self):
        for proto, word in (('openai', 'OpenAI'), ('anthropic', 'Anthropic'), ('converse', 'Converse')):
            with self.assertRaises(ValueError) as cm:
                bp.parse_response(proto, {})
            self.assertIn(word, str(cm.exception))

    def test_constrained_output_forces_tool_or_schema(self):
        self.assertEqual(bp.build_body('openai', 'm', MSGS, 5, schema=SCHEMA)['response_format']['json_schema']['schema'], SCHEMA)
        self.assertEqual(bp.build_body('anthropic', 'm', MSGS, 5, schema=SCHEMA)['tool_choice'], {'type': 'tool', 'name': 'result'})
        self.assertEqual(bp.build_body('converse', 'm', MSGS, 5, schema=SCHEMA)['toolConfig']['toolChoice'], {'tool': {'name': 'result'}})

    def test_token_only_in_headers_and_final_urls(self):
        urls = {'openai': 'https://h/v1/chat/completions', 'anthropic': 'https://h/v1/v1/messages',
                'converse': 'https://h/v1/model/m1/converse'}
        for proto, url in urls.items():
            self.assertEqual(bp.build_url(proto, 'https://h/v1/', 'm1'), url)
            self.assertNotIn('SECRET', url)
            self.assertNotIn('SECRET', json.dumps(bp.build_body(proto, 'm1', MSGS, 5)))
            self.assertIn('SECRET', json.dumps(bp.build_headers(proto, 'SECRET')))
        self.assertNotIn('Authorization', bp.build_headers('anthropic', 'SECRET'))


class RedactionTests(unittest.TestCase):
    def test_http_error_body_and_reason_are_redacted(self):
        from urllib.error import HTTPError
        def transport(method, url, data, headers, timeout):
            return 401, 'bad SECRET', {}, b'echo SECRET ' + b'z' * 10
        with mock.patch.object(http, '_via_http1', transport), mock.patch.object(http, 'wants_http2', lambda s: False):
            with self.assertRaises(HTTPError) as cm:
                http._request('https://h/x', 'SECRET', {'a': 1})
        self.assertNotIn('SECRET', str(cm.exception.reason))
        self.assertNotIn(b'SECRET', cm.exception.read())

    def test_redact_token_empty_token_is_noop(self):
        self.assertEqual(self_hosted.redact_token('abc', ''), 'abc')


if __name__ == '__main__':
    unittest.main()
