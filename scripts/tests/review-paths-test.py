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



class IgnoredPaths(unittest.TestCase):
    """A file committed before its ignore rule existed stays tracked forever.

    `--exclude-standard` only filters untracked files and `git diff` reports
    tracked ones whatever the rules say, so such a file kept reaching the
    review document and every agent prompt built from a project scan. Ignore
    rules are read back through git so they resolve per project: nested
    .gitignore files, negations and info/exclude all count.
    """

    def build(self, directory):
        root = Path(directory)

        def git(*args):
            subprocess.run(['git', *args], cwd=directory, check=True,
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

        git('init')
        git('config', 'commit.gpgsign', 'false')
        git('config', 'tag.gpgsign', 'false')
        git('config', 'user.name', 'Fixture')
        git('config', 'user.email', 'fixture@example.invalid')
        # `build/*`, not `build/`: git cannot re-include a file whose parent
        # directory is excluded, which is exactly why the canonical uncle block
        # is `.uncle/*` plus `!.uncle/docs/`.
        (root / '.gitignore').write_text('build/*\n!build/keep.txt\n')
        (root / 'src.py').write_text('kept')
        junk = root / 'build'
        junk.mkdir()
        (junk / 'out.o').write_text('binary noise')
        (junk / 'keep.txt').write_text('negated back in')
        git('add', '-f', '.gitignore', 'src.py', 'build/out.o', 'build/keep.txt')
        git('commit', '--no-gpg-sign', '-m', 'fixture')
        (root / 'src.py').write_text('changed')
        (junk / 'out.o').write_text('changed noise')
        (junk / 'keep.txt').write_text('changed but negated back in')
        return root

    def test_review_paths_drops_tracked_but_ignored(self):
        with tempfile.TemporaryDirectory() as directory:
            self.build(directory)
            previous = os.getcwd()
            try:
                os.chdir(directory)
                found = paths()
            finally:
                os.chdir(previous)
            self.assertIn('src.py', found)
            self.assertNotIn('build/out.o', found)
            # A negation puts the path back: the rules are read, not guessed.
            self.assertIn('build/keep.txt', found)

    def test_project_files_drops_tracked_but_ignored(self):
        sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'lib'))
        from project_paths import project_files
        with tempfile.TemporaryDirectory() as directory:
            self.build(directory)
            found = set(project_files(directory))
            self.assertIn('src.py', found)
            self.assertNotIn('build/out.o', found)
            self.assertIn('build/keep.txt', found)


if __name__=='__main__':unittest.main()
