"""Self-hosted post() retries transient HTTP answers (issue 201) and fails fast on the rest."""
import http.server
import io
import sys
import threading
import unittest
from contextlib import redirect_stderr
from pathlib import Path
from unittest import mock
from urllib.error import HTTPError

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts' / 'lib'))
import self_hosted_http as h


def serve(codes):
    seen = []

    class H(http.server.BaseHTTPRequestHandler):
        def do_POST(self):
            self.rfile.read(int(self.headers.get('Content-Length', 0)))
            code = codes[min(len(seen), len(codes) - 1)]
            seen.append(code)
            body = b'{"choices": []}' if code == 200 else b'{"error": "boom %d"}' % code
            self.send_response(code)
            if code == 429:
                self.send_header('Retry-After', '0')
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *a):
            pass
    srv = http.server.HTTPServer(('127.0.0.1', 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, seen


class Retry(unittest.TestCase):
    def run_post(self, codes):
        srv, seen = serve(codes)
        self.addCleanup(srv.shutdown)
        err = io.StringIO()
        with mock.patch.object(h.time, 'sleep'), redirect_stderr(err):
            try:
                result = h.post('http://127.0.0.1:%d/v1/chat/completions' % srv.server_port, 'k', {}, 5)
            except HTTPError as e:
                result = e
        return result, seen, err.getvalue()

    def test_500_twice_then_200(self):
        result, seen, log = self.run_post([500, 500, 200])
        self.assertEqual(seen, [500, 500, 200])
        self.assertEqual(result, {'choices': []})
        self.assertEqual(log.count('retry'), 2)

    def test_429_honors_retry_after(self):
        result, seen, _ = self.run_post([429, 200])
        self.assertEqual(seen, [429, 200])

    def test_always_500_stops_at_limit(self):
        result, seen, _ = self.run_post([500])
        self.assertEqual(len(seen), h.RETRY_LIMIT)
        self.assertIsInstance(result, HTTPError)
        self.assertEqual(result.code, 500)

    def test_permanent_errors_not_retried(self):
        for code in (400, 401, 403, 404, 422):
            result, seen, _ = self.run_post([code])
            self.assertEqual(seen, [code])


if __name__ == '__main__':
    unittest.main()
