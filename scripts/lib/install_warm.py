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
import signal
import subprocess
import sys
import tempfile

from browser_install import install_lock
from process_tree import start_check, wait_check, kill_tree, finish_check

NAME = r'(?:@[a-z0-9][a-z0-9._-]*/)?[a-z0-9][a-z0-9._-]*'      # npm names are lowercase
SPEC = re.compile(r'^(%s)(?:@[\w.^~<>=*|-]+)?$' % NAME)
STOP = {'run', 'for', 'and', 'the', 'with', 'via', 'plus', 'also', 'then', 'only', 'each', 'all', 'none',
        'npm', 'node', 'yarn', 'pnpm', 'lockfile', 'deps', 'dependencies', 'devdependencies', 'install', 'add',
        'pinned', 'exact', 'versions', 'version', 'latest', 'dev', 'test', 'build', 'start', 'scripts', 'script',
        # Words a plan's prose puts after the keyword (noinit: the 40 "packages" were these, and one invalid name fails the whole
        # install, so nothing was cached).
        'to', 'create', 'write', 'on', 'in', 'at', 'it', 'any', 'never', 'must', 'have', 'which', 'include', 'list', 'first',
        'read', 'place', 'project', 'root', 'output', 'already', 'exist', 'existing', 'content', 'adapt', 'blindly', 'entries',
        'module', 'webpage', 'launch', 'untracked', 'tests', 'preview', 'div', 'overwriting', 'preserving', 'of', 'is', 'are',
        'be', 'by', 'as', 'a', 'an', 'or', 'not', 'no', 'if', 'when', 'that', 'this', 'from', 'into', 'its', 'so', 'do', 'use',
        'used', 'uses', 'using', 'set', 'get', 'add', 'make', 'see', 'one', 'two', 'both', 'same', 'other', 'than', 'after',
        'before', 'while', 'until', 'where', 'what', 'how', 'file', 'files', 'step', 'steps', 'plan', 'app', 'code', 'page'}
KEYWORD = re.compile(r'\b(?:dev[ -]?dependencies|dependencies|deps)\b\s*[:=]?|\bdev\s*:', re.I)
COMMAND = re.compile(r'\bnpm\s+(?:i|install|add)\b([^`\n;|&]*)', re.I)
LIMIT = 40
# After a "dependencies" keyword a plan's prose runs on ("... covers mutation, sets scratch ..."): a bare word is taken only when it is
# a package people actually install, or looks like a package name (a hyphen, scope, version, or backticks around it).
KNOWN = {'vite', 'vitest', 'react', 'react-dom', 'svelte', 'vue', 'jsdom', 'express', 'typescript', 'eslint', 'prettier',
         'playwright', 'jest', 'mocha', 'chai', 'webpack', 'rollup', 'esbuild', 'tailwindcss', 'postcss', 'sass', 'lodash',
         'axios', 'zod', 'fastify', 'next', 'nuxt', 'preact', 'solid-js', 'puppeteer', 'cypress', 'sinon', 'ts-node', 'tsx'}


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

    def add(token, prose=False):
        value = clean(token)
        if prose and value and '`' not in token and not re.search(r'[-/@\d]', value) and value.split('@')[0] not in KNOWN:
            return
        base = re.sub(r'(?<=.)@[^/]*$', '', value)
        if value and not any(re.sub(r'(?<=.)@[^/]*$', '', other) == base for other in found):
            found.append(value)

    for line in text.splitlines():
        for match in COMMAND.finditer(line):
            # A command in code (backticks, or a line that starts with it) is a list of packages; the same words inside a
            # sentence ("run npm install to create the lockfile, and write ...") are prose.
            code = line[:match.start()].count('`') % 2 == 1 or line.lstrip().startswith(('npm', '$', '(npm'))
            for token in re.split(r'[,\s]+', match.group(1).strip()):
                if token in ('to', 'and', 'then', 'which', 'that', 'so') and not code:
                    break
                add(token, prose=not code)
        # Every keyword on the line ("deps: a, b; dev: c, d"), each list ending at its ';' or ')'.
        for keyword in KEYWORD.finditer(line):
            tail = re.split(r'[;)]|\.\s|\bthen\b|\brun\b|\bwith\b', line[keyword.end():], maxsplit=1)[0]
            for token in re.split(r',|\band\b', tail):
                add(token, prose=True)
        # A scoped package named anywhere is a package.
        for scoped in re.findall(r'(?<![\w@/])(@[a-z0-9][a-z0-9._-]*/[a-z0-9][a-z0-9._-]*)', line):
            add(scoped)
        # A well-known package named in prose on a line about dependencies ("React 18, Vite 5, Vitest, Playwright dependencies").
        if re.search(r'depend|install', line, re.I):
            for word in re.findall(r'[A-Za-z][A-Za-z0-9-]*', line):
                name = word.lower()
                if name in KNOWN:
                    add('@playwright/test' if name == 'playwright' else name)
    return found[:LIMIT]


def wants_playwright(names):
    return any(re.match(r'(?:@playwright/test|playwright)(?:@|$)', name) for name in names)


def fingerprint(names):
    return hashlib.sha256('\n'.join(sorted(names)).encode()).hexdigest()[:16]


def run(command, cwd, timeout):
    """Run a command with a bound on how long it may take.

    `subprocess.run(..., timeout=...)` only kills the direct child on a timeout: `npm`/`npx`
    routinely fork a further process (e.g. the browser download `npx playwright install`
    launches) that keeps running after its parent is killed, invisible to this script and to
    anything waiting on it.  A leftover download can hold Playwright's own installer lock in
    the shared cache indefinitely, so a *later, real* `playwright install` -- the one the
    actual build depends on -- blocks forever waiting for a lock an orphan from this warm-up
    never released.  Starting the child in its own process group and killing the whole group
    on timeout (or on any other exit) means nothing from this script outlives it.
    """
    try:
        with tempfile.TemporaryFile() as output, install_lock(output):
            env = dict(os.environ, PLAYWRIGHT_SKIP_BROWSER_GC='1')
            process = start_check(command, cwd=cwd, env=env, stdout=output, stderr=subprocess.STDOUT)
            try:
                status = wait_check(process, timeout, output)
                if status in (123, 124):
                    output.seek(0)
                    print('Install warm-up: ' + output.read().decode('utf-8', errors='replace')[-2000:],
                          file=sys.stderr, flush=True)
                return status
            finally:
                kill_tree(process)
                process.wait()
                finish_check(process)
    except OSError:
        return 1


def _kill_group(process):
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except OSError:
        pass
    try:
        process.wait(timeout=5)
    except Exception:
        pass


def usable(names):
    """The names npm knows, checked together.  One unknown name makes `npm install` of the lot fail and cache nothing."""
    from concurrent.futures import ThreadPoolExecutor
    bare = [re.sub(r'(?<=.)@[^/]*$', '', name) for name in names]
    with ThreadPoolExecutor(max_workers=8) as pool:
        codes = list(pool.map(lambda n: run(['npm', 'view', n, 'name', '--loglevel=error'], tempfile.gettempdir(), 40), bare))
    return [name for name, code in zip(names, codes) if code == 0]


def warm(names, state_dir=None):
    """Fill the caches; returns a one-line summary.  Repeats for an unchanged package set are skipped."""
    if not names or not shutil.which('npm'):
        return 'nothing to warm'
    marker = Path(state_dir) / ('install-warm-' + fingerprint(names)) if state_dir else None
    if marker and marker.exists():
        return 'already warmed'
    folder = tempfile.mkdtemp(prefix='uncle-warm-')
    try:
        install = ['npm', 'install', '--ignore-scripts', '--no-audit', '--no-fund', '--no-package-lock', '--loglevel=error']
        status = run(install + names, folder, 900)
        if status != 0:
            known = usable(names)
            if known and known != names:
                names = known
                status = run(install + names, folder, 900)
        browser = 1
        summary = ['%d package(s) %s' % (len(names), 'cached' if status == 0 else 'not fully cached')]
        if wants_playwright(names) and status == 0 and shutil.which('npx'):
            browser = run([sys.executable, str(Path(__file__).with_name('browser_setup.py')), 'chromium'], folder, 360)
            summary.append('chromium %s' % ('ready' if browser == 0 else 'not downloaded'))
        if marker and status == 0 and (not wants_playwright(names) or browser == 0):
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
    def interrupted(signum, frame):
        raise KeyboardInterrupt
    signal.signal(signal.SIGTERM, interrupted)
    sys.exit(main(sys.argv[1:]))
