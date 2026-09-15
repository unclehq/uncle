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
if __name__=='__main__':unittest.main()
