"""The draft checklist prompt drops everything that exists only after implementation and says what the draft is for."""
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts/lib'))
import checklist_draft_prompt as d

D = '.uncle/workflow/documents/'
FINAL = ('## Canonical inputs (binding)\n\nRead only these canonical JSON artifacts: `%sREQUIREMENTS_INTERPRETATION.json`, '
         '`%sPROJECT_PLAN.json`, `%sUPDATED_PROJECT_PLAN.json`, `%sADVERSARIAL_REVIEW.json`, and `%sTEST_REVIEW.json`, plus the completed driver '
         'record `.uncle/workflow/green-check.tsv`. Do not inspect any rendered Markdown view or enumerate directories.\n\nTreat the driver '
         'record as authoritative for dependency, build, unit, and automated-browser commands: cite it rather than proposing those commands '
         'again. Never require or mention Git history.\n\n## Assigned checklist lens\n\nFocus only on **coverage**.\n') % ((D,) * 5)
EARLY = FINAL.replace(', and `%sTEST_REVIEW.json`' % D, '')


class Draft(unittest.TestCase):
    def test_the_test_review_and_the_verification_record_are_gone(self):
        for text in (FINAL, EARLY):
            out = d.transform(text)
            self.assertNotIn('TEST_REVIEW', out)
            self.assertNotIn('green-check', out)
            self.assertNotIn('driver record', out)
            self.assertNotIn('cite it rather', out)

    def test_what_exists_before_implementation_is_kept(self):
        out = d.transform(FINAL)
        for name in ('REQUIREMENTS_INTERPRETATION.json', 'PROJECT_PLAN.json', 'UPDATED_PROJECT_PLAN.json', 'ADVERSARIAL_REVIEW.json'):
            self.assertIn(name, out)
        self.assertIn('## Assigned checklist lens', out)               # the lens heading the embedder splits on must survive
        self.assertIn('Never require or mention Git history', out)

    def test_the_note_says_the_draft_is_independent_and_will_be_reconciled(self):
        out = d.transform(FINAL)
        self.assertIn('## Draft before implementation (binding)', out)
        self.assertIn('independent of the implementation on purpose', out)
        self.assertIn('reconciler', out)
        self.assertIn('do not look for the application\'s source', out)

    def test_the_real_lens_prompt_loses_its_green_check_references(self):
        out = d.transform((ROOT / 'prompts/change/manual-checklist-review-worker.md').read_text())
        self.assertNotIn('green-check', out)
        self.assertNotIn('green\ncheck', out)

    def test_it_rewrites_the_file_in_place(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'lens.md'
            path.write_text(FINAL)
            self.assertEqual(d.main([str(path)]), 0)
            self.assertIn('Draft before implementation', path.read_text())
            self.assertNotIn('TEST_REVIEW', path.read_text())


if __name__ == '__main__':
    unittest.main()
