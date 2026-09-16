"""scripts/lib/worktree_runs.py (Issue 64, AC-6, T-3).

`runs()` lists every worktree holding `.uncle/workflow/state`, in git's order,
with the issue from `origin` or the state prefix. Fixtures run under an
inherited signing configuration that points at a failing fake signer.
"""
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'lib'))
import fixture_repo  # noqa: E402
import worktree_runs  # noqa: E402

SCRIPT = Path(__file__).resolve().parents[1] / 'lib' / 'worktree_runs.py'


class WorktreeRunsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.env, self.signer_log = fixture_repo.fake_signer(self.root)
        self.repo = fixture_repo.init_repo(self.root / 'proj', env=self.env)
        (self.repo / 'file.txt').write_text('one\n')
        fixture_repo.commit(self.repo, 'initial', env=self.env)
        self.saved = dict(os.environ)
        os.environ.clear()
        os.environ.update(self.env)
        self.addCleanup(self.restore)

    def restore(self):
        os.environ.clear()
        os.environ.update(self.saved)

    def worktree(self, name, state=None, origin=None, lock=False):
        path = self.root / name
        fixture_repo.git(self.repo, 'worktree', 'add', '-q', str(path), '-b', name, 'HEAD', env=self.env)
        workflow = path / '.uncle/workflow'
        workflow.mkdir(parents=True)
        if state is not None:
            (workflow / 'state').write_text(state + '\n')
        if origin is not None:
            (workflow / 'origin').write_text(origin + '\n')
        if lock:
            (workflow / 'lock').mkdir()
        return path

    def test_rows_ordering_and_identity(self):
        self.worktree('proj-issue-64', '64:IMPLEMENT', 'owner/repo\t64\tgh', lock=True)
        self.worktree('proj-issue-7', '7:COMPLETE', 'owner/repo\t7\tcurl')
        self.worktree('proj-hand', '42:IMPLEMENT')
        self.worktree('proj-bare', 'IMPLEMENT')
        self.worktree('proj-nostate')
        rows = worktree_runs.runs(str(self.repo))
        self.assertEqual(sorted((r['issue'], r['state'], r['locked'], Path(r['path']).name) for r in rows), sorted([
            ('64', 'IMPLEMENT', True, 'proj-issue-64'),
            ('7', 'COMPLETE', False, 'proj-issue-7'),
            ('42', 'IMPLEMENT', False, 'proj-hand'),
            ('?', 'IMPLEMENT', False, 'proj-bare'),
        ]))
        # Rows follow git's own listing order; the state-less worktree is omitted.
        listed = [Path(p).name for p in worktree_runs.worktrees(str(self.repo))]
        self.assertEqual(listed[0], 'proj')
        self.assertIn('proj-nostate', listed)
        self.assertEqual([Path(r['path']).name for r in rows], [n for n in listed if n not in ('proj', 'proj-nostate')])
        self.assertFalse(self.signer_log.exists())

    def test_main_checkout_with_state_is_listed_first(self):
        workflow = self.repo / '.uncle/workflow'
        workflow.mkdir(parents=True)
        (workflow / 'state').write_text('COMPLETE\n')
        (workflow / 'origin').write_text('owner/repo\t3\tgh\n')
        self.worktree('proj-issue-64', '64:ANALYZE', 'owner/repo\t64\tgh')
        rows = worktree_runs.runs(str(self.repo))
        self.assertEqual([r['issue'] for r in rows], ['3', '64'])
        self.assertEqual(rows[0]['state'], 'COMPLETE')
        self.assertFalse(self.signer_log.exists())

    def test_origin_wins_over_state_prefix_only_when_numeric(self):
        self.worktree('proj-a', '9:PLAN', 'owner/repo\tabc\tgh')
        self.worktree('proj-b', 'PLAN', 'owner/repo\t\tgh')
        rows = worktree_runs.runs(str(self.repo))
        self.assertEqual([r['issue'] for r in rows], ['9', '?'])

    def cli(self, project, env=None):
        return subprocess.run([sys.executable, str(SCRIPT), str(project)], env=env or self.env,
                              text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)

    def test_cli_prints_rows(self):
        wt = self.worktree('proj-issue-64', '64:IMPLEMENT', 'owner/repo\t64\tgh', lock=True)
        self.worktree('proj-issue-7', '7:COMPLETE', 'owner/repo\t7\tgh')
        result = self.cli(self.repo)
        self.assertEqual(result.returncode, 0, result.stdout)
        lines = result.stdout.splitlines()
        self.assertEqual(len(lines), 2)
        self.assertEqual(lines[0].split('\t')[:3], ['#64', 'IMPLEMENT', 'locked'])
        self.assertEqual(Path(lines[0].split('\t')[3]).resolve(), wt.resolve())
        self.assertEqual(lines[1].split('\t')[:3], ['#7', 'COMPLETE', 'idle'])

    def test_cli_no_runs_and_no_worktrees(self):
        result = self.cli(self.repo)
        self.assertEqual((result.returncode, result.stdout), (0, 'no runs\n'))
        nogit = dict(self.env, PATH=str(self.root / 'empty-bin'))
        (self.root / 'empty-bin').mkdir()
        with self.assertRaises(worktree_runs.WorktreeListError):
            os.environ['PATH'] = str(self.root / 'empty-bin')
            worktree_runs.runs(str(self.repo))
        os.environ['PATH'] = self.env['PATH']
        result = self.cli(self.repo, env=nogit)
        self.assertEqual((result.returncode, result.stdout), (0, 'no worktrees\n'))
        result = self.cli(self.root / 'not-a-repo')
        self.assertEqual((result.returncode, result.stdout), (0, 'no worktrees\n'))
        self.assertFalse(self.signer_log.exists())


if __name__ == '__main__':
    unittest.main()
