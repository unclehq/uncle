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
