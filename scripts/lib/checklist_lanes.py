#!/usr/bin/env python3
"""Pack a checklist into lanes that run side by side: one worker per lane, no barriers.

The reviewer declares, per check, the resources it needs exclusively and the checks it depends on.
Barrier groups ("consecutive runs sharing no resource") turned that into rounds: a checklist with three
checks on one port ran as three sequential rounds, each waiting for the slowest worker, even though
only those three conflict with each other (noinit: 71 s for 15 checks).  What a declaration actually
says is narrower: checks that share a resource, or depend on one another, must not overlap, and nothing
else is constrained.  So:

  * checks linked by a shared resource or a dependency form a lane, executed in checklist order inside one
    worker session, so they can never overlap;
  * every check linked to nothing is free; free checks are pooled into small batches;
  * all lanes and batches run at the same time.

Conservative where it matters: a check that declared nothing at all conflicts with everything (the whole
checklist becomes one lane, i.e. one agent); a dependency that points forward, or at a check that is not
being run, makes the checklist one lane too.  Serial is always correct.

usage: checklist_lanes.py MANUAL_CHECKLIST.json BATCH_SIZE MAX_WORKERS   (one batch of check IDs per line)
"""
import json
import os
import re
import sys


def normalize(token):
    return re.sub(r'[\s:_-]+', ':', str(token).strip().strip('`*_').lower()).strip(':')


def shared_worker_resource(token):
    """Whether a declared resource is shareable by isolated worker sessions.

    Execute-checklist workers drive separate browser contexts against one
    driver-owned app server.  Serializing every row that says
    ``browser:system`` turns a broad UI checklist into one long parent call,
    even though the browser state is not shared.  Preserve serialization for
    a real user profile/visible-session reservation and every write resource.
    Set WORKFLOW_EXECUTE_CHECKLIST_BROWSER_FANOUT=0 for integrations that
    really do have one non-isolatable browser.
    """
    return (token == 'browser:system'
            and os.environ.get('WORKFLOW_EXECUTE_CHECKLIST_BROWSER_FANOUT', '1') == '1')


def lanes(checklist):
    """(lanes, free): multi-check lanes in order, and the independent checks, all in checklist order."""
    checks = [c for c in checklist.get('checks', []) if isinstance(c, dict) and c.get('id') and c.get('required', True)]
    ids = [c['id'] for c in checks]
    position = {cid: i for i, cid in enumerate(ids)}
    parent = list(range(len(ids)))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    def union(a, b):
        parent[find(a)] = find(b)

    resources = {}
    serial = False
    for i, check in enumerate(checks):
        # Older and weaker runner packets occasionally omit optional empty
        # arrays despite the worker schema.  An absent declaration means the
        # worker did not claim a write conflict; treating it as a global lock
        # collapses every later row into one slow lane.  Preserve every
        # explicit resource and dependency, but normalize omitted/invalid
        # resource declarations to the schema's empty-list default.
        declared = check.get('exclusive_resources')
        if not isinstance(declared, list):
            declared = []
        for token in declared:
            token = normalize(token)
            if token and not shared_worker_resource(token):
                resources.setdefault(token, []).append(i)
        for dep in check.get('depends_on') or []:
            if dep not in position:
                continue                                # a check that is not being run constrains nothing
            if position[dep] >= i:
                serial = True                           # forward or self edge: order is unclear
            else:
                union(i, position[dep])
    for members in resources.values():
        for other in members[1:]:
            union(members[0], other)
    if serial:
        return ([ids] if len(ids) > 1 else []), ([ids[0]] if len(ids) == 1 else [])
    groups = {}
    for i, cid in enumerate(ids):
        groups.setdefault(find(i), []).append(cid)
    ordered = sorted(groups.values(), key=lambda g: position[g[0]])
    return [g for g in ordered if len(g) > 1], [g[0] for g in ordered if len(g) == 1]


def batches(checklist, size=1, workers=8):
    size, workers = max(1, size), max(1, workers)
    multi, free = lanes(checklist)
    multi = [list(lane) for lane in multi]
    # Too many lanes for the worker limit: running two lanes one after the other is always safe.
    while len(multi) > workers:
        multi.sort(key=len)
        first, second = multi.pop(0), multi.pop(0)
        multi.append(first + second)
    out = list(multi)
    if free:
        room = max(1, workers - len(out))
        chunk = max(size, -(-len(free) // room))
        out += [free[i:i + chunk] for i in range(0, len(free), chunk)]
    return out


def main(argv):
    if len(argv) != 3:
        raise SystemExit(__doc__)
    try:
        with open(argv[0], encoding='utf-8') as handle:
            checklist = json.load(handle)
        size, workers = int(argv[1]), int(argv[2])
    except (OSError, ValueError):
        return 1
    for batch in batches(checklist, size, workers):
        print(' '.join(batch))
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
