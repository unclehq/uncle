#!/usr/bin/env python3
"""Which workers the updated-plan panel launches, one `name<TAB>ids` line each.

The dispositions lens reads every adversarial finding, which makes it the longest worker
in the panel (calculator-local: 147-329 s against 75-250 s for the others).  Past
SLICE findings it is split into `dispositions-1`, `dispositions-2`, ... each owning a
consecutive run of finding ids, and the panel waits only for the slowest slice.  At or
under SLICE findings -- and for a review whose ids cannot be read -- there is a single
`dispositions` worker with no id list, which is exactly the panel before this existed.
"""
import json
import os
import sys

LENSES = ('ownership', 'verification', 'scope')
SLICE = 8


def finding_ids(path):
    try:
        with open(path, encoding='utf-8') as handle:
            findings = json.load(handle).get('findings')
    except (OSError, ValueError, AttributeError):
        return []
    ids = []
    for finding in findings if isinstance(findings, list) else []:
        value = finding.get('id') if isinstance(finding, dict) else None
        if isinstance(value, str) and value.strip() and value.strip() not in ids:
            ids.append(value.strip())
    return ids


def workers(path, size=SLICE):
    ids = finding_ids(path)
    size = max(1, size)
    if len(ids) <= size:
        rows = [('dispositions', [])]
    else:
        count = -(-len(ids) // size)
        per = -(-len(ids) // count)  # even slices: 9 findings make 5+4, not 8+1
        rows = [('dispositions-%d' % (n + 1), ids[n * per:(n + 1) * per]) for n in range(count)]
    return rows + [(lens, []) for lens in LENSES]


def main(argv):
    if not argv:
        raise SystemExit('usage: updated_plan_slices.py ADVERSARIAL_REVIEW.json')
    try:
        size = int(os.environ.get('WORKFLOW_UPDATED_PLAN_SLICE') or SLICE)
    except ValueError:
        size = SLICE
    for name, ids in workers(argv[0], size):
        print('%s\t%s' % (name, ','.join(ids)))
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
