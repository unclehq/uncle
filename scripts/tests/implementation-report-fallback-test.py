#!/usr/bin/env python3
import json
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / 'scripts/lib/implementation_report_fallback.py'

class ImplementationReportFallbackTests(unittest.TestCase):
    def test_change_handoff_is_created_without_claiming_tests_passed(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); (root / '.uncle/docs').mkdir(parents=True)
            subprocess.run(['python3', str(SCRIPT), '--project', str(root), '--kind', 'change', '--missing-only'], check=True)
            text = (root / '.uncle/docs/CHANGE_TEST_REPORT.md').read_text()
            self.assertTrue((root / '.uncle/docs/IMPLEMENTATION_NOTES.md').is_file())
            self.assertIn('no command result', text)
            self.assertNotIn('PASS', text)

    def test_missing_only_preserves_real_handoff(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); docs = root / '.uncle/docs'; docs.mkdir(parents=True)
            notes = root / '.uncle/workflow/documents/IMPLEMENTATION_NOTES.json'; notes.parent.mkdir(parents=True); notes.write_text(json.dumps({
                'schema': 'uncle.artifact/v1', 'kind': 'implementation-notes',
                'changed_files': [], 'deviations': [], 'unresolved_concerns': ['real notes']}))
            subprocess.run(['python3', str(SCRIPT), '--project', str(root), '--kind', 'application', '--missing-only'], check=True)
            self.assertIn('real notes', (docs / 'IMPLEMENTATION_NOTES.md').read_text())
            self.assertTrue((root / '.uncle/workflow/documents/IMPLEMENTATION_NOTES.json').is_file())
            self.assertTrue((docs / 'AUTOMATED_TEST_REPORT.md').is_file())

if __name__ == '__main__':
    unittest.main()
