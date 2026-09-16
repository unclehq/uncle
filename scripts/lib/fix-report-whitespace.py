#!/usr/bin/env python3
"""Repair whitespace errors in workflow Markdown, retaining other diff failures."""
import re
import subprocess
from pathlib import Path


# Top-level workflow markdown: the only files this script may rewrite.
REPAIRABLE = re.compile(
    r'([A-Z][A-Z0-9_]*\.md):(\d+): (trailing whitespace\.|new blank line at EOF\.)')


def check():
    return subprocess.run(['git', '-c', 'core.quotePath=false', 'diff', '--check'],
                          stdout=subprocess.PIPE, stderr=subprocess.PIPE)


def main():
    result = check()
    if result.returncode == 0:
        return 0
    fixes = {}
    for line in result.stdout.decode('utf-8', errors='replace').splitlines():
        match = REPAIRABLE.fullmatch(line)
        if match:
            name, number, problem = match.groups()
            fixes.setdefault(name, []).append((int(number), problem))
    for name, problems in fixes.items():
        path = Path(name)
        if path.is_symlink() or not path.is_file():
            continue
        original = path.read_bytes()
        lines = original.splitlines(keepends=True)
        for number, problem in problems:
            if problem == 'trailing whitespace.' and 0 < number <= len(lines):
                line = lines[number - 1]
                ending = b'\r\n' if line.endswith(b'\r\n') else b'\n' if line.endswith(b'\n') else b''
                body = line[:-len(ending)] if ending else line
                lines[number - 1] = body.rstrip(b' \t') + ending
        if any(problem == 'new blank line at EOF.' for _, problem in problems):
            while lines and not lines[-1].strip():
                lines.pop()
        updated = b''.join(lines)
        if updated != original and path.read_bytes() == original:
            path.write_bytes(updated)
            print(f'Fixed report whitespace: {name}', flush=True)
    result = check()
    import sys
    sys.stdout.buffer.write(result.stdout)
    sys.stderr.buffer.write(result.stderr)
    # `git diff --check` fails on ANY changed file with trailing whitespace:
    # product code, tests, and the driver's own logs under .uncle/. This script
    # repairs only top-level workflow markdown, so returning git's status made
    # the driver die on whitespace it had just refused to touch -- and because
    # the caller runs under `set -e` without checking, it died silently right
    # after a stage reported success, with no stop reason and no completion
    # marker written. Report everything, but fail only when something this
    # script is responsible for is still wrong.
    remaining = [line for line in result.stdout.decode('utf-8', errors='replace').splitlines()
                 if REPAIRABLE.fullmatch(line)]
    if remaining:
        return result.returncode or 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
