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

    def test_verification_outputs_do_not_invalidate_the_verified_source(self):
        root = project()
        before = fp.fingerprint(root)
        for directory in ('.test-out', 'test-results', 'app/playwright-report'):
            output = root / directory
            output.mkdir(parents=True)
            (output/'results.json').write_text('{"elapsed":1}')
        self.assertEqual(fp.fingerprint(root), before)
        (root/'tests').mkdir()
        (root/'tests/test.js').write_text('assert(false)')
        self.assertNotEqual(fp.fingerprint(root), before)

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



class IgnoreFileFingerprint(unittest.TestCase):
    """Uncle's own ignore lines must not make an identical tree look changed (live run 9: the background verification restarted
    three times as the driver appended `.uncle` to .gitignore just after it started)."""

    def with_ignore(self, text):
        root = project()
        (root / '.gitignore').write_text(text)
        return root

    def test_the_drivers_bare_uncle_line_does_not_change_it(self):
        root = self.with_ignore('node_modules\ndist\n'); before = fp.fingerprint(root)
        (root / '.gitignore').write_text('node_modules\ndist\n.uncle\n')
        self.assertEqual(fp.fingerprint(root), before)

    def test_the_canonical_managed_block_does_not_change_it(self):
        root = self.with_ignore('node_modules\n'); before = fp.fingerprint(root)
        (root / '.gitignore').write_text('node_modules\n.uncle/*\n!.uncle/docs/\n')
        self.assertEqual(fp.fingerprint(root), before)

    def test_a_rule_of_the_projects_own_changes_it(self):
        root = self.with_ignore('node_modules\n'); before = fp.fingerprint(root)
        (root / '.gitignore').write_text('node_modules\nsecret.txt\n')
        self.assertNotEqual(fp.fingerprint(root), before)

    def test_removing_a_rule_changes_it(self):
        root = self.with_ignore('node_modules\ndist\n'); before = fp.fingerprint(root)
        (root / '.gitignore').write_text('node_modules\n')
        self.assertNotEqual(fp.fingerprint(root), before)

    def test_a_managed_line_beside_a_new_rule_still_changes_it(self):
        root = self.with_ignore('node_modules\n'); before = fp.fingerprint(root)
        (root / '.gitignore').write_text('node_modules\n.uncle\nsecret.txt\n')
        self.assertNotEqual(fp.fingerprint(root), before)

    def test_only_the_ignore_file_gets_this_treatment(self):
        root = project(); before = fp.fingerprint(root)
        (root / 'src' / 'a.js').write_text('one\n.uncle\n')
        self.assertNotEqual(fp.fingerprint(root), before)

    def test_an_ignore_file_in_a_subdirectory_is_treated_the_same_way(self):
        root = project(); (root / 'src' / '.gitignore').write_text('x\n'); before = fp.fingerprint(root)
        (root / 'src' / '.gitignore').write_text('x\n.uncle\n')
        self.assertEqual(fp.fingerprint(root), before)


class ApplicationFingerprint(unittest.TestCase):
    """The early checklist ran against the application; later test waves add files the application does not depend on."""

    def app(self, root):
        return fp.fingerprint(root, app_only=True)

    def test_a_new_test_file_does_not_change_it(self):
        root = project(); before = self.app(root)
        (root / 'tests').mkdir(); (root / 'tests' / 'a.test.js').write_text('x')
        (root / 'e2e').mkdir(); (root / 'e2e' / 'a.spec.js').write_text('x')
        (root / 'tests' / 'mutations').mkdir(); (root / 'tests' / 'mutations' / 'list.mjs').write_text('x')
        self.assertEqual(self.app(root), before)

    def test_a_change_to_a_test_file_does_not_change_it(self):
        root = project(); (root / 'src' / 'a.test.js').write_text('one'); before = self.app(root)
        (root / 'src' / 'a.test.js').write_text('two')
        self.assertEqual(self.app(root), before)

    def test_a_document_does_not_change_it(self):
        root = project(); before = self.app(root)
        (root / 'README.md').write_text('hello'); (root / 'src' / 'CONTRACT.md').write_text('hello')
        self.assertEqual(self.app(root), before)

    def test_a_source_change_does_change_it(self):
        root = project(); before = self.app(root)
        (root / 'src' / 'a.js').write_text('changed')
        self.assertNotEqual(self.app(root), before)

    def test_a_new_source_file_does_change_it(self):
        root = project(); before = self.app(root)
        (root / 'src' / 'b.js').write_text('x')
        self.assertNotEqual(self.app(root), before)

    def test_the_manifest_and_config_are_part_of_it(self):
        root = project(); before = self.app(root)
        (root / 'package.json').write_text('{"dependencies": {"react": "1"}}')
        changed = self.app(root); self.assertNotEqual(changed, before)
        (root / 'vite.config.js').write_text('export default {}')
        self.assertNotEqual(self.app(root), changed)

    def test_the_whole_tree_fingerprint_still_sees_tests(self):
        root = project(); before = fp.fingerprint(root)
        (root / 'src' / 'a.test.js').write_text('x')
        self.assertNotEqual(fp.fingerprint(root), before)

    def test_the_drivers_own_ignore_line_still_does_not_change_it(self):
        root = project(); (root / '.gitignore').write_text('dist\n'); before = self.app(root)
        (root / '.gitignore').write_text('dist\n.uncle\n')
        self.assertEqual(self.app(root), before)

    CONFIG = "import {defineConfig} from 'vitest/config';\nexport default defineConfig({\n  server: {port: 5173},\n  test: {\n    include: ['%s'],\n  },\n});\n"

    def test_where_the_unit_tests_look_does_not_change_it(self):
        root = project(); (root / 'vite.config.js').write_text(self.CONFIG % 'tests/unit/**/*.test.js')
        before, whole = self.app(root), fp.fingerprint(root)
        (root / 'vite.config.js').write_text(self.CONFIG % 'tests/*.test.js')
        self.assertEqual(self.app(root), before)
        self.assertNotEqual(fp.fingerprint(root), whole)    # the whole-tree fingerprint, used to skip verification, still sees it

    def test_a_change_to_the_server_or_build_part_of_the_config_does_change_it(self):
        root = project(); (root / 'vite.config.js').write_text(self.CONFIG % 'x')
        before = self.app(root)
        (root / 'vite.config.js').write_text((self.CONFIG % 'x').replace('5173', '5174'))
        self.assertNotEqual(self.app(root), before)

    def test_a_config_without_a_test_block_is_hashed_whole(self):
        root = project(); (root / 'vite.config.js').write_text('export default {server: {port: 1}}\n')
        before = self.app(root)
        (root / 'vite.config.js').write_text('export default {server: {port: 2}}\n')
        self.assertNotEqual(self.app(root), before)

    def test_other_files_with_a_test_block_are_hashed_whole(self):
        root = project(); (root / 'src' / 'cfg.js').write_text(self.CONFIG % 'a')
        before = self.app(root)
        (root / 'src' / 'cfg.js').write_text(self.CONFIG % 'b')
        self.assertNotEqual(self.app(root), before)

    def test_what_follows_the_test_block_still_counts(self):
        root = project()
        text = "export default {\n  test: {include: ['a']},\n  server: {port: %d},\n}\n"
        (root / 'vite.config.js').write_text(text % 1); before = self.app(root)
        (root / 'vite.config.js').write_text(text % 2)
        self.assertNotEqual(self.app(root), before)

    def test_another_config_file_is_not_trimmed(self):
        root = project(); (root / 'playwright.config.js').write_text(self.CONFIG % 'a')
        before = self.app(root)
        (root / 'playwright.config.js').write_text(self.CONFIG % 'b')
        self.assertNotEqual(self.app(root), before)

    def test_the_command_line_flag(self):
        root = project(); script = ROOT / 'scripts' / 'lib' / 'tree_fingerprint.py'
        whole = subprocess.run([sys.executable, str(script), str(root)], capture_output=True, text=True).stdout.strip()
        only = subprocess.run([sys.executable, str(script), '--app', str(root)], capture_output=True, text=True).stdout.strip()
        self.assertEqual(only, fp.fingerprint(root, app_only=True))
        self.assertEqual(whole, fp.fingerprint(root))

if __name__ == '__main__':
    unittest.main()
