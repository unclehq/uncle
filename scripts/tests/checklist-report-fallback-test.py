#!/usr/bin/env python3
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / 'scripts/lib/checklist_report_fallback.py'


class ChecklistReportFallbackTests(unittest.TestCase):
    def test_json_renders_verification_and_defects(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); docs = root/'.uncle/docs'; docs.mkdir(parents=True)
            artifact = root/'.uncle/workflow/documents'; artifact.mkdir(parents=True)
            (artifact/'EXECUTE_CHECKLIST.json').write_text('{"schema":"uncle.artifact/v1","kind":"execute-checklist","results":[{"id":"MC-1","required":true,"status":"FAIL","evidence":"expected x"}]}')
            module = __import__('importlib').util
            spec = module.spec_from_file_location('fallback', SCRIPT); fallback = module.module_from_spec(spec); spec.loader.exec_module(fallback)
            fallback.render_from_json(root)
            self.assertIn('| MC-1 | YES | FAIL | expected x |', (docs/'VERIFICATION_REPORT.md').read_text())
            self.assertIn('## MC-1', (docs/'DEFECTS.md').read_text())

    def test_json_with_full_fields_renders_findings_and_defects(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); docs = root/'.uncle/docs'; docs.mkdir(parents=True)
            artifact = root/'.uncle/workflow/documents'; artifact.mkdir(parents=True)
            (artifact/'EXECUTE_CHECKLIST.json').write_text(
                '{"schema":"uncle.artifact/v1","kind":"execute-checklist","results":'
                '[{"id":"MC-1","required":true,"status":"FAIL","evidence":"expected 50, got 40",'
                '"action":"resized window","expected_result":"centered at 50px","actual_result":"centered at 40px",'
                '"defect_ids":["DEF-1"]}]}')
            import importlib.util
            spec = importlib.util.spec_from_file_location('fallback', SCRIPT); fallback = importlib.util.module_from_spec(spec); spec.loader.exec_module(fallback)
            fallback.render_from_json(root)
            report = (docs/'VERIFICATION_REPORT.md').read_text()
            self.assertIn('### MC-1', report)
            self.assertIn('**Action:** resized window', report)
            self.assertIn('**Expected result:** centered at 50px', report)
            self.assertIn('**Actual result:** centered at 40px', report)
            self.assertIn('**Defects:** DEF-1', report)
            defects = (docs/'DEFECTS.md').read_text()
            self.assertIn('## DEF-1', defects)
            self.assertIn('centered at 50px', defects)

    def test_markdown_findings_block_round_trips_into_json(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); docs = root/'.uncle/docs'; docs.mkdir(parents=True)
            (docs/'VERIFICATION_REPORT.md').write_text(
                '# Verification report\n\n## Findings\n\n### MC-1\n\n'
                '- **Action:** resized window\n- **Expected result:** centered at 50px\n'
                '- **Actual result:** centered at 40px\n- **Defects:** DEF-1\n\n'
                '## Acceptance gate\n\n| ID | Required | Status | Evidence |\n|---|---|---|---|\n'
                '| MC-1 | YES | FAIL | expected 50, got 40 |\n')
            import importlib.util
            spec = importlib.util.spec_from_file_location('fallback', SCRIPT); fallback = importlib.util.module_from_spec(spec); spec.loader.exec_module(fallback)
            fallback.export_from_markdown(root)
            import json
            payload = json.loads((root/'.uncle/workflow/documents/EXECUTE_CHECKLIST.json').read_text())
            row = payload['results'][0]
            self.assertEqual(row['action'], 'resized window')
            self.assertEqual(row['expected_result'], 'centered at 50px')
            self.assertEqual(row['actual_result'], 'centered at 40px')
            self.assertEqual(row['defect_ids'], ['DEF-1'])

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
