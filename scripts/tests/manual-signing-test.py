#!/usr/bin/env python3
import ast
from pathlib import Path
import unittest
from unittest.mock import Mock

SOURCE = (Path(__file__).resolve().parents[1] / 'lib/change-pr.sh').read_text().split("<<'PY'", 1)[1].split("\n", 1)[1].split('\nPY\n', 1)[0]
TREE = ast.parse(SOURCE)
FUNCTION = next(node for node in TREE.body if isinstance(node, ast.FunctionDef) and node.name == 'manual_signed_commit')


class Checks(unittest.TestCase):
    def run_case(self, tree='tree', signature=True):
        def git(*args):
            if args[0] == 'rev-parse': return tree
            if args[0] == 'rev-list': return 'new old'
            if args[0] == 'verify-commit' and not signature: raise ValueError('bad signature')
        ns = dict(ask=Mock(), head=lambda: 'new', git=Mock(side_effect=git), validate=Mock(), save=Mock())
        exec(compile(ast.Module(body=[FUNCTION], type_ignores=[]), '<helper>', 'exec'), ns)
        journal = dict(original_head='old', commit_tree='tree', intended_head='', manual_signing=True,
                       title="Fix user's signing dialog")
        return ns, journal

    def test_signed_audited_commit_resumes(self):
        ns, j = self.run_case()
        ns['manual_signed_commit'](j)
        self.assertEqual(j['intended_head'], 'new')
        self.assertNotIn('manual_signing', j)
        ns['git'].assert_any_call('verify-commit', 'new')
        ns['validate'].assert_called_once_with(j)
        ns['save'].assert_called_once_with(j)
        self.assertIn('press ENTER (OK)', ns['ask'].call_args.args[0])
        import shlex
        prompt = ns['ask'].call_args.args[0]
        command = prompt.split('then run: ', 1)[1].split('. Return here', 1)[0]
        self.assertEqual(shlex.split(command), ['git', 'commit', '-S', '-m', j['title']])

    def test_signing_configuration_prompts_before_commit(self):
        import subprocess
        function = next(node for node in TREE.body if isinstance(node, ast.FunctionDef) and node.name == 'prepare_commit')
        for enabled in (True, False):
            api = Mock()
            api.PIPE = subprocess.PIPE
            api.run.return_value = subprocess.CompletedProcess([], 0, 'true\n' if enabled else 'false\n', '')
            ns = dict(subprocess=api, save=Mock(), manual_signed_commit=Mock(), git=Mock(return_value='new'))
            exec(compile(ast.Module(body=[function], type_ignores=[]), '<helper>', 'exec'), ns)
            j = dict(title='Fix signing', commit_tree='tree', original_head='old', intended_head='')
            ns['prepare_commit'](j)
            if enabled:
                ns['git'].assert_not_called()
                ns['manual_signed_commit'].assert_called_once_with(j)
                self.assertTrue(j['manual_signing'])
                ns['save'].assert_called_once_with(j)
            else:
                ns['manual_signed_commit'].assert_not_called()
                self.assertEqual(j['intended_head'], 'new')

    def test_wrong_tree_or_signature_stays_pending(self):
        for kwargs in [dict(tree='different'), dict(signature=False)]:
            ns, j = self.run_case(**kwargs)
            with self.assertRaises(ValueError): ns['manual_signed_commit'](j)
            self.assertEqual(j['intended_head'], '')
            self.assertTrue(j['manual_signing'])
            ns['save'].assert_not_called()


if __name__ == '__main__':
    unittest.main()
