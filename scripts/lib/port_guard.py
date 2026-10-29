"""Free the ports a verification run is about to bind, or say who holds them.

A plan whose browser tests start their own server (Playwright `webServer` with
reuseExistingServer false) fails at once with "already used" when anything is
listening on that port.  noinit lost three runs to this: a stray http.server, a
worker's leftover vite, and a dev server nobody could identify later.  The
failure read as a test failure, and a repair stage tried to fix code that was
fine.

Ports are read from the verification commands and the project's own server
config.  A listener whose working directory or command line is inside the
project, or inside a temp directory (a worker's disposable copy), is a leftover of
this project's own run and is stopped.  Any other
listener is never touched; it is named so the failure that follows is explained.

A background verification run executes from an isolated copy of the
project (its port is deliberately different from the live checkout's), so
PROJECT_ROOT here is that copy, not the project the operator actually
works in. A leftover server still running from that original checkout --
an earlier attended run, a hung webServer process, an operator's own `npm
run dev` -- has a cwd under the original root, not the copy, and used to
read as "not part of this project" for that reason alone even though it
plainly is. ORIGINAL_ROOT lets a caller name that second, equally valid
identity for the same project.

usage: port_guard.py COMMANDS_FILE PROJECT_ROOT [ORIGINAL_ROOT]
"""
import os
import re
import signal
import subprocess
import sys
import time
from pathlib import Path

CONFIGS = ('playwright.config.js', 'playwright.config.ts', 'playwright.config.mjs',
           'playwright.config.cjs', 'vite.config.js', 'vite.config.ts', 'vite.config.mjs',
           'package.json')
PATTERNS = (
    re.compile(r'(?:127\.0\.0\.1|localhost|0\.0\.0\.0|\[::1?\]):(\d{2,5})\b'),
    re.compile(r'--port[ =](\d{2,5})\b'),
    re.compile(r'\bport\s*:\s*(\d{2,5})\b'),
)


def declared_ports(commands, root):
    texts = []
    try:
        texts.append(Path(commands).read_text(encoding='utf-8', errors='replace'))
    except OSError:
        pass
    for name in CONFIGS:
        try:
            texts.append((Path(root) / name).read_text(encoding='utf-8', errors='replace'))
        except OSError:
            pass
    ports = set()
    for text in texts:
        for pattern in PATTERNS:
            ports.update(int(m) for m in pattern.findall(text) if 0 < int(m) < 65536)
    return sorted(ports)


def run(*argv):
    try:
        return subprocess.run(argv, capture_output=True, text=True, timeout=10).stdout
    except (OSError, subprocess.TimeoutExpired):
        return ''


def listeners(port):
    pids = []
    for line in run('lsof', '-nP', '-iTCP:%d' % port, '-sTCP:LISTEN', '-Fp').splitlines():
        if line.startswith('p') and line[1:].isdigit():
            pids.append(int(line[1:]))
    return sorted(set(pids))


def describe(pid):
    command = run('ps', '-o', 'command=', '-p', str(pid)).strip()
    cwd = ''
    for line in run('lsof', '-a', '-p', str(pid), '-d', 'cwd', '-Fn').splitlines():
        if line.startswith('n'):
            cwd = line[1:]
    return command, cwd


def inside(root, text):
    root = str(Path(root).resolve())
    return text == root or text.startswith(root + os.sep) or (root + os.sep) in text


def scratch(text):
    """A throwaway copy a worker built to run a server from (defect injection, disposable
    checklist copies).  Those outlive the worker that started them and hold the port."""
    tmp = {os.path.realpath(d) for d in ('/tmp', '/var/tmp', os.environ.get('TMPDIR', '/tmp'))}
    tmp.add('/private/tmp')
    tmp.add('/var/folders')
    tmp = tmp | {os.path.realpath('/var/folders')}
    return any(text == d or text.startswith(d + os.sep) or (d + os.sep) in text for d in tmp)


def stop(pid):
    try:
        group = os.getpgid(pid)
    except ProcessLookupError:
        return
    # Never take our own group down with the leftover.
    target = group if group != os.getpgrp() else None
    for sig in (signal.SIGTERM, signal.SIGKILL):
        try:
            if target is not None:
                os.killpg(target, sig)
            else:
                os.kill(pid, sig)
        except ProcessLookupError:
            return
        for _ in range(20):
            time.sleep(.1)
            try:
                os.kill(pid, 0)
            except ProcessLookupError:
                return


def main(argv):
    if len(argv) not in (2, 3):
        print(__doc__, file=sys.stderr)
        return 2
    commands, root = argv[0], argv[1]
    roots = [root]
    if len(argv) == 3 and argv[2] and argv[2] != root:
        roots.append(argv[2])
    for port in declared_ports(commands, root):
        for pid in listeners(port):
            command, cwd = describe(pid)
            if any(inside(r, cwd) or inside(r, command) for r in roots) or scratch(cwd) or scratch(command):
                print('port %d: stopped leftover server pid %d (%s, cwd %s)' % (port, pid, command, cwd or 'unknown'))
                stop(pid)
            else:
                print('port %d: held by pid %d (%s, cwd %s), which is not part of this project; '
                      'not stopped. A check that binds this port will fail until it is.'
                      % (port, pid, command, cwd or 'unknown'))
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
