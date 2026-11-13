#!/usr/bin/env python3
"""Start the project's application detached, for a host that supplies the browser (UNCLE_HOSTED=1).

    host_preview.py serve PROJECT    starts (or reuses) the app, writes .uncle/preview.json, prints UNCLE_PREVIEW_PORT=<n>
    host_preview.py mode-check       exit 0 when UNCLE_HOSTED is exactly `1`, else 1

serve always exits 0: a failure is a `failed` record, never a build failure.  Stdout carries only the single port line.
"""
import ipaddress
import json
import os
import re
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from urllib.parse import urlparse
from urllib.request import urlopen

sys.path.insert(0, str(Path(__file__).resolve().parent))
import completion_preview as cp
import app_server
from process_tree import group_options

SCHEMA = 'uncle.preview/v1'
LOOPBACK = ('127.0.0.1', 'localhost', '::1')
_ENV_KEEP = ('PATH', 'HOME', 'USER', 'LOGNAME', 'SHELL', 'LANG', 'TERM', 'TMPDIR', 'TZ', 'SYSTEMROOT', 'PYTHONPATH')


def is_host_mode(env=None):
    """The one place the mode is decided: hosted mode (UNCLE_HOSTED exactly 1)."""
    return (os.environ if env is None else env).get('UNCLE_HOSTED') == '1'


class Failed(Exception):
    pass


def valid_port(text):
    if not re.fullmatch('[0-9]+', text or ''):
        return None
    value = int(text)
    return value if 1024 <= value <= 65535 else None


def valid_host(text):
    if text == 'localhost':
        return text
    try:
        if isinstance(ipaddress.ip_address(text), ipaddress.IPv4Address):
            return text
    except ValueError:
        pass
    return None


def urls_for(host, port):
    shown = '127.0.0.1' if host in ('0.0.0.0', '127.0.0.1') else host
    return shown, 'http://%s:%d/' % (shown, port)


def write_record(project, **fields):
    record = {'schema': SCHEMA, 'status': 'failed', 'kind': None, 'host': None, 'port': None, 'url': None,
              'pid': None, 'pid_start': None, 'pid_cmd': None, 'reason': None}
    record.update(fields)
    directory = Path(project) / '.uncle'
    directory.mkdir(parents=True, exist_ok=True)
    temporary = directory / ('preview.json.%d.tmp' % os.getpid())
    temporary.write_text(json.dumps(record, indent=2) + '\n')
    os.replace(temporary, directory / 'preview.json')


def process_identity(pid):
    def ps(field):
        try:
            return subprocess.run(['ps', '-o', field + '=', '-p', str(pid)], capture_output=True, text=True,
                                  timeout=5).stdout.strip()
        except (OSError, subprocess.SubprocessError):
            return ''
    return ps('lstart'), ps('command')


def alive(pid):
    try:
        os.kill(pid, 0)
        return True
    except (OSError, TypeError):
        return False


def kill_group(pgid):
    for sig, wait in ((signal.SIGTERM, 2.0), (signal.SIGKILL, 1.0)):
        try:
            os.killpg(pgid, sig)
        except (OSError, TypeError):
            return
        deadline = time.monotonic() + wait
        while time.monotonic() < deadline:
            try:
                os.killpg(pgid, 0)
            except OSError:
                return
            time.sleep(0.05)


def answers(url):
    try:
        with urlopen(url, timeout=1):
            return True
    except OSError:
        return False


def port_in_use(host, port):
    probe = '127.0.0.1' if host == '0.0.0.0' else host
    try:
        with socket.create_connection((probe, port), timeout=1):
            return True
    except OSError:
        return False


def wait_port_free(host, port, seconds=5.0):
    """Give a server that was just told to stop (the live preview) time to release the port."""
    deadline = time.monotonic() + seconds
    while port_in_use(host, port) and time.monotonic() < deadline:
        time.sleep(0.1)


def free_port(host):
    with socket.socket() as s:
        s.bind(('127.0.0.1' if host == 'localhost' else host, 0))
        return s.getsockname()[1]


def child_env(host, port):
    env = {k: v for k, v in os.environ.items() if k in _ENV_KEEP or k.startswith('LC_')}
    env['PYTHONUNBUFFERED'] = '1'
    env['HOST'] = host
    env['PORT'] = str(port)
    return env


def reuse(project, requested):
    """The running port of an existing, verified record, else None (stale records are terminated)."""
    try:
        record = json.loads((Path(project) / '.uncle' / 'preview.json').read_text())
        if not isinstance(record, dict) or record.get('status') != 'running':
            return None
        pid, port, url = record.get('pid'), record.get('port'), record.get('url') or ''
    except (OSError, ValueError):
        return None
    if not isinstance(pid, int) or isinstance(pid, bool) or pid <= 1 or not alive(pid):
        return None
    start, cmd = process_identity(pid)
    identity = bool(record.get('pid_start')) and (start, cmd) == (record.get('pid_start'), record.get('pid_cmd'))
    if not identity:
        return None
    loopback = urlparse(url).hostname in LOOPBACK
    if loopback and isinstance(port, int) and urlparse(url).port == port and answers(url) and requested in (None, port):
        return port
    try:
        kill_group(os.getpgid(pid))
    except OSError:
        pass
    return None


def static_root(project, spec):
    root = Path(project).resolve()
    directory = (root / spec['path']).resolve().parent
    if not directory.is_relative_to(root):
        raise Failed('static root outside project')
    if directory == root or (directory / '.uncle').exists() or (directory / '.git').exists():
        staging = Path(tempfile.mkdtemp(prefix='uncle-preview-'))
        skip = shutil.ignore_patterns('.uncle', '.git', 'node_modules')

        def ignore(src, names):
            return set(skip(src, names)) | {n for n in names if (Path(src) / n).is_symlink()}
        shutil.copytree(directory, staging, ignore=ignore, dirs_exist_ok=True)
        return staging
    return directory


def build_command(project, spec, host, port):
    """(argv, staging dir or None)."""
    if spec.get('kind') == 'webpage' and spec.get('path'):
        directory = static_root(project, spec)
        staged = directory if str(directory).startswith(tempfile.gettempdir()) or directory.name.startswith('uncle-preview-') else None
        return [sys.executable, '-m', 'http.server', str(port), '--bind', host, '--directory', str(directory)], staged
    command = app_server.command_for(project, spec, host, port)
    if not isinstance(command, list) or not command:
        raise Failed('no launch command')
    cp.prepare_project(project, command)
    return command, None


def serve(project, env=None):
    """Returns the port of a running preview, else None.  Always leaves a record in .uncle/preview.json."""
    env = os.environ if env is None else env
    project = Path(project)
    kind = None
    child = None
    staged = None
    try:
        try:
            if (Path(project) / '.uncle' / 'launch.json').is_file():
                spec = cp.launch_spec(project)
            else:
                # No launch.json (a self-hosted agent cannot write one, and a change plan never assigns it): work the spec out
                # from the project itself, as the repair of an invalid file does. Used in memory only; nothing is written into
                # the audited tree. A project with no dev or start script derives `none`, which is a skipped preview, not a failure.
                spec = cp.validate_launch_spec(project, dict(cp.derive_launch_manifest(project)))
        except (OSError, ValueError, TypeError) as error:
            raise Failed('launch.json missing or invalid')
        kind = spec.get('kind')
        host_text = env.get('UNCLE_PREVIEW_HOST') or '127.0.0.1'
        host = valid_host(host_text)
        if host is None:
            raise Failed('invalid host')
        if kind == 'none':
            write_record(project, status='none', kind='none', reason='launch kind none')
            return None
        requested = None
        if env.get('UNCLE_PREVIEW_PORT'):
            requested = valid_port(env['UNCLE_PREVIEW_PORT'])
            if requested is None:
                raise Failed('invalid port')
        port = requested
        if kind == 'webpage' and spec.get('url') and not spec.get('path') or (kind == 'command' and spec.get('url')):
            parsed = urlparse(spec['url'])
            if parsed.hostname not in LOOPBACK:
                raise Failed('launch url is not loopback')
            if requested is None and parsed.port is not None:
                port = valid_port(str(parsed.port))
                if port is None:
                    raise Failed('invalid launch url port')
        reused = reuse(project, port)
        if reused:
            return reused
        if port is None:
            port = free_port(host)
        else:
            wait_port_free(host, port)
            if port_in_use(host, port):
                raise Failed('port already in use')
        command, staged = build_command(project, spec, host, port)
        log = project / '.uncle' / 'preview.log'
        log.parent.mkdir(parents=True, exist_ok=True)
        with open(log, 'wb') as out:
            child = subprocess.Popen(command, cwd=project, stdin=subprocess.DEVNULL, stdout=out, stderr=out,
                                     env=child_env(host, port), **group_options())
        shown, url = urls_for(host, port)
        timeout = float(env.get('UNCLE_PREVIEW_TIMEOUT') or 30)
        deadline = time.monotonic() + timeout
        ready = False
        while time.monotonic() < deadline:
            if child.poll() is not None:
                raise Failed('application exited before it answered')
            if answers(url) and child.poll() is None:
                ready = True
                break
            time.sleep(0.2)
        if not ready:
            raise Failed('application did not answer in time')
        start, cmd = process_identity(child.pid)
        write_record(project, status='running', kind=kind, host=host, port=port, url=url, pid=child.pid,
                     pid_start=start, pid_cmd=cmd, reason=None)
        return port
    except Failed as error:
        reason = str(error)
    except Exception as error:
        reason = 'unexpected %s' % type(error).__name__
    if child is not None:
        kill_group(child.pid)
        try:
            child.wait(timeout=1)
        except Exception:
            pass
    if staged is not None:
        shutil.rmtree(staged, ignore_errors=True)
    try:
        write_record(project, status='failed', kind=kind, reason=reason)
    except OSError:
        pass
    print('Application preview: failed (%s)' % reason, file=sys.stderr)
    return None


def main(argv):
    if argv[:1] == ['mode-check']:
        return 0 if is_host_mode() else 1
    if argv[:1] == ['serve'] and len(argv) == 2:
        try:
            port = serve(argv[1])
        except Exception:
            port = None
        if port:
            print('UNCLE_PREVIEW_PORT=%d' % port)
            sys.stdout.flush()
        return 0
    raise SystemExit(__doc__)


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
