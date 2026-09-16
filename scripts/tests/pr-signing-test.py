"""Signing remains a user action, including interrupted handoff resumes.
Unsigned commits are automatic only when the effective config says so."""
import contextlib
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[2]
SOURCE = (ROOT / 'scripts/lib/change-pr.sh').read_text().split("<<'PY'", 1)[1].split('\n', 1)[1].split('\nPY\n', 1)[0]
NOSIGN = ['-c', 'commit.gpgsign=false', '-c', 'tag.gpgsign=false']


def result(code, out='', err=''):
    return Mock(returncode=code, stdout=out, stderr=err)


class SigningTests(unittest.TestCase):
    def test_legacy_origin_is_verified_before_resolving_repository(self):
        import json
        self.j.update(origin='owner/repo\t34\n', original_branch='main')
        self.ns['git'] = Mock(return_value='origin')
        self.ns['remote_identity'] = Mock(return_value='owner/repo')
        for issue, expected in [({'number':35,'html_url':'https://github.com/owner/repo/issues/35'}, 'Legacy issue'),
                                ({'number':34,'html_url':'https://github.com/owner/repo/issues/34'}, 'verified origin')]:
            def gh(*args):
                if args[0] == 'api': return json.dumps(issue)
                raise ValueError('verified origin')
            self.ns['gh'] = gh
            with self.assertRaisesRegex(ValueError, expected):
                self.ns['resolve'](self.j)
            self.assertEqual(self.j['origin'], 'owner/repo\t34\n')

    def setUp(self):
        self.ns = {}
        exec(SOURCE[:SOURCE.rindex('\ntry:\n    main()')], self.ns)
        self.real = dict(git=self.ns['git'], head=self.ns['head'], subprocess=self.ns['subprocess'])
        self.j = dict(original_head='old', intended_head='', commit_tree='tree', title='Change', manual_signing=True)
        self.git = Mock(side_effect=lambda *a, **k: {
            'rev-parse': 'tree', 'rev-list': 'new old', 'verify-commit': '', 'read-tree': ''
        }[a[0]])
        self.ask = Mock()
        self.ns.update(head=lambda: 'new', git=self.git, ask=self.ask, save=Mock(), validate=Mock())

    def mock_git_runs(self, *results):
        # Each subprocess.run call in prepare_commit, in order: config, then commit.
        self.ns['subprocess'] = Mock()
        self.ns['subprocess'].run = Mock(side_effect=list(results))
        return self.ns['subprocess'].run

    def test_existing_signed_commit_is_verified_without_prompt(self):
        self.ns['manual_signed_commit'](self.j)
        self.ask.assert_not_called()
        self.git.assert_any_call('verify-commit', 'new')
        self.assertEqual(self.j['manual_signed_head'], 'new')
        self.assertNotIn('manual_signing', self.j)

    def test_no_commit_prompts_once_without_executing_signing(self):
        self.ns['head'] = lambda: 'old'
        with self.assertRaisesRegex(ValueError, 'No new commit'):
            self.ns['manual_signed_commit'](self.j)
        self.assertEqual(self.ask.call_count, 2)
        self.assertIn('git commit -S', self.ask.call_args_list[0].args[0])
        self.git.assert_not_called()

    def test_user_commit_after_prompt_is_verified(self):
        self.ns['head'] = Mock(side_effect=['old', 'new'])
        self.ns['manual_signed_commit'](self.j)
        self.ask.assert_called_once()
        self.git.assert_any_call('verify-commit', 'new')

    def test_invalid_existing_commit_does_not_request_another_commit(self):
        self.git.side_effect = lambda *a, **k: 'wrong tree'
        with self.assertRaisesRegex(ValueError, 'differs from the audited'):
            self.ns['manual_signed_commit'](self.j)
        self.ask.assert_not_called()
        self.assertTrue(self.j['manual_signing'])

    def test_missing_remote_requests_destination_instead_of_silent_exit(self):
        self.j.update(origin='owner/repo\t34\tgh\n', original_branch='main')
        self.git.side_effect = lambda *a, **k: ''
        self.ask.return_value = ''
        with self.assertRaisesRegex(ValueError, 'destination not configured'):
            self.ns['resolve'](self.j)
        self.assertIn('No Git remote', self.ask.call_args.args[0])
        self.assertFalse(any(call.args[:2] == ('remote', 'add') for call in self.git.call_args_list))

    def signing_config(self, returncode=0, stdout='', stderr=''):
        self.ns['subprocess'] = Mock()
        self.ns['subprocess'].run.return_value = Mock(returncode=returncode, stdout=stdout, stderr=stderr)
        self.j.pop('manual_signing')

    def test_unsigned_commit_is_automatic(self):
        # T-1 / AC-1: signing off creates the commit itself; nobody is asked.
        run = self.mock_git_runs(result(0, 'false\n'), result(0))
        self.ns['head'] = lambda: 'auto'
        self.ns['prepare_commit'](self.j)
        self.ask.assert_not_called()
        self.git.assert_called_once_with('read-tree', 'tree')
        self.assertEqual(run.call_args_list[1].args[0],
                         ['git', 'commit', '--no-gpg-sign', '-m', 'Change'])
        self.assertEqual(self.j['intended_head'], 'auto')
        self.assertFalse(self.j['requires_signature'])
        self.assertNotIn('manual_signing', self.j)
        self.ns['validate'].assert_called_once_with(self.j)
        self.ns['save'].assert_called_once_with(self.j)
        self.assertEqual(run.call_args_list[0].args[0],
                         ['git', 'config', '--includes', '--bool', '--get', 'commit.gpgsign'])

    def test_unreadable_signing_config_asks_for_a_signature(self):
        # T-2 / AC-5: UNCERTAIN routes to the human signing handoff.
        self.signing_config(128, '', "fatal: bad boolean config value 'maybe' for 'commit.gpgsign'\n")
        self.ns['head'] = Mock(side_effect=['old', 'new'])
        self.ns['prepare_commit'](self.j)
        self.ask.assert_called_once()
        self.assertTrue(self.ask.call_args.args[0].startswith('Commit signing needs your help. '))
        self.assertIn('git commit -S ', self.ask.call_args.args[0])
        self.assertTrue(self.j['requires_signature'])
        self.assertFalse(any(call.args[0] in ('commit', 'commit-tree') for call in self.git.call_args_list))
        self.git.assert_any_call('verify-commit', 'new')

    def test_signing_error_from_automatic_commit_falls_back_to_person(self):
        # T-3 / AC-3: git reports a signing failure; the reason is printed and the person signs.
        import contextlib, io
        self.mock_git_runs(result(0, 'false\n'),
                           result(128, err='error: gpg failed to sign the data'))
        self.ns['head'] = Mock(side_effect=['old', 'new'])
        def git(*a, **k):
            return {'read-tree': '', 'rev-parse': 'tree', 'rev-list': 'new old', 'verify-commit': ''}[a[0]]
        self.git.side_effect = git
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.ns['prepare_commit'](self.j)
        self.assertIn('Automatic commit failed; git requires a signature: error: gpg failed to sign the data\n', out.getvalue())
        self.ask.assert_called_once()
        self.assertTrue(self.ask.call_args.args[0].startswith('Commit signing needs your help. '))
        self.assertEqual((self.j['requires_signature'], self.j['signing_fallback']),
                         (True, 'error: gpg failed to sign the data'))
        self.assertEqual(self.j['intended_head'], 'new')
        self.git.assert_any_call('verify-commit', 'new')

    def test_other_commit_tree_failure_raises_without_prompt(self):
        # T-4 / AC-6: a non-signing failure is an error, not a handoff.
        self.mock_git_runs(result(0, 'false\n'),
                           result(128, err='fatal: not a valid object name tree'))
        self.ns['head'] = lambda: 'old'
        with self.assertRaisesRegex(ValueError, 'not a valid object name'):
            self.ns['prepare_commit'](self.j)
        self.ask.assert_not_called()
        self.ns['save'].assert_not_called()
        self.assertEqual(self.j['intended_head'], '')
        self.assertNotIn('manual_signing', self.j)

    def test_confirmation_without_commit_can_retry_in_same_handoff(self):
        self.ns['head'] = Mock(side_effect=['old', 'old', 'new'])
        self.ask.side_effect = ['', 'y', '']
        self.ns['manual_signed_commit'](self.j)
        self.assertEqual(self.j['intended_head'], 'new')
        self.assertEqual(self.ask.call_count, 3)

    # T-1 (AC-1): off or unset effective config commits without any prompt.
    def test_unsigned_config_commits_automatically_without_prompt(self):
        for config in (result(0, 'false\n'), result(1)):
            with self.subTest(config=config.returncode):
                self.setUp()
                self.ns['head'] = Mock(side_effect=['new'])
                run = self.mock_git_runs(config, result(0))
                self.ns['prepare_commit'](self.j)
                self.ask.assert_not_called()
                self.assertEqual(run.call_args_list[0].args[0], ['git', 'config', '--includes', '--bool', '--get', 'commit.gpgsign'])
                self.assertEqual(run.call_args_list[1].args[0], ['git', 'commit', '--no-gpg-sign', '-m', 'Change'])
                self.git.assert_called_once_with('read-tree', 'tree')
                self.assertFalse(self.j['requires_signature'])
                self.assertEqual(self.j['intended_head'], 'new')
                self.assertNotIn('manual_signing', self.j)
                self.ns['validate'].assert_called_once_with(self.j)

    # T-2 (AC-2): true keeps the human signing handoff and runs no commit.
    def test_signing_config_keeps_human_handoff(self):
        run = self.mock_git_runs(result(0, 'true\n'))
        self.ns['head'] = Mock(side_effect=['old', 'new'])
        self.ns['prepare_commit'](self.j)
        self.ask.assert_called_once()
        self.assertIn('git commit -S', self.ask.call_args.args[0])
        self.assertNotIn('--no-gpg-sign', self.ask.call_args.args[0])
        self.assertNotIn('Automatic unsigned commit failed', self.ask.call_args.args[0])
        self.assertEqual(run.call_count, 1)
        self.assertTrue(self.j['requires_signature'])
        self.assertFalse(any(call.args[0] in ('commit', 'commit-tree', 'read-tree') for call in self.git.call_args_list))
        self.git.assert_any_call('verify-commit', 'new')

    # T-3 (AC-3): a signing failure of the automatic commit falls back with the reason.
    def test_signing_failure_falls_back_to_human_with_reason(self):
        noise = 'error: gpg failed to sign the data:\n' + 'x' * 300 + '\nfatal: failed to write commit object\n'
        self.mock_git_runs(result(0, 'false\n'), result(128, err=noise))
        self.ns['head'] = Mock(side_effect=['old', 'old'])
        self.ask.return_value = ''
        with self.assertRaisesRegex(ValueError, 'No new commit'):
            self.ns['prepare_commit'](self.j)
        prompt = self.ask.call_args_list[0].args[0]
        self.assertTrue(prompt.startswith('Commit signing needs your help. Automatic unsigned commit failed: error: gpg failed to sign the data: xxx'))
        self.assertIn('x' * 204 + '. ', prompt)  # 240 - len('error: gpg failed to sign the data: ')
        self.assertNotIn('x' * 205, prompt)
        self.assertNotIn('fatal', prompt)
        self.assertIn('git commit -S', prompt)
        self.assertNotIn('--no-gpg-sign', prompt)
        self.assertEqual(self.ask.call_count, 2)
        self.assertTrue(self.j['requires_signature'])
        self.assertTrue(self.j['manual_signing'])
        self.assertEqual(self.j['intended_head'], '')

    # T-7 (E-3, E-5): unreadable config prompts manually; other commit errors raise.
    def test_config_error_prompts_manually_and_other_commit_errors_raise(self):
        self.mock_git_runs(result(128, err='fatal: bad config line 3'))
        self.ns['head'] = Mock(side_effect=['old', 'old'])
        self.ask.return_value = ''
        with self.assertRaisesRegex(ValueError, 'No new commit'):
            self.ns['prepare_commit'](self.j)
        prompt = self.ask.call_args_list[0].args[0]
        self.assertIn('cannot read commit signing configuration: fatal: bad config line 3', prompt)
        self.assertIn('git commit -S', prompt)
        self.assertNotIn('--no-gpg-sign', prompt)
        self.assertTrue(self.j['requires_signature'])
        self.git.assert_not_called()

        self.setUp()
        self.mock_git_runs(result(0, 'false\n'), result(1, err='nothing to commit, working tree clean'))
        with self.assertRaisesRegex(ValueError, 'Automatic commit failed: nothing to commit'):
            self.ns['prepare_commit'](self.j)
        self.ask.assert_not_called()
        self.assertEqual(self.j['intended_head'], '')

    # T-6 (D-4): a legacy pending journal is redetected before any prompt.
    def test_legacy_pending_journal_is_redetected_in_handoff(self):
        run = self.mock_git_runs(result(0, 'false\n'), result(0))
        self.ns['head'] = lambda: 'new' if run.call_count == 2 else 'old'  # HEAD moves only after the auto commit
        self.ns['gh'] = Mock(side_effect=RuntimeError('stop after signing'))
        with self.assertRaisesRegex(RuntimeError, 'stop after signing'):
            self.ns['handoff'](self.j)
        self.ask.assert_not_called()
        self.assertEqual(self.j['intended_head'], 'new')
        self.assertNotIn('manual_signing', self.j)

        self.setUp()
        self.j['intended_head'] = 'new'
        self.ns['prepare_commit'] = Mock()
        self.ns['manual_signed_commit'] = Mock()
        self.ns['gh'] = Mock(side_effect=RuntimeError('stop after signing'))
        with self.assertRaisesRegex(RuntimeError, 'stop after signing'):
            self.ns['handoff'](self.j)
        self.ns['manual_signed_commit'].assert_called_once_with(self.j)
        self.ns['prepare_commit'].assert_not_called()

    # Disposable fixtures: no signer, no user config, no system config.
    @contextlib.contextmanager
    def fixture(self):
        self.setUp()
        with tempfile.TemporaryDirectory() as d:
            env = dict(GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_NOSYSTEM='1', GIT_TERMINAL_PROMPT='0',
                       GNUPGHOME=os.path.join(d, 'nogpg'))
            with patch.dict(os.environ, env):
                repo = os.path.join(d, 'repo')
                os.mkdir(repo)
                def g(*args):
                    return subprocess.run(['git', *NOSIGN, *args], cwd=repo, check=True, stdout=subprocess.PIPE,
                                          stderr=subprocess.PIPE, text=True).stdout.strip()
                g('init', '-q', '-b', 'main')
                for key, value in (('commit.gpgsign', 'false'), ('tag.gpgsign', 'false'),
                                   ('user.name', 'Fixture'), ('user.email', 'fixture@example.invalid')):
                    g('config', key, value)
                Path(repo, 'a.txt').write_text('one\n')
                g('add', 'a.txt')
                g('commit', '--no-gpg-sign', '-q', '-m', 'base')
                Path(repo, 'a.txt').write_text('two\n')
                g('add', 'a.txt')
                tree = g('write-tree')
                g('read-tree', 'HEAD')
                self.ns.update(self.real)
                self.j.update(original_head=g('rev-parse', 'HEAD'), commit_tree=tree, title='Change')
                previous = os.getcwd()
                os.chdir(repo)
                try:
                    yield repo, g
                finally:
                    os.chdir(previous)

    def config_value(self):
        probe = subprocess.run(['git', 'config', '--includes', '--bool', '--get', 'commit.gpgsign'],
                               stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        return probe.returncode, probe.stdout.strip()

    # T-4 (AC-2, D-3): local false auto-commits; includeIf and worktree true prompt.
    def test_effective_config_precedence_in_disposable_repositories(self):
        with self.fixture() as (repo, g):
            self.assertEqual(self.config_value(), (0, 'false'))
            self.ns['prepare_commit'](self.j)
            self.ask.assert_not_called()
            self.assertEqual(self.j['intended_head'], g('rev-parse', 'HEAD'))
            self.assertNotEqual(self.j['intended_head'], self.j['original_head'])
            self.assertEqual(g('rev-parse', 'HEAD^{tree}'), self.j['commit_tree'])
            self.assertEqual(g('rev-parse', 'HEAD^'), self.j['original_head'])
            self.assertEqual(g('log', '-1', '--format=%G?'), 'N')
        for label, enable in (('includeIf', self.enable_include), ('worktree', self.enable_worktree)):
            with self.subTest(label=label), self.fixture() as (repo, g):
                enable(repo, g)
                self.assertEqual(self.config_value(), (0, 'true'))
                self.ask.return_value = ''
                with self.assertRaisesRegex(ValueError, 'No new commit'):
                    self.ns['prepare_commit'](self.j)
                self.assertIn('git commit -S', self.ask.call_args_list[0].args[0])
                self.assertNotIn('--no-gpg-sign', self.ask.call_args_list[0].args[0])
                self.assertEqual(g('rev-parse', 'HEAD'), self.j['original_head'])
                self.assertEqual(self.j['intended_head'], '')
                self.assertTrue(self.j['requires_signature'])

    def enable_include(self, repo, g):
        Path(repo, '.git', 'signing.inc').write_text('[commit]\n\tgpgsign = true\n')
        g('config', 'includeIf.gitdir:' + os.path.realpath(repo) + '/.path', 'signing.inc')

    def enable_worktree(self, repo, g):
        g('config', 'extensions.worktreeConfig', 'true')
        g('config', '--worktree', 'commit.gpgsign', 'true')

    # T-5 (AC-3, AC-4): a hook that rejects unsigned commits is not bypassed.
    def test_rejecting_hook_falls_back_without_unsigned_commit(self):
        with self.fixture() as (repo, g):
            g('config', '--unset', 'commit.gpgsign')
            self.assertEqual(self.config_value()[0], 1)
            hook_dir = Path(repo) / '.git' / 'hooks'
            hook = hook_dir / 'pre-commit'
            hook.write_text('#!/bin/sh\necho "policy: signing required for every commit" >&2\nexit 1\n')
            hook.chmod(0o755)
            self.ask.return_value = ''
            with self.assertRaisesRegex(ValueError, 'No new commit'):
                self.ns['prepare_commit'](self.j)
            prompt = self.ask.call_args_list[0].args[0]
            self.assertIn('Automatic unsigned commit failed: policy: signing required for every commit.', prompt)
            self.assertIn('git commit -S', prompt)
            self.assertEqual(g('rev-parse', 'HEAD'), self.j['original_head'])
            self.assertEqual(g('rev-list', '--count', 'HEAD'), '1')
            self.assertEqual(self.j['intended_head'], '')
            self.assertTrue(self.j['requires_signature'])
            self.assertTrue(self.j['manual_signing'])

    # AC-4: detection and the auto path never write configuration.
    def test_no_config_writes_in_change_pr(self):
        body = SOURCE
        self.assertNotRegex(body, r"'config',\s*'--(add|unset|unset-all|replace-all|edit|rename-section|remove-section)'")
        self.assertNotRegex(body, r"'config',\s*'(--global|--system|--local|--worktree|--file)'")
        for line in body.splitlines():
            if "'config'" in line:
                self.assertIn("'--get'", line, line)


if __name__ == '__main__':
    unittest.main()
