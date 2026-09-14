#!/usr/bin/env python3
"""Manual-commit checks not covered by pr-signing-test: the generated command's
transport and shell safety, and the parent/signature guards."""
import ast
import json
import os
import shlex
import subprocess
import tempfile
from pathlib import Path
import unittest
from unittest.mock import Mock

SOURCE = (Path(__file__).resolve().parents[1] / 'lib/change-pr.sh').read_text().split("<<'PY'", 1)[1].split("\n", 1)[1].split('\nPY\n', 1)[0]
TREE = ast.parse(SOURCE)
FUNCTION = next(node for node in TREE.body if isinstance(node, ast.FunctionDef) and node.name == 'manual_signed_commit')


class Checks(unittest.TestCase):
    def run_case(self, tree='tree', signature=True, heads=('new',)):
        def git(*args):
            if args[0] == 'rev-parse': return tree
            if args[0] == 'rev-list': return 'new old'
            if args[0] == 'verify-commit' and not signature: raise ValueError('bad signature')
        # The prompt is shown only while HEAD is still the audited commit, so a
        # case that inspects the prompt starts on 'old' and moves to 'new'.
        ns = dict(os=os, json=json, ask=Mock(), head=Mock(side_effect=list(heads)), git=Mock(side_effect=git),
                  validate=Mock(), save=Mock())
        exec(compile(ast.Module(body=[FUNCTION], type_ignores=[]), '<helper>', 'exec'), ns)
        journal = dict(original_head='old', commit_tree='tree', intended_head='', manual_signing=True,
                       title="Fix user's signing dialog")
        return ns, journal

    def test_command_transport_and_shell_safety(self):
        from unittest.mock import patch
        for title in ("Fix user's café 日本語 $(touch injected)", 'Fix "press ENTER (OK) when finished: " [y/n]'):
            ns, j = self.run_case(heads=('old', 'new', 'old', 'new'))
            j['title'] = title
            with patch.dict(os.environ, {}, clear=True):
                ns['manual_signed_commit'](j)
            cli = ns['ask'].call_args.args[0].split('\n', 1)[1].split('\nReturn here', 1)[0]
            j['manual_signing'] = True
            with patch.dict(os.environ, {'UNCLE_SIGNING_JSON': '1'}):
                ns['manual_signed_commit'](j)
            framed = ns['ask'].call_args.args[0].removeprefix('Commit signing needs your help. ')
            command, end = json.JSONDecoder().raw_decode(framed)
            self.assertEqual(command, cli)
            self.assertTrue(framed[end:].startswith(' Return here'))
            with tempfile.TemporaryDirectory() as folder:
                script = Path(folder) / 'git'
                script.write_text('#!/usr/bin/env python3\nimport json, os, sys\nwith open(os.environ["CALLS"], "a") as f: f.write(json.dumps(sys.argv[1:]) + "\\n")\nsys.exit(1 if os.environ.get("FAIL_READ_TREE") and sys.argv[1] == "read-tree" else 0)\n')
                script.chmod(0o755)
                calls = Path(folder) / 'calls'
                env = dict(os.environ, PATH=folder + os.pathsep + os.environ['PATH'], CALLS=str(calls))
                subprocess.run(['sh', '-c', command], cwd=folder, env=env, check=True)
                rows = [json.loads(line) for line in calls.read_text().splitlines()]
                self.assertEqual(rows, [['read-tree', 'tree'], ['commit', '-S', '-m', title]])
                self.assertFalse((Path(folder) / 'injected').exists())
                calls.unlink()
                self.assertNotEqual(subprocess.run(['sh', '-c', command], cwd=folder, env=dict(env, FAIL_READ_TREE='1')).returncode, 0)
                self.assertEqual(len(calls.read_text().splitlines()), 1)

    def test_wrong_parent_merge_and_missing_commit(self):
        for parents in ('new other', 'new old other'):
            ns, j = self.run_case()
            original = ns['git'].side_effect
            ns['git'].side_effect = lambda *args: parents if args[0] == 'rev-list' else original(*args)
            with self.assertRaises(ValueError): ns['manual_signed_commit'](j)
            ns['save'].assert_not_called()
        ns, j = self.run_case()
        ns['head'] = lambda: 'old'
        with self.assertRaises(ValueError): ns['manual_signed_commit'](j)
        ns['save'].assert_not_called()

    def test_wrong_tree_or_signature_stays_pending(self):
        for kwargs in [dict(tree='different'), dict(signature=False)]:
            ns, j = self.run_case(**kwargs)
            with self.assertRaises(ValueError): ns['manual_signed_commit'](j)
            self.assertEqual(j['intended_head'], '')
            self.assertTrue(j['manual_signing'])
            ns['save'].assert_not_called()


if __name__ == '__main__':
    unittest.main()
