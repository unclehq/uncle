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
        env.update(UNCLE_CONFIG=str(Path(tmp.name) / 'config'), UNCLE_STATUS_STAGE='implementation')
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


if __name__ == '__main__':
    unittest.main()
