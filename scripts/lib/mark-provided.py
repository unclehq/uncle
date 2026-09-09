#!/usr/bin/env python3
"""Mark preflight rows satisfied at the gate, in place.

The alternative was re-running the preflight agent so it could rediscover a
file the operator had just typed a path to: a full stage, minutes and tokens,
to reach the conclusion the driver already holds. This edits the rows instead.

What it will not do is launder a blocker. It only touches rows whose id was
named on the command line, only inside the one `## Acceptance gate` table, and
only when that row is currently blocked; the evidence it writes says the input
was handed over at the gate, by whom, when, and with what digest, so the row
never reads as something preflight observed for itself. Every other line of the
report is passed through byte for byte.

Usage: mark-provided.py REPORT ID=PATH [ID=PATH ...]
Exit 0 when every id was marked, 1 otherwise.
"""
import hashlib
from pathlib import Path
import re
import sys
import time

BLOCKED = ('BLOCKED', 'BLOCKED-SETUP', 'BLOCKED-HUMAN', 'BLOCKED-IMPOSSIBLE',
           'NOT RUN')


def digest(path):
    h = hashlib.sha256()
    with open(path, 'rb') as handle:
        for chunk in iter(lambda: handle.read(65536), b''):
            h.update(chunk)
    return h.hexdigest()


def mark(report, supplied):
    lines = Path(report).read_text(encoding="utf-8").splitlines(keepends=True)
    when = time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())
    active = False
    marked = set()
    out = []
    for line in lines:
        stripped = line.strip()
        if re.fullmatch(r'##\s+Acceptance gate', stripped):
            active = True
            out.append(line)
            continue
        # Any other heading ends the table; only the gate rows are ours.
        if active and stripped.startswith('#'):
            active = False
        if not active or stripped.count('|') < 5:
            out.append(line)
            continue
        cells = stripped.split('|')
        if len(cells) != 6:
            out.append(line)
            continue
        row_id, required, status = (c.strip() for c in cells[1:4])
        if row_id not in supplied or status not in BLOCKED:
            out.append(line)
            continue
        path = supplied[row_id]
        # A pipe in the evidence would split the row and corrupt the table the
        # next reader parses, so the path is reported with it stripped.
        safe = path.replace('|', '')
        evidence = (f'provided at the preflight gate {when}; '
                    f'{safe} sha256 {digest(path)[:12]}; '
                    f'recorded by the operator, not observed by preflight')
        out.append(f'| {row_id} | {required} | PASS | {evidence} |\n')
        marked.add(row_id)
    missing = sorted(set(supplied) - marked)
    if missing:
        print(f'no blocked gate row to mark for: {", ".join(missing)}',
              file=sys.stderr)
        return 1
    Path(report).write_bytes(''.join(out).encode('utf-8'))
    return 0


if __name__ == '__main__':
    if len(sys.argv) < 3:
        print(__doc__, file=sys.stderr)
        sys.exit(1)
    pairs = {}
    for argument in sys.argv[2:]:
        key, _, value = argument.partition('=')
        if not key or not value or not Path(value).is_file() \
                or Path(value).stat().st_size == 0:
            print(f'not a readable non-empty file: {argument}', file=sys.stderr)
            sys.exit(1)
        pairs[key] = value
    sys.exit(mark(sys.argv[1], pairs))
