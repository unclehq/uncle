"""Run the Python regression suites (scripts/tests/*-test.py) concurrently, one process each.

`python3 -m unittest discover` runs the same files one after another in one process: about eight and a half minutes of work
on this repository, against two and a half minutes at four workers here. It also lets one file's import-time state leak into the
next. This is the same runner as the shell one (shell_suites.run_commands): separate output per suite, live progress, one
process tree per suite so a hung one is killed whole, and a nonzero exit if any suite fails.

    python_suites.py [JOBS] [NAME ...]      NAME is a suite without its -test.py suffix
"""
import glob
import os
from pathlib import Path
import re
import shutil
import sys

from shell_suites import isolate_git, run_commands


def suite_command(path):
    """How one suite is launched. WORKFLOW_PYTHON_TESTS_RUNNER: `python` (the default), `uv` or `pytest`.

    `uv` runs the same file under uv's interpreter; `pytest` runs it under `uv run --with pytest pytest`. Only the first two keep
    every suite's own exit status: the plain-script suites collect no pytest tests (exit 5) and some import fixtures from
    their own directory, so `pytest` is for comparison, not for gating.
    """
    mode = os.environ.get('WORKFLOW_PYTHON_TESTS_RUNNER', 'python')
    uv = shutil.which('uv') if mode in ('uv', 'pytest') else None
    if not uv:
        return [sys.executable, '-B', path]
    if mode == 'uv':
        return [uv, 'run', '--no-project', '--quiet', 'python', '-B', path]
    return [uv, 'run', '--no-project', '--quiet', '--with', 'pytest', 'pytest', '-q', '-p', 'no:cacheprovider',
            '--import-mode=importlib', '-o', 'python_files=*-test.py', path]


def run(jobs, suites=()):
    if not 1 <= jobs <= 16:
        raise ValueError('WORKFLOW_VERIFY_JOBS must be from 1 to 16')
    if any(not re.fullmatch(r'[a-z0-9][a-z0-9-]*', name) for name in suites):
        raise ValueError('Invalid python suite name')
    files = ([f'scripts/tests/{name}-test.py' for name in suites] if suites
             else sorted(glob.glob('scripts/tests/*-test.py')))
    files = [Path(path).as_posix() for path in files]
    if not files:
        print('FAIL: no python test suites found', file=sys.stderr)
        return 1
    isolate_git()
    # Keep suites off the network and the real model cache, as the shell runner does.
    os.environ.setdefault('UNCLE_MODEL_REFRESH', '0')
    return run_commands(jobs, {path: suite_command(path) for path in files}, kind='python')


if __name__ == '__main__':
    raise SystemExit(run(int(sys.argv[1] if len(sys.argv) > 1 else os.environ.get('WORKFLOW_VERIFY_JOBS', '4')), sys.argv[2:]))
