#!/usr/bin/env python3
"""Safe helpers for streaming completed checklist lanes.

The streamed result is always a normal collated worker-packet document.  The
remaining checklist is derived by ID, so a later full execution cannot rerun a
lane that already wrote valid evidence.
"""
import json
import sys
from pathlib import Path


def read(path):
    value = json.loads(Path(path).read_text(encoding='utf-8'))
    if not isinstance(value, dict):
        raise ValueError('%s is not an object' % path)
    return value


def write(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + '\n', encoding='utf-8')


def remaining(checklist_path, completed_path, output):
    checklist, completed = read(checklist_path), read(completed_path)
    seen = {row.get('id') for row in completed.get('results', []) if isinstance(row, dict)}
    checks = [row for row in checklist.get('checks', [])
              if isinstance(row, dict) and row.get('id') not in seen]
    result = dict(checklist)
    result['checks'] = checks
    write(output, result)


def merge(output, *paths):
    workers, rows, seen = [], [], set()
    for path in paths:
        payload = read(path)
        if payload.get('kind') != 'checklist-execution-worker-packets':
            raise ValueError('%s is not a collated checklist worker document' % path)
        for row in payload.get('results', []):
            if not isinstance(row, dict) or not row.get('id'):
                raise ValueError('%s has an invalid result' % path)
            if row['id'] in seen:
                raise ValueError('%s duplicates check %s' % (path, row['id']))
            seen.add(row['id'])
            rows.append(row)
        workers.extend(payload.get('workers', []))
    write(output, {'schema': 'uncle.artifact/v1',
                   'kind': 'checklist-execution-worker-packets',
                   'workers': workers,
                   'results': sorted(rows, key=lambda row: row['id'])})


def main(argv):
    try:
        command = argv.pop(0)
        if command == 'remaining' and len(argv) == 3:
            remaining(*argv)
        elif command == 'merge' and len(argv) >= 2:
            merge(argv[0], *argv[1:])
        else:
            raise ValueError('usage: remaining CHECKLIST COMPLETED OUTPUT | merge OUTPUT INPUT...')
    except (OSError, ValueError, json.JSONDecodeError) as error:
        print('checklist stream: %s' % error, file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main(sys.argv[1:]))
