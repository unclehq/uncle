"""A refused optional request field is remembered across stage processes (issue 203)."""
import http.server
import json
import os
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'scripts' / 'lib'))
import self_hosted_http as h


def serve():
    seen = []

    class H(http.server.BaseHTTPRequestHandler):
        def do_POST(self):
            body = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
            seen.append('chat_template_kwargs' in body)
            if 'chat_template_kwargs' in body:
                code, out = 400, b'{"error": "chat_template_kwargs isn\'t a supported request field; remove it"}'
            else:
                code, out = 200, b'{"choices": [{"message": {"role": "assistant", "content": "ok"}}]}'
            self.send_response(code)
            self.send_header('Content-Length', str(len(out)))
            self.end_headers()
            self.wfile.write(out)

        def log_message(self, *a):
            pass
    srv = http.server.HTTPServer(('127.0.0.1', 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, seen


class Refused(unittest.TestCase):
    def test_second_process_does_not_resend(self):
        srv, seen = serve()
        self.addCleanup(srv.shutdown)
        self.addCleanup(srv.server_close)
        d = tempfile.TemporaryDirectory()
        self.addCleanup(d.cleanup)
        values = {'base_url': 'http://127.0.0.1:%d/v1' % srv.server_port, 'api_key': 'k', 'model': 'm'}
        env = {'UNCLE_OUTAGE_DIR': d.name, 'UNCLE_STATUS_STAGE': 'final-audit'}
        with mock.patch.dict(os.environ, env):
            for process in (1, 2):
                h._request_features.clear()      # a new stage process starts with no in-memory state
                seen.clear()
                data = h.compatible_post(values, {'model': 'm', 'messages': [], 'max_tokens': 5}, 10)
                self.assertEqual(data['choices'][0]['message']['content'], 'ok')
                if process == 1:
                    self.assertEqual(seen, [True, False])    # sent once, refused, retried clean
                else:
                    self.assertEqual(seen, [False])          # remembered: never sent again


if __name__ == '__main__':
    unittest.main()
