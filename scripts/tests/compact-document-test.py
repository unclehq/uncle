from pathlib import Path
import sys,tempfile,unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'lib'))
from compact_document import replace
class Compact(unittest.TestCase):
    def test_safe_replacement_and_rejection(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);original=root/'report.md';candidate=root/'candidate.md'
            contract='## Findings\n| AC-1 | PASS | output.log:2 |\n```sh\nbash tests.sh\n```\nREADY\n'
            before=contract+'Repeated background. '*20
            original.write_text(before)
            for bad in ['Compacting once',contract.replace('AC-1','AC-2'),contract.replace('bash tests.sh','true'),contract.replace('READY','NOT READY')]:
                candidate.write_text(bad)
                with self.assertRaises(ValueError):replace(original,candidate)
                self.assertEqual(original.read_text(),before)
            candidate.write_text(contract)
            a,b=replace(original,candidate)
            self.assertGreater(a,b)
            self.assertEqual(original.read_text(),contract)
            self.assertEqual(len(list((root/'.uncle/workflow/compaction-backups').glob('report.md-*'))),1)
if __name__=='__main__':unittest.main()
