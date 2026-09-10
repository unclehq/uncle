#!/usr/bin/env python3
"""Repair literal pipes in acceptance evidence without changing decisions."""
import os
from pathlib import Path
import re
import sys
import tempfile


def repair(text):
    active = False
    lines = []
    for line in text.splitlines(keepends=True):
        if re.match(r'^## Acceptance gate\s*$', line):
            active = True
        elif line.startswith('#'):
            active = False
        if active and line.strip().startswith('|') and line.strip().endswith('|'):
            cells = line.strip()[1:-1].split('|')
            if (len(cells) > 4 and re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_./-]*', cells[0].strip())
                    and cells[1].strip() in ('YES', 'NO')
                    and cells[2].strip() in ('PASS', 'FAIL', 'BLOCKED', 'BLOCKED-SETUP',
                                             'BLOCKED-HUMAN', 'BLOCKED-IMPOSSIBLE', 'NOT RUN', 'N/A')):
                evidence = '|'.join(cells[3:]).replace('\\|', '|').replace('|', '&#124;')
                ending = '\r\n' if line.endswith('\r\n') else '\n' if line.endswith('\n') else ''
                line = '|' + '|'.join(cells[:3]) + '|' + evidence + '|' + ending
        lines.append(line)
    return ''.join(lines)


def main(filename):
    path = Path(filename)
    if not path.is_file() or path.is_symlink():
        return
    original = path.read_bytes()
    candidate = repair(original.decode('utf-8')).encode('utf-8')
    if candidate == original:
        return
    logs = path.parent/'.uncle/workflow/logs'
    logs.mkdir(parents=True, exist_ok=True)
    fd, backup = tempfile.mkstemp(prefix=path.stem.lower()+'-before-table-repair-', suffix='.md', dir=logs)
    with os.fdopen(fd, 'wb') as stream:
        stream.write(original)
    fd, pending = tempfile.mkstemp(prefix='.'+path.name, dir=path.parent)
    try:
        with os.fdopen(fd, 'wb') as stream:
            stream.write(candidate)
        if path.is_symlink() or path.read_bytes() != original:
            raise ValueError('Report changed during table repair; refusing to overwrite it')
        os.chmod(pending, path.stat().st_mode)
        os.replace(pending, path)
    finally:
        if os.path.exists(pending):
            os.unlink(pending)
    print('Repaired acceptance evidence pipes in '+str(path)+'; original retained at '+backup, file=sys.stderr)


if __name__ == '__main__':
    main(sys.argv[1])
