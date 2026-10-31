"""Progress and absolute bounds for self-hosted writers, including retries."""
from contextlib import contextmanager
import os
import signal
import threading
import time


def option(name, default):
    from self_hosted_http import _config_values
    from self_hosted import config_stage
    import re
    config = _config_values()
    stage = os.environ.get('UNCLE_STATUS_STAGE', '')
    names = list(dict.fromkeys([stage, config_stage(stage, config)]))
    for scope in names + ['']:
        key = 'WORKFLOW_SELF_HOSTED_' + name.upper().replace('-', '_')
        if scope:
            key += '_' + re.sub(r'[^A-Z0-9]', '_', scope.upper())
        if key in os.environ:
            value = int(os.environ[key])
            break
    else:
        value = int(next((config[scope + '.' + name] for scope in names + ['self-hosted']
                          if scope + '.' + name in config), default))
    if value < 1:
        raise ValueError('self-hosted.%s must be positive' % name)
    return value


def jobs():
    return option('writer-jobs', 12)


def seconds(default=3600):
    stage = os.environ.get('UNCLE_STATUS_STAGE', '')
    if '-worker-edits' in stage or '-worker-resolve' in stage:
        return min(default, option('writer-seconds', max(600, 60 * jobs())))
    return default


_last_progress = 0.0
_last_saved = 0.0
_deadline_end = None


def progress():
    global _last_progress, _last_saved
    _last_progress = time.monotonic()
    path = os.environ.get('UNCLE_WRITER_PROGRESS_FILE')
    if path and _last_progress - _last_saved >= .1:
        try:
            os.utime(path, None)
        except FileNotFoundError:
            pass
        _last_saved = _last_progress


def failed(reason, path=None):
    path = path or os.environ.get('UNCLE_WRITER_PROGRESS_FILE')
    if path:
        with open(path + '.failed', 'w') as handle:
            handle.write(reason + '\n')


@contextmanager
def deadline(limit):
    # One timer covers all transport, schema and tool retries in this invocation.
    global _last_progress, _deadline_end
    if not hasattr(signal, 'setitimer') or threading.current_thread() is not threading.main_thread():
        yield
        return
    idle = option('writer-no-progress-seconds', 45)
    previous = signal.getsignal(signal.SIGALRM)
    timer = signal.getitimer(signal.ITIMER_REAL)
    started = time.monotonic()
    outer_end = _deadline_end
    _deadline_end = min(started + limit, outer_end) if outer_end is not None else started + limit
    effective_limit = _deadline_end - started
    if outer_end is None:
        _last_progress = started
    def expired(*_):
        now = time.monotonic()
        if now >= _deadline_end:
            signal.setitimer(signal.ITIMER_REAL, 0)
            failed('deadline: ceiling (%gs wall-clock budget)' % effective_limit)
            raise ValueError('Self hosted writer deadline: ceiling (%gs wall-clock budget)' % effective_limit)
        if now - _last_progress >= idle:
            signal.setitimer(signal.ITIMER_REAL, 0)
            failed('deadline: no-progress (%gs)' % idle)
            raise ValueError('Self hosted writer deadline: no-progress (%gs)' % idle)
    signal.signal(signal.SIGALRM, expired)
    signal.setitimer(signal.ITIMER_REAL, min(.1, limit, idle), .1)
    try:
        yield
    finally:
        _deadline_end = outer_end
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, previous)
        if timer[0]:
            signal.setitimer(signal.ITIMER_REAL, max(.001, timer[0] - (time.monotonic() - started)), timer[1])


def watch(pid, limit, worker, heartbeat='', logs=()):
    import sys
    idle = option('writer-no-progress-seconds', 45)
    started = changed = time.monotonic()
    previous = None
    while True:
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return
        current = []
        for path in (heartbeat,) + tuple(logs):
            try:
                info = os.stat(path)
                current.append((info.st_size, info.st_mtime_ns))
            except OSError:
                current.append(None)
        now = time.monotonic()
        if current != previous:
            changed, previous = now, current
        reason = ('ceiling (%gs wall-clock budget)' % limit if now - started >= limit else
                  'no-progress (%gs)' % idle if now - changed >= idle else '')
        if reason:
            print('%s: self-hosted writer deadline: %s' % (worker, reason), file=sys.stderr, flush=True)
            failed('deadline: ' + reason, heartbeat)
            terminate(pid)
            return
        time.sleep(.1)


def terminate(pid):
    import subprocess
    if os.name == 'nt':
        subprocess.run(['taskkill.exe', '/PID', str(pid), '/T', '/F'], capture_output=True)
        return
    rows = subprocess.check_output(['ps', '-axo', 'pid=,ppid='], text=True)
    parents = {int(row.split()[0]): int(row.split()[1]) for row in rows.splitlines() if row.strip()}
    owned = {pid}
    while True:
        descendants = {child for child, parent in parents.items() if parent in owned}
        if descendants <= owned:
            break
        owned.update(descendants)
    # Stop the parent before its children so it cannot launch more on failure.
    for child in [pid] + sorted(owned - {pid}, reverse=True):
        try:
            os.kill(child, signal.SIGKILL)
        except ProcessLookupError:
            pass


if __name__ == '__main__':
    import sys
    if sys.argv[1] == 'seconds':
        print(seconds())
    elif sys.argv[1] == 'jobs':
        print(jobs())
    elif sys.argv[1] == 'stop':
        terminate(int(sys.argv[2]))
    elif sys.argv[1] == 'watch':
        watch(int(sys.argv[2]), float(sys.argv[3]), sys.argv[4], *([sys.argv[5], sys.argv[6:]] if len(sys.argv) > 5 else []))
