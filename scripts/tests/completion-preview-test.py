#!/usr/bin/env python3
import json
from pathlib import Path
import queue
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'lib'))
from completion_preview import CompletionPreview, launch_spec, has_starred


class ScriptFallback(unittest.TestCase):
    def project(self, scripts, built=False, command=('npm', 'run', 'start')):
        root = Path(tempfile.mkdtemp())
        (root / '.uncle').mkdir()
        (root / 'package.json').write_text(json.dumps({'scripts': scripts}))
        (root / '.uncle/launch.json').write_text(json.dumps({'kind': 'webpage', 'command': list(command), 'url': 'http://127.0.0.1:4173'}))
        if built:
            (root / 'dist').mkdir()
            (root / 'dist/index.html').write_text('x')
        return root

    def test_a_missing_start_script_becomes_dev_before_a_build_exists(self):
        # noinit: launch.json said `npm run start`; package.json had dev, build and preview; the page was blank
        root = self.project({'dev': 'vite', 'build': 'vite build', 'preview': 'vite preview'})
        self.assertEqual(launch_spec(root)['command'], ['npm', 'run', 'dev'])

    def test_it_becomes_preview_once_the_build_is_there(self):
        root = self.project({'dev': 'vite', 'preview': 'vite preview'}, built=True)
        self.assertEqual(launch_spec(root)['command'], ['npm', 'run', 'preview'])

    def test_a_script_that_exists_or_another_command_is_left_alone(self):
        self.assertEqual(launch_spec(self.project({'start': 'x', 'dev': 'y'}))['command'], ['npm', 'run', 'start'])
        self.assertEqual(launch_spec(self.project({'dev': 'y'}, command=('node', 'server.js')))['command'], ['node', 'server.js'])
        self.assertEqual(launch_spec(self.project({'build': 'b'}))['command'], ['npm', 'run', 'start'])


class Prepare(unittest.TestCase):
    def test_a_project_with_no_install_or_build_gets_both_before_it_is_launched(self):
        import completion_preview as cp
        root = Path(tempfile.mkdtemp())
        (root / 'package.json').write_text(json.dumps({'scripts': {'build': 'vite build', 'preview': 'vite preview'}}))
        calls = []
        with patch('completion_preview.subprocess.run', side_effect=lambda cmd, **kw: calls.append(cmd)):
            did = cp.prepare_project(root, ['npm', 'run', 'preview'])
        self.assertEqual(calls, [['npm', 'install', '--no-audit', '--no-fund'], ['npm', 'run', 'build']])
        self.assertEqual(did, 'npm install, npm run build')

    def test_nothing_is_done_when_the_project_is_ready_or_the_command_is_not_npm(self):
        import completion_preview as cp
        root = Path(tempfile.mkdtemp())
        (root / 'package.json').write_text(json.dumps({'scripts': {'build': 'b', 'preview': 'p'}}))
        (root / 'node_modules').mkdir()
        (root / 'dist').mkdir()
        (root / 'dist/index.html').write_text('x')
        with patch('completion_preview.subprocess.run') as run:
            self.assertEqual(cp.prepare_project(root, ['npm', 'run', 'preview']), '')
            self.assertEqual(cp.prepare_project(root, ['node', 'server.js']), '')
            run.assert_not_called()

    def test_a_dev_launch_installs_but_does_not_build(self):
        import completion_preview as cp
        root = Path(tempfile.mkdtemp())
        (root / 'package.json').write_text(json.dumps({'scripts': {'build': 'b', 'dev': 'vite'}}))
        calls = []
        with patch('completion_preview.subprocess.run', side_effect=lambda cmd, **kw: calls.append(cmd)):
            cp.prepare_project(root, ['npm', 'run', 'dev'])
        self.assertEqual(calls, [['npm', 'install', '--no-audit', '--no-fund']])


class PreviewTests(unittest.TestCase):
    def test_uncle_preview_hands_off_terminal_before_completion(self):
        self.spec({'kind':'command','command':['python3','uncle_tui.py']})
        with patch('completion_preview.subprocess.Popen') as spawn, patch('completion_preview.has_starred', return_value=True):
            preview = CompletionPreview(self.root)
            try:
                self.assertEqual(preview.events.get(timeout=3), ('terminal', ['python3','uncle_tui.py']))
                spawn.assert_not_called()
                self.assertTrue(preview.events.empty())
                preview.terminal_done.set()
                self.assertEqual(preview.events.get(timeout=3), ('done', True))
            finally:
                preview.close()

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / '.uncle').mkdir()

    def spec(self, data):
        (self.root / '.uncle/launch.json').write_text(json.dumps(data))

    def events(self, preview):
        events = []
        while True:
            event = preview.events.get(timeout=5)
            events.append(event)
            if event[0] == 'done':
                return events

    def test_command_streams_and_accepts_input_before_finished(self):
        self.spec({'kind': 'command', 'command': [sys.executable, '-u', '-c',
            'print("ready",flush=True); print("received:"+input(),flush=True)']})
        with patch('completion_preview.has_starred', return_value=True):
            preview = CompletionPreview(self.root)
            self.addCleanup(preview.close)
            seen = []
            while not any('ready' in str(e) for e in seen):
                seen.append(preview.events.get(timeout=5))
            self.assertFalse(any(e[0] == 'done' for e in seen))
            preview.send('hello')
            seen += self.events(preview)
            self.assertTrue(any('received:hello' in str(e) for e in seen))
            self.assertEqual(seen[-1], ('done', True))

    def test_it_opens_the_port_the_server_announces_when_the_manifest_names_another(self):
        """noinit: launch.json said 4173, `npm run start` served 5173, and no browser ever opened."""
        import socket
        with socket.socket() as sock:
            sock.bind(('127.0.0.1', 0)); real = sock.getsockname()[1]
        with socket.socket() as sock:
            sock.bind(('127.0.0.1', 0)); wrong = sock.getsockname()[1]
        script = ('import http.server\n'
                  'print("Local:   http://127.0.0.1:%d/", flush=True)\n'
                  'http.server.HTTPServer(("127.0.0.1", %d), http.server.SimpleHTTPRequestHandler).serve_forever()\n') % (real, real)
        self.spec({'kind': 'webpage', 'command': [sys.executable, '-u', '-c', script], 'url': 'http://127.0.0.1:%d' % wrong})
        opened = []
        with patch('completion_preview.has_starred', return_value=True), \
                patch('completion_preview.webbrowser.open', side_effect=lambda url: opened.append(url) or True):
            preview = CompletionPreview(self.root)
            self.addCleanup(preview.close)
            events = self.events(preview)
        self.assertEqual(opened, ['http://127.0.0.1:%d' % real], events)
        self.assertFalse(any('did not become ready' in str(e) for e in events))

    def test_announced_ports_are_read_through_colour_codes_and_in_order(self):
        from completion_preview import announced_ports
        text = '  \x1b[32m➜\x1b[39m  Local:   \x1b[36mhttp://127.0.0.1:\x1b[1m5173\x1b[22m/\x1b[39m\n  Network: http://localhost:5174/\nhttp://example.com:80'
        self.assertEqual(announced_ports(text), [5173, 5174])
        self.assertEqual(announced_ports(''), [])
        self.assertEqual(announced_ports('http://[::1]:3000 and http://127.0.0.1:3000'), [3000])

    def test_static_page_opened_before_star_check(self):
        (self.root / 'index.html').write_text('<h1>App</h1>')
        order = []
        with patch('completion_preview.webbrowser.open', side_effect=lambda url: order.append(url) or True), patch('completion_preview.has_starred', side_effect=lambda: order.append('star') or True):
            self.events(CompletionPreview(self.root))
        self.assertEqual(order, [(self.root / 'index.html').resolve().as_uri(), 'star'])

    def test_server_readiness_precedes_browser(self):
        self.spec({'kind': 'webpage', 'command': [sys.executable, '-c', 'import time; time.sleep(30)'],
                   'url': 'http://127.0.0.1:8765'})
        order = []
        from unittest.mock import MagicMock
        response = MagicMock()
        with patch('completion_preview.urlopen', side_effect=lambda *a, **k: order.append('ready') or response), patch('completion_preview.webbrowser.open', side_effect=lambda url: order.append('browser') or True), patch('completion_preview.has_starred', return_value=True):
            preview = CompletionPreview(self.root)
            try:
                self.events(preview)
                self.assertEqual(order, ['ready', 'browser'])
                self.assertIsNone(preview.process.poll())
            finally:
                preview.close()
            self.assertIsNotNone(preview.process.poll())

    def test_readiness_falls_back_to_an_equivalent_loopback_host(self):
        # A real run: `.uncle/launch.json` declared `127.0.0.1`, but the
        # launch command (a vite-style preview server) bound its default
        # host `localhost`, which on that machine resolved to `::1` only.
        # `127.0.0.1` was refused forever even though the server was ready
        # the whole time under a name launch_spec already treats as
        # equivalent -- the readiness check and the final browser URL must
        # honor that too, not just the validator.
        self.spec({'kind': 'webpage', 'command': [sys.executable, '-c', 'import time; time.sleep(30)'],
                   'url': 'http://127.0.0.1:8765'})
        from unittest.mock import MagicMock
        response = MagicMock()

        def fake_urlopen(candidate, timeout=None):
            if candidate == 'http://localhost:8765':
                return response
            raise OSError('Connection refused')

        opened = []
        with patch('completion_preview.urlopen', side_effect=fake_urlopen), \
             patch('completion_preview.webbrowser.open', side_effect=lambda url: opened.append(url) or True), \
             patch('completion_preview.has_starred', return_value=True):
            preview = CompletionPreview(self.root)
            try:
                self.events(preview)
                self.assertEqual(opened, ['http://localhost:8765'],
                                  'must open the host that actually answered, not the one on record')
            finally:
                preview.close()

    def test_readiness_tries_the_bracketed_ipv6_form(self):
        self.spec({'kind': 'webpage', 'command': [sys.executable, '-c', 'import time; time.sleep(30)'],
                   'url': 'http://127.0.0.1:8765'})
        from unittest.mock import MagicMock
        response = MagicMock()

        def fake_urlopen(candidate, timeout=None):
            if candidate == 'http://[::1]:8765':
                return response
            raise OSError('Connection refused')

        opened = []
        with patch('completion_preview.urlopen', side_effect=fake_urlopen), \
             patch('completion_preview.webbrowser.open', side_effect=lambda url: opened.append(url) or True), \
             patch('completion_preview.has_starred', return_value=True):
            preview = CompletionPreview(self.root)
            try:
                self.events(preview)
                self.assertEqual(opened, ['http://[::1]:8765'])
            finally:
                preview.close()

    def test_invalid_manifest_does_not_launch(self):
        for spec in ({'kind':'command','command':'git commit'},  # rejected manifest, never run
                     {'kind':'webpage','url':'https://example.com'},
                     {'kind':'webpage','path':'../outside.html'}):
            self.spec(spec)
            with self.assertRaises(ValueError):
                launch_spec(self.root)

    def test_none_overrides_static_detection(self):
        (self.root / 'index.html').write_text('documentation')
        self.spec({'kind':'none'})
        self.assertEqual(launch_spec(self.root), {'kind':'none'})

    def test_star_check_read_only_bounded_and_unknown_is_false(self):
        with patch('completion_preview.subprocess.run') as run:
            run.return_value.returncode = 0
            self.assertTrue(has_starred())
            self.assertIn('GET', run.call_args.args[0])
            self.assertEqual(run.call_args.kwargs['timeout'], 5)
            run.return_value.returncode = 1
            self.assertFalse(has_starred())
            run.side_effect = subprocess.TimeoutExpired('gh', 5)
            self.assertFalse(has_starred())

    def test_browser_failure_is_visible_and_finishes(self):
        (self.root / 'index.html').write_text('app')
        with patch('completion_preview.webbrowser.open', return_value=False):
            events = self.events(CompletionPreview(self.root))
        self.assertIn('Could not open browser', str(events))
        self.assertEqual(events[-1][0], 'done')


if __name__ == '__main__':
    unittest.main()
