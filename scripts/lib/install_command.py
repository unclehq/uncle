#!/usr/bin/env python3
"""A clean-install command that cannot work without a lockfile, run where it can.

`npm ci` installs exactly what `package-lock.json` says and fails (EUSAGE) when there is none.  A new project has no
lockfile, and no implementation step may create one (installing is the verification block's job, run once by the driver),
so a plan whose install fallback is `npm ci` fails its first command and every command after it (noinit: five of six
green-check commands, no test or mutation ever ran).  Where the lockfile is missing the command is changed to the install
that creates it; where it exists the command is untouched.

    install_command.py normalize COMMANDS_FILE [PROJECT_ROOT]   rewrite in place, one line per command, and say what changed
"""
import re
import sys
from pathlib import Path

NPM_CI = re.compile(r'\bnpm\s+(?:ci|clean-install)\b')
YARN_FROZEN = re.compile(r'(\byarn(?:\s+install)?)\s+--frozen-lockfile\b')
PNPM_FROZEN = re.compile(r'(\bpnpm\s+(?:install|i))\s+--frozen-lockfile\b')


def adapt(line, root):
    """(the command to run, why it changed or '')."""
    root = Path(root)
    changed = []
    if NPM_CI.search(line) and not (root / 'package-lock.json').exists() and not (root / 'npm-shrinkwrap.json').exists():
        line = NPM_CI.sub('npm install', line)
        changed.append('`npm ci` needs a package-lock.json and there is none; `npm install` creates it')
    if YARN_FROZEN.search(line) and not (root / 'yarn.lock').exists():
        line = YARN_FROZEN.sub(r'\1', line)
        changed.append('`--frozen-lockfile` needs a yarn.lock and there is none')
    if PNPM_FROZEN.search(line) and not (root / 'pnpm-lock.yaml').exists():
        line = PNPM_FROZEN.sub(r'\1', line)
        changed.append('`--frozen-lockfile` needs a pnpm-lock.yaml and there is none')
    return line, '; '.join(changed)


def normalize(path, root='.'):
    """Rewrite the commands file in place (same number of lines); return [(old, new, why)]."""
    source = Path(path)
    text = source.read_text(encoding='utf-8')
    out, notes = [], []
    for line in text.split('\n'):
        new, why = adapt(line, root)
        if why:
            notes.append((line, new, why))
        out.append(new)
    if notes:
        source.write_text('\n'.join(out), encoding='utf-8')
    return notes


def main(argv):
    if len(argv) in (2, 3) and argv[0] == 'normalize':
        for old, new, why in normalize(argv[1], argv[2] if len(argv) == 3 else '.'):
            print('Install command adapted: %s -> %s (%s)' % (old.strip(), new.strip(), why))
        return 0
    raise SystemExit(__doc__)


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
