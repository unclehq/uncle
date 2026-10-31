#!/usr/bin/env python3
"""Detect a project's test commands from the repository itself, so the baseline can start before the plan says what they are.

The approved baseline command list is written by the planning model (BASELINE_REPORT), which is why the baseline used to start
only after ANALYZE: IMPLEMENT then waited on a suite that had barely begun (354 s on issue 117). Starting at the very beginning
needs commands that are known without a model, so this reads the repository's own conventions:

  * Uncle's runners:   scripts/run-python-tests.sh, scripts/run-shell-tests.sh
  * npm:               a real `test` script in package.json            -> npm test
  * Make:              a `test:` target                                -> make test
  * Go / Cargo:        go.mod -> go test ./...,  Cargo.toml -> cargo test
  * pytest:            pytest.ini, [tool.pytest*] in pyproject.toml, tox.ini or setup.cfg [tool:pytest] -> pytest

Detection is a guess about what will be approved, and a guess is only ever *reused*: the early result of an approved command counts
as its baseline only when the tree is byte-identical to the one the early run started from and the early run finished
(scripts/lib/early-baseline.sh). Approved commands the early run did not run are run then, and only those; if the tree changed
or the early run failed, everything runs as before.

    early_baseline.py detect PROJECT      # one command per line
    early_baseline.py covers COMMANDS_FILE EARLY_COMMANDS_FILE    # exit 0 when every approved command was run early
    early_baseline.py remaining COMMANDS_FILE EARLY_COMMANDS_FILE # the approved commands the early run did NOT run
"""
import json
from pathlib import Path
import re
import sys

NPM_PLACEHOLDER = re.compile(r'no test specified', re.I)


def _read(path):
    try:
        return Path(path).read_text(encoding='utf-8', errors='replace')
    except OSError:
        return ''


def detect(project):
    root = Path(project)
    commands = []
    for kind in ('python', 'shell'):
        if (root / f'scripts/run-{kind}-tests.sh').is_file():
            commands.append(f'bash scripts/run-{kind}-tests.sh')
    if commands:
        return commands           # Uncle's own runners already cover the suites; a generic pytest on top would only repeat them
    package = _read(root / 'package.json')
    if package:
        try:
            script = (json.loads(package).get('scripts') or {}).get('test')
        except ValueError:
            script = None
        if isinstance(script, str) and script.strip() and not NPM_PLACEHOLDER.search(script):
            commands.append('npm test')
    if re.search(r'(?m)^test\s*:', _read(root / 'Makefile')):
        commands.append('make test')
    if (root / 'go.mod').is_file():
        commands.append('go test ./...')
    if (root / 'Cargo.toml').is_file():
        commands.append('cargo test')
    pytest_configured = ((root / 'pytest.ini').is_file() or (root / 'tox.ini').is_file()
                         or re.search(r'(?m)^\[tool\.pytest', _read(root / 'pyproject.toml'))
                         or re.search(r'(?m)^\[tool:pytest\]', _read(root / 'setup.cfg')))
    if pytest_configured:
        commands.append('pytest')
    return commands


def normalize(line):
    return ' '.join(line.split())


def covers(commands_file, early_file):
    approved = [normalize(l) for l in _read(commands_file).splitlines() if l.strip()]
    early = {normalize(l) for l in _read(early_file).splitlines() if l.strip()}
    return bool(approved) and all(command in early for command in approved)


def partition(commands_file, early_file):
    """(covered, remaining) approved commands, in approved order: what the early run already ran, and what it did not."""
    early = {normalize(l) for l in _read(early_file).splitlines() if l.strip()}
    covered, remaining = [], []
    for line in _read(commands_file).splitlines():
        if line.strip():
            (covered if normalize(line) in early else remaining).append(line)
    return covered, remaining


def main(argv):
    if len(argv) == 4 and argv[1] == 'remaining':
        for command in partition(argv[2], argv[3])[1]:
            print(command)
        return 0
    if len(argv) == 3 and argv[1] == 'detect':
        for command in detect(argv[2]):
            print(command)
        return 0
    if len(argv) == 4 and argv[1] == 'covers':
        return 0 if covers(argv[2], argv[3]) else 1
    print(__doc__, file=sys.stderr)
    return 2


if __name__ == '__main__':
    raise SystemExit(main(sys.argv))
