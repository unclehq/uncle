#!/usr/bin/env python3
"""Classify a test review that needs report reconciliation, not code repair."""
import json
import sys
from pathlib import Path

MARKERS = ('incomplete-handoff placeholder', 'unpopulated fallback', 'implementation stage omitted its required test handoff', 'no command result or requirement coverage is inferred by this fallback')

def evidence_handoff_only(payload, automated_report=None):
    if payload.get('schema') != 'uncle.artifact/v1' or payload.get('kind') != 'acceptance-report': return False
    rows = {row.get('id'): row for row in payload.get('rows', []) if isinstance(row, dict)}
    if rows.get('RESULTS', {}).get('status') != 'PASS': return False
    required = [row for row in rows.values() if row.get('required')]
    if not required or not any(row.get('status') in ('FAIL', 'NOT RUN') for row in required): return False
    text = (payload.get('narrative', '') + '\n' + '\n'.join(str(row.get('evidence', '')) for row in required)).lower()
    report_text = json.dumps(automated_report or {}).lower()
    return any(marker in text for marker in MARKERS) and 'implementation stage omitted its required test handoff' in report_text

def report_stale(report):
    """True only for the implementation fallback, never for a real failed test."""
    if report.get('schema') != 'uncle.artifact/v1' or report.get('kind') != 'automated-test-report':
        return False
    commands = report.get('commands', [])
    text = json.dumps(report).lower()
    return (any(isinstance(row, dict) and row.get('status') in ('NOT RUN', 'DRIVER PENDING') for row in commands)
            and 'implementation stage omitted its required test handoff' in text)

def mutation_evidence_gap(payload):
    """A bounded evidence task, not a source-code repair.

    Return true only when the driver suite passed and the review explicitly
    says representative defect mutation proof is missing.  A functional FAIL
    remains a normal stopped failure.
    """
    if payload.get('schema') != 'uncle.artifact/v1' or payload.get('kind') != 'acceptance-report':
        return False
    rows = [row for row in payload.get('rows', []) if isinstance(row, dict) and row.get('required')]
    if not rows or any(row.get('id') == 'RESULTS' and row.get('status') != 'PASS' for row in rows):
        return False
    failing = [str(row.get('evidence', '')).lower() for row in rows if row.get('status') == 'FAIL']
    return bool(failing) and all(('mutation' in text or 'defect-injection' in text) and
                                 ('proof' in text or 'fail' in text) for text in failing)

if __name__ == '__main__':
    try:
        if sys.argv[1] == '--report-stale':
            report = json.loads(Path(sys.argv[2]).read_text(encoding='utf-8'))
            raise SystemExit(0 if report_stale(report) else 1)
        if sys.argv[1] == '--mutation-evidence-gap':
            payload = json.loads(Path(sys.argv[2]).read_text(encoding='utf-8'))
            raise SystemExit(0 if mutation_evidence_gap(payload) else 1)
        payload = json.loads(Path(sys.argv[1]).read_text(encoding='utf-8'))
        report = json.loads(Path(sys.argv[2]).read_text(encoding='utf-8'))
        raise SystemExit(0 if evidence_handoff_only(payload, report) else 1)
    except (IndexError, OSError, ValueError, json.JSONDecodeError): raise SystemExit(1)
