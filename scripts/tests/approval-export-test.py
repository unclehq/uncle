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
            plan = root/'PROJECT_PLAN.md'
            plan.write_text('anything at all')
            self.assertFalse(module.refresh('PROJECT_PLAN', plan, root))
            self.assertFalse((root/'.uncle/workflow/documents').exists())

    def test_invalid_edited_document_fails_closed_without_raising(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            review = root/'ADVERSARIAL_REVIEW.md'
            review.write_text('not a valid review at all, no heading')
            self.assertFalse(module.refresh('ADVERSARIAL_REVIEW', review, root))


if __name__ == '__main__':
    unittest.main()
