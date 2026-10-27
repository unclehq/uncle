#!/usr/bin/env python3
"""Warm the package and browser caches for the final build while the slow stages run.

The final build installs its dependencies in the first implementation step and again in the
verification commands, and downloads a browser for its tests -- all of it after planning and review
have finished, on the critical path.  Planning and review are model-bound and leave the network and
disk idle for minutes, and the plan already names the packages.  So as soon as a plan exists the
driver downloads them into the machine-wide caches (npm's, Playwright's) in the background.  The
install the build runs later finds everything cached.

Nothing here touches the project: it installs into a temporary directory, only to fill the shared
caches, with install scripts disabled.  It never fails a stage and is cancelled with the run.

usage: install_warm.py PLAN.md
"""
import hashlib
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile

NAME = r'(?:@[a-z0-9][\w.-]*/)?[a-z0-9][\w.-]*'
SPEC = re.compile(r'^(%s)(?:@[\w.^~<>=*|-]+)?$' % NAME)
STOP = {'run', 'for', 'and', 'the', 'with', 'via', 'plus', 'also', 'then', 'only', 'each', 'all', 'none',
        'npm', 'node', 'yarn', 'pnpm', 'lockfile', 'deps', 'dependencies', 'devdependencies', 'install', 'add',
        'pinned', 'exact', 'versions', 'version', 'latest', 'dev', 'test', 'build', 'start', 'scripts', 'script'}
KEYWORD = re.compile(r'\b(?:dev[ -]?dependencies|dependencies|deps)\b\s*[:=]?|\bdev\s*:', re.I)
COMMAND = re.compile(r'\bnpm\s+(?:i|install|add)\b([^`\n;|&]*)', re.I)
LIMIT = 40


def clean(token):
    token = token.strip().strip('`"\'').strip(' .,:;()[]')
    # "@playwright/test pinned to an exact version": the package is the first word.
    if ' ' in token:
        first, rest = token.split(None, 1)
        if not re.match(r'(?:pinned|exact|exactly|at|version|latest|\d)', rest, re.I):
            return ''                      # prose ("are fine"), not "<package> pinned to ..."
        token = first.strip('`"\'').strip(' .,:;()[]')
    if not token or token.startswith('-') or '/' in token and not token.startswith('@'):
        return ''
    match = SPEC.match(token)
    if not match:
        return ''
    name = match.group(1)
    if name.lower() in STOP or len(name) < 2 or re.search(r'\.(js|jsx|ts|tsx|json|css|html|md|mjs|cjs)$', name):
        return ''
    return token


def packages(text):
    """npm package names (with a pinned version when the plan gives one) the plan says to install."""
    found = []

    def add(token):
        value = clean(token)
        if value and value not in found:
            found.append(value)

    for line in text.splitlines():
        for match in COMMAND.finditer(line):
            for token in match.group(1).split():
                add(token)
        # Every keyword on the line ("deps: a, b; dev: c, d"), each list ending at its ';' or ')'.
        for keyword in KEYWORD.finditer(line):
            tail = re.split(r'[;)]|\.\s|\bthen\b|\brun\b|\bwith\b', line[keyword.end():], maxsplit=1)[0]
            for token in re.split(r',|\band\b', tail):
                add(token)
    return found[:LIMIT]


def wants_playwright(names):
    return any(re.match(r'(?:@playwright/test|playwright)(?:@|$)', name) for name in names)


def fingerprint(names):
    return hashlib.sha256('\n'.join(sorted(names)).encode()).hexdigest()[:16]


def run(command, cwd, timeout):
    try:
        return subprocess.run(command, cwd=cwd, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                              stderr=subprocess.DEVNULL, timeout=timeout).returncode
    except (OSError, subprocess.TimeoutExpired):
        return 1


def warm(names, state_dir=None):
    """Fill the caches; returns a one-line summary.  Repeats for an unchanged package set are skipped."""
    if not names or not shutil.which('npm'):
        return 'nothing to warm'
    marker = Path(state_dir) / ('install-warm-' + fingerprint(names)) if state_dir else None
    if marker and marker.exists():
        return 'already warmed'
    folder = tempfile.mkdtemp(prefix='uncle-warm-')
    try:
        status = run(['npm', 'install', '--ignore-scripts', '--no-audit', '--no-fund', '--no-package-lock',
                      '--loglevel=error', *names], folder, 900)
        summary = ['%d package(s) %s' % (len(names), 'cached' if status == 0 else 'not fully cached')]
        if wants_playwright(names) and status == 0 and shutil.which('npx'):
            browser = run(['npx', '--no-install', 'playwright', 'install', 'chromium'], folder, 1200)
            summary.append('chromium %s' % ('ready' if browser == 0 else 'not downloaded'))
        if marker and status == 0:
            try:
                marker.write_text('\n'.join(names) + '\n')
            except OSError:
                pass
        return ', '.join(summary)
    finally:
        shutil.rmtree(folder, ignore_errors=True)


def main(argv):
    if len(argv) < 1 or not Path(argv[0]).is_file():
        return 0
    try:
        text = Path(argv[0]).read_text(encoding='utf-8')
        names = packages(text)
        print('Install warm-up: ' + warm(names, argv[1] if len(argv) > 1 else None), flush=True)
    except Exception as error:     # a convenience, never a reason to stop
        print('Install warm-up: skipped (%s).' % error)
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
