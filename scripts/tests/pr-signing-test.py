"""Signing remains a user action, including interrupted handoff resumes."""
from pathlib import Path
import unittest
from unittest.mock import Mock

ROOT = Path(__file__).resolve().parents[2]
SOURCE = (ROOT / 'scripts/lib/change-pr.sh').read_text().split("<<'PY'", 1)[1].split('\n', 1)[1].split('\nPY\n', 1)[0]


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
        self.j = dict(original_head='old', intended_head='', commit_tree='tree', title='Change', manual_signing=True)
        self.git = Mock(side_effect=lambda *a, **k: {
            'rev-parse': 'tree', 'rev-list': 'new old', 'verify-commit': ''
        }[a[0]])
        self.ask = Mock()
        self.ns.update(head=lambda: 'new', git=self.git, ask=self.ask, save=Mock(), validate=Mock())

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

    def test_unsigned_commit_is_also_a_user_action(self):
        self.ns['subprocess'] = Mock()
        self.ns['subprocess'].run.return_value = Mock(returncode=0, stdout='false\n')
        self.ns['head'] = Mock(side_effect=['old', 'new'])
        self.ns['prepare_commit'](self.j)
        self.assertIn('git commit --no-gpg-sign', self.ask.call_args.args[0])
        self.assertFalse(self.j['requires_signature'])
        self.assertEqual(self.j['intended_head'], 'new')
        self.assertFalse(any(call.args[0] in ('commit', 'commit-tree', 'verify-commit') for call in self.git.call_args_list))

    def test_confirmation_without_commit_can_retry_in_same_handoff(self):
        self.ns['head'] = Mock(side_effect=['old', 'old', 'new'])
        self.ask.side_effect = ['', 'y', '']
        self.ns['manual_signed_commit'](self.j)
        self.assertEqual(self.j['intended_head'], 'new')
        self.assertEqual(self.ask.call_count, 3)

    def test_signing_configuration_prompts_without_automatic_commit(self):
        self.ns['subprocess'] = Mock()
        self.ns['subprocess'].run.return_value = Mock(returncode=0, stdout='true\n')
        self.ns['head'] = lambda: 'old'
        with self.assertRaisesRegex(ValueError, 'No new commit'):
            self.ns['prepare_commit'](self.j)
        self.git.assert_not_called()
        self.assertEqual(self.ask.call_count, 2)


if __name__ == '__main__':
    unittest.main()
