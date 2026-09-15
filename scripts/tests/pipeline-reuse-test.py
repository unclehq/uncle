import io,json,os
from pathlib import Path
import sys,tempfile,unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'lib'))
import approval_snapshot,check_reuse

class Reuse(unittest.TestCase):
    def test_approval_content_not_presentation(self):
        with tempfile.TemporaryDirectory() as d:
            old=os.getcwd();os.chdir(d)
            try:
                state=Path('.uncle/workflow');(state/'approvals').mkdir(parents=True)
                Path('app.txt').write_text('source')
                (state/'approvals/IMPLEMENTATION_REVIEW.sha256').write_text('approved')
                with patch.object(approval_snapshot,'paths',return_value=['app.txt']):
                    approval_snapshot.main('prepare',state);approval_snapshot.main('record',state)
                    (state/'IMPLEMENTATION_REVIEW.md').write_text('new formatting')
                    approval_snapshot.main('python3 --version',state)
                    Path('app.txt').write_text('modified')
                    with self.assertRaises(ValueError):approval_snapshot.main('python3 --version',state)
            finally:os.chdir(old)

    def test_reuse_is_opt_in_and_invalidates(self):
        with tempfile.TemporaryDirectory() as d:
            old=os.getcwd();os.chdir(d)
            try:
                state=Path('.uncle/workflow');state.mkdir(parents=True)
                Path('app.txt').write_text('source');Path('scopes').write_text('app.txt\n')
                self.assertIsNone(check_reuse.key('python3 --version'))
                policy=state/'check-reuse.json'
                policy.write_text(json.dumps({'python3 --version':{'deterministic_read_only':True,'always_run':False,'input_scopes':'scopes'}}))
                key=check_reuse.key('python3 --version');Path('log').write_text('assertion passed')
                check_reuse.record(key,'log');output=io.BytesIO()
                self.assertTrue(check_reuse.restore(key,output));self.assertIn(b'REUSED',output.getvalue())
                Path('app.txt').write_text('changed')
                self.assertNotEqual(key,check_reuse.key('python3 --version'))
                self.assertFalse(check_reuse.restore(check_reuse.key('python3 --version'),io.BytesIO()))
            finally:os.chdir(old)

if __name__=='__main__':unittest.main()
