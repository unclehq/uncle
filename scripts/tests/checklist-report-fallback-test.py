#!/usr/bin/env python3
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / 'scripts/lib/checklist_report_fallback.py'


class ChecklistReportFallbackTests(unittest.TestCase):
    def test_missing_reports_become_explicit_not_run_records(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            docs = root / '.uncle/docs'
            docs.mkdir(parents=True)
            (docs / 'MANUAL_CHECKLIST.md').write_text(
                '# Manual checklist\n\n### MC-1: First\n- Exact action: do it\n- Expected result: it works\n\n### MC-2: Second\n- Exact action: do it again\n- Expected result: it still works\n')
            subprocess.run(['python3', str(SCRIPT), '--project', str(root), '--missing-only'], check=True)
            report = (docs / 'VERIFICATION_REPORT.md').read_text()
            self.assertIn('| MC-1 | YES | NOT RUN |', report)
            self.assertIn('| MC-2 | YES | NOT RUN |', report)
            self.assertIn('## Acceptance gate', report)
            self.assertIn('CHECKLIST-EVIDENCE-MISSING', (docs / 'DEFECTS.md').read_text())

    def test_missing_only_preserves_a_real_report(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            docs = root / '.uncle/docs'
            docs.mkdir(parents=True)
            (docs / 'MANUAL_CHECKLIST.md').write_text('### MC-1: First\n- Exact action: x\n- Expected result: y\n')
            report = docs / 'VERIFICATION_REPORT.md'
            report.write_text('real evidence\n')
            subprocess.run(['python3', str(SCRIPT), '--project', str(root), '--missing-only'], check=True)
            self.assertEqual('real evidence\n', report.read_text())
            self.assertTrue((docs / 'DEFECTS.md').is_file())


if __name__ == '__main__':
    unittest.main()
