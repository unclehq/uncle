import importlib.util
from pathlib import Path
import tempfile
import unittest

spec = importlib.util.spec_from_file_location(
    'acceptance_context', Path(__file__).resolve().parents[1] / 'lib/acceptance_context.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class AcceptanceContext(unittest.TestCase):
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
