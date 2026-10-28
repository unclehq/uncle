#!/usr/bin/env python3
"""Verification runs in a private copy: files copied, dependencies linked, the project's port moved, output copied back."""
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

LIB = Path(__file__).resolve().parents[1] / 'lib'
sys.path.insert(0, str(LIB))
import isolated_verify as iv


def fixture(root):
    root = Path(root)
    root.mkdir(parents=True)
    (root / 'src').mkdir()
    (root / 'src/app.js').write_text('export const x = 1;\n')
    (root / 'node_modules/pkg').mkdir(parents=True)
    (root / 'node_modules/pkg/index.js').write_text('module.exports = 1;\n')
    (root / 'dist').mkdir()
    (root / 'dist/old.js').write_text('old')
    (root / 'playwright.config.js').write_text(
        "export default { webServer: { command: 'vite preview --port 4173', url: 'http://127.0.0.1:4173' }, use: { baseURL: 'http://127.0.0.1:4173' } };\n")
    (root / 'tests').mkdir()
    (root / 'tests/e2e.spec.js').write_text("await page.goto('/'); // 4173\nconst n = 41730; const m = 14173;\n")
    (root / '.uncle/docs').mkdir(parents=True)
    (root / '.uncle/docs/UPDATED_PROJECT_PLAN.md').write_text('run `vite preview --port 4173`\n')
    (root / '.uncle/workflow').mkdir()
    (root / '.uncle/workflow/state').write_text('VERIFY')
    return root


class Isolated(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.project = fixture(Path(self.tmp.name) / 'project')
        self.copy = Path(self.tmp.name) / 'copy'

    def tearDown(self):
        self.tmp.cleanup()

    def test_the_copy_has_the_sources_and_the_plan_but_not_build_output_or_driver_state(self):
        iv.prepare(self.project, self.copy)
        self.assertTrue((self.copy / 'src/app.js').is_file())
        self.assertTrue((self.copy / '.uncle/docs/UPDATED_PROJECT_PLAN.md').is_file())
        self.assertFalse((self.copy / 'dist').exists())
        self.assertFalse((self.copy / '.uncle/workflow').exists())

    def test_dependencies_are_linked_not_copied(self):
        iv.prepare(self.project, self.copy)
        self.assertTrue((self.copy / 'node_modules').is_symlink())
        self.assertTrue((self.copy / 'node_modules/pkg/index.js').is_file())

    def test_the_project_port_is_moved_in_the_copy_only_and_other_numbers_are_left_alone(self):
        found = iv.prepare(self.project, self.copy)
        self.assertEqual((found['base'], found['port']), (4173, 4173 + iv.OFFSET))
        config = (self.copy / 'playwright.config.js').read_text()
        self.assertNotIn('4173', config)
        self.assertEqual(config.count(str(4173 + iv.OFFSET)), 3)
        spec = (self.copy / 'tests/e2e.spec.js').read_text()
        self.assertIn('41730', spec)
        self.assertIn('14173', spec)
        self.assertIn('--port %d' % (4173 + iv.OFFSET), (self.copy / '.uncle/docs/UPDATED_PROJECT_PLAN.md').read_text())
        self.assertIn('4173', (self.project / 'playwright.config.js').read_text())

    def test_a_project_without_a_port_is_copied_unchanged(self):
        (self.project / 'playwright.config.js').unlink()
        (self.project / 'tests/e2e.spec.js').write_text('x')
        (self.project / '.uncle/docs/UPDATED_PROJECT_PLAN.md').write_text('no port here')
        self.assertEqual(iv.prepare(self.project, self.copy), {'base': None, 'port': None})

    def test_what_the_run_wrote_is_copied_back(self):
        iv.prepare(self.project, self.copy)
        (self.copy / '.test-out').mkdir()
        (self.copy / '.test-out/mutations.json').write_text('{"caught": 3}')
        (self.copy / 'test-results').mkdir()
        (self.copy / 'test-results/trace.zip').write_text('z')
        iv.finish(self.project, self.copy)
        self.assertEqual(json.loads((self.project / '.test-out/mutations.json').read_text()), {'caught': 3})
        self.assertTrue((self.project / 'test-results/trace.zip').is_file())

    def test_an_install_and_a_build_done_in_the_copy_become_the_projects(self):
        # noinit: both ran in the copy only, the project had no dependencies and no build, and its page was blank
        (self.project / 'node_modules').rename(self.project / 'nm-old')
        (self.project / 'dist/old.js').unlink()
        (self.project / 'dist').rmdir()
        iv.prepare(self.project, self.copy)
        (self.copy / 'node_modules/react').mkdir(parents=True)
        (self.copy / 'node_modules/react/index.js').write_text('r')
        (self.copy / 'dist').mkdir()
        (self.copy / 'dist/index.html').write_text('<div id=root>')
        (self.copy / 'package-lock.json').write_text('{}')
        iv.finish(self.project, self.copy)
        self.assertTrue((self.project / 'node_modules/react/index.js').is_file())
        self.assertTrue((self.project / 'dist/index.html').is_file())
        self.assertTrue((self.project / 'package-lock.json').is_file())

    def test_an_existing_installation_is_not_replaced_and_a_linked_one_is_never_moved(self):
        iv.prepare(self.project, self.copy)
        iv.finish(self.project, self.copy)
        self.assertTrue((self.project / 'node_modules/pkg/index.js').is_file())
        self.assertTrue((self.copy / 'node_modules').is_symlink())

    def test_the_command_line_prints_the_ports(self):
        done = subprocess.run([sys.executable, str(LIB / 'isolated_verify.py'), 'prepare', str(self.project), str(self.copy)],
                              capture_output=True, text=True)
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertEqual(json.loads(done.stdout)['base'], 4173)


if __name__ == '__main__':
    unittest.main()
