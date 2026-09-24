#!/usr/bin/env python3
"""Classify a test review that needs report reconciliation, not code repair."""
import json
import sys
from pathlib import Path

MARKERS = ('incomplete-handoff placeholder', 'unpopulated fallback', 'no command result or requirement coverage is inferred by this fallback')

def evidence_handoff_only(payload, automated_report=''):
    if payload.get('schema') != 'uncle.artifact/v1' or payload.get('kind') != 'acceptance-report': return False
    rows = {row.get('id'): row for row in payload.get('rows', []) if isinstance(row, dict)}
    if rows.get('RESULTS', {}).get('status') != 'PASS': return False
    required = [row for row in rows.values() if row.get('required')]
    if not required or not any(row.get('status') in ('FAIL', 'NOT RUN') for row in required): return False
    text = (payload.get('narrative', '') + '\n' + '\n'.join(str(row.get('evidence', '')) for row in required)).lower()
    return any(marker in text for marker in MARKERS) and 'implementation stage omitted its required test handoff' in automated_report.lower()

if __name__ == '__main__':
    try:
        payload = json.loads(Path(sys.argv[1]).read_text(encoding='utf-8'))
        report = Path(sys.argv[2]).read_text(encoding='utf-8')
        raise SystemExit(0 if evidence_handoff_only(payload, report) else 1)
    except (IndexError, OSError, ValueError, json.JSONDecodeError): raise SystemExit(1)
