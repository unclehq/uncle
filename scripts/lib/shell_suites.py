from process_tree import check_timeout, wait_check
"""Run shell regression suites concurrently with separate output and live progress."""
from concurrent.futures import ThreadPoolExecutor, wait, FIRST_COMPLETED
import glob
import os
from pathlib import Path
import re
import signal
import subprocess
import sys
import tempfile
import threading
import time
from process_tree import bash_executable, start_check, finish_check, kill_tree


def run(jobs, suites=()):
    if not 1 <= jobs <= 8:
        raise ValueError('WORKFLOW_VERIFY_JOBS must be from 1 to 8')
    if any(not re.fullmatch(r'[a-z0-9][a-z0-9-]*', name) for name in suites):
        raise ValueError('Invalid shell suite name')
    files = ([f'scripts/tests/{name}-test.sh' for name in suites] if suites
             else sorted(glob.glob('scripts/tests/*-test.sh')))
    files = [Path(path).as_posix() for path in files]
    if not files:
        print('FAIL: no shell test suites found', file=sys.stderr)
        return 1
    isolate_git()
    return run_commands(jobs, {path: [bash_executable(), path] for path in files})


def isolate_git():
    """Fixture git never sees the user's global or system configuration, so no
    suite can reach a real signer or key even if a fixture forgets a flag."""
    if 'GIT_CONFIG_GLOBAL' not in os.environ:
        fd, path = tempfile.mkstemp(prefix='uncle-shell-tests-gitconfig-')
        os.write(fd, b'[commit]\n\tgpgsign = false\n[tag]\n\tgpgsign = false\n[user]\n\tname = Fixture\n\temail = fixture@example.test\n')
        os.close(fd)
        os.environ['GIT_CONFIG_GLOBAL'] = path
    os.environ.setdefault('GIT_CONFIG_NOSYSTEM', '1')


def run_commands(jobs, commands):
    """Execute named isolated commands with shared progress and cleanup."""
    if not 1 <= jobs <= 8:
        raise ValueError('Worker count must be from 1 to 8')
    timeout = check_timeout('WORKFLOW_SHELL_SUITE_TIMEOUT_SECONDS', 600)
    files = list(commands)
    active, lock, stopped = set(), threading.Lock(), threading.Event()
    running = {}
    def interrupted(*_):
        raise KeyboardInterrupt
    previous = signal.signal(signal.SIGTERM, interrupted)
    print(f'Running {len(files)} shell suites with up to {jobs} workers.', flush=True)
    try:
        with tempfile.TemporaryDirectory(prefix='uncle-shell-tests-') as directory:
            def check(path):
                log = Path(directory) / (Path(path).name + '.log')
                with log.open('wb') as output:
                    with lock:
                        if stopped.is_set():
                            return path, 130, log
                        child = start_check(commands[path], stdout=output, stderr=subprocess.STDOUT)
                        active.add(child)
                        running[path] = time.monotonic()
                    try:
                        status = wait_check(child, timeout, output)
                    finally:
                        finish_check(child)
                        with lock:
                            active.discard(child)
                            running.pop(path, None)
                return path, status, log
            pool = ThreadPoolExecutor(max_workers=jobs)
            failed = skipped = 0
            try:
                futures = [pool.submit(check, path) for path in files]
                pending = set(futures)
                last_update = time.monotonic()
                while pending:
                    completed, pending = wait(pending, timeout=0.5, return_when=FIRST_COMPLETED)
                    for future in completed:
                        path, status, log = future.result()
                        print(f'--- {path} ---', flush=True)
                        with log.open('rb') as source:
                            while chunk := source.read(65536):
                                sys.stdout.buffer.write(chunk)
                        sys.stdout.buffer.flush()
                        label = 'SKIP' if status == 77 else ('PASS' if status == 0 else f'FAIL({status})')
                        print(f'{label} {path}', flush=True)
                        skipped += status == 77
                        failed += status not in (0, 77)
                    if pending and time.monotonic() - last_update >= 10:
                        with lock:
                            names = ', '.join(f'{Path(path).name} ({int(time.monotonic() - start)}s)'
                                              for path, start in running.items())
                        print(f'Progress: {len(files) - len(pending)}/{len(files)} finished; running: {names or "starting workers"}', flush=True)
                        last_update = time.monotonic()
            finally:
                stopped.set()
                with lock:
                    for child in active:
                        kill_tree(child)
                pool.shutdown(wait=True)
            print(f'Shell suites: {len(files) - failed - skipped} passed, {failed} failed, {skipped} skipped.', flush=True)
            return int(bool(failed))
    finally:
        signal.signal(signal.SIGTERM, previous)


if __name__ == '__main__':
    raise SystemExit(run(int(sys.argv[1] if len(sys.argv) > 1 else os.environ.get('WORKFLOW_VERIFY_JOBS', '4')), sys.argv[2:]))
