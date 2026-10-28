#!/usr/bin/env python3
"""Start the project's application for the checklist's browser checks, so its workers drive a page that is already running.

A checklist worker is not allowed to start a server (noinit: `npm run start` was denied and five browser checks came back
BLOCKED-SETUP after 86 s).  The driver can: it reads `.uncle/launch.json`, makes sure the project is installed and built, starts the
command on the port that file names, waits until it answers, and writes where it is.

    app_server.py start PROJECT STATE_DIR      prints the URL (empty and exit 1 when the application could not be started)
    app_server.py stop STATE_DIR               stops it
"""
import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path
from urllib.parse import urlparse
from urllib.request import urlopen

sys.path.insert(0, str(Path(__file__).resolve().parent))
import completion_preview as cp


def command_for(root, spec):
    """The launch command, on the launch URL's port, for the Vite-style script a plan usually names."""
    command = cp.existing_script(root, spec.get('command'))
    port = urlparse(spec.get('url') or '').port
    if not (isinstance(command, list) and command[:2] == ['npm', 'run'] and len(command) == 3 and port):
        return command
    try:
        script = (json.loads((Path(root) / 'package.json').read_text()).get('scripts') or {}).get(command[2], '')
    except (OSError, ValueError):
        return command
    if 'vite' in script:
        return command + ['--', '--host', '127.0.0.1', '--port', str(port), '--strictPort']
    return command


def answers(url):
    try:
        with urlopen(url, timeout=1):
            return True
    except OSError:
        return False


def start(project, state):
    project, state = Path(project), Path(state)
    spec = cp.launch_spec(project)
    command = command_for(project, spec)
    if spec.get('kind') != 'webpage' or not command or not spec.get('url'):
        return ''
    cp.prepare_project(project, command)
    log = state / 'app-server.log'
    process = subprocess.Popen(command, cwd=project, stdin=subprocess.DEVNULL, stdout=open(log, 'w'), stderr=subprocess.STDOUT,
                               start_new_session=True)
    (state / 'app-server.pid').write_text(str(process.pid))
    port = urlparse(spec['url']).port
    url = spec['url']
    deadline = time.monotonic() + 40
    while time.monotonic() < deadline:
        if process.poll() is not None:
            break
        seen = log.read_text(errors='replace') if log.exists() else ''
        for candidate in [url] + ['http://127.0.0.1:%d/' % p for p in cp.announced_ports(seen) if p != port]:
            if answers(candidate):
                (state / 'app-server.url').write_text(candidate)
                return candidate
        time.sleep(0.2)
    stop(state)
    return ''


def stop(state):
    state = Path(state)
    try:
        pid = int((state / 'app-server.pid').read_text())
        os.killpg(os.getpgid(pid), signal.SIGTERM)
    except (OSError, ValueError):
        pass
    for name in ('app-server.pid', 'app-server.url'):
        (state / name).unlink(missing_ok=True)


def main(argv):
    if argv[:1] == ['start'] and len(argv) == 3:
        url = start(argv[1], argv[2])
        print(url)
        return 0 if url else 1
    if argv[:1] == ['stop'] and len(argv) == 2:
        stop(argv[1])
        return 0
    raise SystemExit(__doc__)


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
