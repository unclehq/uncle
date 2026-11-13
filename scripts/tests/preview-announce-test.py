#!/usr/bin/env python3
"""Every run says where the preview is: Local preview / Preview (not local), and names a Vite dev server."""
import io
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts/lib'))
import preview_announce as pa  # noqa: E402


class Wording(unittest.TestCase):
    def test_loopback_outside_a_hosted_run_is_local(self):
        for url in ('http://127.0.0.1:5173/', 'http://localhost:3000/index.html', 'http://[::1]:8080/'):
            self.assertEqual(pa.line(url), 'Local preview: ' + url)

    def test_anything_else_says_it_is_not_local(self):
        self.assertEqual(pa.line('http://10.0.0.5:5000/'), 'Preview (not local): http://10.0.0.5:5000/')
        self.assertEqual(pa.line('https://x.example/p'), 'Preview (not local): https://x.example/p')

    def test_a_hosted_run_is_never_local_even_on_loopback(self):
        self.assertEqual(pa.line('http://127.0.0.1:5000/', is_hosted=True), 'Preview (not local): http://127.0.0.1:5000/')

    def test_vite_is_named(self):
        self.assertEqual(pa.line('http://127.0.0.1:5173/', vite=True), 'Local preview (Vite): http://127.0.0.1:5173/')
        self.assertEqual(pa.line('http://10.0.0.5:5173/', vite=True), 'Preview (not local, Vite): http://10.0.0.5:5173/')


class Scan(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.dir = self.tmp.name

    def put(self, name, text):
        Path(self.dir, name).write_text(text)

    def server(self, name, url, pid=None):
        self.put(name + '.pid', str(os.getpid() if pid is None else pid))
        self.put(name + '.url', url)

    def test_new_address_is_said_once(self):
        seen = set()
        self.server('preview-server', 'http://127.0.0.1:5000/')
        self.assertEqual(pa.scan(self.dir, seen), ['Local preview: http://127.0.0.1:5000/'])
        self.assertEqual(pa.scan(self.dir, seen), [])
        self.server('preview-server', 'http://127.0.0.1:6000/')
        self.assertEqual(pa.scan(self.dir, seen), ['Local preview: http://127.0.0.1:6000/'])

    def test_vite_start_is_announced_once_even_though_the_static_record_is_rewritten(self):
        seen = set()
        self.server('preview-server', 'http://127.0.0.1:5000/')
        pa.scan(self.dir, seen)
        self.server('preview-vite', 'http://127.0.0.1:5173/')
        self.put('preview-server.url', 'http://127.0.0.1:5173/')
        self.assertEqual(pa.scan(self.dir, seen), ['Local preview (Vite): http://127.0.0.1:5173/'])

    def test_dead_pid_and_junk_urls_are_ignored(self):
        self.server('preview-server', 'http://127.0.0.1:5000/', pid=999999999)
        self.assertEqual(pa.scan(self.dir, set()), [])
        self.server('preview-server', 'javascript:alert(1)')
        self.assertEqual(pa.scan(self.dir, set()), [])

    def test_hosted_run_announces_it_as_not_local(self):
        self.server('preview-server', 'http://127.0.0.1:5000/')
        self.assertEqual(pa.scan(self.dir, set(), is_hosted=True), ['Preview (not local): http://127.0.0.1:5000/'])

    def test_watch_prints_and_stops_when_the_driver_is_gone(self):
        self.server('preview-server', 'http://127.0.0.1:5000/')
        out = io.StringIO()
        self.assertEqual(pa.watch(self.dir, 999999999, out=out, sleep=lambda _: None), 0)
        self.assertEqual(out.getvalue(), 'Local preview: http://127.0.0.1:5000/\n')

    def test_cli_runs_as_a_script(self):
        self.server('preview-server', 'http://127.0.0.1:5000/')
        done = subprocess.run([sys.executable, '-I', str(ROOT / 'scripts/lib/preview_announce.py'), 'watch', self.dir, '999999999'],
                              capture_output=True, text=True, timeout=30, env={'PATH': os.environ['PATH']})
        self.assertEqual(done.stdout, 'Local preview: http://127.0.0.1:5000/\n')
        hosted = subprocess.run([sys.executable, '-I', str(ROOT / 'scripts/lib/preview_announce.py'), 'watch', self.dir, '999999999'],
                                capture_output=True, text=True, timeout=30, env={'PATH': os.environ['PATH'], 'UNCLE_HOSTED': '1'})
        self.assertEqual(hosted.stdout, 'Preview (not local): http://127.0.0.1:5000/\n')


class DriverWiring(unittest.TestCase):
    def test_the_driver_starts_and_stops_the_announcer(self):
        text = (ROOT / 'scripts/stagegate.sh').read_text()
        # Not through the per-run Python host, which would hold its output until the run ended.
        self.assertIn('command python3 -B "$ROOT/scripts/lib/preview_announce.py" watch "$STATE_DIR" $$', text)
        self.assertIn('kill "$PREVIEW_ANNOUNCE_PID"', text)


if __name__ == '__main__':
    unittest.main()
