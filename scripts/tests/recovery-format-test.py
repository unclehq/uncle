from pathlib import Path
import importlib.util
import shutil
import subprocess
import sys
import tempfile
import unittest

LIB = Path(__file__).resolve().parents[1] / 'lib'
sys.path.insert(0, str(LIB))
import triage_guard
spec = importlib.util.spec_from_file_location('repair_acceptance', LIB / 'repair-acceptance.py')
repair = importlib.util.module_from_spec(spec)
spec.loader.exec_module(repair)

class RecoveryTests(unittest.TestCase):
    def test_missing_registered_sandbox_can_be_recreated(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / 'project'
            root.mkdir()
            def git(*args):
                return subprocess.run(['git', *args], cwd=root, check=True, capture_output=True)
            git('init', '-q')
            git('config', 'commit.gpgsign', 'false')
            git('config', 'tag.gpgsign', 'false')
            git('config', 'user.name', 'Fixture')
            git('config', 'user.email', 'fixture@example.invalid')
            (root / 'app').write_text('original')
            git('add', 'app')
            git('commit', '--no-gpg-sign', '-qm', 'fixture')
            sandbox = root / '.uncle/workflow/triage/sandbox'
            triage_guard.make_sandbox(root, sandbox)
            shutil.rmtree(sandbox)
            triage_guard.make_sandbox(root, sandbox)
            self.assertEqual((sandbox / 'app').read_text(), 'original')
            triage_guard.drop_sandbox(root, sandbox)
            self.assertNotIn(str(sandbox).encode(), git('worktree', 'list', '--porcelain').stdout)

    def test_labels_repaired_without_changing_decisions(self):
        text = '## Acceptance gate\n| ID | Required | Status | Evidence |\n|---|---|---|---|\n| FR-1 (REQ-1) | YES | FAIL | failed check |\n| Text visible | YES | BLOCKED-HUMAN | pending |\n'
        result = repair.repair(text)
        self.assertIn('| FR-1 | YES | FAIL | Original label: FR-1 (REQ-1). failed check |', result)
        self.assertIn('| Text-visible | YES | BLOCKED-HUMAN | Original label: Text visible. pending |', result)
        self.assertEqual(repair.repair(result), result)

    def test_colliding_identifiers_still_fail_closed(self):
        text = '## Acceptance gate\n| A (alias) | YES | FAIL | failed |\n| A | YES | PASS | passed |\n'
        self.assertEqual(repair.repair(text), text)

if __name__ == '__main__':
    unittest.main()
