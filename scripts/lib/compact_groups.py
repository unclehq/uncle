#!/usr/bin/env python3
"""The checklist groups compact mode runs: the reviewer's own, minus checks that are not required.

Compact mode used to put every required check on one line, which made the whole
checklist one group.  Batches inside a group launch together, so checks that
declared the same exclusive resource -- a port, a browser, a database -- ran
side by side, and the two checks fighting over it produced a FAIL that reads like
a product defect.  What may overlap is the independent reviewer's declaration,
not the executing driver's convenience, so the groups stay exactly as approved:
consecutive runs sharing no declared resource, each a barrier for the next.
Compact mode still bounds how many checks one worker session takes (batches within
a group); it no longer changes which checks may share a moment.

usage: compact_groups.py GROUPS_FILE MANUAL_CHECKLIST.json   (writes the groups to stdout)
"""
import json
import sys


def compact_groups(groups_text, checklist):
    required = {check.get('id') for check in checklist.get('checks', []) if check.get('required', True)}
    lines = []
    for line in groups_text.splitlines():
        kept = [cid for cid in line.split() if cid in required]
        if kept:
            lines.append(' '.join(kept))
    return lines


def main(argv):
    if len(argv) != 2:
        raise SystemExit(__doc__)
    with open(argv[0], encoding='utf-8') as handle:
        text = handle.read()
    with open(argv[1], encoding='utf-8') as handle:
        checklist = json.load(handle)
    print('\n'.join(compact_groups(text, checklist)))
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
