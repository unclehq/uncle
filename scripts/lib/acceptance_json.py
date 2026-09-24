#!/usr/bin/env python3
"""Workflow routing verdicts from canonical acceptance JSON, never Markdown."""
import json
import sys
from pathlib import Path


def result(path, expected=()):
    payload = json.loads(Path(path).read_text(encoding='utf-8'))
    if payload.get('schema') != 'uncle.artifact/v1' or payload.get('kind') != 'acceptance-report':
        return 'UNKNOWN'
    rows = payload.get('rows')
    if not isinstance(rows, list):
        return 'UNKNOWN'
    seen, required = set(), {}
    for row in rows:
        if not isinstance(row, dict) or not row.get('id') or row['id'] in seen or not row.get('evidence'):
            return 'UNKNOWN'
        seen.add(row['id'])
        if row.get('required') is True:
            required[row['id']] = row.get('status')
    if not required or any(identifier not in required for identifier in expected):
        return 'UNKNOWN'
    statuses = set(required.values())
    if 'FAIL' in statuses: return 'REPAIR'
    if 'BLOCKED-IMPOSSIBLE' in statuses: return 'BLOCKED-IMPOSSIBLE'
    if statuses & {'BLOCKED', 'BLOCKED-SETUP', 'NOT RUN', 'N/A'}: return 'BLOCKED-SETUP'
    if 'BLOCKED-HUMAN' in statuses: return 'BLOCKED-HUMAN'
    return 'PASS' if statuses <= {'PASS'} else 'UNKNOWN'

def ids(path, status):
    payload = json.loads(Path(path).read_text(encoding='utf-8'))
    if payload.get('schema') != 'uncle.artifact/v1' or payload.get('kind') != 'acceptance-report':
        return ''
    return '\n'.join(str(row['id']) for row in payload.get('rows', [])
                     if isinstance(row, dict) and row.get('required') is True and row.get('status') == status)


if __name__ == '__main__':
    try:
        if len(sys.argv) == 4 and sys.argv[1] == '--ids':
            print(ids(sys.argv[2], sys.argv[3]))
        else:
            print(result(sys.argv[1], sys.argv[2:]))
    except (IndexError, OSError, ValueError, json.JSONDecodeError):
        print('UNKNOWN')
