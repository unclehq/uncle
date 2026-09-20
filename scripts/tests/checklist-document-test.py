import sys,tempfile,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'lib'))
from checklist_document import validate
class Document(unittest.TestCase):
    def test_rejects_progress_and_filename_but_accepts_checks(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'checklist'
            for text in ['MANUAL_CHECKLIST.md','Compacting pass 1.','## MC-1\nIncomplete']:
                p.write_text(text)
                with self.assertRaises(ValueError):validate(p)
            p.write_text('## MC-1\nExact action: Open page\nExpected result: Greeting\n')
            self.assertEqual(len(validate(p)),1)

    def test_bold_prose_labels_are_normalized_in_place(self):
        # A real checklist: complete, correct content under a self-hosted
        # reviewer's own prose-style labels instead of the required bullet
        # fields. The content must survive untouched; only the labels change.
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / 'checklist'
            p.write_text(
                '## MC-1 — Field order\n'
                '**Checks:** Open an existing stage in the TUI.\n'
                '**Pass condition:** Field order matches spec.\n'
                '## MC-2 — Colon outside the bold\n'
                '**Steps**: Create a new stage.\n'
                '**Pass condition**: Catalogue is vendor-specific.\n')
            checks = validate(p)
            self.assertEqual(len(checks), 2)
            fixed = p.read_text()
            self.assertIn('- Exact action: Open an existing stage in the TUI.', fixed)
            self.assertIn('- Expected result: Field order matches spec.', fixed)
            self.assertIn('- Exact action: Create a new stage.', fixed)
            self.assertIn('- Expected result: Catalogue is vendor-specific.', fixed)
            self.assertNotIn('**', fixed, 'no stray markup should survive the relabel')
            # Already normalized: a second validate() must be a no-op, not
            # rewrite the file again or drop content.
            before = p.read_text()
            validate(p)
            self.assertEqual(p.read_text(), before)

    def test_normalization_never_masks_a_genuinely_incomplete_checklist(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / 'checklist'
            p.write_text('## MC-1 — No content at all\nJust prose, no fields.\n')
            with self.assertRaises(ValueError):
                validate(p)
            self.assertEqual(p.read_text(), '## MC-1 — No content at all\nJust prose, no fields.\n')
    def test_categorized_check_ids_preserve_dependencies(self):
        from checklist_document import validate_text
        rows = validate_text("""# Checklist
| ID | Excl | Deps | Action | Expected |
|---|---|---|---|---|
| MC-S-1 | none | none | Read evidence | All assertions present |
| MC-UV-1 | browser:system | MC-S-1 | View page | Greeting visible |
| MC-H-2 | browser:system | MC-UV-1 | Open file | Page renders |
""")
        self.assertEqual([r.id for r in rows], ['MC-S-1','MC-UV-1','MC-H-2'])
        self.assertEqual(rows[1].depends, ['MC-S-1'])
        self.assertEqual(rows[2].depends, ['MC-UV-1'])

    def test_native_correction_is_bounded_and_only_for_invalid_checklists(self):
        from types import SimpleNamespace
        from native_kimi import checklist_correction
        stage=SimpleNamespace(side='reviewer',stage='manual-checklist',final_answer='The checklist is written. Key points: MC-1')
        self.assertIn('entire MANUAL_CHECKLIST.md',checklist_correction(stage,0))
        self.assertEqual(checklist_correction(stage,1),'')
        stage.final_answer='## MC-1\nExact action: Open page\nExpected result: Greeting\n'
        self.assertEqual(checklist_correction(stage,0),'')
        stage.final_answer='A summary'
        stage.stage='final-audit'
        self.assertEqual(checklist_correction(stage,0),'')
        stage.stage='manual-checklist'
        stage.side='agent'
        self.assertEqual(checklist_correction(stage,0),'')
if __name__=='__main__':unittest.main()
