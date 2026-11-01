"""Uncle's own ignore entries appearing in .gitignore must not fail an approval or refuse a triage turn; real edits still must."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

LIB = Path(__file__).resolve().parents[1] / 'lib'
sys.path.insert(0, str(LIB))
from uncle_gitignore import only_adds_managed
import approval_snapshot

BASE = 'node_modules/\n.uncle/*\n!.uncle/docs/\ndist/\n'


class Tolerance(unittest.TestCase):
    def test_a_bare_uncle_line_is_benign(self):
        self.assertTrue(only_adds_managed(BASE, BASE + '.uncle\n'))
        self.assertTrue(only_adds_managed(BASE, BASE))

    def test_a_project_rule_is_not_benign(self):
        self.assertFalse(only_adds_managed(BASE, BASE + '.uncle\nsecrets.txt\n'))
        self.assertFalse(only_adds_managed(BASE, BASE + '*.js\n'))

    def test_removing_a_rule_is_not_benign(self):
        self.assertFalse(only_adds_managed(BASE, 'node_modules/\n.uncle/*\n!.uncle/docs/\n.uncle\n'))

    def test_approval_snapshot_ignores_uncle_entries_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / '.gitignore').write_text(BASE)
            cwd = Path.cwd()
            try:
                import os
                os.chdir(root)
                first = approval_snapshot.snapshot(['.gitignore'])
                (root / '.gitignore').write_text(BASE + '.uncle\n')
                self.assertEqual(first, approval_snapshot.snapshot(['.gitignore']))
                (root / '.gitignore').write_text(BASE + 'secrets.txt\n')
                self.assertNotEqual(first, approval_snapshot.snapshot(['.gitignore']))
            finally:
                os.chdir(cwd)


if __name__ == '__main__':
    unittest.main()
