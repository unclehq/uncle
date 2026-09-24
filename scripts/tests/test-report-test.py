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


if __name__ == '__main__':
    unittest.main()
