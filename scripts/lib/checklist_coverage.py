#!/usr/bin/env python3
"""Which required checks did the parallel workers not execute?

The worker fan-out used to skip a group of one check, and the fast path then rendered the report from the
workers alone -- so a skipped check silently vanished from the verification report instead of failing it.
Whatever the workers did not cover is handed to the single execution agent instead.

usage: checklist_coverage.py MANUAL_CHECKLIST.json EXECUTE_CHECKLIST_WORKERS.json   (uncovered ids, one per line)
"""
import json
import sys


def uncovered(checklist, workers):
    done = {r.get('id') for r in (workers or {}).get('results', []) if isinstance(r, dict)}
    return [c['id'] for c in checklist.get('checks', [])
            if isinstance(c, dict) and c.get('id') and c.get('required', True) and c['id'] not in done]


def main(argv):
    if len(argv) != 2:
        raise SystemExit(__doc__)
    try:
        checklist = json.load(open(argv[0], encoding='utf-8'))
    except (OSError, ValueError):
        return 0
    try:
        workers = json.load(open(argv[1], encoding='utf-8'))
    except (OSError, ValueError):
        workers = {}
    for cid in uncovered(checklist, workers):
        print(cid)
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
