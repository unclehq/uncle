"""A host spending stop (HTTP 402, issue 230) is a SpendingStop, not a bad Base URL or key."""
import http.server
import json
import os
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts' / 'lib'))
import self_hosted_http as h
import supervisor

BUDGET = {'code': 'budget_reached', 'scope': 'task', 'limit_atomic': 6000000,
          'used_atomic': 5310221, 'suggested_increase_atomic': 60000}


def serve(status, payload):
    class H(http.server.BaseHTTPRequestHandler):
        def do_POST(self):
            self.rfile.read(int(self.headers.get('Content-Length', 0)))
            body = json.dumps(payload).encode()
            self.send_response(status)
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *a):
            pass
    srv = http.server.HTTPServer(('127.0.0.1', 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv


class SpendingStop(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.TemporaryDirectory()
        self.addCleanup(self.root.cleanup)
        patch = mock.patch.dict(os.environ, {'UNCLE_PROJECT_ROOT': self.root.name})
        patch.start()
        self.addCleanup(patch.stop)

    def chat(self, status, payload):
        srv = serve(status, payload)
        self.addCleanup(srv.shutdown)
        values = {'base_url': 'http://127.0.0.1:%d/v1' % srv.server_port, 'api_key': 'test-key-0000', 'model': 'm'}
        return h.chat(values, [{'role': 'user', 'content': 'hi'}], None, 16, timeout=5)

    def marker(self):
        return Path(self.root.name, '.uncle/workflow/spending-stop')

    def test_budget_reached_is_a_typed_stop_naming_the_limit_and_the_suggestion(self):
        with self.assertRaises(h.SpendingStop) as caught:
            self.chat(402, BUDGET)
        stop = caught.exception
        self.assertEqual((stop.code, stop.scope, stop.limit_atomic, stop.used_atomic, stop.suggested_increase_atomic),
                         ('budget_reached', 'task', 6000000, 5310221, 60000))
        self.assertIn('$6.00', str(stop))
        self.assertIn('$0.06', str(stop))
        self.assertNotIn('Base URL', str(stop))

    def test_balance_exhausted_is_a_typed_stop(self):
        with self.assertRaises(h.SpendingStop) as caught:
            self.chat(402, {'code': 'balance_exhausted', 'balance_atomic': 0})
        self.assertEqual(caught.exception.code, 'balance_exhausted')
        self.assertIn('balance', str(caught.exception))

    def test_stop_leaves_the_marker_the_stage_driver_reads(self):
        with self.assertRaises(h.SpendingStop):
            self.chat(402, BUDGET)
        self.assertIn('spending limit', self.marker().read_text())

    def test_other_402_and_other_errors_stay_a_configuration_error_without_a_marker(self):
        for status, payload in ((402, {'code': 'something_else'}), (402, {'error': 'pay up'}), (401, {'error': 'no'})):
            with self.assertRaises(ValueError) as caught:
                self.chat(status, payload)
            self.assertNotIsInstance(caught.exception, h.SpendingStop)
            self.assertIn('check the Base URL', str(caught.exception))
        self.assertFalse(self.marker().exists())

    def test_it_is_still_a_value_error_for_existing_handlers(self):
        self.assertTrue(issubclass(h.SpendingStop, ValueError))

    def test_supervisor_treats_a_spending_stop_as_external_capacity(self):
        for text in ('HTTP 402: {"code":"budget_reached"}', 'balance_exhausted', 'the task spending limit was reached'):
            self.assertTrue(supervisor.external_capacity_failure(text), text)
        self.assertFalse(supervisor.external_capacity_failure('HTTP 401: bad key'))


if __name__ == '__main__':
    unittest.main()
