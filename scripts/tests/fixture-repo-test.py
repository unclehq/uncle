#!/usr/bin/env python3
"""AC-25 / I-13: the fixture helper never reaches a signer, and the trap is real."""
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import fixture_repo  # noqa: E402


class FixtureRepoTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='fixture-repo-')
        self.addCleanup(self.temp.cleanup)
        self.tmp = Path(self.temp.name)
        self.env, self.log = fixture_repo.fake_signer(self.tmp)

    def test_helper_commits_without_invoking_the_signer(self):
        repo = fixture_repo.init_repo(self.tmp / 'repo', env=self.env)
        self.assertEqual(fixture_repo.git(repo, 'config', '--bool', 'commit.gpgsign', env=self.env), 'false')
        (repo / 'a.txt').write_text('a\n')
        sha = fixture_repo.commit(repo, 'first', env=self.env)
        self.assertEqual(len(sha), 40)
        self.assertNotIn('gpgsig', fixture_repo.git(repo, 'cat-file', 'commit', 'HEAD', env=self.env))
        self.assertFalse(self.log.exists(), 'the fake signer was invoked')

    def test_fake_signer_is_reachable_without_the_local_override(self):
        # Negative case: a commit that inherits the global `commit.gpgsign=true`
        # and lacks the helper's overrides reaches the trap and fails.
        repo = self.tmp / 'raw'
        repo.mkdir()
        subprocess.run([fixture_repo.REAL_GIT, 'init', '-q', '-b', 'main', str(repo)], check=True, env=self.env)
        subprocess.run([fixture_repo.REAL_GIT, 'config', 'user.email', 'f@example.test'], cwd=repo, check=True, env=self.env)
        subprocess.run([fixture_repo.REAL_GIT, 'config', 'user.name', 'F'], cwd=repo, check=True, env=self.env)
        result = subprocess.run([fixture_repo.REAL_GIT, 'commit', '--allow-empty', '-q', '-m', 'signed'],
                                cwd=repo, env=self.env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        self.assertNotEqual(result.returncode, 0, result.stderr)
        self.assertTrue(self.log.exists(), 'the trap signer was not reachable; the helper test proves nothing')


if __name__ == '__main__':
    unittest.main(verbosity=0)
