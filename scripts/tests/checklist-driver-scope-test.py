#!/usr/bin/env python3
"""Regression tests for shrinking manual execution to non-driver evidence."""
import json
import subprocess
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
TOOL = ROOT / 'scripts/lib/checklist_driver_scope.py'


def check(identifier, action, section=''):
    return {
        'id': identifier, 'section': section, 'required': True,
        'exact_action': action, 'expected_result': 'Observed result.',
        'evidence_to_capture': 'Evidence.', 'exclusive_resources': [], 'depends_on': [],
    }


with tempfile.TemporaryDirectory() as directory:
    directory = Path(directory)
    checklist = directory / 'MANUAL_CHECKLIST.json'
    scope = directory / 'scope.json'
    proposed = directory / 'proposed.json'
    original = {
        'schema': 'uncle.artifact/v1', 'kind': 'manual-checklist',
        'checks': [
            check('MC-100', 'Read package.json and inspect the dependency lockfile.'),
            check('MC-200', 'Use Playwright to run the automated browser suite.'),
            check('MC-300', 'Open the page in a browser, click 2 + 3 =, and take a screenshot.'),
            check('MC-400', 'Use the supplied database client to create an order, then retrieve it through the service API.'),
        ],
    }
    checklist.write_text(json.dumps(original), encoding='utf-8')
    subprocess.run(['python3', '-B', str(TOOL), str(checklist), '--scope', str(scope),
                    '--proposed', str(proposed)], check=True, capture_output=True, text=True)
    reduced = json.loads(checklist.read_text(encoding='utf-8'))
    assert [row['id'] for row in reduced['checks']] == ['MC-300', 'MC-400'], reduced
    assert [row['id'] for row in json.loads(scope.read_text())['excluded']] == ['MC-100', 'MC-200']
    assert json.loads(proposed.read_text()) == original

print('checklist-driver-scope-test.py: driver rows are excluded while live interaction remains')
