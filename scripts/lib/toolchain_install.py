"""Best-effort install of missing verification toolchains on hosted runs.

Never fatal: every failure is recorded and the caller continues to preflight,
which checks actual PATH availability afterwards.
"""
import json
import os
import shutil
import signal
import subprocess
import sys
import time
from pathlib import Path

DEADLINE_SECONDS = 300
GRACE_SECONDS = 3

# Fixed executable -> Debian package table. Unmapped tools are skipped. A value is a package name or a tuple of names tried in order,
# the first one apt can install: Debian 13 (the hosted sandbox) renamed `dune` to `ocaml-dune`, and with the old name the whole
# `apt-get install` failed (exit 100, "has no installation candidate") and dune was never installed.
PACKAGES = {
    'ocaml': 'ocaml', 'ocamlc': 'ocaml', 'ocamlopt': 'ocaml',
    'ocamlfind': 'ocaml-findlib', 'dune': ('ocaml-dune', 'dune'), 'opam': 'opam',
    'make': 'make', 'gcc': 'gcc', 'g++': 'g++', 'cc': 'gcc', 'cmake': 'cmake',
    'clang': 'clang', 'java': 'default-jre-headless', 'javac': 'default-jdk-headless',
    'mvn': 'maven', 'gradle': 'gradle', 'php': 'php-cli', 'lua': 'lua5.4',
    'perl': 'perl', 'ghc': 'ghc', 'cabal': 'cabal-install', 'elixir': 'elixir',
    'erl': 'erlang-base', 'sbcl': 'sbcl', 'nim': 'nim', 'scala': 'scala',
    'kotlinc': 'kotlin', 'swipl': 'swi-prolog', 'racket': 'racket',
    'ruby': 'ruby', 'go': 'golang-go', 'cargo': 'cargo', 'rustc': 'rustc',
    'node': 'nodejs', 'npm': 'npm',
}


def is_enabled():
    return os.environ.get('UNCLE_HOSTED') == '1' and os.environ.get('WORKFLOW_TOOLCHAIN_INSTALL') != '0'


def discover(commands_text):
    """Per-line tokenizing: malformed lines are recorded and skipped."""
    from preflight import prerequisites
    names, malformed = set(), []
    for number, line in enumerate(commands_text.splitlines(), 1):
        if not line.strip() or line.lstrip().startswith('#'):
            continue
        try:
            names.update(prerequisites(line))
        except ValueError as exc:
            malformed.append({'line': number, 'text': line.strip(), 'reason': str(exc)})
    return sorted(names), malformed


def _group_alive(pgid):
    try:
        os.killpg(pgid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def _signal_group(pgid, sig):
    try:
        os.killpg(pgid, sig)
    except ProcessLookupError:
        return
    except PermissionError:
        name = 'TERM' if sig == signal.SIGTERM else 'KILL'
        subprocess.run(['sudo', '-n', 'kill', '-' + name, '--', '-%d' % pgid],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)


def _terminate_tree(child, grace):
    """SIGTERM the group, grace, SIGKILL, reap. Returns a cleanup description."""
    pgid = child.pid
    _signal_group(pgid, signal.SIGTERM)
    end = time.monotonic() + grace
    while time.monotonic() < end and _group_alive(pgid) and child.poll() is None:
        time.sleep(0.05)
    time.sleep(0.05)
    if _group_alive(pgid):
        _signal_group(pgid, signal.SIGKILL)
    try:
        child.wait(timeout=10)
    except subprocess.TimeoutExpired:
        pass
    end = time.monotonic() + 5
    while _group_alive(pgid) and time.monotonic() < end:
        time.sleep(0.05)
    if _group_alive(pgid):
        return 'cleanup could not be confirmed: process group %d still present' % pgid
    return 'process group terminated and reaped'


def _run(argv, deadline):
    """Run one apt command under a deadline. Returns an outcome dict."""
    if not shutil.which('sudo') or not shutil.which('apt-get'):
        return {'argv': argv, 'status': 'unavailable', 'detail': 'sudo or apt-get not found on PATH'}
    if deadline <= 0:
        return {'argv': argv, 'status': 'skipped', 'detail': 'deadline exhausted before install'}
    env = dict(os.environ, DEBIAN_FRONTEND='noninteractive')
    try:
        child = subprocess.Popen(argv, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                                 stderr=subprocess.DEVNULL, env=env, start_new_session=True)
    except OSError as exc:
        return {'argv': argv, 'status': 'error', 'detail': str(exc)}
    try:
        code = child.wait(timeout=deadline)
    except subprocess.TimeoutExpired:
        grace = float(os.environ.get('WORKFLOW_TOOLCHAIN_GRACE', GRACE_SECONDS))
        cleanup = _terminate_tree(child, grace)
        return {'argv': argv, 'status': 'timeout', 'timed_out': True, 'cleanup': cleanup,
                'detail': 'install exceeded %ss deadline' % deadline}
    # Reap any lingering descendants of a finished install as well.
    return {'argv': argv, 'status': 'ok' if code == 0 else 'failed', 'exit_status': code}


def run_install(packages, deadline):
    """One apt-get invocation under a shared deadline. Returns an outcome dict."""
    return _run(['sudo', '-n', 'apt-get', 'install', '-y', '--no-install-recommends', *packages], deadline)


def run_update(deadline):
    """Refresh apt's package lists once. Returns an outcome dict."""
    return _run(['sudo', '-n', 'apt-get', 'update', '-qq'], deadline)


def has_candidate(package):
    """Whether apt can install `package`. True when that cannot be told (no apt-cache, an error), so apt itself decides."""
    exe = shutil.which('apt-cache')
    if not exe:
        return True
    try:
        out = subprocess.run([exe, 'policy', package], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True, timeout=30)
    except (OSError, subprocess.SubprocessError):
        return True
    if out.returncode:
        return True
    for line in out.stdout.splitlines():
        line = line.strip()
        if line.startswith('Candidate:'):
            return line.split(':', 1)[1].strip() not in ('', '(none)')
    return False        # apt knows no such package


def candidates(tool):
    value = PACKAGES.get(tool)
    return () if not value else ((value,) if isinstance(value, str) else tuple(value))


def choose(tools):
    """({tool: package apt can install}, {tool: names tried}) for the tools that have a mapping."""
    chosen, unresolved = {}, {}
    for tool in tools:
        names = candidates(tool)
        if not names:
            continue
        found = next((n for n in names if has_candidate(n)), None)
        if found:
            chosen[tool] = found
        else:
            unresolved[tool] = names
    return chosen, unresolved


def install(commands_path, record_path):
    text = Path(commands_path).read_text(encoding='utf-8', errors='replace')
    record = {'schema': 'uncle.toolchain-install/v1', 'enabled': is_enabled(), 'malformed': [],
              'missing': [], 'packages': [], 'skipped': [], 'install': None, 'still_missing': []}
    names, record['malformed'] = discover(text)
    record['missing'] = [n for n in names if not shutil.which(n)]
    for name in record['missing']:
        if not candidates(name):
            record['skipped'].append({'tool': name, 'reason': 'no package mapping'})
    mapped = []
    if not record['enabled']:
        record['skipped'].extend({'tool': n, 'reason': 'installer disabled (not hosted or WORKFLOW_TOOLCHAIN_INSTALL=0)'}
                                 for n in record['missing'] if candidates(n))
    else:
        try:
            deadline = float(os.environ.get('WORKFLOW_TOOLCHAIN_DEADLINE', DEADLINE_SECONDS))
            started = time.monotonic()
            chosen, unresolved = choose(record['missing'])
            if unresolved:
                # Stale or empty package lists look the same as a package that does not exist: refresh them once and look again.
                record['update'] = run_update(deadline)
                chosen, unresolved = choose(record['missing'])
            for tool, tried in unresolved.items():
                # Left out of the install: one name apt cannot install made the whole `apt-get install` fail (exit 100).
                record['skipped'].append({'tool': tool, 'reason': 'no installable package (tried: %s)' % ', '.join(tried)})
            for pkg in chosen.values():
                if pkg not in mapped:
                    mapped.append(pkg)
            if mapped:
                record['install'] = run_install(mapped, deadline - (time.monotonic() - started))
        except Exception as exc:  # never fatal
            record['install'] = {'status': 'error', 'detail': str(exc)}
        status = (record['install'] or {}).get('status')
        if status in ('timeout', 'skipped', 'unavailable', 'error'):
            record['skipped'].extend({'tool': p, 'reason': 'package not installed: ' + status} for p in mapped)
    record['packages'] = mapped
    record['still_missing'] = [n for n in record['missing'] if not shutil.which(n)]
    installed = [n for n in record['missing'] if n not in record['still_missing']]
    record['installed'] = installed
    record['summary'] = ('Toolchain install: %d missing (%s); installed/available now: %s; still missing: %s; '
                         'malformed lines skipped: %d.' % (
                             len(record['missing']), ', '.join(record['missing']) or 'none',
                             ', '.join(installed) or 'none', ', '.join(record['still_missing']) or 'none',
                             len(record['malformed'])))
    # Say WHY something is still missing, in the same line the run output and the supervisor read: a bare "still missing: dune" gave
    # nobody a cause to act on (the package had been renamed and the install failed with apt's generic exit 100).
    why = []
    outcome = record.get('install') or {}
    if outcome.get('status') in ('failed', 'timeout', 'error'):
        why.append('apt-get install %s%s' % (outcome['status'], ' (exit %s)' % outcome['exit_status'] if 'exit_status' in outcome else ''))
    why.extend('%s: %s' % (row['tool'], row['reason']) for row in record['skipped'] if row['tool'] in record['still_missing'])
    if why and record['still_missing']:
        record['summary'] += ' Why: ' + '; '.join(why) + '.'
    Path(record_path).parent.mkdir(parents=True, exist_ok=True)
    Path(record_path).write_text(json.dumps(record, indent=2) + '\n', encoding='utf-8')
    print(record['summary'])
    return record


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if len(argv) != 2:
        print('usage: toolchain_install.py <commands> <record-json>', file=sys.stderr)
        return 2
    try:
        install(argv[0], argv[1])
    except Exception as exc:  # never fatal
        print('Toolchain install skipped: %s' % exc, file=sys.stderr)
    return 0


if __name__ == '__main__':
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    raise SystemExit(main())
