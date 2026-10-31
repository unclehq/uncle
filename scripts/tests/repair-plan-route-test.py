#!/usr/bin/env python3
"""Regression coverage for routing plan-owned verification failures out of source repair."""
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts/lib'))


def load(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / 'scripts/lib' / name)
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    return module


ROUTE = load('repair_plan_route.py')
CHECK = load('repair_check.py')


def blocker(kind='DESIGN'):
    return {'id': 'PB-1', 'class': kind, 'requirement_ids': [], 'restriction_ids': [],
            'evidence': 'the approved command is malformed', 'independent_work': 'none'}


class RepairPlanRoute(unittest.TestCase):
    def test_non_coding_blocker_routes_to_canonical_plan_packet(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); notes = root / 'notes.md'; classification = root / 'green.tsv'; output = root / 'packet.json'
            notes.write_text('```plan-blockers\n' + json.dumps([blocker()]) + '\n```\n')
            classification.write_text('REGRESSION\tgrep required content index.html\nPASS\ttest -f index.html\n')
            self.assertTrue(ROUTE.route(notes, classification, output))
            payload = json.loads(output.read_text())
            self.assertEqual(payload['kind'], 'repair-plan-revision')
            self.assertEqual(payload['failed_commands'], ['grep required content index.html'])

    def test_coding_blocker_stays_in_source_repair(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); notes = root / 'notes.md'
            notes.write_text('```plan-blockers\n' + json.dumps([blocker('CODING')]) + '\n```\n')
            self.assertFalse(ROUTE.route(notes, root / 'green.tsv', root / 'packet.json'))

    def test_fallback_repair_brief_never_has_empty_still_open(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); snapshot = root / 'snapshot.json'; output = root / 'brief.md'
            snapshot.write_text(json.dumps({'findings': {'(source tree)': {'row': '', 'paths': []}}}))
            CHECK.brief(str(root / 'missing.md'), snapshot, output, [])
            self.assertIn('**(source tree)**', output.read_text())


if __name__ == '__main__':
    unittest.main()
