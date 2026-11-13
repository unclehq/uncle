import importlib.util
import json
import os
import signal
import socket
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[2]
LIB = ROOT / 'scripts/lib'
sys.path.insert(0, str(LIB))
HOST_PREVIEW = LIB / 'host_preview.py'
HOOK = LIB / 'host_preview_hook.sh'

STUB = ("import os,http.server;"
        "http.server.HTTPServer((os.environ.get('HOST','127.0.0.1'),int(os.environ['PORT'])),"
        "http.server.SimpleHTTPRequestHandler).serve_forever()")


def free_port():
    with socket.socket() as s:
        s.bind(('127.0.0.1', 0))
        return s.getsockname()[1]


def answers(url, wait=5):
    end = time.time() + wait
    while time.time() < end:
        try:
            with urlopen(url, timeout=1) as r:
                return r.read()
        except OSError:
            time.sleep(.1)
    return None


def kill_group(pid):
    try:
        os.killpg(os.getpgid(pid), signal.SIGKILL)
    except (OSError, ProcessLookupError):
        pass


def alive(pid):
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


class Base(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.project = Path(self._tmp.name).resolve() / 'proj'
        (self.project / '.uncle').mkdir(parents=True)
        self.addCleanup(self.reap)

    def reap(self):
        record = self.record()
        if record and isinstance(record.get('pid'), int):
            kill_group(record['pid'])

    def record(self):
        try:
            return json.loads((self.project / '.uncle/preview.json').read_text())
        except (OSError, ValueError):
            return None

    def launch(self, data):
        (self.project / '.uncle/launch.json').write_text(json.dumps(data))

    def command_launch(self, port=None):
        self.launch({'kind': 'command', 'command': [sys.executable, '-c', STUB],
                     'url': 'http://127.0.0.1:%d/' % (port or free_port())})

    def serve(self, **env):
        e = {k: v for k, v in os.environ.items() if not k.startswith('UNCLE_PREVIEW') and k != 'UNCLE_HOSTED'}
        e.update({'UNCLE_HOSTED': '1', 'UNCLE_PREVIEW_TIMEOUT': '8'})
        e.update(env)
        return subprocess.run([sys.executable, str(HOST_PREVIEW), 'serve', str(self.project)], env=e,
                              capture_output=True, text=True, timeout=60, stdin=subprocess.DEVNULL)

    def assert_one_port_line(self, result, port=None):
        lines = result.stdout.splitlines()
        self.assertEqual(len(lines), 1, result.stdout + result.stderr)
        self.assertRegex(lines[0], r'^UNCLE_PREVIEW_PORT=\d+$')
        if port is not None:
            self.assertEqual(lines[0], 'UNCLE_PREVIEW_PORT=%d' % port)
        return int(lines[0].split('=')[1])


class Serve(Base):
    def test_command_app_outlives_serve_and_records_state(self):  # AC-1, AC-2
        port = free_port()
        self.command_launch()
        r = self.serve(UNCLE_PREVIEW_PORT=str(port))
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assert_one_port_line(r, port)
        rec = self.record()
        self.assertEqual(rec['schema'], 'uncle.preview/v1')
        self.assertEqual(rec['status'], 'running')
        self.assertEqual((rec['kind'], rec['port'], rec['host']), ('command', port, '127.0.0.1'))
        self.assertEqual(rec['url'], 'http://127.0.0.1:%d/' % port)
        self.assertTrue(alive(rec['pid']))
        self.assertIsNotNone(answers(rec['url']))

    def test_detached_survives_process_group_kill_of_serve(self):  # AC-1 detachment
        port = free_port()
        self.command_launch()
        env = dict(os.environ, UNCLE_HOSTED='1', UNCLE_PREVIEW_PORT=str(port), UNCLE_PREVIEW_TIMEOUT='8')
        p = subprocess.Popen([sys.executable, str(HOST_PREVIEW), 'serve', str(self.project)], env=env,
                             stdout=subprocess.PIPE, stderr=subprocess.PIPE, start_new_session=True)
        p.communicate(timeout=60)
        try:
            os.killpg(p.pid, signal.SIGKILL)
        except OSError:
            pass
        self.assertIsNotNone(answers('http://127.0.0.1:%d/' % port))

    def test_port_from_launch_url_when_env_unset(self):  # AC-1
        port = free_port()
        self.command_launch(port)
        r = self.serve()
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assert_one_port_line(r, port)
        self.assertEqual(self.record()['port'], port)

    def test_env_port_overrides_launch_url_port(self):  # D-7
        url_port, env_port = free_port(), free_port()
        self.command_launch(url_port)
        r = self.serve(UNCLE_PREVIEW_PORT=str(env_port))
        self.assert_one_port_line(r, env_port)

    def test_static_webpage_served(self):  # AC-3
        (self.project / 'site').mkdir()
        (self.project / 'site/index.html').write_text('<h1>hello-static</h1>')
        port = free_port()
        self.launch({'kind': 'webpage', 'path': 'site/index.html'})
        r = self.serve(UNCLE_PREVIEW_PORT=str(port))
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assert_one_port_line(r, port)
        self.assertIn(b'hello-static', answers('http://127.0.0.1:%d/' % port))

    def test_static_root_never_serves_uncle_or_git(self):  # AC-3
        (self.project / 'index.html').write_text('<h1>root-page</h1>')
        (self.project / '.git').mkdir()
        (self.project / '.git/config').write_text('SECRET-GIT')
        (self.project / '.uncle/secret.txt').write_text('SECRET-UNCLE')
        port = free_port()
        self.launch({'kind': 'webpage', 'path': 'index.html'})
        r = self.serve(UNCLE_PREVIEW_PORT=str(port))
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn(b'root-page', answers('http://127.0.0.1:%d/' % port))
        for path in ('.git/config', '.uncle/secret.txt', '.uncle/launch.json'):
            try:
                with urlopen('http://127.0.0.1:%d/%s' % (port, path), timeout=2) as resp:
                    body = resp.read()
            except OSError:
                continue
            self.assertNotIn(b'SECRET', body)
            self.assertNotIn(b'"kind"', body)

    def test_static_symlink_escape_is_failed(self):  # AC-3
        outside = Path(self._tmp.name) / 'outside'
        outside.mkdir()
        (outside / 'index.html').write_text('outside')
        (self.project / 'link').symlink_to(outside)
        self.launch({'kind': 'webpage', 'path': 'link/index.html'})
        r = self.serve(UNCLE_PREVIEW_PORT=str(free_port()))
        self.assertEqual(r.returncode, 0)
        self.assertEqual(r.stdout.strip(), '')
        self.assertEqual(self.record()['status'], 'failed')

    def test_static_dotdot_path_is_failed(self):  # AC-3
        (Path(self._tmp.name) / 'index.html').write_text('outside')
        self.launch({'kind': 'webpage', 'path': '../index.html'})
        r = self.serve(UNCLE_PREVIEW_PORT=str(free_port()))
        self.assertEqual(r.returncode, 0)
        self.assertEqual(self.record()['status'], 'failed')


class Address(Base):
    def test_default_bind_is_loopback(self):  # AC-4
        self.command_launch()
        port = free_port()
        r = self.serve(UNCLE_PREVIEW_PORT=str(port))
        self.assert_one_port_line(r, port)
        self.assertEqual(self.record()['host'], '127.0.0.1')
        self.assertIsNotNone(answers('http://127.0.0.1:%d/' % port))

    def test_wildcard_host_records_loopback_url(self):  # AC-4
        self.command_launch()
        port = free_port()
        r = self.serve(UNCLE_PREVIEW_PORT=str(port), UNCLE_PREVIEW_HOST='0.0.0.0')
        self.assertEqual(r.returncode, 0, r.stderr)
        rec = self.record()
        self.assertEqual(rec['status'], 'running')
        self.assertEqual(rec['host'], '0.0.0.0')
        self.assertEqual(rec['url'], 'http://127.0.0.1:%d/' % port)
        loopback_body = answers(rec['url'])
        self.assertIsNotNone(loopback_body)
        addr = self.non_loopback_ipv4()
        if addr is None:
            print('SKIP: no non-loopback IPv4 address; wildcard reachability not verified')
            return
        body = answers('http://%s:%d/' % (addr, port), wait=5)
        self.assertIsNotNone(body, 'wildcard-bound server did not answer on %s' % addr)
        self.assertEqual(body, loopback_body)

    @staticmethod
    def non_loopback_ipv4():
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
                s.connect(('192.0.2.1', 9))
                addr = s.getsockname()[0]
        except OSError:
            return None
        return None if addr.startswith('127.') or addr == '0.0.0.0' else addr

    def test_invalid_hosts_fail_without_spawning(self):  # AC-4
        self.command_launch()
        for bad in ('example.com', '-x', 'a b', '127.0.0.1;ls', '$(id)', '::', '::1', '[::1]', '0.0.0.0 '):
            with self.subTest(host=bad):
                (self.project / '.uncle/preview.json').unlink(missing_ok=True)
                r = self.serve(UNCLE_PREVIEW_PORT=str(free_port()), UNCLE_PREVIEW_HOST=bad)
                self.assertEqual(r.returncode, 0)
                self.assertEqual(r.stdout.strip(), '')
                rec = self.record()
                self.assertEqual(rec['status'], 'failed')
                self.assertTrue(rec['reason'])
                self.assertFalse(rec.get('pid'))


class Failure(Base):
    def check_failed(self, r, status='failed'):
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertNotIn('UNCLE_PREVIEW_PORT', r.stdout)
        rec = self.record()
        self.assertEqual(rec['status'], status)
        self.assertTrue(rec['reason'])
        return rec

    def test_command_exits_early(self):  # AC-5
        self.launch({'kind': 'command', 'command': [sys.executable, '-c', 'raise SystemExit(3)'],
                     'url': 'http://127.0.0.1:%d/' % free_port()})
        self.check_failed(self.serve(UNCLE_PREVIEW_PORT=str(free_port())))

    def test_never_answers_leaves_no_child(self):  # AC-5
        marker = Path(self._tmp.name) / 'pid'
        code = "import os,time;open(%r,'w').write(str(os.getpid()));time.sleep(120)" % str(marker)
        self.launch({'kind': 'command', 'command': [sys.executable, '-c', code],
                     'url': 'http://127.0.0.1:%d/' % free_port()})
        self.check_failed(self.serve(UNCLE_PREVIEW_PORT=str(free_port()), UNCLE_PREVIEW_TIMEOUT='2'))
        pid = int(marker.read_text())
        end = time.time() + 5
        while alive(pid) and time.time() < end:
            try:
                os.waitpid(pid, os.WNOHANG)
            except OSError:
                pass
            time.sleep(.1)
        self.assertFalse(alive(pid))

    def test_kind_none_is_none_status(self):  # AC-5
        self.launch({'kind': 'none'})
        self.check_failed(self.serve(), 'none')

    def test_missing_launch_json_is_failed(self):  # AC-5
        self.check_failed(self.serve())

    def test_invalid_ports_fail(self):  # AC-5
        self.command_launch()
        for bad in ('0', '80', '1023', '65536', '-1', '+5000', ' 5000', '50 00', 'abc', '5000.0'):
            with self.subTest(port=bad):
                self.check_failed(self.serve(UNCLE_PREVIEW_PORT=bad))

    def test_invalid_launch_url_port_is_failed_not_fallback(self):  # D-7
        self.launch({'kind': 'command', 'command': [sys.executable, '-c', STUB], 'url': 'http://127.0.0.1:80/'})
        self.check_failed(self.serve())

    def test_non_loopback_launch_url_is_failed(self):  # D-7
        self.launch({'kind': 'command', 'command': [sys.executable, '-c', STUB],
                     'url': 'http://example.com:%d/' % free_port()})
        self.check_failed(self.serve(UNCLE_PREVIEW_PORT=str(free_port())))

    def test_foreign_server_on_port_not_adopted(self):  # D-6
        foreign = subprocess.Popen([sys.executable, '-m', 'http.server', '0', '--bind', '127.0.0.1'],
                                   stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True)
        self.addCleanup(foreign.kill)
        # find its port without parsing buffered output
        time.sleep(1)
        out = subprocess.run(['lsof', '-a', '-p', str(foreign.pid), '-iTCP', '-sTCP:LISTEN', '-Fn'],
                             capture_output=True, text=True).stdout
        ports = [int(l.rsplit(':', 1)[1]) for l in out.splitlines() if l.startswith('n') and ':' in l]
        if not ports:
            self.skipTest('lsof unavailable')
        self.launch({'kind': 'command', 'command': [sys.executable, '-c', 'raise SystemExit(1)'],
                     'url': 'http://127.0.0.1:%d/' % ports[0]})
        self.check_failed(self.serve(UNCLE_PREVIEW_PORT=str(ports[0])))
        self.assertIsNone(foreign.poll())


class Reuse(Base):
    def test_second_run_reuses_live_server(self):  # AC-6
        port = free_port()
        self.command_launch()
        r1 = self.serve(UNCLE_PREVIEW_PORT=str(port))
        pid1 = self.record()['pid']
        r2 = self.serve(UNCLE_PREVIEW_PORT=str(port))
        self.assertEqual(r2.returncode, 0, r2.stderr)
        self.assertEqual(r1.stdout, r2.stdout)
        self.assert_one_port_line(r2, port)
        self.assertEqual(self.record()['pid'], pid1)
        self.assertTrue(alive(pid1))

    def test_different_port_starts_new_server(self):  # D-8
        p1, p2 = free_port(), free_port()
        self.command_launch()
        self.serve(UNCLE_PREVIEW_PORT=str(p1))
        first = self.record()['pid']
        r = self.serve(UNCLE_PREVIEW_PORT=str(p2))
        self.assert_one_port_line(r, p2)
        self.assertNotEqual(self.record()['pid'], first)
        kill_group(first)

    def test_stale_record_is_overwritten(self):  # AC-6
        port = free_port()
        self.command_launch()
        (self.project / '.uncle/preview.json').write_text(json.dumps({
            'schema': 'uncle.preview/v1', 'status': 'running', 'kind': 'command', 'host': '127.0.0.1',
            'port': port, 'url': 'http://127.0.0.1:%d/' % port, 'pid': 2 ** 22 + 12345,
            'pid_start': 'x', 'pid_cmd': 'x', 'reason': ''}))
        r = self.serve(UNCLE_PREVIEW_PORT=str(port))
        self.assert_one_port_line(r, port)
        rec = self.record()
        self.assertNotEqual(rec['pid'], 2 ** 22 + 12345)
        self.assertTrue(alive(rec['pid']))

    def test_default_mode_never_touches_preview_json(self):  # AC-6 / INV-3
        marker = '{"left":"by earlier host run"}'
        (self.project / '.uncle/preview.json').write_text(marker)
        self.command_launch()
        for mode in (None, '', 'true', '0'):
            e = {k: v for k, v in os.environ.items() if not k.startswith('UNCLE_PREVIEW') and k != 'UNCLE_HOSTED'}
            if mode is not None:
                e['UNCLE_HOSTED'] = mode
            subprocess.run([sys.executable, str(HOST_PREVIEW), 'mode-check'], env=e, capture_output=True)
            self.assertEqual((self.project / '.uncle/preview.json').read_text(), marker)


class NoSecrets(Base):
    def test_parent_secret_absent_from_child_env_record_and_log(self):
        port = free_port()
        dump = Path(self._tmp.name) / 'env.txt'
        code = ("import os,http.server;open(%r,'w').write(repr(sorted(os.environ)));"
                "http.server.HTTPServer(('127.0.0.1',int(os.environ['PORT'])),"
                "http.server.SimpleHTTPRequestHandler).serve_forever()") % str(dump)
        self.launch({'kind': 'command', 'command': [sys.executable, '-c', code],
                     'url': 'http://127.0.0.1:%d/' % port})
        r = self.serve(UNCLE_PREVIEW_PORT=str(port), SENTINEL_SECRET_TOKEN='s3cr3t-value-xyz', HOST='parent-host')
        self.assertEqual(r.returncode, 0, r.stderr)
        answers('http://127.0.0.1:%d/' % port)
        names = dump.read_text()
        self.assertNotIn('SENTINEL_SECRET_TOKEN', names)
        blob = (self.project / '.uncle/preview.json').read_text() + r.stderr
        log = self.project / '.uncle/preview.log'
        if log.exists():
            blob += log.read_text()
        self.assertNotIn('s3cr3t-value-xyz', blob)

    def test_child_host_and_port_override_inherited(self):  # D-4
        port = free_port()
        dump = Path(self._tmp.name) / 'hp.txt'
        code = ("import os,http.server;open(%r,'w').write(os.environ['HOST']+' '+os.environ['PORT']);"
                "http.server.HTTPServer(('127.0.0.1',int(os.environ['PORT'])),"
                "http.server.SimpleHTTPRequestHandler).serve_forever()") % str(dump)
        self.launch({'kind': 'command', 'command': [sys.executable, '-c', code],
                     'url': 'http://127.0.0.1:%d/' % port})
        self.serve(UNCLE_PREVIEW_PORT=str(port), HOST='wrong', PORT='1')
        self.assertEqual(dump.read_text(), '127.0.0.1 %d' % port)


class ModeHelper(unittest.TestCase):
    def mode(self, value):
        e = {k: v for k, v in os.environ.items() if k != 'UNCLE_HOSTED'}
        if value is not None:
            e['UNCLE_HOSTED'] = value
        return subprocess.run([sys.executable, str(HOST_PREVIEW), 'mode-check'], env=e,
                              capture_output=True).returncode

    def test_only_exact_1_is_host_mode(self):  # D-1
        self.assertEqual(self.mode('1'), 0)
        for v in (None, '', 'host', 'true', ' 1', '1 ', 'false', '0'):
            with self.subTest(value=v):
                self.assertEqual(self.mode(v), 1)

    def test_is_host_mode_function(self):
        import host_preview
        self.assertTrue(host_preview.is_host_mode({'UNCLE_HOSTED': '1'}))
        for v in ('', 'host', ' 1', 'false'):
            self.assertFalse(host_preview.is_host_mode({'UNCLE_HOSTED': v}))
        self.assertFalse(host_preview.is_host_mode({}))


class CompletionPreviewHostMode(unittest.TestCase):
    def test_host_mode_never_opens_browser(self):  # AC-7
        import completion_preview as cp
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root / '.uncle').mkdir()
            (root / '.uncle/launch.json').write_text(json.dumps({'kind': 'none'}))
            with mock.patch.dict(os.environ, {'UNCLE_HOSTED': '1'}), \
                    mock.patch.object(cp.webbrowser, 'open', side_effect=AssertionError('browser opened')) as opener, \
                    mock.patch('sys.stdout') as out:
                try:
                    cp.CompletionPreview(root).run()
                except AssertionError:
                    raise
                except Exception:
                    pass
            opener.assert_not_called()
            written = ''.join(str(c.args[0]) for c in out.write.call_args_list if c.args)
            self.assertNotIn('Could not open browser', written)


class Hook(unittest.TestCase):
    def run_hook(self, project, mode, extra=''):
        env = {k: v for k, v in os.environ.items() if not k.startswith('UNCLE_PREVIEW') and k != 'UNCLE_HOSTED'}
        env['ROOT'] = str(ROOT)
        if mode is not None:
            env['UNCLE_HOSTED'] = mode
        script = 'source %s; uncle_host_preview_hook %s %s; echo "rc=$?"' % (HOOK, project, extra)
        return subprocess.run(['bash', '-c', script], env=env, capture_output=True, text=True, timeout=60,
                              cwd=project)

    def test_hook_returns_zero_even_when_preview_fails(self):  # AC-9
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / '.uncle').mkdir()
            r = self.run_hook(d, '1')
            self.assertIn('rc=0', r.stdout, r.stdout + r.stderr)
            rec = json.loads((Path(d) / '.uncle/preview.json').read_text())
            self.assertEqual(rec['status'], 'failed')

    def test_hook_does_nothing_unless_exactly_host(self):  # AC-8
        for mode in (None, '', 'HOST', 'false', ' host'):
            with self.subTest(mode=mode), tempfile.TemporaryDirectory() as d:
                (Path(d) / '.uncle').mkdir()
                r = self.run_hook(d, mode)
                self.assertEqual(r.stdout.strip(), 'rc=0', r.stderr)
                self.assertFalse((Path(d) / '.uncle/preview.json').exists())
                self.assertFalse((Path(d) / '.uncle/preview.log').exists())

    def test_drivers_use_only_the_shared_hook(self):  # AC-9
        for name in ('stagegate.sh', 'change-workflow.sh'):
            with self.subTest(driver=name):
                text = (ROOT / 'scripts' / name).read_text()
                self.assertIn('host_preview_hook.sh', text)
                self.assertIn('uncle_host_preview_hook', text)
                self.assertNotIn('UNCLE_HOSTED', text)


class CommandForParity(unittest.TestCase):
    """Golden values captured from the pre-change app_server.command_for (host/port omitted)."""

    def setUp(self):
        import app_server
        self.module = app_server
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)

    def pkg(self, scripts):
        (self.root / 'package.json').write_text(json.dumps({'scripts': scripts}))

    def test_vite_script_with_url_port(self):
        self.pkg({'dev': 'vite'})
        spec = {'kind': 'command', 'command': ['npm', 'run', 'dev'], 'url': 'http://127.0.0.1:5173/'}
        self.assertEqual(self.module.command_for(self.root, spec),
                         ['npm', 'run', 'dev', '--', '--host', '127.0.0.1', '--port', '5173', '--strictPort'])

    def test_non_vite_npm_script_unchanged(self):
        self.pkg({'start': 'node server.js'})
        spec = {'kind': 'command', 'command': ['npm', 'run', 'start'], 'url': 'http://127.0.0.1:3000/'}
        self.assertEqual(self.module.command_for(self.root, spec), ['npm', 'run', 'start'])

    def test_vite_without_url_port_unchanged(self):
        self.pkg({'dev': 'vite'})
        spec = {'kind': 'command', 'command': ['npm', 'run', 'dev'], 'url': 'http://127.0.0.1/'}
        self.assertEqual(self.module.command_for(self.root, spec), ['npm', 'run', 'dev'])

    def test_non_npm_command_unchanged(self):
        spec = {'kind': 'command', 'command': ['python3', 'app.py', '--x'], 'url': 'http://127.0.0.1:8000/'}
        self.assertEqual(self.module.command_for(self.root, spec), ['python3', 'app.py', '--x'])

    def test_missing_script_falls_back_like_before(self):
        self.pkg({'dev': 'vite', 'build': 'vite build'})
        spec = {'kind': 'command', 'command': ['npm', 'run', 'start'], 'url': 'http://127.0.0.1:4173/'}
        self.assertEqual(self.module.command_for(self.root, spec),
                         ['npm', 'run', 'dev', '--', '--host', '127.0.0.1', '--port', '4173', '--strictPort'])

    def test_no_package_json_unchanged(self):
        spec = {'kind': 'command', 'command': ['npm', 'run', 'dev'], 'url': 'http://127.0.0.1:5173/'}
        self.assertEqual(self.module.command_for(self.root, spec), ['npm', 'run', 'dev'])

    def test_host_and_port_params_are_optional(self):
        import inspect
        params = inspect.signature(self.module.command_for).parameters
        for name in ('host', 'port'):
            self.assertIn(name, params)
            self.assertIsNot(params[name].default, inspect.Parameter.empty)


class LiveViteOnHostPort(Base):
    """In hosted mode the live preview binds the host's one port: Vite takes it over from the placeholder, preview.json stays running."""
    FAKE_VITE = ("#!/usr/bin/env python3\nimport sys,http.server\na=sys.argv\n"
                 "class H(http.server.BaseHTTPRequestHandler):\n"
                 "    def do_GET(s):\n        s.send_response(200); s.end_headers(); s.wfile.write(b'VITE')\n"
                 "    def log_message(*x): pass\n"
                 "http.server.HTTPServer((a[a.index('--host')+1],int(a[a.index('--port')+1])),H).serve_forever()\n")

    def project_with_vite(self, vite_source):
        p = self.project
        (p / 'node_modules/.bin').mkdir(parents=True)
        for name in ('react', 'react-dom'):
            (p / 'node_modules' / name).mkdir()
            (p / 'node_modules' / name / 'package.json').write_text('{}')
        (p / 'package.json').write_text(json.dumps({'scripts': {'start': 'vite'},
                                                    'dependencies': {'react': '1', 'react-dom': '1', 'vite': '1'}}))
        vite = p / 'node_modules/.bin/vite'
        vite.write_text(vite_source)
        vite.chmod(0o755)
        self.state = Path(self._tmp.name) / 'state'
        (self.state / 'preview').mkdir(parents=True)
        (self.state / 'preview/static-index.html').write_text('STATIC')
        (p / 'index.html').write_text('STATIC')

    def start(self, port):
        e = dict(os.environ, UNCLE_HOSTED='1', UNCLE_PREVIEW_HOST='127.0.0.1', UNCLE_PREVIEW_PORT=str(port))
        proc = subprocess.Popen([sys.executable, '-B', str(LIB / 'preview_server.py'), 'start', str(self.project), str(self.state)],
                                env=e, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, stdin=subprocess.DEVNULL)
        self.addCleanup(lambda: (proc.terminate(), proc.wait(10)))
        return proc

    def test_vite_serves_on_the_host_port_and_the_record_stays_running(self):
        port = free_port()
        self.project_with_vite(self.FAKE_VITE)
        self.start(port)
        end = time.time() + 15
        body = None
        while time.time() < end and body != b'VITE':
            body = answers('http://127.0.0.1:%d/' % port, 1)
        self.assertEqual(body, b'VITE')
        rec = self.record()
        self.assertEqual((rec['status'], rec['port']), ('running', port))

    def test_a_vite_that_dies_leaves_the_static_page_on_the_port(self):
        port = free_port()
        self.project_with_vite('#!/bin/sh\nexit 1\n')
        self.start(port)
        time.sleep(3)
        body = answers('http://127.0.0.1:%d/' % port, 5)
        self.assertIn(b'STATIC', body or b'')
        self.assertEqual(self.record()['status'], 'running')


if __name__ == '__main__':
    unittest.main()
