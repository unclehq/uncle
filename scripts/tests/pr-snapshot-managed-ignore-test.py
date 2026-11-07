"""An `.uncle` line that uncle itself adds to a tracked .gitignore during the audit is not a change to the project: the snapshot the audit is bound to ignores it."""
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SOURCE = (ROOT / 'scripts/lib/change-pr.sh').read_text().split("<<'PY'", 1)[1].split('\n', 1)[1].split('\nPY\n', 1)[0]
NS = {}
exec(SOURCE[:SOURCE.rindex('\ntry:\n    main()')], NS)


class ManagedIgnore(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.old = os.getcwd()
        os.chdir(self.tmp.name)
        self.addCleanup(os.chdir, self.old)
        os.environ['UNCLE_LIB_DIR'] = str(ROOT / 'scripts/lib')
        self.addCleanup(os.environ.pop, 'UNCLE_LIB_DIR', None)
        for cmd in (['git', 'init', '-q'], ['git', 'config', 'user.email', 'a@b.c'], ['git', 'config', 'user.name', 'a'],
                    ['git', 'config', 'commit.gpgsign', 'false']):
            subprocess.run(cmd, check=True)
        Path('.uncle/workflow').mkdir(parents=True)
        Path('.uncle/docs').mkdir(parents=True)
        Path('.uncle/docs/FINAL_AUDIT.md').write_text('audit\n')
        Path('.gitignore').write_text('node_modules\n')
        Path('app.js').write_text('x\n')
        subprocess.run(['git', 'add', '.'], check=True)
        subprocess.run(['git', 'commit', '--no-gpg-sign', '-q', '-m', 'base'], check=True)
        # the real checkout's .uncle state is ignored; a bare checkout here has none to hide, so ignore it as uncle does
        self.reviewed = NS['snapshot']()

    def test_an_added_uncle_line_does_not_change_the_comparison_snapshot(self):
        Path('.gitignore').write_text('node_modules\n.uncle\n')
        self.assertEqual(NS['snapshot'](), self.reviewed)

    def test_every_managed_spelling_is_tolerated(self):
        Path('.gitignore').write_text('node_modules\n.uncle/*\n!.uncle/docs/\n')
        self.assertEqual(NS['snapshot'](), self.reviewed)

    def test_a_real_ignore_change_still_counts(self):
        Path('.gitignore').write_text('node_modules\ndist\n')
        self.assertNotEqual(NS['snapshot'](), self.reviewed)

    def test_a_real_source_change_still_counts(self):
        Path('app.js').write_text('changed\n')
        self.assertNotEqual(NS['snapshot'](), self.reviewed)

    def test_the_commit_tree_keeps_the_exact_bytes(self):
        before = NS['snapshot'](True)
        Path('.gitignore').write_text('node_modules\n.uncle\n')
        self.assertNotEqual(NS['snapshot'](True), before)


class BindNormalizesTheIgnoreFile(unittest.TestCase):
    def test_bind_settles_a_stray_bare_uncle_line_before_binding_the_commit_tree(self):
        # A bare `.uncle` after the canonical block re-ignores .uncle/docs/, so publish refused the audited tree.
        src = (ROOT / 'scripts/lib/change-pr.sh').read_text()
        bind = src.split("elif action == 'bind':", 1)[1].split("elif action == 'artifact':", 1)[0]
        self.assertLess(bind.index('uncle_gitignore.ensure'), bind.index('commit_tree=snapshot(True)'))
        sys.path.insert(0, str(ROOT / 'scripts/lib'))
        import uncle_gitignore
        with tempfile.TemporaryDirectory() as tmp:
            Path(tmp, '.gitignore').write_text('hello\n' + '\n'.join(uncle_gitignore.CANONICAL) + '\n.uncle\n')
            uncle_gitignore.ensure(tmp)
            lines = Path(tmp, '.gitignore').read_text().splitlines()
        self.assertNotIn('.uncle', lines)
        self.assertEqual(lines, ['hello'] + uncle_gitignore.CANONICAL)


class PrePublishAssertion(unittest.TestCase):
    """The publish guard runs before handoff commits the tree: uncommitted tracked edits are expected then."""

    def run_assert(self, mode, tree_extra=''):
        src = (ROOT / 'scripts/lib/change-pr.sh').read_text()
        func = src.split('assert_tree_matches_attested() {', 1)[1].split('\n}\n', 1)[0]
        with tempfile.TemporaryDirectory() as tmp:
            sh = lambda c: subprocess.run(c, shell=True, cwd=tmp, check=True, capture_output=True, text=True).stdout.strip()
            sh('git init -q && git config user.email a@b.c && git config user.name a && git config commit.gpgsign false')
            Path(tmp, 'main.c').write_text('old\n')
            sh('git add . && git commit -q -m base')
            Path(tmp, 'main.c').write_text('new\n')
            Path(tmp, 'FINAL_AUDIT.md').write_text('audit\n')
            Path(tmp, '.uncle/docs').mkdir(parents=True)
            Path(tmp, '.uncle/docs/FINAL_AUDIT.md').write_text('audit\n')
            sh('git add -A && git write-tree > /tmp/.tree_x')
            tree = sh('git write-tree')
            sh('git reset -q && rm FINAL_AUDIT.md')
            res = subprocess.run(['bash', '-c', 'assert_tree_matches_attested() {' + func + '\n}\nassert_tree_matches_attested ' + tree + ' ' + mode],
                                 cwd=tmp, capture_output=True, text=True)
            return res.returncode, res.stderr

    def test_uncommitted_change_and_unwritten_audit_copy_pass_before_handoff(self):
        rc, err = self.run_assert('pre')
        self.assertEqual(rc, 0, err)

    def test_a_stale_tracked_root_audit_copy_passes_when_the_attested_copy_is_this_runs_audit(self):
        src = (ROOT / 'scripts/lib/change-pr.sh').read_text()
        func = src.split('assert_tree_matches_attested() {', 1)[1].split('\n}\n', 1)[0]
        for audit, expect_ok in (('new audit\n', True), ('something else\n', False)):
            with tempfile.TemporaryDirectory() as tmp:
                sh = lambda c: subprocess.run(c, shell=True, cwd=tmp, check=True, capture_output=True, text=True).stdout.strip()
                sh('git init -q && git config user.email a@b.c && git config user.name a && git config commit.gpgsign false')
                Path(tmp, 'FINAL_AUDIT.md').write_text('earlier run\n')
                Path(tmp, '.gitignore').write_text('.uncle/*\n!.uncle/docs/\n')
                sh('git add . && git commit -q -m base')
                Path(tmp, '.uncle/docs').mkdir(parents=True)
                Path(tmp, '.uncle/docs/FINAL_AUDIT.md').write_text('new audit\n')
                Path(tmp, 'FINAL_AUDIT.md').write_text(audit)
                sh('git add -A -f . && git write-tree > /tmp/.t2')
                tree = sh('git write-tree')
                sh('git reset -q')
                Path(tmp, 'FINAL_AUDIT.md').write_text('earlier run\n')   # stale tracked copy on disk
                res = subprocess.run(['bash', '-c', 'assert_tree_matches_attested() {' + func + '\n}\nassert_tree_matches_attested ' + tree + ' pre'],
                                     cwd=tmp, capture_output=True, text=True)
                self.assertEqual(res.returncode == 0, expect_ok, (audit, res.stderr))
        os.path.exists('/tmp/.t2') and os.unlink('/tmp/.t2')

    def test_the_post_commit_check_still_refuses_dirty_tracked_files(self):
        rc, err = self.run_assert('')
        self.assertNotEqual(rc, 0)
        self.assertIn('tracked file not clean', err)


class BindFailureIsExplained(unittest.TestCase):
    def test_the_driver_records_why_a_failed_bind_stopped_it(self):
        driver = (ROOT / 'scripts/change-workflow.sh').read_text()
        block = driver.split('        VALIDATE_AUDIT)', 1)[1].split('\n        WAIT_AUDIT_OVERRIDE)', 1)[0]
        bind = block.split('change_pr_engine bind', 1)[1].split('fi\n', 1)[0]
        self.assertIn('stop-reason', bind)
        self.assertIn('rerun FINAL_AUDIT', bind)


if __name__ == '__main__':
    unittest.main()
