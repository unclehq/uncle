"""Worktree branch naming and PR head (Issue 64, AC-3, T-2).

In a worktree on branch B, `change_pr_engine start` records B as the PR head;
`change_pr_engine branch-name` derives the pre-start name from the same
label_prefix/slug code. Fixtures run under an inherited signing configuration
that points at a failing fake signer; its log must stay absent.
"""
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
import fixture_repo  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
LIB = ROOT / 'scripts/lib/change-pr.sh'
SOURCE = LIB.read_text().split("<<'PY'", 1)[1].split('\n', 1)[1].split('\nPY\n', 1)[0]

GH_FAIL = '#!/usr/bin/env bash\nexit 1\n'
GH_LABEL = '''#!/usr/bin/env bash
printf '%s\\n' "$*" >> "$GH_CALLS"
echo '{"labels":[{"name":"enhancement"}]}'
'''


class WorktreeBranchTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.bin = self.root / 'bin'
        self.bin.mkdir()
        self.env, self.signer_log = fixture_repo.fake_signer(self.root, fixture_repo.isolated_env(
            PATH=str(self.bin) + os.pathsep + os.environ['PATH'], GH_CALLS=str(self.root / 'gh.log'),
            UNCLE_LIB_DIR=str(ROOT / 'scripts/lib')))
        self.gh(GH_FAIL)
        self.repo = fixture_repo.init_repo(self.root / 'repo', env=self.env)
        (self.repo / 'file.txt').write_text('one\n')
        fixture_repo.commit(self.repo, 'initial', env=self.env)
        bare = self.root / 'remote.git'
        subprocess.run([fixture_repo.REAL_GIT, 'init', '--bare', '-q', str(bare)], check=True, env=self.env)
        self.git('remote', 'add', 'origin', str(bare))
        self.git('push', '-q', 'origin', 'main')
        self.git('remote', 'set-head', 'origin', 'main')
        self.worktree = self.root / 'repo-issue-64'
        self.git('worktree', 'add', '-q', str(self.worktree), '-b', 'feat/x', 'HEAD')
        state = self.worktree / '.uncle/workflow'
        state.mkdir(parents=True)
        (state / 'state').write_text('64:ANALYZE\n')
        (state / 'origin').write_text('owner/repo\t64\tgh\n')
        (self.worktree / 'CHANGE_REQUEST.md').write_text('# Change\n\n## Summary\n\nAdd widget support\n')

    def gh(self, text):
        (self.bin / 'gh').write_text(text)
        (self.bin / 'gh').chmod(0o755)

    def git(self, *args, cwd=None):
        return fixture_repo.git(cwd or self.repo, *args, env=self.env)

    def engine(self, *args, cwd=None):
        return subprocess.run(['bash', '-c', '. "$1"; shift; change_pr_engine "$@"', 'test', str(LIB), *args],
                              cwd=cwd or self.worktree, env=self.env, text=True,
                              stdout=subprocess.PIPE, stderr=subprocess.STDOUT)

    def in_process(self):
        ns = {}
        exec(SOURCE[:SOURCE.rindex('\ntry:\n    main()')], ns)
        return ns

    def test_start_in_worktree_records_the_worktree_branch(self):
        result = self.engine('start')
        self.assertEqual(result.returncode, 0, result.stdout)
        journal = __import__('json').loads((self.worktree / '.uncle/workflow/pr/journal.json').read_text())
        self.assertEqual(journal['head_branch'], 'feat/x')
        self.assertEqual(journal['original_branch'], 'feat/x')
        self.assertIn('Branch: feat/x', result.stdout)
        self.assertEqual(self.git('branch', '--show-current', cwd=self.worktree), 'feat/x')
        self.assertEqual(self.git('branch', '--show-current'), 'main')
        self.assertFalse(self.signer_log.exists())

    def test_branch_name_matches_label_prefix_and_slug(self):
        title = 'Run an issue in a Git worktree!'
        ns = self.in_process()
        expected = ns['label_prefix']('owner/repo\t64\tgh') + ns['slug'](title)
        self.assertTrue(expected.startswith('uncle/'), expected)
        result = self.engine('branch-name', title, 'owner/repo', '64', 'gh')
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertEqual(result.stdout.strip().splitlines()[-1], expected)
        self.assertEqual(expected, 'uncle/run-an-issue-in-a-git-worktree')

        self.gh(GH_LABEL)
        with_label = self.engine('branch-name', title, 'owner/repo', '64', 'gh')
        self.assertEqual(with_label.returncode, 0, with_label.stdout)
        self.assertEqual(with_label.stdout.strip().splitlines()[-1], 'feat/run-an-issue-in-a-git-worktree')
        with patch.dict(os.environ, {'PATH': self.env['PATH'], 'GH_CALLS': self.env['GH_CALLS']}):
            self.assertEqual(ns['label_prefix']('owner/repo\t64\tgh') + ns['slug'](title),
                             'feat/run-an-issue-in-a-git-worktree')
        self.assertIn('issue view 64 --repo owner/repo --json labels', (self.root / 'gh.log').read_text())
        # A curl-fetched origin never asks gh.
        curl = self.engine('branch-name', title, 'owner/repo', '64', 'curl')
        self.assertEqual(curl.stdout.strip().splitlines()[-1], 'uncle/run-an-issue-in-a-git-worktree')
        self.assertFalse((self.worktree / '.uncle/workflow/pr').exists())
        self.assertFalse(self.signer_log.exists())

    def test_branch_name_does_not_touch_the_journal(self):
        self.engine('start')
        before = (self.worktree / '.uncle/workflow/pr/journal.json').read_bytes()
        result = self.engine('branch-name', 'Other title', 'owner/repo', '64', 'gh')
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertEqual((self.worktree / '.uncle/workflow/pr/journal.json').read_bytes(), before)
        self.assertFalse(self.signer_log.exists())


if __name__ == '__main__':
    unittest.main()
