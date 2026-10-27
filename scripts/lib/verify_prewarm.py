#!/usr/bin/env python3
"""Run the plan's setup commands (dependency install, browser download) in the background, while the
rest of implementation is still being written, so verification does not wait for them.

The slowest, least model-dependent part of verification is setup: `npm ci`, `playwright install chromium`.
The scaffold step has written the manifest long before the last implementation step finishes, so as soon as a
group of steps has merged and `package.json` exists the driver starts those commands here, in the real
project, detached.  When verification starts it joins this job (waits only for what is still running) and
skips each setup command that already succeeded against the same manifest and lockfile.  A manifest that
changed since runs the command again; a failure or a timeout is never trusted -- the command simply runs in
verification as it always did.

    verify_prewarm.py start COMMANDS ROOT STATE        detached; returns at once
    verify_prewarm.py finish COMMANDS ROOT STATE OUT [SECONDS]   join, then write the commands to skip
    verify_prewarm.py cancel STATE                     stop a running job (from the EXIT trap)
    verify_prewarm.py run COMMANDS ROOT STATE          the job itself (internal)
"""
import hashlib
import os
import re
import signal
import subprocess
import sys
import time
from pathlib import Path

INSTALL = re.compile(r'\b(?:npm\s+(?:ci|install|i)|yarn\s+install|pnpm\s+(?:install|i)|pip3?\s+install)\b'
                     r'|\bplaywright\s+install\b')
NOT_SETUP = re.compile(r'\b(?:vitest|jest|pytest|mocha)\b|\bplaywright\s+test\b|\bnpm\s+(?:run|test|t)\b'
                       r'|\bnpx\s+(?:--no-install\s+)?(?:vite|tsc|eslint)\b|\bnode\s+\S+\.m?js\b')
MANIFESTS = ('package.json', 'package-lock.json', 'npm-shrinkwrap.json', 'yarn.lock', 'pnpm-lock.yaml',
             'requirements.txt', 'pyproject.toml')
TIMEOUT = int(os.environ.get('WORKFLOW_PREWARM_TIMEOUT_SECONDS') or 900)


def is_setup(command):
    return bool(INSTALL.search(command)) and not NOT_SETUP.search(command)


def read_commands(path):
    try:
        lines = Path(path).read_text(encoding='utf-8').splitlines()
    except OSError:
        return []
    return [line.rstrip('\r') for line in lines if line.strip()]


def setup_commands(path):
    return [command for command in read_commands(path) if is_setup(command)]


def manifest_hash(root):
    digest = hashlib.sha256()
    found = False
    for name in MANIFESTS:
        file = Path(root) / name
        if file.is_file():
            found = True
            digest.update(name.encode() + b'\0' + file.read_bytes() + b'\0')
    return digest.hexdigest()[:16] if found else ''


def directory(state):
    path = Path(state) / 'prewarm'
    path.mkdir(parents=True, exist_ok=True)
    return path


def results(state):
    """{(command, manifest hash): exit status} from every setup run so far."""
    found = {}
    try:
        for line in (directory(state) / 'results.tsv').read_text(encoding='utf-8').splitlines():
            status, digest, command = line.split('\t', 2)
            found[(command, digest)] = int(status)
    except (OSError, ValueError):
        pass
    return found


def alive(state):
    try:
        pid = int((directory(state) / 'pid').read_text())
        os.kill(pid, 0)
        return pid
    except (OSError, ValueError):
        return 0


def pending(commands, root, state):
    digest = manifest_hash(root)
    done = results(state)
    return digest, [c for c in setup_commands(commands) if done.get((c, digest)) != 0]


def start(commands, root, state):
    if alive(state):
        return 'running'
    digest, todo = pending(commands, root, state)
    if not digest or not todo:
        return 'nothing to do'
    log = Path(state) / 'logs' / 'verify-prewarm.log'
    log.parent.mkdir(parents=True, exist_ok=True)
    out = open(log, 'ab')
    child = subprocess.Popen([sys.executable, '-B', str(Path(__file__).resolve()), 'run', commands, root, state],
                             cwd=root, stdin=subprocess.DEVNULL, stdout=out, stderr=subprocess.STDOUT,
                             start_new_session=True)
    (directory(state) / 'pid').write_text(str(child.pid))
    return 'started %d setup command(s)' % len(todo)


def run(commands, root, state):
    digest, todo = pending(commands, root, state)
    for command in todo:
        print('$ %s' % command, flush=True)
        began = time.monotonic()
        try:
            status = subprocess.run(['bash', '-o', 'pipefail', '-c', command], cwd=root, stdin=subprocess.DEVNULL,
                                    timeout=TIMEOUT).returncode
        except subprocess.TimeoutExpired:
            status = 124
        except OSError:
            status = 127
        print('  exit %d after %.0fs' % (status, time.monotonic() - began), flush=True)
        # A manifest that changed while this ran makes the result about a tree that no longer exists.
        recorded = digest if manifest_hash(root) == digest else 'stale'
        with open(directory(state) / 'results.tsv', 'a', encoding='utf-8') as handle:
            handle.write('%d\t%s\t%s\n' % (status, recorded, command))
        if status != 0:
            break
    try:
        (directory(state) / 'pid').unlink()
    except OSError:
        pass
    return 0


def stop(state):
    pid = alive(state)
    if pid:
        try:
            os.killpg(pid, signal.SIGTERM)
        except OSError:
            pass
    try:
        (directory(state) / 'pid').unlink()
    except OSError:
        pass


def finish(commands, root, state, out, seconds=TIMEOUT):
    """Join the job, then write the setup commands verification may skip, one per line."""
    deadline = time.monotonic() + seconds
    while alive(state) and time.monotonic() < deadline:
        time.sleep(0.5)
    if alive(state):
        stop(state)
    digest = manifest_hash(root)
    done = results(state)
    skip = [c for c in setup_commands(commands) if digest and done.get((c, digest)) == 0]
    Path(out).write_text(''.join(c + '\n' for c in skip), encoding='utf-8')
    return skip


def main(argv):
    if not argv:
        raise SystemExit(__doc__)
    command, rest = argv[0], argv[1:]
    if command == 'start' and len(rest) == 3:
        print(start(*rest))
    elif command == 'run' and len(rest) == 3:
        return run(*rest)
    elif command == 'finish' and len(rest) in (4, 5):
        skip = finish(*rest[:4], *( [int(rest[4])] if len(rest) == 5 else []))
        print('%d setup command(s) already done in the background' % len(skip))
    elif command == 'cancel' and len(rest) == 1:
        stop(rest[0])
    else:
        raise SystemExit(__doc__)
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
