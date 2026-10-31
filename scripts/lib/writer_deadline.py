"""One wall-clock allowance for a self-hosted writer, including HTTP retries."""
from contextlib import contextmanager
import os
import signal
import threading
import time


def seconds(default=3600):
    from self_hosted_http import positive_option
    stage = os.environ.get('UNCLE_STATUS_STAGE', '')
    if '-worker-edits-' in stage or '-worker-resolve-' in stage:
        return min(default, positive_option('writer-seconds', 150))
    return default


@contextmanager
def deadline(limit):
    # Each CLI writer has its own process. SIGALRM also interrupts a server
    # that keeps a stream alive forever by trickling bytes below socket timeout.
    if not hasattr(signal, 'setitimer') or threading.current_thread() is not threading.main_thread():
        yield
        return
    def expired(*_):
        raise ValueError('Self hosted writer exceeded its %s-second wall-clock budget' % limit)
    previous = signal.getsignal(signal.SIGALRM)
    timer = signal.getitimer(signal.ITIMER_REAL)
    started = time.monotonic()
    signal.signal(signal.SIGALRM, expired)
    signal.setitimer(signal.ITIMER_REAL, min(limit, timer[0]) if timer[0] else limit)
    try:
        yield
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, previous)
        if timer[0]:
            signal.setitimer(signal.ITIMER_REAL, max(.001, timer[0] - (time.monotonic() - started)), timer[1])


def watch(pid, limit, worker):
    import subprocess
    import sys
    expires = time.monotonic() + limit
    while time.monotonic() < expires:
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return
        time.sleep(min(.1, max(0, expires - time.monotonic())))
    print('%s: self-hosted writer exceeded its %gs wall-clock budget' % (worker, limit), file=sys.stderr, flush=True)
    terminate(pid)


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
        from self_hosted_http import positive_option
        print(positive_option('writer-seconds', 150))
    elif sys.argv[1] == 'stop':
        terminate(int(sys.argv[2]))
    elif sys.argv[1] == 'watch':
        watch(int(sys.argv[2]), float(sys.argv[3]), sys.argv[4])
