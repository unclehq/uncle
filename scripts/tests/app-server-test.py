#!/usr/bin/env python3
"""The driver starts the application for the checklist's browser checks, on the launch URL's port, and stops it."""
import json
import socket
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from urllib.request import urlopen

LIB = Path(__file__).resolve().parents[1] / 'lib'
sys.path.insert(0, str(LIB))
import app_server


def free_port():
    with socket.socket() as s:
        s.bind(('127.0.0.1', 0))
        return s.getsockname()[1]


class AppServer(unittest.TestCase):
    def project(self, launch, scripts=None):
        root = Path(tempfile.mkdtemp())
        (root / '.uncle').mkdir()
        (root / '.uncle/launch.json').write_text(json.dumps(launch))
        (root / 'index.html').write_text('<h1>hello</h1>')
        if scripts is not None:
            (root / 'package.json').write_text(json.dumps({'scripts': scripts}))
        self.state = Path(tempfile.mkdtemp())
        return root

    def tearDown(self):
        if not hasattr(self, 'state'):
            return
        app_server.stop(self.state)

    def test_the_command_is_started_and_the_url_it_answers_on_is_returned_then_stopped(self):
        port = free_port()
        root = self.project({'kind': 'webpage', 'command': ['python3', '-m', 'http.server', str(port), '--bind', '127.0.0.1'],
                             'url': 'http://127.0.0.1:%d/' % port})
        url = app_server.start(root, self.state)
        self.assertEqual(url, 'http://127.0.0.1:%d/' % port)
        self.assertIn('hello', urlopen(url, timeout=2).read().decode())
        app_server.stop(self.state)
        with self.assertRaises(OSError):
            urlopen(url, timeout=1)

    def test_a_server_that_exits_gives_no_url(self):
        root = self.project({'kind': 'webpage', 'command': ['python3', '-c', 'raise SystemExit(1)'], 'url': 'http://127.0.0.1:%d/' % free_port()})
        self.assertEqual(app_server.start(root, self.state), '')

    def test_start_reuses_an_early_server_instead_of_binding_a_second_port(self):
        port = free_port()
        root = self.project({'kind': 'webpage', 'command': ['python3', '-m', 'http.server', str(port), '--bind', '127.0.0.1'],
                             'url': 'http://127.0.0.1:%d/' % port})
        first = app_server.start(root, self.state)
        pid = (self.state / 'app-server.pid').read_text()
        self.assertEqual(app_server.start(root, self.state), first)
        self.assertEqual((self.state / 'app-server.pid').read_text(), pid)

    def test_prewarm_refuses_to_install_or_build(self):
        port = free_port()
        root = self.project({'kind': 'webpage', 'command': ['npm', 'run', 'preview'],
                             'url': 'http://127.0.0.1:%d/' % port},
                            {'preview': 'vite preview', 'build': 'vite build'})
        self.assertEqual(app_server.start(root, self.state, prepare=False), '')

    def test_a_non_webpage_project_is_not_started(self):
        root = self.project({'kind': 'command', 'command': ['python3', '-c', 'print(1)']})
        self.assertEqual(app_server.start(root, self.state), '')

    def test_a_vite_script_gets_the_launch_urls_port_and_a_missing_script_becomes_one_that_exists(self):
        root = self.project({'kind': 'webpage', 'command': ['npm', 'run', 'start'], 'url': 'http://127.0.0.1:4173'},
                            {'dev': 'vite', 'build': 'vite build', 'preview': 'vite preview'})
        spec = json.loads((root / '.uncle/launch.json').read_text())
        self.assertEqual(app_server.command_for(root, spec),
                         ['npm', 'run', 'dev', '--', '--host', '127.0.0.1', '--port', '4173', '--strictPort'])
        spec['command'] = ['npm', 'run', 'dev']
        self.assertEqual(app_server.command_for(root, spec)[-1], '--strictPort')

    def test_the_driver_starts_it_for_the_workers_and_stops_it(self):
        text = (Path(__file__).resolve().parents[1] / 'stagegate.sh').read_text()
        block = text[text.index('run_parallel_checklist_workers() {'):]
        self.assertLess(block.index('app_server.py" start'), block.index('checklist_run_lanes'))
        self.assertIn('The application is already running', block)
        self.assertIn('app_server.py" prewarm', text)
        self.assertIn('Prewarm never', text)
        self.assertIn('app_server.py" stop', text[text.index('snapshot_checklist_groups > /dev/null'):])


if __name__ == '__main__':
    unittest.main()
