"""The plan stage names the exact .gitignore lines its own check demands, in the first pass and in the repair (calculator run:
a Vite project's .gitignore ignored dist/ but not build/, the model judged it sufficient, and both passes failed `build/probe`)."""
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts' / 'lib'))
import project_plan_stage as pps

PLAN = '# Plan\n\nA small web app built with npm and vite, rendered in the browser.\n'


class IgnoreInstruction(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.old = os.getcwd()
        os.chdir(self.tmp.name)
        Path('plan.md').write_text(PLAN)

    def tearDown(self):
        os.chdir(self.old)
        self.tmp.cleanup()

    def gitignore(self, text):
        Path('.gitignore').write_text(text)

    def test_missing_build_is_named_as_the_line_to_add(self):
        self.gitignore('node_modules/\ndist/\n.env\n.env.*\n.DS_Store\n')
        text = pps.ignore_instruction('plan.md')
        self.assertIn('build/probe', text)
        self.assertIn('\n    build/\n', text)
        self.assertNotIn('    dist/\n', text)

    def test_nothing_missing_means_no_instruction(self):
        self.gitignore('node_modules/\ndist/\nbuild/\n.env\n.env.*\n.DS_Store\n')
        self.assertEqual(pps.ignore_instruction('plan.md'), '')

    def test_probe_paths_map_to_ignore_lines(self):
        self.assertEqual(pps.ignore_entries(['build/probe', '__pycache__/probe.pyc', 'probe.pyc', '.env', 'build/probe']),
                         ['build/', '__pycache__/', '*.pyc', '.env'])

    def test_first_pass_and_repair_prompts_carry_the_lines(self):
        self.gitignore('node_modules/\ndist/\n.env\n.env.*\n.DS_Store\n')
        pps.prepare('.', 'plan.md', 'first.md')
        pps.prepare_repair('.', 'plan.md', 'repair.md', 'ignore verification failed: build/probe')
        for name in ('first.md', 'repair.md'):
            self.assertIn('\n    build/\n', Path(name).read_text(), name)

    def test_prompts_are_unchanged_when_nothing_is_missing(self):
        self.gitignore('node_modules/\ndist/\nbuild/\n.env\n.env.*\n.DS_Store\n')
        pps.prepare('.', 'plan.md', 'first.md')
        self.assertNotIn('Add exactly these lines', Path('first.md').read_text())

    def test_verify_still_rejects_the_gap(self):
        self.gitignore('node_modules/\ndist/\n.env\n.env.*\n.DS_Store\n')
        with self.assertRaisesRegex(ValueError, 'ignore verification failed: build/probe'):
            pps.verify('.', 'plan.md')


if __name__ == '__main__':
    unittest.main()
