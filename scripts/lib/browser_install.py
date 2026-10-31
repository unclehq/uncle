"""Serialize managed cache writes and check the project's local Playwright build."""
from contextlib import contextmanager, nullcontext
import json
import os
from pathlib import Path
import re
import shlex
import subprocess
import tempfile
import time

from execution_options import option, seconds
from process_tree import start_check, wait_check, kill_tree, finish_check


def command_needs(command, root='.', depth=0):
    """Recognize direct commands and package scripts, without evaluating shell text."""
    root = Path(root).resolve()
    install = browser = False
    # shlex's default word characters split paths; use shell whitespace rules.
    lexer = shlex.shlex(command, posix=True, punctuation_chars=';&|()')
    lexer.whitespace_split = True
    segments, segment = [], []
    for token in lexer:
        if token and all(c in ';&|()' for c in token):
            segments.append(segment)
            segment = []
        else:
            segment.append(token)
    segments.append(segment)
    for words in segments:
        while words and re.match(r'^\w+=', words[0]):
            words = words[1:]
        if not words:
            continue
        name = Path(words[0]).name
        if name == 'cd' and len(words) == 2:
            root = (root / words[1]).resolve()
        if name in ('pip', 'pip3', 'uv'):
            install |= 'install' in words[1:3]
        if name in ('python', 'python3') and words[1:4] == ['-m', 'pip', 'install']:
            install = True
        if name in ('npm', 'pnpm', 'yarn', 'bun'):
            install |= len(words) > 1 and words[1] in ('install', 'i', 'ci', 'add', 'clean-install')
            script = words[2] if len(words) > 2 and words[1] == 'run' else (words[1] if len(words) > 1 else '')
            if depth < 3:
                try:
                    body = json.loads((root / 'package.json').read_text()).get('scripts', {}).get(script, '')
                    nested_install, nested_browser, _ = command_needs(body, root, depth + 1)
                    install |= nested_install
                    browser |= nested_browser
                except (OSError, ValueError):
                    pass
        if name in ('npx', 'npm', 'pnpm', 'yarn', 'bun', 'playwright') or name.endswith('/playwright'):
            if 'playwright' in words:
                index = words.index('playwright')
                action = words[index + 1] if len(words) > index + 1 else ''
            else:
                action = words[1] if name == 'playwright' and len(words) > 1 else ''
            install |= action == 'install'
            browser |= action == 'test'
    return install, browser, root


@contextmanager
def install_lock(output, cancelled=None):
    # One permanent inode per user. Never remove a lock or another install's partial files.
    path = Path(option('install-lock', str(Path.home() / '.cache/uncle/install.lock')))
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('a+b') as stream:
        if stream.tell() == 0:
            stream.write(b'0')
            stream.flush()
        deadline = time.monotonic() + seconds('install-lock-seconds', 15)
        announced = False
        while True:
            if cancelled is not None and cancelled.is_set():
                raise InterruptedError('Install cancelled by this run')
            try:
                if os.name == 'nt':
                    import msvcrt
                    stream.seek(0)
                    msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
                else:
                    import fcntl
                    fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except OSError:
                if not announced:
                    output.write(b'Waiting for another managed cache install to finish.\n')
                    output.flush()
                    announced = True
                if time.monotonic() >= deadline:
                    raise TimeoutError('INSTALL_BUSY: shared cache lock is held by another run; retry after it finishes')
                time.sleep(.1)
        try:
            yield
        finally:
            if os.name == 'nt':
                stream.seek(0)
                msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(stream, fcntl.LOCK_UN)


PROBE = r'''
const path = require('path');
let pkg;
for (const entry of ['@playwright/test', 'playwright', 'playwright-core']) {
  try {
    let local = require.resolve(entry + '/package.json', {paths: [process.cwd()]});
    if (entry === '@playwright/test')
      local = require.resolve('playwright/package.json', {paths: [path.dirname(local)]});
    pkg = require.resolve('playwright-core/package.json', {paths: [path.dirname(local)]});
    break;
  } catch (_) {}
}
if (!pkg) throw new Error('No installed Playwright package found');
const {registry} = require(path.join(path.dirname(pkg), 'lib/server/registry/index.js'));
const names = process.argv[1].split(',');
const selected = registry.executables().filter(e => names.includes(e.name) ||
  (names.includes('chromium') && e.name === 'chromium-headless-shell'));
if (!selected.length || names.some(n => !selected.some(e => e.name === n)))
  throw new Error('Unknown browser selection: ' + names);
console.log(JSON.stringify({cli: path.join(path.dirname(pkg), 'cli.js'),
  executables: selected.map(e => ({name: e.name, path: e.executablePath()}))}));
'''


def probe(root):
    names = option('playwright-browsers', 'chromium')
    if any(name not in ('chromium', 'firefox', 'webkit') for name in names.split(',')):
        raise ValueError('execution.playwright-browsers must be comma-separated chromium,firefox,webkit')
    with tempfile.TemporaryFile() as log:
        child = start_check(['node', '-e', PROBE, names], cwd=root, stdout=log, stderr=log)
        try:
            status = wait_check(child, 5, log, idle=0)
        finally:
            kill_tree(child)
            child.wait()
            finish_check(child)
        log.seek(0)
        text = log.read().decode('utf-8', errors='replace')
    if status:
        # A setup this probe cannot read (no local install, a global or npx-fetched
        # Playwright) runs as it always has; stall detection still bounds a hang.
        return None, names
    return json.loads(text), names


def ensure_browser(root, output, env, cancelled=None):
    data, names = probe(root)
    if data is None:
        note = 'Browser preflight skipped: cannot inspect local Playwright in %s.\n' % root
        output.write(note if 'b' not in getattr(output, 'mode', 'b') else note.encode())
        output.flush()
        return
    missing = [entry['path'] for entry in data['executables']
               if not entry.get('path') or not Path(entry['path']).is_file()]
    if not missing:
        return
    if option('playwright-auto-install', '0').lower() not in ('1', 'true'):
        raise ValueError('BROWSER_MISSING: installed Playwright requires %s. Run node %s install %s, '
                         'or set execution.playwright-auto-install true.' %
                         (', '.join(str(p) for p in missing), shlex.quote(data['cli']), names.replace(',', ' ')))
    child = start_check(['node', data['cli'], 'install', *names.split(',')], cwd=root,
                        env=dict(env, PLAYWRIGHT_SKIP_BROWSER_GC='1'), stdout=output, stderr=subprocess.STDOUT)
    try:
        status = wait_check(child, seconds('browser-install-seconds', 180), output, cancelled=cancelled)
    finally:
        kill_tree(child)
        child.wait()
        finish_check(child)
    if status or any(not p or not Path(p).is_file() for p in missing):
        raise ValueError('BROWSER_MISSING: serialized Playwright install failed (status %s); required: %s' %
                         (status, ', '.join(str(p) for p in missing)))


@contextmanager
def prepare(command, output, env, cancelled=None):
    install, browser, root = command_needs(command)
    browser = browser and option('playwright-preflight', '1').lower() in ('1', 'true')
    # One command that installs and then tests runs exactly as before: its browser
    # revision is only known after its own install, so there is nothing to check first.
    if browser and not install:
        with install_lock(output, cancelled):
            ensure_browser(root, output, env, cancelled)
    with install_lock(output, cancelled) if install else nullcontext():
        if install:
            env['PLAYWRIGHT_SKIP_BROWSER_GC'] = '1'
        yield
