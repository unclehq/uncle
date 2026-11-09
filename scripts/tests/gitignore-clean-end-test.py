"""ensure_exclude, the TUI helper and the publish/completion guard never leave or ship an unaudited tracked edit (issue 149)."""
import os
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts' / 'lib'))
import uncle_gitignore as ug

GIT = ['git', '-c', 'commit.gpgsign=false', '-c', 'tag.gpgsign=false', '-c', 'user.name=t', '-c', 'user.email=t@t']
BLOCK = '\n'.join([ug.BLOCK_START, *ug.CANONICAL, ug.BLOCK_END]) + '\n'


def git(cwd, *args, check=True):
    return subprocess.run([*GIT, *args], cwd=cwd, capture_output=True, text=True, check=check)


def repo(tmp, gitignore='node_modules/\n'):
    git(tmp, 'init', '-q')
    git(tmp, 'config', 'commit.gpgsign', 'false')
    git(tmp, 'config', 'tag.gpgsign', 'false')
    (Path(tmp) / '.gitignore').write_text(gitignore)
    git(tmp, 'add', '.gitignore')
    git(tmp, 'commit', '-q', '--no-gpg-sign', '-m', 'init')
    return Path(tmp)


def exclude(r):
    return (r / '.git' / 'info' / 'exclude')


class EnsureExclude(unittest.TestCase):
    def test_absent_info_dir_and_idempotent(self):
        with tempfile.TemporaryDirectory() as t:
            r = repo(t)
            import shutil
            shutil.rmtree(r / '.git' / 'info', ignore_errors=True)
            self.assertTrue(ug.ensure_exclude(str(r)))
            self.assertEqual(exclude(r).read_text(), BLOCK)
            self.assertFalse(ug.ensure_exclude(str(r)))
            self.assertEqual(exclude(r).read_text().count(ug.BLOCK_START), 1)

    def test_cases_replace_with_one_block_and_keep_user_lines(self):
        cases = {
            'partial': 'mine\n.uncle/*\n',
            'duplicated': 'mine\n' + BLOCK + BLOCK,
            'legacy': 'mine\n.uncle\n.workflow/\n.uncle/workflow-history/\n',
            'no-trailing-newline': 'mine',
        }
        for name, text in cases.items():
            with self.subTest(name), tempfile.TemporaryDirectory() as t:
                r = repo(t)
                exclude(r).parent.mkdir(exist_ok=True)
                exclude(r).write_text(text)
                self.assertTrue(ug.ensure_exclude(str(r)))
                out = exclude(r).read_text()
                self.assertEqual(out.count(ug.BLOCK_START), 1)
                self.assertEqual(out.count('!.uncle/docs/'), 1)
                self.assertIn('mine\n', out)
                self.assertTrue(out.endswith('\n'))
                self.assertFalse(ug.ensure_exclude(str(r)))

    def test_non_git_root_returns_false(self):
        with tempfile.TemporaryDirectory() as t:
            self.assertFalse(ug.ensure_exclude(t))

    def test_symlinked_exclude_is_refused(self):
        with tempfile.TemporaryDirectory() as t, tempfile.TemporaryDirectory() as o:
            r = repo(t)
            target = Path(o) / 'elsewhere'
            target.write_text('keep\n')
            exclude(r).parent.mkdir(exist_ok=True)
            if exclude(r).exists():
                exclude(r).unlink()
            exclude(r).symlink_to(target)
            self.assertFalse(ug.ensure_exclude(str(r)))
            self.assertEqual(target.read_text(), 'keep\n')

    def test_symlinked_info_dir_is_refused(self):
        with tempfile.TemporaryDirectory() as t, tempfile.TemporaryDirectory() as o:
            r = repo(t)
            import shutil
            shutil.rmtree(r / '.git' / 'info', ignore_errors=True)
            (r / '.git' / 'info').symlink_to(o)
            self.assertFalse(ug.ensure_exclude(str(r)))
            self.assertEqual(os.listdir(o), [])

    def test_visibility_root_and_linked_worktree(self):
        with tempfile.TemporaryDirectory() as t:
            r = repo(t)
            self.assertTrue(ug.ensure_exclude(str(r)))
            wt = Path(t + '-wt')
            git(r, 'worktree', 'add', '-q', str(wt), '-b', 'x')
            try:
                for where in (r, wt):
                    ign = git(where, 'check-ignore', '-q', '.uncle/workflow/x', check=False)
                    self.assertEqual(ign.returncode, 0, where)
                    for visible in ('.uncle/docs/PLAN.md', '.uncle/attestation.json'):
                        self.assertEqual(git(where, 'check-ignore', '-q', visible, check=False).returncode, 1, (where, visible))
                self.assertFalse(ug.ensure_exclude(str(wt)))
            finally:
                git(r, 'worktree', 'remove', '--force', str(wt), check=False)

    def test_legacy_bare_uncle_hides_docs_until_worktree_normalizes(self):
        with tempfile.TemporaryDirectory() as t:
            r = repo(t, '.uncle\n')
            ug.ensure_exclude(str(r))
            self.assertEqual(git(r, 'check-ignore', '-q', '.uncle/docs/PLAN.md', check=False).returncode, 0)
            self.assertTrue(ug.tracked_needs_normalization(str(r)))


class CallerEnumeration(unittest.TestCase):
    def test_only_worktree_creation_runs_ensure(self):
        offenders = []
        files = list((ROOT / 'scripts').rglob('*.py')) + list((ROOT / 'scripts').rglob('*.sh')) + [ROOT / 'uncle_tui.py']
        for f in files:
            if 'tests' in f.parts or f.name == 'uncle_gitignore.py':
                continue
            for n, line in enumerate(f.read_text(errors='replace').splitlines(), 1):
                # change-pr.sh `bind` normalizes inside a linked worktree only (guarded by the git-dir/common-dir comparison there).
                if f.name == 'change-pr.sh' and 'worktree-only' in line:
                    continue
                if re.search(r'uncle_gitignore\.ensure\(', line) or (re.search(r'python3?\b.*uncle_gitignore\.py', line) and 'worktrees.sh' != f.name
                                                                     and not line.lstrip().startswith('#') and 'import' not in line):
                    offenders.append(f'{f.relative_to(ROOT)}:{n}')
        self.assertEqual(offenders, [])


def tui():
    import importlib.util
    spec = importlib.util.spec_from_file_location('uncle_tui_gi', ROOT / 'uncle_tui.py')
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


class TuiHelper(unittest.TestCase):
    def test_tui_reload_leaves_gitignore_unchanged(self):
        m = tui()
        for start in ('node_modules/\n', '.uncle\n', '.uncle/*\n!.uncle/docs/\n'):
            with self.subTest(start), tempfile.TemporaryDirectory() as t:
                r = repo(t, start)
                for _ in range(3):
                    m._ensure_uncle_gitignored(str(r))
                self.assertEqual((r / '.gitignore').read_text(), start)
                self.assertEqual(git(r, 'status', '--porcelain', '--untracked-files=no').stdout, '')
                self.assertEqual(exclude(r).read_text().count(ug.BLOCK_START), 1)

    def test_deferral_notice_once_per_root(self):
        m = tui()
        import io, contextlib
        with tempfile.TemporaryDirectory() as t:
            r = repo(t, '.uncle\n')
            buf = io.StringIO()
            with contextlib.redirect_stderr(buf):
                for _ in range(3):
                    m._ensure_uncle_gitignored(str(r))
            lines = [l for l in buf.getvalue().splitlines() if '.gitignore' in l and 'worktree' in l]
            self.assertEqual(len(lines), 1)


class Guard(unittest.TestCase):
    def run_guard(self, cwd, tree=''):
        script = f'source {ROOT}/scripts/lib/change-pr.sh; assert_tree_matches_attested "{tree}"'
        return subprocess.run(['bash', '-c', script], cwd=cwd, capture_output=True, text=True)

    def attested(self, r):
        git(r, 'add', '-A')
        tree = git(r, 'write-tree').stdout.strip()
        git(r, 'reset', '-q')
        return tree

    def test_clean_passes_silently(self):
        with tempfile.TemporaryDirectory() as t:
            r = repo(t)
            tree = git(r, 'rev-parse', 'HEAD^{tree}').stdout.strip()
            out = self.run_guard(r, tree)
            self.assertEqual((out.returncode, out.stderr), (0, ''))
            self.assertEqual(self.run_guard(r).returncode, 0)

    def test_gitignore_managed_line_only_difference_fails(self):
        with tempfile.TemporaryDirectory() as t:
            r = repo(t, 'node_modules/\n.uncle/*\n')
            tree = git(r, 'rev-parse', 'HEAD^{tree}').stdout.strip()
            (r / '.gitignore').write_text('node_modules/\n.uncle/*\n.uncle\n')
            out = self.run_guard(r, tree)
            self.assertNotEqual(out.returncode, 0)
            self.assertIn('.gitignore', out.stderr)

    def test_no_attestation_dirty_tracked_fails_and_names_file(self):
        with tempfile.TemporaryDirectory() as t:
            r = repo(t)
            (r / '.gitignore').write_text('changed\n')
            out = self.run_guard(r)
            self.assertNotEqual(out.returncode, 0)
            self.assertIn('.gitignore', out.stderr)

    def test_extra_staged_paths_fail_naming_both(self):
        with tempfile.TemporaryDirectory() as t:
            r = repo(t)
            tree = git(r, 'rev-parse', 'HEAD^{tree}').stdout.strip()
            (r / '.uncle').mkdir()
            (r / '.uncle' / 'secret').write_text('k\n')
            (r / 'extra.txt').write_text('x\n')
            git(r, 'add', '-f', '.uncle/secret', 'extra.txt')
            out = self.run_guard(r, tree)
            self.assertNotEqual(out.returncode, 0)
            self.assertIn('.uncle/secret', out.stderr)
            self.assertIn('extra.txt', out.stderr)

    def test_untracked_artifacts_do_not_fail(self):
        with tempfile.TemporaryDirectory() as t:
            r = repo(t, ug.BLOCK_START and '\n'.join(ug.CANONICAL) + '\n')
            (r / '.uncle' / 'docs').mkdir(parents=True)
            (r / '.uncle' / 'docs' / 'PLAN.md').write_text('p\n')
            (r / 'new.txt').write_text('n\n')
            tree = self.attested(r)
            out = self.run_guard(r, tree)
            self.assertEqual((out.returncode, out.stderr), (0, ''))

    def test_ignored_docs_in_attested_tree_fail(self):
        with tempfile.TemporaryDirectory() as t:
            r = repo(t, '.uncle\n')
            (r / '.uncle' / 'docs').mkdir(parents=True)
            (r / '.uncle' / 'docs' / 'PLAN.md').write_text('p\n')
            git(r, 'add', '-f', '.uncle/docs/PLAN.md')
            tree = git(r, 'write-tree').stdout.strip()
            git(r, 'reset', '-q')
            out = self.run_guard(r, tree)
            self.assertNotEqual(out.returncode, 0)
            self.assertIn('PLAN.md', out.stderr)


if __name__ == '__main__':
    unittest.main()
