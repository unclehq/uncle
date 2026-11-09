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
            text = json.dumps(http._strip_temperature(bp.build_body(MSGS, 5, None, SCHEMA)))
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

    @mock.patch.dict(os.environ, {'WORKFLOW_SELF_HOSTED_USE_TEMPERATURE': 'on'})  # temperature is off by default
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
    def test_removed_protocol_surface(self):
        for name in ('normalize_protocol', 'PROTOCOLS'):
            self.assertFalse(hasattr(bp, name), name)

    def test_region_validation(self):
        self.assertEqual(bp.validate_region(' us-east-1 '), 'us-east-1')
        for bad in ('US-EAST-1', '', '  ', None, 'us_east_1', 'us-east', 'a.b-1', 'us-east-1/x'):
            with self.assertRaises(ValueError, msg=repr(bad)):
                bp.validate_region(bad)

    def test_region_from_url_legacy(self):
        self.assertEqual(bp.region_from_url('https://bedrock-runtime.eu-west-1.amazonaws.com'), 'eu-west-1')
        self.assertEqual(bp.region_from_url('https://bedrock.eu-west-1.amazonaws.com'), 'eu-west-1')
        for bad in ('http://bedrock-runtime.eu-west-1.amazonaws.com', 'https://bedrock-runtime.eu-west-1.example.com',
                    'https://u:p@bedrock-runtime.eu-west-1.amazonaws.com', 'https://bedrock-runtime.eu-west-1.amazonaws.com:443', '', None):
            self.assertIsNone(bp.region_from_url(bad), bad)

    def test_missing_usage_is_zeros(self):
        data = {'output': {'message': {'content': [{'text': 'x'}]}}}
        self.assertEqual(bp.parse_response(data)['usage'], {'input': 0, 'output': 0})

    def test_missing_required_keys_error_names_converse(self):
        with self.assertRaises(ValueError) as cm:
            bp.parse_response({})
        self.assertIn('Converse', str(cm.exception))

    def test_constrained_output_forces_tool(self):
        body = bp.build_body(MSGS, 5, schema=SCHEMA)
        self.assertEqual(body['toolConfig']['toolChoice'], {'tool': {'name': 'result'}})
        self.assertEqual(body['toolConfig']['tools'][0]['toolSpec']['inputSchema']['json'], SCHEMA)

    def test_token_only_in_headers_and_final_url(self):
        url = 'https://bedrock-runtime.us-east-1.amazonaws.com/model/m1/converse'
        self.assertEqual(bp.build_url('us-east-1', 'm1'), url)
        self.assertNotIn('SECRET', url)
        self.assertNotIn('SECRET', json.dumps(bp.build_body(MSGS, 5)))
        self.assertEqual(bp.build_headers('SECRET')['Authorization'], 'Bearer SECRET')
        self.assertEqual(set(bp.build_headers('SECRET')), {'Content-Type', 'Authorization'})


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
