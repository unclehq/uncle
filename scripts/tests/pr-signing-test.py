"""Signing remains a user action, including interrupted handoff resumes."""
from pathlib import Path
import unittest
from unittest.mock import Mock

ROOT = Path(__file__).resolve().parents[2]
SOURCE = (ROOT / 'scripts/lib/change-pr.sh').read_text().split("<<'PY'", 1)[1].split('\n', 1)[1].split('\nPY\n', 1)[0]


class SigningTests(unittest.TestCase):
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
        self.ask.assert_called_once()
        self.assertIn('git commit -S', self.ask.call_args.args[0])
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

    def test_unsigned_automatic_commit_explicitly_disables_signing(self):
        self.ns['subprocess'] = Mock()
        self.ns['subprocess'].run.return_value = Mock(returncode=0, stdout='false\n')
        self.git.side_effect = None
        self.git.return_value = 'unsigned'
        self.ns['prepare_commit'](self.j)
        self.assertEqual(self.git.call_args.args[:2], ('commit-tree', '--no-gpg-sign'))
        self.ask.assert_not_called()

    def test_unsigned_failure_never_requests_signing(self):
        self.ns['subprocess'] = Mock()
        self.ns['subprocess'].run.return_value = Mock(returncode=0, stdout='false\n')
        self.git.side_effect = ValueError('Command failed: git commit-tree --no-gpg-sign')
        with self.assertRaisesRegex(ValueError, 'Command failed'):
            self.ns['prepare_commit'](self.j)
        self.ask.assert_not_called()
        self.ns['save'].assert_not_called()

    def test_signing_configuration_prompts_without_automatic_commit(self):
        self.ns['subprocess'] = Mock()
        self.ns['subprocess'].run.return_value = Mock(returncode=0, stdout='true\n')
        self.ns['head'] = lambda: 'old'
        with self.assertRaisesRegex(ValueError, 'No new commit'):
            self.ns['prepare_commit'](self.j)
        self.git.assert_not_called()
        self.ask.assert_called_once()


if __name__ == '__main__':
    unittest.main()
