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


class BindFailureIsExplained(unittest.TestCase):
    def test_the_driver_records_why_a_failed_bind_stopped_it(self):
        driver = (ROOT / 'scripts/change-workflow.sh').read_text()
        block = driver.split('        VALIDATE_AUDIT)', 1)[1].split('\n        WAIT_AUDIT_OVERRIDE)', 1)[0]
        bind = block.split('change_pr_engine bind', 1)[1].split('fi\n', 1)[0]
        self.assertIn('stop-reason', bind)
        self.assertIn('rerun FINAL_AUDIT', bind)


if __name__ == '__main__':
    unittest.main()
