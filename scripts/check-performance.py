#!/usr/bin/env python3
"""Show repeated check commands and timeouts from a project's recorded metrics.

Usage: python3 scripts/check-performance.py [project-directory]
Repetition is a candidate for investigation, not evidence a rerun was unnecessary.
"""
import json
from pathlib import Path
import sys


def report(root):
    groups = {}
    for path in sorted((Path(root) / '.uncle/workflow/metrics').glob('*.json')):
        try:
            row = json.loads(path.read_text())
        except (OSError, ValueError):
            continue
        if row.get('kind') != 'check':
            continue
        groups.setdefault(row.get('stage', '(unknown command)'), []).append(row)
    print('Check execution history (repeated runs may be required after changes)')
    for command, rows in sorted(groups.items(), key=lambda pair: -sum(float(r.get('elapsed_seconds', 0)) for r in pair[1])):
        total = sum(float(r.get('elapsed_seconds', 0)) for r in rows)
        timeouts = sum(r.get('process_exit') == 124 for r in rows)
        print(f'\n{command}\n  Runs: {len(rows)}; total: {total:.1f}s; timeouts: {timeouts}')
        for row in rows:
            print('  %.1fs exit=%s state=%s log=%s' % (float(row.get('elapsed_seconds', 0)),
                  row.get('process_exit'), row.get('workflow_state', ''), row.get('log', '')))
    if not groups:
        print('No check metrics recorded.')


if __name__ == '__main__':
    report(sys.argv[1] if len(sys.argv) > 1 else '.')
