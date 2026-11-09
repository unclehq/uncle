"""Self Hosted stages on servers that refuse `temperature`.

Hosted OpenAI-compatible gateways refuse the field on some models (newer Claude
and GPT models behind Bedrock-backed gateways answer 400 "<model> does not
support temperature"). Uncle retries such a refusal without the field, once per
model, and `temperature none` leaves it out from the start. Only the network
post is replaced; no network, no model calls.
"""
import io
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock
from urllib.error import HTTPError

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts' / 'lib'))

import self_hosted_http as http  # noqa: E402

OK = {'choices': [{'message': {'content': 'done'}, 'finish_reason': 'stop'}], 'usage': {}}
BASE = 'https://gateway.example/v1'


class Server:
    """Answers OK unless the body carries a field the server refuses."""
    def __init__(self, refusal=b'{"error":"Claude Opus 5.5 does not support temperature"}', refuses='temperature'):
        self.bodies, self.refusal, self.refuses = [], refusal, refuses

    def __call__(self, url, key, body, timeout, what='model request'):
        self.bodies.append(body)
        if self.refuses in body or self.refuses is None:
            raise HTTPError(url, 400, 'Bad Request', {}, io.BytesIO(self.refusal))
        return OK


class TemperatureRefusalTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        env = {k: v for k, v in os.environ.items() if not k.startswith(('WORKFLOW_SELF_HOSTED', 'UNCLE_'))}
        env.update(UNCLE_CONFIG=str(Path(tmp.name) / 'config'), UNCLE_STATUS_STAGE='implementation',
                   WORKFLOW_SELF_HOSTED_USE_TEMPERATURE='on')  # off by default; these tests are about the on case
        for patcher in (mock.patch.dict(os.environ, env, clear=True),
                        mock.patch.dict(http._request_features, {}, clear=True)):
            patcher.start()
            self.addCleanup(patcher.stop)

    def chat(self, server, model='m1'):
        values = {'base_url': BASE, 'api_key': 'k', 'model': model}
        with mock.patch.object(http, 'post', server):
            return http.chat(values, [{'role': 'user', 'content': 'x'}], None, 100)

    def test_refused_temperature_is_retried_without_it_and_remembered_for_the_model(self):
        server = Server()
        self.assertEqual(self.chat(server)['choices'][0]['message']['content'], 'done')
        self.assertEqual(['temperature' in body for body in server.bodies], [True, False])
        self.chat(server)
        self.assertEqual(['temperature' in body for body in server.bodies], [True, False, False])

    def test_another_model_on_the_same_server_still_sends_temperature(self):
        server = Server()
        self.chat(server, 'm1')
        self.chat(server, 'm2')
        self.assertEqual(['temperature' in body for body in server.bodies], [True, False, True, False])

    def test_temperature_none_sends_no_temperature(self):
        os.environ['WORKFLOW_SELF_HOSTED_TEMPERATURE'] = 'none'
        server = Server()
        self.assertIsNotNone(self.chat(server))
        self.assertEqual(len(server.bodies), 1)
        self.assertNotIn('temperature', server.bodies[0])

    def test_an_unrelated_refusal_keeps_temperature_and_reports_the_server_reason(self):
        server = Server(refusal=b'{"error":"unknown field foo"}', refuses=None)
        self.assertIsNone(self.chat(server))
        self.assertTrue(server.bodies and all('temperature' in body for body in server.bodies))
        self.assertIn('unknown field foo', http.last_rejection)


class UseTemperatureSwitchTest(unittest.TestCase):
    """`self-hosted.use-temperature` turns temperature on or off; off unless set."""
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.config = Path(tmp.name) / 'config'
        env = {k: v for k, v in os.environ.items() if not k.startswith(('WORKFLOW_SELF_HOSTED', 'UNCLE_'))}
        env.update(UNCLE_CONFIG=str(self.config), UNCLE_STATUS_STAGE='implementation')
        patcher = mock.patch.dict(os.environ, env, clear=True)
        patcher.start()
        self.addCleanup(patcher.stop)

    def write(self, text):
        self.config.write_text(text)

    def test_off_by_default_sends_no_temperature(self):
        self.assertIsNone(http.temperature())
        self.assertEqual(http.sampling({'_profile': 'self-hosted'}), {})

    def test_off_ignores_a_configured_value_and_the_requirements_default(self):
        self.write('self-hosted.temperature 0.7\n')
        self.assertIsNone(http.temperature())
        self.assertIsNone(http.temperature('requirements'))

    def test_on_in_config_sends_the_default_and_configured_values(self):
        self.write('self-hosted.use-temperature on\n')
        self.assertEqual(http.temperature(), 0.0)
        self.assertEqual(http.temperature('requirements'), 1.0)
        self.assertEqual(http.sampling({'_profile': 'self-hosted'}), {'temperature': 0.0})
        self.write('self-hosted.use-temperature on\nself-hosted.temperature 0.7\n')
        self.assertEqual(http.temperature(), 0.7)

    def test_environment_overrides_config_in_both_directions(self):
        self.write('self-hosted.use-temperature on\n')
        os.environ['WORKFLOW_SELF_HOSTED_USE_TEMPERATURE'] = 'off'
        self.assertIsNone(http.temperature())
        self.write('self-hosted.use-temperature off\n')
        os.environ['WORKFLOW_SELF_HOSTED_USE_TEMPERATURE'] = 'on'
        self.assertEqual(http.temperature(), 0.0)

    def test_an_unrecognised_value_is_refused(self):
        self.write('self-hosted.use-temperature maybe\n')
        with self.assertRaisesRegex(ValueError, 'use-temperature must be on or off'):
            http.temperature()

    def test_bedrock_never_sends_one_even_when_on(self):
        os.environ['WORKFLOW_SELF_HOSTED_USE_TEMPERATURE'] = 'on'
        self.assertEqual(http.sampling({'_profile': 'aws-bedrock'}), {})


if __name__ == '__main__':
    unittest.main()
