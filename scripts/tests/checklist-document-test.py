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
