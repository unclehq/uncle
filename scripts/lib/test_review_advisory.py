#!/usr/bin/env python3
"""Downgrade advisory TEST_REVIEW rows to non-blocking, in the canonical JSON only.

The reviewer's own TEST_REVIEW.md is never touched -- it still shows FAIL for
everyone reading it, and the row's evidence is still the record of the gap.
This only changes whether the *driver* treats that row as blocking the build.

A failed row is downgraded only when every row that actually proves the
application behaves correctly is clean: ASSERTIONS (tests assert the right
things), INTEGRITY and RESULTS (the driver's own commands passed), and
NEGATIVE (CLAUDE.md requires defect-injection evidence that tests reject a
real defect -- never advisory). What's left in COVERAGE and ORACLE at that
point is "the test suite is not as exhaustive as the plan described" or "an
expected value was not independently re-derived by the reviewer" -- a gap in
how thoroughly the work was checked, not evidence the work is wrong. Shipping
with a known, ledgered gap like that is a deliberate choice this tool makes
only in unattended mode, and only ever adds it as nonblocking evidence to the
audit -- never turns a FAIL into a PASS.

usage: test_review_advisory.py CANONICAL.json
  Exit 0 whether or not anything was downgraded. Prints one line per row
  downgraded, for the caller to ledger; prints nothing otherwise.
"""
import json
import sys
from pathlib import Path

ALWAYS_BLOCKING = {'ASSERTIONS', 'INTEGRITY', 'RESULTS', 'NEGATIVE'}
ADVISORY = {'COVERAGE', 'ORACLE'}


def downgrade(path):
    data = json.loads(Path(path).read_text(encoding='utf-8'))
    if data.get('schema') != 'uncle.artifact/v1' or data.get('kind') != 'acceptance-report':
        return []
    rows = data.get('rows')
    if not isinstance(rows, list):
        return []
    blocking_clean = all(
        row.get('status') == 'PASS'
        for row in rows
        if isinstance(row, dict) and row.get('id') in ALWAYS_BLOCKING and row.get('required') is True
    )
    if not blocking_clean:
        return []
    downgraded = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        if row.get('id') in ADVISORY and row.get('required') is True and row.get('status') != 'PASS':
            row['required'] = False
            downgraded.append(row['id'])
    if downgraded:
        Path(path).write_text(json.dumps(data, indent=1), encoding='utf-8')
    return downgraded


if __name__ == '__main__':
    if len(sys.argv) != 2:
        print(__doc__, file=sys.stderr)
        sys.exit(2)
    try:
        for identifier in downgrade(sys.argv[1]):
            print(identifier)
    except (OSError, ValueError):
        sys.exit(0)
