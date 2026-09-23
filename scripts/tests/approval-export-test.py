import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

spec = importlib.util.spec_from_file_location('approval_export', Path(__file__).resolve().parents[1]/'lib/approval_export.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

CLEAN = '## Overall assessment\nNo findings.\n'


class ApprovalExport(unittest.TestCase):
    def test_known_document_refreshes_the_canonical_json(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            review = root/'ADVERSARIAL_REVIEW.md'
            review.write_text(CLEAN)
            self.assertTrue(module.refresh('ADVERSARIAL_REVIEW', review, root))
            stored = json.loads((root/'.uncle/workflow/documents/ADVERSARIAL_REVIEW.json').read_text())
            self.assertEqual(stored['findings'], [])
            # A human edit at the gate is picked up on the next approval.
            edited = ('## AR-001: Newly noticed gap\n- Severity: Low\n- References: x\n'
                      '- Failure: y\n- Fix: z\n- Verify: w\n' + CLEAN.replace('No findings.', 'One low finding.'))
            review.write_text(edited)
            self.assertTrue(module.refresh('ADVERSARIAL_REVIEW', review, root))
            stored = json.loads((root/'.uncle/workflow/documents/ADVERSARIAL_REVIEW.json').read_text())
            self.assertEqual(stored['findings'][0]['id'], 'AR-001')

    def test_unknown_document_is_a_silent_no_op(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            report = root/'BASELINE_REPORT.md'
            report.write_text('anything at all')
            self.assertFalse(module.refresh('BASELINE_REPORT', report, root))
            self.assertFalse((root/'.uncle/workflow/documents').exists())

    def test_invalid_edited_document_fails_closed_without_raising(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            review = root/'ADVERSARIAL_REVIEW.md'
            review.write_text('not a valid review at all, no heading')
            self.assertFalse(module.refresh('ADVERSARIAL_REVIEW', review, root))

    def test_plan_family_documents_refresh_from_their_own_render_format(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            plan = root/'PROJECT_PLAN.md'
            plan.write_text('Narrative text.\n\n## Verification commands\n\n```sh\npytest\n```\n')
            self.assertTrue(module.refresh('PROJECT_PLAN', plan, root))
            stored = json.loads((root/'.uncle/workflow/documents/PROJECT_PLAN.json').read_text())
            self.assertEqual(stored['narrative'], 'Narrative text.')
            self.assertEqual(stored['verification_commands'], 'pytest')

            # A human edit is picked up on the next approval.
            plan.write_text('Edited narrative.\n\n## Verification commands\n\n```sh\npytest -x\n```\n')
            self.assertTrue(module.refresh('PROJECT_PLAN', plan, root))
            stored = json.loads((root/'.uncle/workflow/documents/PROJECT_PLAN.json').read_text())
            self.assertEqual(stored['narrative'], 'Edited narrative.')
            self.assertEqual(stored['verification_commands'], 'pytest -x')

    def test_plan_family_document_written_directly_as_markdown_is_a_silent_no_op(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            plan = root/'PROJECT_PLAN.md'
            plan.write_text('# Project plan\n\nSome free-form prose an agent wrote directly.\n')
            self.assertFalse(module.refresh('PROJECT_PLAN', plan, root))
            self.assertFalse((root/'.uncle/workflow/documents').exists())

    def test_change_spec_and_change_plan_refresh(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            spec = root/'CHANGE_SPEC.md'
            spec.write_text('Narrative.\n\n## Acceptance criteria\n\n'
                             '| ID | Criterion | Verification |\n|---|---|---|\n'
                             '| AC-1 | Does the thing | Run it |\n')
            self.assertTrue(module.refresh('CHANGE_SPEC', spec, root))
            stored = json.loads((root/'.uncle/workflow/documents/CHANGE_SPEC.json').read_text())
            self.assertEqual(stored['acceptance_criteria'][0]['id'], 'AC-1')

            plan = root/'CHANGE_PLAN.md'
            plan.write_text('Narrative.\n\n## Adversarial review dispositions\n\n'
                             '| Finding | Disposition | Reason | Exact plan change |\n|---|---|---|---|\n'
                             '| AR-1 | Accepted | Valid gap | Added a check |\n')
            self.assertTrue(module.refresh('CHANGE_PLAN', plan, root))
            stored = json.loads((root/'.uncle/workflow/documents/CHANGE_PLAN.json').read_text())
            self.assertEqual(stored['dispositions'][0]['finding'], 'AR-1')


if __name__ == '__main__':
    unittest.main()
