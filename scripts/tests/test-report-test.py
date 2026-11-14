#!/usr/bin/env python3
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('test_report', ROOT / 'scripts/lib/test_report.py')
reports = importlib.util.module_from_spec(spec); spec.loader.exec_module(reports)


class TestReportTests(unittest.TestCase):
    def payload(self, kind='automated-test-report'):
        return {'schema': 'uncle.artifact/v1', 'kind': kind,
                'commands': [{'command': 'node --test', 'status': 'PASS', 'output': '1 passed', 'requirements': ['AC-1']}],
                'coverage_gaps': [], 'next_action': 'None.'}

    def test_ingest_writes_canonical_json_and_markdown_view(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); path = root / '.uncle/docs/AUTOMATED_TEST_REPORT.md'; path.parent.mkdir(parents=True)
            path.write_text(json.dumps(self.payload()))
            reports.ingest(root, 'application', '.uncle/docs/AUTOMATED_TEST_REPORT.md')
            canonical = json.loads((root / '.uncle/workflow/documents/AUTOMATED_TEST_REPORT.json').read_text())
            self.assertEqual(canonical['kind'], 'automated-test-report')
            self.assertTrue(path.read_text().startswith('# Automated test report'))

    def test_markdown_is_rejected_as_non_authoritative(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); path = root / '.uncle/docs/AUTOMATED_TEST_REPORT.md'; path.parent.mkdir(parents=True)
            path.write_text('# Automated test report\n')
            with self.assertRaises(ValueError):
                reports.ingest(root, 'application', '.uncle/docs/AUTOMATED_TEST_REPORT.md')

    def test_change_report_uses_distinct_canonical_name(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); path = root / '.uncle/docs/CHANGE_TEST_REPORT.md'; path.parent.mkdir(parents=True)
            path.write_text(json.dumps(self.payload('change-test-report')))
            reports.ingest(root, 'change', '.uncle/docs/CHANGE_TEST_REPORT.md')
            self.assertEqual(json.loads((root / '.uncle/workflow/documents/CHANGE_TEST_REPORT.json').read_text())['kind'], 'change-test-report')


    def test_status_variants_of_the_reports_own_words_are_accepted_and_kept_visible(self):
        cases = {'BLOCKED-SETUP': 'BLOCKED', 'blocked_human': 'BLOCKED', 'Blocked-Impossible': 'BLOCKED', 'passed': 'PASS',
                 'FAILED': 'FAIL', 'Skipped': 'NOT RUN', 'not_run': 'NOT RUN', 'na': 'N/A', 'N/A': 'N/A', 'PASS': 'PASS'}
        for written, expected in cases.items():
            self.assertEqual(reports.normalize_status(written), expected, written)
        payload = self.payload('change-test-report')
        payload['commands'].append({'command': 'npx http-server .', 'status': 'BLOCKED-SETUP', 'output': 'no browser', 'requirements': []})
        reports._validate(payload, 'change')
        self.assertEqual(payload['commands'][1]['status'], 'BLOCKED')
        self.assertEqual(payload['commands'][1]['status_detail'], 'BLOCKED-SETUP')       # what the agent wrote is not lost
        self.assertNotIn('status_detail', payload['commands'][0])                         # an exact word is left alone

    def test_an_unclear_status_is_never_read_as_a_pass(self):
        for written in ('PARTIAL', 'PASS WITH WARNINGS', 'MOSTLY PASSING', 'UNKNOWN', '', None, 3, ['PASS']):
            self.assertIsNone(reports.normalize_status(written), repr(written))
        payload = self.payload()
        payload['commands'][0]['status'] = 'PARTIAL'
        with self.assertRaisesRegex(ValueError, r"command result 1 has invalid status 'PARTIAL' \(use one of: PASS, FAIL"):
            reports._validate(payload, 'application')

    def test_ingest_saves_the_canonical_status(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); path = root / '.uncle/workflow/documents/CHANGE_TEST_REPORT.json'; path.parent.mkdir(parents=True)
            payload = self.payload('change-test-report')
            payload['commands'][0]['status'] = 'BLOCKED-SETUP'
            path.write_text(json.dumps(payload))
            reports.ingest(root, 'change', '.uncle/workflow/documents/CHANGE_TEST_REPORT.json')
            saved = json.loads(path.read_text())['commands'][0]
            self.assertEqual((saved['status'], saved['status_detail']), ('BLOCKED', 'BLOCKED-SETUP'))
            self.assertIn('| BLOCKED |', (root / '.uncle/docs/CHANGE_TEST_REPORT.md').read_text())


if __name__ == '__main__':
    unittest.main()
