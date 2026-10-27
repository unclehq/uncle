#!/usr/bin/env python3
"""An identical re-run of the verification commands is skipped; any change to code, tests or commands is not."""
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts' / 'lib'))
import tree_fingerprint as fp


def project():
    root = Path(tempfile.mkdtemp())
    (root / 'src').mkdir()
    (root / 'src' / 'a.js').write_text('one')
    (root / 'package.json').write_text('{}')
    return root


class Fingerprint(unittest.TestCase):
    def test_the_same_tree_has_the_same_fingerprint(self):
        root = project()
        self.assertEqual(fp.fingerprint(root), fp.fingerprint(root))

    def test_a_changed_file_a_new_file_or_a_deleted_file_changes_it(self):
        root = project(); before = fp.fingerprint(root)
        (root / 'src' / 'a.js').write_text('two')
        changed = fp.fingerprint(root); self.assertNotEqual(before, changed)
        (root / 'src' / 'b.js').write_text('x')
        added = fp.fingerprint(root); self.assertNotEqual(changed, added)
        (root / 'src' / 'b.js').unlink()
        self.assertEqual(fp.fingerprint(root), changed)

    def test_the_commands_are_part_of_it(self):
        root = project(); commands = root.parent / ('cmds-%s' % root.name)
        commands.write_text('npm test')
        first = fp.fingerprint(root, [commands])
        commands.write_text('npm run other')
        self.assertNotEqual(first, fp.fingerprint(root, [commands]))

    def test_workflow_state_and_dependencies_do_not_count(self):
        root = project(); before = fp.fingerprint(root)
        (root / '.uncle' / 'workflow').mkdir(parents=True)
        (root / '.uncle' / 'workflow' / 'state').write_text('RUNNING')
        (root / 'node_modules' / 'x').mkdir(parents=True)
        (root / 'node_modules' / 'x' / 'i.js').write_text('dep')
        self.assertEqual(fp.fingerprint(root), before)

    def test_it_is_the_same_from_the_command_line(self):
        root = project()
        out = subprocess.run([sys.executable, '-B', str(ROOT / 'scripts/lib/tree_fingerprint.py'), str(root)],
                             capture_output=True, text=True, check=True).stdout.strip()
        self.assertEqual(out, fp.fingerprint(root))


class Driver(unittest.TestCase):
    def body(self):
        text = (ROOT / 'scripts' / 'stagegate.sh').read_text()
        start = text.index('run_green_check() {')
        return text[start:start + 11000]

    def test_both_outcomes_are_remembered_and_a_failure_is_reused_unless_switched_off(self):
        body = self.body()
        self.assertIn('WORKFLOW_GREEN_CHECK_REUSE:-1', body)
        self.assertIn('WORKFLOW_GREEN_CHECK_REUSE_FAILED:-1', body)
        self.assertIn('already passed on this exact tree', body)
        self.assertIn('already failed on this exact tree', body)
        self.assertIn('green_outcome=failed', body)
        self.assertIn("'%s %s\\n' \"$green_after\" \"$green_outcome\"", body)

    def test_the_fingerprint_is_taken_after_the_run_and_cleared_before_one(self):
        body = self.body()
        self.assertLess(body.index('failures="$(green_regressions'), body.index('green_after="$(python3'))
        self.assertIn('rm -f "$STATE_DIR/green-check.fingerprint"', body)


if __name__ == '__main__':
    unittest.main()
