import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'lib'))
from review_paths import paths, artifact_patterns

class Paths(unittest.TestCase):
    def test_real_changes_retained_history_and_old_files_excluded(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            def git(*args):
                subprocess.run(['git',*args],cwd=d,check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
            git('init');git('config','commit.gpgsign','false');git('config','tag.gpgsign','false')
            git('config','user.name','Fixture');git('config','user.email','fixture@example.invalid')
            (root/'tracked.txt').write_text('before')
            git('add','tracked.txt');git('commit','--no-gpg-sign','-m','fixture')
            (root/'tracked.txt').write_text('after')
            (root/'new file.txt').write_text('new')
            (root/'old.txt').write_text('old')
            (root/'FINAL_AUDIT.md').write_text('generated')
            evidence=root/'.uncle/verify/check.log';evidence.parent.mkdir(parents=True)
            evidence.write_text('generated evidence')
            history=root/'.uncle/workflow-history/run';history.mkdir(parents=True)
            for i in range(500): (history/str(i)).write_text('event')
            baseline=root/'.uncle/baseline';baseline.write_text('old.txt\n.uncle/baseline\n')
            previous=os.getcwd()
            try:
                os.chdir(d)
                self.assertEqual(paths(baseline),['new file.txt','tracked.txt'])
            finally:os.chdir(previous)

    def test_canonical_patterns(self):
        self.assertIn('FINAL_AUDIT.md',artifact_patterns())
        self.assertIn('.uncle/*',artifact_patterns())

if __name__=='__main__':unittest.main()
