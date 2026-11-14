"""Failure-driven repair of a missing program on hosted runs.

The fixed table in toolchain_install.py only knows the tools a command names up front. A build can still die on a program that nothing
named (dune needs ocamlc, a Makefile calls bison, ...). This reads the output of a failed verification run, finds programs the shell or
a build tool reports as missing, asks the system's own package index which package ships each one, installs it and exits 0 so the
caller can run the commands again. No language knowledge: the failure says what is missing and Debian says where it lives.

Hosted runs only (same gate as the installer). Never fatal. Bounded: each program is tried once, and the caller limits the rounds.
Usage: toolchain_heal.py <failed-output-log> <record-json>   Exit 0: something was installed, run again. Exit 1: nothing to do.
"""
import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import toolchain_install as ti  # noqa: E402

NAME = r'([A-Za-z0-9][A-Za-z0-9._+-]{0,63})'
# What shells and build tools print when a program is not on PATH. Only a bare executable name is ever taken from them.
SIGNATURES = [re.compile(p, re.M) for p in (
    NAME + r': (?:command )?not found',                          # bash, sh, dash
    r'Program ' + NAME + r' not found',                          # dune, meson
    r'exec: "' + NAME + r'": executable file not found',         # go
    r'spawn ' + NAME + r' ENOENT',                               # node
    r"env: '?" + NAME + r"'?: No such file or directory",        # env
    r'Can\'t exec "' + NAME + r'"',                              # perl
    r'\[Errno 2\] No such file or directory: \'' + NAME + r'\'', # python subprocess
)]
SKIP_SUFFIXES = ('-dbg', '-dbgsym', '-doc', '-dev-bin')


def missing_programs(text):
    seen = []
    for pattern in SIGNATURES:
        for name in pattern.findall(text):
            if name not in seen and not shutil.which(name):
                seen.append(name)
    return seen


def _apt_file(*args, timeout=120):
    exe = shutil.which('apt-file')
    if not exe:
        return None
    try:
        out = subprocess.run([exe, *args], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True, timeout=timeout)
    except (OSError, subprocess.SubprocessError):
        return None
    return out.stdout if out.returncode == 0 else None


def ensure_index(record, deadline):
    """apt-file and its file lists, fetched once per sandbox."""
    if shutil.which('apt-file') and _apt_file('search', '--regexp', '^/usr/bin/sh$', timeout=60):
        return True
    record['index'] = [ti.run_update(deadline), ti._run(['sudo', '-n', 'apt-get', 'install', '-y', '--no-install-recommends', 'apt-file'], deadline),
                       ti._run(['sudo', '-n', 'apt-file', 'update'], deadline)]
    return bool(shutil.which('apt-file') and _apt_file('search', '--regexp', '^/usr/bin/sh$', timeout=60))


def packages_for(program):
    """Packages that ship /usr/bin/<program> (or /bin, /usr/sbin, /sbin), best first."""
    out = _apt_file('search', '--regexp', r'^/(usr/)?s?bin/' + re.escape(program) + '$')
    found = []
    for line in (out or '').splitlines():
        package = line.split(':', 1)[0].strip()
        if package and package not in found and not package.endswith(SKIP_SUFFIXES):
            found.append(package)
    return sorted(found, key=lambda p: (len(p), p))


def heal(log_path, record_path):
    record = {'schema': 'uncle.toolchain-heal/v1', 'enabled': ti.is_enabled(), 'tried': [], 'rounds': []}
    rp = Path(record_path)
    if rp.is_file():
        try:
            record['tried'] = json.loads(rp.read_text()).get('tried', [])
        except (OSError, ValueError):
            pass
    history = list(record['tried'])
    if not record['enabled']:
        return record, 1, ''
    text = Path(log_path).read_text(encoding='utf-8', errors='replace') if Path(log_path).is_file() else ''
    fresh = [p for p in missing_programs(text) if p not in history]
    if not fresh:
        return record, 1, ''
    round_ = {'programs': fresh, 'packages': {}, 'skipped': {}}
    deadline = float(os.environ.get('WORKFLOW_TOOLCHAIN_DEADLINE', ti.DEADLINE_SECONDS))
    started = time.monotonic()
    chosen = []
    try:
        if not ensure_index(record, deadline):
            round_['skipped'] = {p: 'no package index to search (apt-file unavailable)' for p in fresh}
        else:
            for program in fresh:
                pick = next((p for p in packages_for(program) if ti.has_candidate(p)), None)
                if pick:
                    round_['packages'][program] = pick
                    if pick not in chosen:
                        chosen.append(pick)
                else:
                    round_['skipped'][program] = 'no package ships it'
        if chosen:
            round_['install'] = ti.run_install(chosen, deadline - (time.monotonic() - started))
    except Exception as exc:  # never fatal
        round_['install'] = {'status': 'error', 'detail': str(exc)}
    record['tried'] = history + fresh
    record['rounds'].append(round_)
    ok = (round_.get('install') or {}).get('status') == 'ok'
    now = [p for p in round_['packages'] if shutil.which(p)]
    bits = ['%s (for %s)' % (pkg, prog) for prog, pkg in round_['packages'].items()]
    line = 'Toolchain repair: %s reported missing; ' % ', '.join(fresh)
    line += ('installed %s.' % ', '.join(bits)) if ok else 'could not install%s.' % (
        ': ' + '; '.join('%s: %s' % kv for kv in round_['skipped'].items()) if round_['skipped'] else
        ' (apt-get %s)' % (round_.get('install') or {}).get('status', 'not run'))
    record['summary'] = line
    return record, (0 if ok and now else 1), line


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if len(argv) != 2:
        print('usage: toolchain_heal.py <failed-output-log> <record-json>', file=sys.stderr)
        return 2
    try:
        record, code, line = heal(*argv)
    except Exception as exc:  # never fatal
        print('Toolchain repair skipped: %s' % exc, file=sys.stderr)
        return 1
    if record.get('rounds'):
        Path(argv[1]).parent.mkdir(parents=True, exist_ok=True)
        Path(argv[1]).write_text(json.dumps(record, indent=2) + '\n', encoding='utf-8')
    if line:
        print(line)
    return code


if __name__ == '__main__':
    raise SystemExit(main())
