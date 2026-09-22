import importlib.util
from pathlib import Path
import tempfile
import unittest

spec = importlib.util.spec_from_file_location(
    'acceptance_context', Path(__file__).resolve().parents[1] / 'lib/acceptance_context.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class AcceptanceContext(unittest.TestCase):
    def test_json_report_is_ingested_rendered_and_exported(self):
        import json
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            report = root/'VERIFICATION_REPORT.md'
            payload = {'schema': 'uncle.artifact/v1', 'kind': 'acceptance-report', 'narrative': 'All checks ran.',
                       'rows': [{'id': 'MC-1', 'required': True, 'status': 'PASS', 'evidence': 'ran ok'}]}
            report.write_text(json.dumps(payload))
            self.assertTrue(module.ingest_json(report, root))
            text = report.read_text()
            self.assertIn('## Acceptance gate', text)
            self.assertIn('| MC-1 | YES | PASS | ran ok |', text)
            self.assertIn('All checks ran.', text)
            stored = json.loads((root/'.uncle/workflow/documents/VERIFICATION_REPORT.json').read_text())
            self.assertEqual(stored['rows'][0]['id'], 'MC-1')

    def test_json_report_rejects_wrong_schema(self):
        import json
        with tempfile.TemporaryDirectory() as d:
            report = Path(d)/'VERIFICATION_REPORT.md'
            report.write_text(json.dumps({'schema': 'uncle.artifact/v1', 'kind': 'final-audit'}))
            with self.assertRaises(ValueError):
                module.ingest_json(report, Path(d))

    def test_non_json_report_is_not_ingested(self):
        with tempfile.TemporaryDirectory() as d:
            report = Path(d)/'VERIFICATION_REPORT.md'
            report.write_text('## Acceptance gate\n\n| ID | Required | Status | Evidence |\n|---|---|---|---|\n| MC-1 | YES | PASS | ok |\n')
            self.assertFalse(module.ingest_json(report, Path(d)))

    def test_a_real_report_shape_is_relocated_and_remapped(self):
        # A real stuck run: the checklist agent wrote the true, complete
        # per-check table under "## Summary" using Check ID/Description/
        # Required/Status columns -- no Evidence column at all -- instead
        # of the required "## Acceptance gate" table. The driver's own
        # one-shot format retry reproduced the identical wrong shape a
        # second time.
        text = (
            '# Verification Report\n\n'
            '## Summary\n\n'
            '| Check ID | Description | Required | Status |\n'
            '|----------|-------------|----------|--------|\n'
            '| MC-1 | Groovy background aesthetic judgment | YES | BLOCKED-HUMAN |\n'
            '| MC-2 | Decimal point keyboard input | YES | PASS |\n'
            '| MC-6 | Backspace on negative single digit | NO | FAIL |\n\n'
            '## Defects\n\nD-1.\n')
        normalized = module.normalize_acceptance_shape(text)
        self.assertIn('## Acceptance gate', normalized)
        self.assertIn('| ID | Required | Status | Evidence |', normalized)
        self.assertIn('| MC-1 | YES | BLOCKED-HUMAN | Groovy background aesthetic judgment |', normalized)
        self.assertIn('| MC-6 | NO | FAIL | Backspace on negative single digit |', normalized)
        self.assertIn('## Defects', normalized)  # unrelated content preserved

    def test_wrong_heading_only_is_relocated(self):
        text = (
            '## Summary\n\n'
            '| ID | Required | Status | Evidence |\n'
            '|---|---|---|---|\n'
            '| MC-1 | YES | PASS | works |\n')
        normalized = module.normalize_acceptance_shape(text)
        self.assertIn('## Acceptance gate', normalized)
        self.assertIn('| MC-1 | YES | PASS | works |', normalized)

    def test_narrative_evidence_used_when_no_description_or_evidence_column(self):
        text = (
            '## Summary\n\n'
            '| ID | Required | Status |\n'
            '|---|---|---|\n'
            '| MC-1 | YES | PASS |\n\n'
            '## Status per Group\n\n'
            '1. **MC-1** (keyboard) -> **PASS** - decimal input works end to end.\n')
        normalized = module.normalize_acceptance_shape(text)
        self.assertIn('| MC-1 | YES | PASS | decimal input works end to end. |', normalized)

    def test_an_existing_acceptance_gate_section_is_left_alone(self):
        # Not this function's job: acceptance_problem reports the real defect.
        text = '## Acceptance gate\n\n| ID | Required | Status | Evidence |\n|---|---|---|---|\n'
        self.assertEqual(module.normalize_acceptance_shape(text), text)

    def test_execution_records_repair_a_three_column_summary_gate(self):
        text = ('# Verification report\n\n'
                '### MC-1: first\n- **Status:** PASS\n\n'
                '### MC-2: second\n- **Status:** BLOCKED-SETUP\n\n'
                '## Acceptance gate\n'
                '| Gate | Criteria | Status |\n|---|---|---|\n'
                '| Summary | two checks | PASS |\n')
        normalized = module.normalize_acceptance_shape(text)
        self.assertIn('| MC-1 | YES | PASS | Result recorded in MC-1 above. |', normalized)
        self.assertIn('| MC-2 | YES | BLOCKED-SETUP | Result recorded in MC-2 above. |', normalized)
        self.assertNotIn('| Gate | Criteria | Status |', normalized)

    def test_no_recognizable_table_is_left_alone(self):
        text = '## Summary\n\nEverything passed, trust me.\n'
        self.assertEqual(module.normalize_acceptance_shape(text), text)

    def test_two_competing_tables_are_never_guessed_between(self):
        text = (
            '## Summary A\n\n| ID | Required | Status | Evidence |\n|---|---|---|---|\n| MC-1 | YES | PASS | a |\n\n'
            '## Summary B\n\n| ID | Required | Status | Evidence |\n|---|---|---|---|\n| MC-1 | YES | FAIL | b |\n')
        self.assertEqual(module.normalize_acceptance_shape(text), text)

    def test_main_writes_the_file_only_when_changed(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / 'VERIFICATION_REPORT.md'
            p.write_text('## Summary\n\n| ID | Required | Status | Evidence |\n|---|---|---|---|\n| MC-1 | YES | PASS | ok |\n')
            self.assertTrue(module.main(str(p)))
            self.assertIn('## Acceptance gate', p.read_text())
            self.assertFalse(module.main(str(p)))


if __name__ == '__main__':
    unittest.main()
