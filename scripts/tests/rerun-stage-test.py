import json
from pathlib import Path
import sys
import tempfile
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'lib'))
from rerun_stage import consume

class Rerun(unittest.TestCase):
    def test_review_rerun_preserves_artifact_and_prerequisites(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);state=root/'.uncle/workflow';(state/'approvals').mkdir(parents=True)
            (state/'state').write_text('VALIDATE_ADVERSARIAL_REVIEW\n')
            (state/'rerun-request.json').write_text(json.dumps({'stage':'adversarial-review'}))
            for name in ['BASELINE_REPORT','CHANGE_SPEC','ADVERSARIAL_REVIEW','IMPLEMENTATION_REVIEW']:
                (state/'approvals'/f'{name}.sha256').write_text('approved')
            (root/'ADVERSARIAL_REVIEW.md').write_text('existing findings')
            consume(root,'change')
            self.assertEqual((state/'state').read_text().strip(),'ADVERSARIAL_REVIEW')
            self.assertTrue((state/'approvals/BASELINE_REPORT.sha256').exists())
            self.assertFalse((state/'approvals/IMPLEMENTATION_REVIEW.sha256').exists())
            self.assertEqual((root/'ADVERSARIAL_REVIEW.md').read_text(),'existing findings')
            self.assertEqual(len(list((state/'stage-reruns').glob('*/ADVERSARIAL_REVIEW.md'))),1)
    def test_unknown_does_not_change_state(self):
        with tempfile.TemporaryDirectory() as d:
            state=Path(d)/'.uncle/workflow';state.mkdir(parents=True)
            (state/'state').write_text('COMPLETE')
            (state/'rerun-request.json').write_text('{"stage":"bogus"}')
            with self.assertRaises(ValueError):consume(d,'app')
            self.assertEqual((state/'state').read_text(),'COMPLETE')
if __name__=='__main__':unittest.main()
