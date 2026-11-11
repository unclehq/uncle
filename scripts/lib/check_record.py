#!/usr/bin/env python3
"""Machine-checkable record of the green check, and its reviewer-run replay.

check_record.py snapshot|assemble|environment|rerun

Runners write one sidecar JSON per command (write_sidecar) into a record
directory; assemble merges them in index order into green-check.json together
with the environment block and the executed-file snapshot digest.  rerun
restores the immutable snapshot, compares the recorded environment exactly,
and replays the commands in a fresh, allow-listed environment.

Every rerun precondition is checked before any recorded command executes; a
failed precondition exits nonzero, runs nothing and never claims a match.
"""
import hashlib
import json
import math
import os
import platform
import re
import shutil
import subprocess
import sys
import tempfile
import time

SCHEMA = 'uncle.check-record/v1'

# Capture allow-list: exact, finite names.  No prefix or provenance selection.
# PATH is deliberately absent: only resolved tool versions are recorded.
ALLOWED_ENV_NAMES = (
    'LANG', 'LC_ALL', 'LC_CTYPE', 'TZ', 'CI', 'NO_COLOR', 'TERM',
    'WORKFLOW_CHECK_TIMEOUT_SECONDS',
)
# Rerun execution allow-list: what a replayed child may see besides the
# recorded variables.  PATH is a fixed minimal value; HOME is the temp root.
EXEC_ENV_NAMES = ALLOWED_ENV_NAMES + ('PATH', 'HOME')
MINIMAL_PATH = '/usr/local/bin:/opt/homebrew/bin:/usr/bin:/bin'
# Defence in depth: a name that looks like a credential is never recorded or
# passed, even if someone adds it to the constants above.
CREDENTIAL_RE = re.compile(r'(TOKEN|SECRET|PASSWORD|PASSWD|KEY|AUTH|COOKIE|CREDENTIAL)', re.I)
TOOLS = ('git', 'python3', 'bash', 'node')
BROWSER_RE = re.compile(r'(playwright|puppeteer|chromium|chrome|firefox|webkit|cypress|selenium)', re.I)


class SnapshotMismatch(Exception):
    pass


def _sha256(data):
    return hashlib.sha256(data).hexdigest()


def _permitted(name):
    return name in ALLOWED_ENV_NAMES and not CREDENTIAL_RE.search(name)


# ---------------------------------------------------------------- sidecars

def write_sidecar(record_dir, index, argv, cwd, root, status, pipefail=False, start=None,
                  duration=0.0, timeout=None, output=b'', browser=False):
    """Write <record_dir>/<index>.json.  cwd is stored relative to root, never absolute."""
    os.makedirs(record_dir, exist_ok=True)
    rel = os.path.relpath(os.path.realpath(cwd), os.path.realpath(root))
    entry = {
        'index': int(index), 'argv': list(argv), 'cwd': rel, 'status': int(status),
        'pipefail': bool(pipefail), 'start': start if start is not None else time.time(),
        'duration': float(duration), 'timeout': timeout,
        'output_sha256': _sha256(output if isinstance(output, bytes) else output.encode()),
        'browser': bool(browser),
    }
    tmp = os.path.join(record_dir, '.%d.tmp' % int(index))
    with open(tmp, 'w') as handle:
        json.dump(entry, handle, sort_keys=True)
    os.replace(tmp, os.path.join(record_dir, '%d.json' % int(index)))
    return entry


# --------------------------------------------------------------- environment

def _tool_version(name, path=None):
    exe = shutil.which(name, path=path)
    if not exe:
        return None
    try:
        out = subprocess.run([exe, '--version'], capture_output=True, text=True, timeout=20)
        text = (out.stdout or out.stderr).strip().splitlines()
        return text[0] if text else ''
    except (OSError, subprocess.SubprocessError):
        return None


def capture_environment(env=None):
    env = os.environ if env is None else env
    return {
        'platform': platform.platform(),
        'machine': platform.machine(),
        'tools': {name: _tool_version(name) for name in TOOLS},
        'variables': {name: env[name] for name in ALLOWED_ENV_NAMES
                      if name in env and _permitted(name)},
    }


def compare_environment(recorded, current):
    """Exact comparison, no normalization.  Returns the list of differing fields."""
    diffs = []
    for key in ('platform', 'machine'):
        if recorded.get(key) != current.get(key):
            diffs.append('%s: recorded %r, host %r' % (key, recorded.get(key), current.get(key)))
    for name in sorted(set(recorded.get('tools', {})) | set(current.get('tools', {}))):
        a, b = recorded.get('tools', {}).get(name), current.get('tools', {}).get(name)
        if a != b:
            diffs.append('tool %s: recorded %r, host %r' % (name, a, b))
    for name in sorted(set(recorded.get('variables', {})) | set(current.get('variables', {}))):
        a, b = recorded.get('variables', {}).get(name), current.get('variables', {}).get(name)
        if a != b:
            diffs.append('variable %s: recorded %r, host %r' % (name, a, b))
    return diffs


def execution_environment(recorded_variables, home):
    """Fresh child environment from explicit names only; never os.environ wholesale."""
    env = {'PATH': MINIMAL_PATH, 'HOME': home}
    for name, value in recorded_variables.items():
        if name in EXEC_ENV_NAMES and _permitted(name):
            env[name] = value
    return env


# ------------------------------------------------------------------ snapshot

def _manifest_digest(entries):
    return _sha256(json.dumps(entries, sort_keys=True, separators=(',', ':')).encode())


def list_tree_files(root):
    found = []
    for base, dirs, files in os.walk(root):
        dirs[:] = [d for d in dirs if d != '.git']
        for name in files:
            full = os.path.join(base, name)
            if os.path.isfile(full) and not os.path.islink(full):
                found.append(os.path.relpath(full, root))
    return sorted(found)


def snapshot_capture(root, store, paths=None, rewrites=None):
    """Copy the files actually checked (incl. untracked) into a content-addressed store.

    rewrites maps a path to a short note of the recorded copy rewrite.  Returns
    {'digest', 'store', 'entries'}; the digest binds the manifest to the record.
    """
    paths = list_tree_files(root) if paths is None else sorted(paths)
    rewrites = rewrites or {}
    os.makedirs(os.path.join(store, 'files'), exist_ok=True)
    entries = []
    for rel in paths:
        full = os.path.join(root, rel)
        with open(full, 'rb') as handle:
            data = handle.read()
        digest = _sha256(data)
        blob = os.path.join(store, 'files', digest)
        if not os.path.exists(blob):
            with open(blob, 'wb') as out:
                out.write(data)
        entry = {'path': rel, 'sha256': digest, 'mode': os.stat(full).st_mode & 0o777}
        if rel in rewrites:
            entry['rewrite'] = rewrites[rel]
        entries.append(entry)
    digest = _manifest_digest(entries)
    with open(os.path.join(store, 'manifest.json'), 'w') as handle:
        json.dump({'digest': digest, 'entries': entries}, handle, sort_keys=True)
    return {'digest': digest, 'store': os.path.abspath(store), 'entries': entries}


def snapshot_restore(store, expected_digest, dest):
    """Materialize the snapshot into dest after verifying every hash; raise SnapshotMismatch."""
    try:
        with open(os.path.join(store, 'manifest.json')) as handle:
            manifest = json.load(handle)
    except (OSError, ValueError) as error:
        raise SnapshotMismatch('snapshot manifest unreadable: %s' % error)
    entries = manifest.get('entries')
    if not isinstance(entries, list) or _manifest_digest(entries) != expected_digest \
            or manifest.get('digest') != expected_digest:
        raise SnapshotMismatch('manifest digest differs from the recorded digest')
    blobs = []
    for entry in entries:
        path = entry.get('path', '')
        if os.path.isabs(path) or '..' in path.split(os.sep):
            raise SnapshotMismatch('unsafe path in manifest: %s' % path)
        try:
            with open(os.path.join(store, 'files', entry['sha256']), 'rb') as handle:
                data = handle.read()
        except OSError:
            raise SnapshotMismatch('missing snapshot file: %s' % path)
        if _sha256(data) != entry['sha256']:
            raise SnapshotMismatch('snapshot file differs from its hash: %s' % path)
        blobs.append((entry, data))
    for entry, data in blobs:
        target = os.path.join(dest, entry['path'])
        os.makedirs(os.path.dirname(target), exist_ok=True)
        with open(target, 'wb') as out:
            out.write(data)
        os.chmod(target, entry['mode'])
    return len(blobs)


# ------------------------------------------------------------------ assemble

def assemble(record_dir, out_path, snapshot=None, extra_env=None):
    """Merge sidecars in index order into out_path; flag untrustworthy entries."""
    entries = []
    for name in os.listdir(record_dir) if os.path.isdir(record_dir) else []:
        if not re.fullmatch(r'\d+\.json', name):
            continue
        try:
            with open(os.path.join(record_dir, name)) as handle:
                entry = json.load(handle)
        except (OSError, ValueError):
            entry = {'argv': None}
        if not isinstance(entry, dict):
            entry = {'argv': None}
        entry.setdefault('index', int(name.split('.')[0]))
        entries.append(entry)
    entries.sort(key=lambda e: e.get('index', 0))
    required = ('argv', 'cwd', 'status', 'output_sha256')
    for position, entry in enumerate(entries):
        problems = [k for k in required if entry.get(k) is None]
        cwd = entry.get('cwd')
        if isinstance(cwd, str) and os.path.isabs(cwd):
            problems.append('cwd absolute')
        if entry.get('index') != position + 1:
            problems.append('index gap')
        if problems:
            entry['trusted'] = False
            entry['unavailable'] = 'incomplete record: ' + ', '.join(problems)
        else:
            entry['trusted'] = True
    record = {
        'schema': SCHEMA, 'commands': entries,
        'environment': capture_environment(extra_env),
        'snapshot': ({'digest': snapshot['digest'], 'store': snapshot['store']} if snapshot else None),
    }
    tmp = out_path + '.tmp'
    with open(tmp, 'w') as handle:
        json.dump(record, handle, sort_keys=True, indent=1)
    os.replace(tmp, out_path)
    return record


# --------------------------------------------------------------------- rerun

def parse_rerun_timeout(value):
    """None when omitted; else a finite number > 0; ValueError otherwise."""
    if value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        raise ValueError('--rerun-timeout must be a number greater than zero')
    if not math.isfinite(number) or number <= 0:
        raise ValueError('--rerun-timeout must be a finite number greater than zero')
    return number


def effective_timeout(recorded, override):
    if override is None:
        return recorded
    return override if recorded is None else min(recorded, override)


def contained_cwd(root, cwd):
    """Resolve cwd inside root or raise ValueError (absolute, '..', symlink escape)."""
    if not isinstance(cwd, str) or os.path.isabs(cwd) or '..' in cwd.split(os.sep):
        raise ValueError('cwd not contained in the rerun root: %r' % (cwd,))
    real_root = os.path.realpath(root)
    resolved = os.path.realpath(os.path.join(real_root, cwd))
    if resolved != real_root and not resolved.startswith(real_root + os.sep):
        raise ValueError('cwd escapes the rerun root: %r' % (cwd,))
    if not os.path.isdir(resolved):
        raise ValueError('cwd does not exist in the snapshot: %r' % (cwd,))
    return resolved


def is_browser_command(entry):
    if entry.get('browser'):
        return True
    return bool(BROWSER_RE.search(' '.join(str(a) for a in entry.get('argv') or [])))


def _replay_argv(entry):
    argv = list(entry['argv'])
    if entry.get('pipefail') and len(argv) >= 3 and os.path.basename(argv[0]) in ('bash', 'sh') \
            and argv[1] == '-c':
        argv[2] = 'set -o pipefail; ' + argv[2]
    return argv


def rerun(record_path, rerun_timeout=None, out=None):
    """Replay a record.  Returns (exit_code, status, detail).

    status: match | mismatch | unavailable | snapshot-mismatch | environment-mismatch | usage
    """
    say = out or (lambda line: print(line, flush=True))
    try:
        override = parse_rerun_timeout(rerun_timeout)
    except ValueError as error:
        say('usage: %s' % error)
        return 2, 'usage', str(error)
    try:
        with open(record_path) as handle:
            record = json.load(handle)
        commands = record['commands']
        if record.get('schema') != SCHEMA or not commands:
            raise ValueError('no command record')
    except (OSError, ValueError, KeyError, TypeError):
        say('rerun unavailable: no command record (legacy attestation)')
        return 3, 'unavailable', 'no command record'
    untrusted = [c.get('index') for c in commands if not c.get('trusted')]
    if untrusted:
        say('rerun unavailable: untrustworthy record entries %s' % untrusted)
        return 3, 'unavailable', 'untrustworthy entries'
    if any(is_browser_command(c) for c in commands):
        say('rerun unavailable: browser required')
        return 3, 'unavailable', 'browser required'
    snap = record.get('snapshot')
    if not snap:
        say('rerun unavailable: record has no executed-file snapshot')
        return 3, 'unavailable', 'no snapshot'
    diffs = compare_environment(record.get('environment') or {}, capture_environment())
    if diffs:
        for line in diffs:
            say('environment-mismatch: ' + line)
        return 4, 'environment-mismatch', '; '.join(diffs)
    root = tempfile.mkdtemp(prefix='uncle-rerun-')
    try:
        try:
            snapshot_restore(snap['store'], snap['digest'], root)
        except SnapshotMismatch as error:
            say('snapshot-mismatch: %s' % error)
            return 5, 'snapshot-mismatch', str(error)
        try:
            cwds = [contained_cwd(root, c['cwd']) for c in commands]
        except ValueError as error:
            say('rerun unavailable: %s' % error)
            return 3, 'unavailable', str(error)
        env = execution_environment((record.get('environment') or {}).get('variables', {}), root)
        mismatches = 0
        for entry, cwd in zip(commands, cwds):
            argv = _replay_argv(entry)
            say('rerun: %s' % ' '.join(argv))
            limit = effective_timeout(entry.get('timeout'), override)
            try:
                done = subprocess.run(argv, cwd=cwd, env=env, stdout=subprocess.PIPE,
                                      stderr=subprocess.STDOUT, timeout=limit)
                code, data, timed_out = done.returncode, done.stdout, False
            except subprocess.TimeoutExpired:
                code, data, timed_out = None, b'', True
            except OSError as error:
                code, data, timed_out = 126, str(error).encode(), False
            if timed_out:
                say('mismatch (timed out after %ss): %s' % (limit, argv))
                mismatches += 1
            elif code != entry['status'] or _sha256(data) != entry['output_sha256']:
                say('mismatch (status %s, recorded %s): %s' % (code, entry['status'], argv))
                mismatches += 1
            else:
                say('match: %s' % argv)
        if mismatches:
            return 1, 'mismatch', '%d of %d commands differ' % (mismatches, len(commands))
        return 0, 'match', '%d commands match' % len(commands)
    finally:
        shutil.rmtree(root, ignore_errors=True)


# ----------------------------------------------------------------------- CLI

def main(argv):
    if len(argv) < 2:
        print('usage: check_record.py snapshot|assemble|environment|rerun ...', file=sys.stderr)
        return 2
    cmd, args = argv[1], argv[2:]
    if cmd == 'environment':
        print(json.dumps(capture_environment(), sort_keys=True, indent=1))
        return 0
    if cmd == 'snapshot' and len(args) >= 2:
        result = snapshot_capture(args[0], args[1])
        print(result['digest'])
        return 0
    if cmd == 'assemble' and len(args) >= 2:
        snapshot = None
        if len(args) >= 4:
            snapshot = {'store': args[3], 'digest': args[2]}
        record = assemble(args[0], args[1], snapshot)
        return 0 if all(c.get('trusted') for c in record['commands']) else 0
    if cmd == 'rerun' and args:
        timeout = None
        if '--rerun-timeout' in args:
            i = args.index('--rerun-timeout')
            timeout = args[i + 1] if i + 1 < len(args) else ''
        code, _status, _detail = rerun(args[0], timeout)
        return code
    print('usage: check_record.py snapshot ROOT STORE | assemble DIR OUT [DIGEST STORE] | '
          'environment | rerun RECORD [--rerun-timeout S]', file=sys.stderr)
    return 2


if __name__ == '__main__':
    sys.exit(main(sys.argv))
