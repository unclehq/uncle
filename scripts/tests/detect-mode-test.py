#!/usr/bin/env python3
"""Mode detection: a new application versus a change, from the repository contents and the prompt."""
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts/lib'))
import detect_mode as dm  # noqa: E402

BODY = '// ' + 'x' * 40 + '\n'
BIG = ''.join('function f%d() { return %d; }\n%s' % (i, i, BODY) for i in range(40))   # well over the template-sized threshold


class Detect(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp())
        # Its own repository, so a parent directory's git state can never leak into the fixture.
        subprocess.run(['git', 'init', '-q', str(self.dir)], check=True)

    def write(self, name, text=BIG):
        path = self.dir / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)

    def app(self):
        for name in ('src/App.jsx', 'src/calc.js', 'src/keymap.js', 'src/main.jsx'):
            self.write(name)
        self.write('tests/calc.test.js')
        self.write('package.json', '{"name":"calculator"}')

    def detect(self, prompt=''):
        return dm.classify(str(self.dir), prompt)

    def test_an_empty_directory_with_a_build_request_is_new(self):
        r = self.detect('build me a todo app')
        self.assertEqual((r['mode'], r['confidence'], r['repository']), ('new', 'high', 'empty'))

    def test_an_empty_directory_with_no_prompt_is_new(self):
        self.assertEqual(self.detect()['mode'], 'new')

    def test_a_change_request_in_an_empty_directory_asks_and_falls_back_to_new(self):
        r = self.detect('fix the bug in the existing checkout page')
        self.assertEqual((r['mode'], r['fallback']), ('ask', 'new'))
        self.assertTrue(any('no source code' in x for x in r['reasons']))

    def test_a_real_application_with_a_change_request_is_change(self):
        self.app()
        r = self.detect('restyle the calculator display')
        self.assertEqual((r['mode'], r['repository']), ('change', 'existing'))

    def test_a_real_application_with_no_prompt_is_change(self):
        self.app()
        self.assertEqual(self.detect()['mode'], 'change')

    def test_a_new_build_request_over_a_real_application_asks_and_falls_back_to_change(self):
        # The costly mistake is a new build over code that exists, so the fallback never picks it.
        self.app()
        r = self.detect('build me a new inventory app from scratch')
        self.assertEqual((r['mode'], r['fallback']), ('ask', 'change'))

    def test_a_request_naming_a_file_that_exists_is_a_change(self):
        self.app()
        r = self.detect('update calc.js so division by zero shows Error')
        self.assertEqual(r['mode'], 'change')
        self.assertIn('calc.js', r['prompt']['repo_references'])

    def test_a_template_scaffold_is_new(self):
        self.write('src/main.js', 'console.log("hi")\n')
        self.write('package.json', '{}')
        r = self.detect('build a calculator')
        self.assertEqual((r['mode'], r['repository']), ('new', 'scaffold'))

    def test_a_scaffold_with_a_request_about_its_own_file_is_change(self):
        self.write('src/main.js', 'console.log("hi")\n')
        self.assertEqual(self.detect('fix src/main.js, it crashes')['mode'], 'change')

    def test_a_change_request_file_in_progress_is_change(self):
        self.write('src/main.js', 'console.log("hi")\n')
        self.write('.uncle/docs/CHANGE_REQUEST.md', '# Change\nsomething\n')
        self.assertEqual(self.detect()['mode'], 'change')

    def test_an_application_plan_in_progress_is_new(self):
        self.write('.uncle/docs/PROJECT_PLAN.md', '# Plan\n')
        self.write('.uncle/workflow/state', 'IMPLEMENT\n')
        self.assertEqual(self.detect('')['mode'], 'new')

    def test_a_finished_uncle_build_is_a_change_target(self):
        self.app()
        self.write('.uncle/attestation.json', '{}')
        r = self.detect('add a dark mode')
        self.assertEqual((r['mode'], r['repository'], r['confidence']), ('change', 'prior-uncle-build', 'high'))

    def test_uncles_own_template_scripts_are_not_the_application(self):
        self.write('scripts/stagegate.sh', BIG)
        self.write('scripts/lib/x.sh', BIG)
        self.write('prompts/a.md', 'x')
        self.assertEqual(self.detect('build me a todo app')['mode'], 'new')

    def test_build_output_and_dependencies_are_not_source(self):
        self.write('node_modules/lib/index.js')
        self.write('dist/app.js')
        self.assertEqual(self.detect()['repository'], 'empty')

    def test_a_directory_that_is_not_a_repository_is_still_classified(self):
        plain = Path(tempfile.mkdtemp())
        (plain / 'src').mkdir()
        for n in ('a.js', 'b.js', 'c.js', 'd.js'):
            (plain / 'src' / n).write_text(BIG)
        self.assertEqual(dm.classify(str(plain), '')['mode'], 'change')

    def test_the_home_agent_is_told_what_the_repository_looks_like(self):
        import home_agent_session as h
        self.app()
        section = h.project_state_section(str(ROOT), str(self.dir))
        self.assertIn('existing', section)
        self.assertIn('create_change', section)
        self.assertIn('Project state', h.system_prompt(str(ROOT), [], str(self.dir)))
        self.assertNotIn('Project state', h.system_prompt(str(ROOT), [], None))     # no project, nothing invented
        self.assertEqual(h.project_state_section(str(ROOT), '/nonexistent/path/zzz')[:0], '')

    def test_the_command_line_prints_a_single_field(self):
        out = subprocess.run([sys.executable, '-B', str(ROOT / 'scripts/lib/detect_mode.py'), '--project', str(self.dir),
                              '--prompt', 'build me a todo app', '--field', 'mode'], capture_output=True, text=True)
        self.assertEqual(out.stdout.strip(), 'new')


if __name__ == '__main__':
    unittest.main()
