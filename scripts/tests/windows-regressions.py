"""Run isolated Windows regression suites with bounded concurrency."""
from concurrent.futures import ThreadPoolExecutor
import os
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts/lib'))
from process_tree import bash_executable, start_check, finish_check, kill_tree

SHELL = 'verification-integrity checklist-groups parallel-checks review-compaction agent-kimi reviewer-claude document-budget provided-inputs windows-probes'.split()
PYTHON = ['self-hosted', 'session-totals', 'audit-findings']


def run_suites(suites, directory, jobs=4):
    def run(item):
        name, command = item
        log = Path(directory) / (name + '.log')
        with log.open('wb') as output:
            child = start_check(command, stdout=output, stderr=subprocess.STDOUT)
            try:
                status = child.wait()
            finally:
                if child.poll() is None:
                    kill_tree(child)
                finish_check(child)
        return name, status, log
    with ThreadPoolExecutor(max_workers=jobs) as pool:
        return list(pool.map(run, suites))


def main():
    os.chdir(ROOT)
    suites = [('shell-regressions', [bash_executable(), 'scripts/run-shell-tests.sh', '--jobs', '4', '--', *SHELL])]
    suites += [(name, [sys.executable, '-B', f'scripts/tests/{name}-test.py']) for name in PYTHON]
    with tempfile.TemporaryDirectory(prefix='uncle-regressions-') as directory:
        results = run_suites(suites, directory)
        for name, status, log in results:
            print(f'::group::{name}', flush=True)
            sys.stdout.buffer.write(log.read_bytes())
            sys.stdout.buffer.flush()
            print(f'{"FAIL" if status else "PASS"}: {name} (exit {status})\n::endgroup::', flush=True)
        failures = [name for name, status, _ in results if status]
    print('Regression suites failed: ' + str(len(failures)))
    if failures:
        message = 'Failed suites: ' + ', '.join(failures)
        print(message)
        if os.environ.get('GITHUB_STEP_SUMMARY'):
            with open(os.environ['GITHUB_STEP_SUMMARY'], 'a') as output:
                output.write(message + '\n')
    return bool(failures)


if __name__ == '__main__':
    raise SystemExit(main())
