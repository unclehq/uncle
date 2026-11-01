#!/usr/bin/env python3
"""Empty checklist completion must not fabricate optional observations."""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

LIB = Path(__file__).resolve().parents[1] / 'lib'


def module(name):
    spec = importlib.util.spec_from_file_location(name, LIB / (name + '.py'))
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


REPORTS = module('execute_checklist_reports')
ACCEPTANCE = module('acceptance_json')


class EmptyChecklists(unittest.TestCase):
    def test_missing_checklist_scope_cannot_become_a_pass(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            state = root / '.uncle/workflow/documents'
            state.mkdir(parents=True)
            (state / 'MANUAL_CHECKLIST.json').write_text('{}')
            (state / 'EXECUTE_CHECKLIST_WORKERS.json').write_text('{"results": []}')
            with self.assertRaisesRegex(ValueError, 'explicit checks list'):
                REPORTS.main(root)
            self.assertFalse((state / 'VERIFICATION_REPORT.json').exists())

    def verify(self, checks, expected):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            state = root / '.uncle/workflow/documents'
            state.mkdir(parents=True)
            (root / '.uncle/docs').mkdir(parents=True)
            (state / 'MANUAL_CHECKLIST.json').write_text(json.dumps({'checks': checks}))
            (state / 'EXECUTE_CHECKLIST_WORKERS.json').write_text('{"results": []}')
            REPORTS.main(root)
            self.assertEqual(ACCEPTANCE.result(state / 'VERIFICATION_REPORT.json'), expected)
            rows = json.loads((state / 'EXECUTE_CHECKLIST.json').read_text())['results']
            for check in checks:
                row = next(row for row in rows if row['id'] == check['id'])
                self.assertEqual(row['status'], 'NOT RUN')
                self.assertEqual(row['required'], check['required'])
            return rows

    def test_optional_only_records_unobserved_item_and_passes_scope(self):
        self.verify([{'id': 'MC-1', 'required': False}], 'PASS')

    def test_empty_checklist_has_valid_acceptance(self):
        self.verify([], 'PASS')

    def test_missing_required_observation_still_blocks(self):
        rows = self.verify([{'id': 'MC-1', 'required': True}], 'BLOCKED-SETUP')
        self.assertFalse(any(row['status'] == 'PASS' for row in rows))

    def test_scope_identifier_does_not_replace_optional_check(self):
        self.verify([{'id': 'CHECKLIST-SCOPE', 'required': False}], 'PASS')


if __name__ == '__main__':
    unittest.main()
