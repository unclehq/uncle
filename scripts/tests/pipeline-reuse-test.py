import io,json,os,subprocess
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
                subprocess.run(['git','init','-q'],check=True)
                subprocess.run(['git','config','commit.gpgsign','false'],check=True)
                subprocess.run(['git','config','tag.gpgsign','false'],check=True)
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

    def test_record_is_not_raced_by_a_new_file_appearing_after_prepare(self):
        # calculator-local (2026-09-28): the approval snapshot's path *set*
        # was re-derived live (git diff/ls-files) on both prepare and record.
        # A background job -- backgrounded preflight is the default -- still
        # finishing between the two and touching the tree made record see a
        # different set than prepare did, raising and killing the whole
        # driver right after a correctly auto-recorded --unattended
        # approval. State was left parked at WAIT_IMPLEMENT_APPROVAL with no
        # process running -- indistinguishable from "still waiting."
        with tempfile.TemporaryDirectory() as d:
            old=os.getcwd();os.chdir(d)
            try:
                subprocess.run(['git','init','-q'],check=True)
                subprocess.run(['git','config','commit.gpgsign','false'],check=True)
                subprocess.run(['git','config','tag.gpgsign','false'],check=True)
                state=Path('.uncle/workflow');(state/'approvals').mkdir(parents=True)
                Path('app.txt').write_text('source')
                (state/'approvals/IMPLEMENTATION_REVIEW.sha256').write_text('approved')
                approval_snapshot.main('prepare',state)
                # A background job writes a new untracked file in the window
                # between prepare and record.
                Path('background-output.txt').write_text('written by a still-finishing background job')
                approval_snapshot.main('record',state)
                recorded=json.loads((state/'approvals/IMPLEMENTATION_REVIEW.inputs.json').read_text())
                self.assertNotIn('background-output.txt',recorded['inputs'])
            finally:os.chdir(old)

    def test_approval_ignores_generated_uncle_evidence(self):
        with tempfile.TemporaryDirectory() as d:
            old=os.getcwd();os.chdir(d)
            try:
                subprocess.run(['git','init','-q'],check=True)
                subprocess.run(['git','config','commit.gpgsign','false'],check=True)
                subprocess.run(['git','config','tag.gpgsign','false'],check=True)
                state=Path('.uncle/workflow');(state/'approvals').mkdir(parents=True)
                evidence=Path('.uncle/verify/check.log');evidence.parent.mkdir(parents=True)
                Path('app.txt').write_text('source');evidence.write_text('first run')
                (state/'green-check.current.tsv').write_text('PASS\tcheck\n')
                (state/'approvals/IMPLEMENTATION_REVIEW.sha256').write_text('approved')
                approval_snapshot.main('prepare',state);approval_snapshot.main('record',state)
                evidence.write_text('rerun output')
                approval_snapshot.main('check',state)
                Path('app.txt').write_text('modified')
                with self.assertRaises(ValueError):approval_snapshot.main('check',state)
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
