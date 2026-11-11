"""After freeze(root), uncle never edits the tracked .gitignore again (issue 260)."""
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
LIB = ROOT / 'scripts' / 'lib'
sys.path.insert(0, str(LIB))
import uncle_gitignore as ug

GIT = ['git', '-c', 'commit.gpgsign=false', '-c', 'tag.gpgsign=false', '-c', 'user.name=t', '-c', 'user.email=t@t']
LEGACY = 'node_modules/\n.uncle\n'
CLI = [sys.executable, str(LIB / 'uncle_gitignore.py')]


def git(cwd, *args):
    return subprocess.run([*GIT, *args], cwd=cwd, capture_output=True, text=True, check=True)


def repo(tmp, gitignore=LEGACY):
    git(tmp, 'init', '-q')
    git(tmp, 'config', 'commit.gpgsign', 'false')
    r = Path(tmp)
    if gitignore is not None:
        (r / '.gitignore').write_text(gitignore)
        git(tmp, 'add', '.gitignore')
        git(tmp, 'commit', '-q', '--no-gpg-sign', '-m', 'init')
    return r


def marker(r):
    return r / '.uncle' / 'workflow' / 'gitignore-frozen'


def clean_env():
    env = dict(os.environ)
    for k in list(env):
        if 'GITIGNORE' in k and 'UNCLE' in k:
            del env[k]
    return env


def run_cli(r):
    return subprocess.run([*CLI, str(r)], capture_output=True, text=True, env=clean_env())


class FreezeBehavior(unittest.TestCase):
    def test_unfrozen_ensure_normalizes_legacy(self):
        with tempfile.TemporaryDirectory() as t:
            r = repo(t)
            run_cli(r)
            self.assertNotEqual((r / '.gitignore').read_text(), LEGACY)

    def test_freeze_writes_marker_and_cli_leaves_gitignore_untouched(self):
        with tempfile.TemporaryDirectory() as t:
            r = repo(t)
            before = (r / '.gitignore').read_bytes()
            self.assertTrue(ug.freeze(str(r)))
            self.assertTrue(marker(r).is_file())
            run_cli(r)
            self.assertEqual((r / '.gitignore').read_bytes(), before)
            self.assertEqual(git(t, 'status', '--porcelain', '--', '.gitignore').stdout.strip(), '')

    def test_in_process_ensure_after_freeze_is_readonly(self):
        with tempfile.TemporaryDirectory() as t:
            r = repo(t)
            before = (r / '.gitignore').read_bytes()
            self.assertTrue(ug.freeze(str(r)))
            ug.ensure(str(r))
            self.assertEqual((r / '.gitignore').read_bytes(), before)

    def test_absent_gitignore_stays_absent(self):
        with tempfile.TemporaryDirectory() as t:
            r = repo(t, gitignore=None)
            ug.freeze(str(r))
            ug.ensure(str(r))
            run_cli(r)
            self.assertFalse((r / '.gitignore').exists())

    def test_marker_survives_second_freeze_and_is_idempotent(self):
        with tempfile.TemporaryDirectory() as t:
            r = repo(t)
            self.assertTrue(ug.freeze(str(r)))
            self.assertTrue(ug.freeze(str(r)))
            self.assertTrue(marker(r).is_file())


class SymlinkRefusal(unittest.TestCase):
    def _check(self, build):
        with tempfile.TemporaryDirectory() as t, tempfile.TemporaryDirectory() as out:
            r = repo(t)
            outside = Path(out)
            target = build(r, outside)
            before = target.read_bytes() if target.is_file() else None
            self.assertFalse(ug.freeze(str(r)))
            if before is None:
                self.assertFalse(target.exists())
            else:
                self.assertEqual(target.read_bytes(), before)
            # fail closed: ensure stays read-only in this process
            legacy = (r / '.gitignore').read_bytes()
            ug.ensure(str(r))
            self.assertEqual((r / '.gitignore').read_bytes(), legacy)

    def test_symlinked_uncle(self):
        def build(r, out):
            (r / '.uncle').symlink_to(out, target_is_directory=True)
            return out / 'workflow' / 'gitignore-frozen'
        self._check(build)

    def test_symlinked_workflow(self):
        def build(r, out):
            (r / '.uncle').mkdir()
            (r / '.uncle' / 'workflow').symlink_to(out, target_is_directory=True)
            return out / 'gitignore-frozen'
        self._check(build)

    def test_symlinked_leaf_not_truncated(self):
        def build(r, out):
            (r / '.uncle' / 'workflow').mkdir(parents=True)
            victim = out / 'victim.txt'
            victim.write_text('keep me')
            marker(r).symlink_to(victim)
            return victim
        self._check(build)

    def test_symlinked_leaf_dangling_not_created(self):
        def build(r, out):
            (r / '.uncle' / 'workflow').mkdir(parents=True)
            victim = out / 'absent.txt'
            marker(r).symlink_to(victim)
            return victim
        self._check(build)


class CallSites(unittest.TestCase):
    """Supplementary source checks: each publish/commit path references freeze."""

    def test_sites_reference_freeze(self):
        for rel in ('scripts/lib/change-pr.sh', 'scripts/from-issue.sh', 'scripts/stagegate.sh'):
            with self.subTest(rel):
                self.assertIn('freeze', (ROOT / rel).read_text())

    def test_from_issue_freezes_before_commit(self):
        text = (ROOT / 'scripts' / 'from-issue.sh').read_text()
        i = text.index('uncle_gitignore.freeze(')
        c = text.index('commit -q -m "uncle: issue', i - 2000)
        self.assertLess(i, c)

    def test_docs_note(self):
        self.assertIn('.gitignore', (ROOT / 'docs' / 'plan-duties.md').read_text())


if __name__ == '__main__':
    unittest.main()
