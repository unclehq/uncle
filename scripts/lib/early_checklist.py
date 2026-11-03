#!/usr/bin/env python3
"""Checklist rows run early, and which of their results the real checklist stage may reuse.

The checklist is drafted beside implementation by reviewers who never see the code; the reconciliation that follows the build leaves nearly
every row as drafted (run 12: 14 of 14 identical). So the draft rows can be executed against the application as soon as its source has
landed, and a row that fails there can be fixed while the worker that wrote the code still holds the context, instead of in a repair loop
that reruns the whole test review and the whole checklist (about 2.5 to 3 minutes and $3 each).

This module is the logic and nothing else: row identity, what failed, what is reusable, how results merge. No processes, no model.

A result is reused only when all of these hold, and otherwise the row simply runs again:
  * the early result is a PASS, or BLOCKED-HUMAN (a row that is for a person to judge stays so; a worker only rediscovers that, and
    reusing it cannot turn a blocked row into a pass). A failure and any other blocked result (setup, impossible) are always seen fresh;
  * the row is the same row: action, expected result and exclusive resources hash to the same key;
  * the application's files are the same as when it ran (tree_fingerprint.py --app, which leaves out tests and documents).

usage: early_checklist.py slice IN.json OUT.json [ID ...]
       early_checklist.py changed DRAFT.json FINAL.json OUT.json    the final rows the draft did not have or that reconciliation changed
       early_checklist.py exclude REDUCED.json DONE_WORKERS.json OUT.json    REDUCED without the rows DONE_WORKERS already has results for
       early_checklist.py failures WORKERS.json                 JSON list of the FAIL rows, with their evidence
       early_checklist.py manifest CHECKLIST.json WORKERS.json APP_FINGERPRINT OUT.json
       early_checklist.py plan FINAL.json MANIFEST.json EARLY_WORKERS.json APP_FINGERPRINT_NOW REUSED.json REDUCED.json
       early_checklist.py merge-early EARLY_WORKERS.json NEW_WORKERS.json OUT.json     newer results replace older ones, by id
       early_checklist.py merge FINAL.json REUSED.json FRESH.json|- OUT.json            the reused and the freshly executed rows, together
exit:  plan exits 3 when nothing is reusable; changed exits 3 when no row changed.
"""
import hashlib
import json
from pathlib import Path
import sys

SCHEMA = 'uncle.artifact/v1'
WORKERS_KIND = 'checklist-execution-worker-packets'
EARLY_SOURCE = 'early-checklist'


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False)


def row_key(row):
    """Identity of a checklist row: what is done, what is expected, and what it needs exclusively. Not its id."""
    return hashlib.sha256(canonical({
        'action': str(row.get('exact_action', '')).strip(),
        'expected': str(row.get('expected_result', '')).strip(),
        'resources': sorted(str(r) for r in (row.get('exclusive_resources') or [])),
    }).encode('utf-8')).hexdigest()


def checks(document):
    return [row for row in (document or {}).get('checks', []) if isinstance(row, dict) and row.get('id')]


def results(workers):
    return [r for r in (workers or {}).get('results', []) if isinstance(r, dict) and r.get('id')]


def slice_document(document, ids=None):
    """The checklist with only the named rows, in their original order; every row when `ids` is None."""
    keep = None if ids is None else set(ids)
    out = {key: value for key, value in document.items() if key != 'checks'}
    out['checks'] = [row for row in checks(document) if keep is None or row['id'] in keep]
    return out


def failures(workers):
    """The rows that failed (FAIL only: a blocked row is not one a code change can fix), with the evidence a fixer needs."""
    return [{key: r.get(key, '') for key in ('id', 'status', 'action', 'expected_result', 'actual_result', 'evidence')}
            for r in results(workers) if r.get('status') == 'FAIL']


def manifest(checklist, workers, app_fingerprint):
    """What the early execution covered: each row's key, which rows passed, and the application it ran against."""
    passed = sorted(r['id'] for r in results(workers) if r.get('status') == 'PASS')
    blocked_human = sorted(r['id'] for r in results(workers) if r.get('status') == 'BLOCKED-HUMAN')
    return {'schema': SCHEMA, 'kind': 'early-checklist-manifest', 'app_fingerprint': app_fingerprint,
            'rows': {row['id']: row_key(row) for row in checks(checklist)}, 'passed': passed, 'blocked_human': blocked_human}


def plan(final, early_manifest, early_workers, app_fingerprint_now):
    """(reused, reduced): the early PASS results the final checklist may reuse, and the checklist of rows that still have to run."""
    reused = {}
    if early_manifest and app_fingerprint_now and early_manifest.get('app_fingerprint') == app_fingerprint_now:
        early_keys = early_manifest.get('rows') or {}
        recorded = {'PASS': set(early_manifest.get('passed') or []), 'BLOCKED-HUMAN': set(early_manifest.get('blocked_human') or [])}
        by_id = {r['id']: r for r in results(early_workers)}
        for row in checks(final):
            result = by_id.get(row['id'])
            # The manifest must name the row under the very status the result carries, so a result file edited after the fact is not trusted.
            if result and row['id'] in recorded.get(result.get('status'), ()) and early_keys.get(row['id']) == row_key(row):
                reused[row['id']] = result
    return reused, slice_document(final, [row['id'] for row in checks(final) if row['id'] not in reused])


def changed(draft, final):
    """The final rows that cannot reuse an early result: new to the draft, or reworded by the reconciliation. Known the moment the
    reconciled checklist exists, so they can start without waiting for the early rows to finish."""
    draft_keys = {row['id']: row_key(row) for row in checks(draft)}
    return slice_document(final, [row['id'] for row in checks(final) if draft_keys.get(row['id']) != row_key(row)])


def exclude(reduced, done):
    """The rows still to run once `done` has results for some of them."""
    finished = {r['id'] for r in results(done)}
    return slice_document(reduced, [row['id'] for row in checks(reduced) if row['id'] not in finished])


def merge_early(old, new):
    """The early results with the re-run of some rows laid over them: newer replaces older, by id."""
    by_id = {r['id']: r for r in results(old)}
    by_id.update({r['id']: r for r in results(new)})
    sources = {w.get('source'): w for w in (old or {}).get('workers', [])}
    sources.update({w.get('source'): w for w in (new or {}).get('workers', [])})
    return {'schema': SCHEMA, 'kind': WORKERS_KIND, 'workers': [sources[k] for k in sorted(sources, key=str)],
            'results': [by_id[k] for k in sorted(by_id)]}


def merge(final, reused, fresh):
    """The workers document the real stage records: reused early results marked as such, beside the rows executed now."""
    by_id = {r['id']: r for r in results(fresh)}
    for identifier, result in reused.items():
        if identifier not in by_id:
            by_id[identifier] = dict(result, source=EARLY_SOURCE)
    workers = [w for w in (fresh or {}).get('workers', []) if w.get('source') != EARLY_SOURCE]
    reused_count = sum(1 for r in by_id.values() if r.get('source') == EARLY_SOURCE)
    if reused_count:
        workers.append({'source': EARLY_SOURCE, 'status': 'ok', 'result_count': reused_count})
    wanted = {row['id'] for row in checks(final)}
    return {'schema': SCHEMA, 'kind': WORKERS_KIND, 'workers': workers,
            'results': [by_id[k] for k in sorted(by_id) if k in wanted]}


def load(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def save(path, value):
    Path(path).write_text(json.dumps(value, indent=2, sort_keys=True) + '\n', encoding='utf-8')


def main(argv):
    if not argv:
        raise SystemExit(__doc__)
    command, rest = argv[0], argv[1:]
    if command == 'slice' and len(rest) >= 2:
        save(rest[1], slice_document(load(rest[0]), rest[2:] or None))
        return 0
    if command == 'changed' and len(rest) == 3:
        rows = changed(load(rest[0]), load(rest[1]))
        save(rest[2], rows)
        return 0 if checks(rows) else 3
    if command == 'exclude' and len(rest) == 3:
        save(rest[2], exclude(load(rest[0]), load(rest[1])))
        return 0
    if command == 'failures' and len(rest) == 1:
        found = failures(load(rest[0]))
        if found:
            print(json.dumps(found))
        return 0
    if command == 'manifest' and len(rest) == 4:
        save(rest[3], manifest(load(rest[0]), load(rest[1]), rest[2]))
        return 0
    if command == 'plan' and len(rest) == 6:
        reused, reduced = plan(load(rest[0]), load(rest[1]), load(rest[2]), rest[3])
        save(rest[4], reused)
        save(rest[5], reduced)
        total = len(checks(load(rest[0])))
        print('reusing %d of %d early results' % (len(reused), total))
        return 0 if reused else 3
    if command == 'merge-early' and len(rest) == 3:
        save(rest[2], merge_early(load(rest[0]), load(rest[1])))
        return 0
    if command == 'merge' and len(rest) == 4:
        save(rest[3], merge(load(rest[0]), load(rest[1]), None if rest[2] == '-' else load(rest[2])))
        return 0
    raise SystemExit(__doc__)


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
