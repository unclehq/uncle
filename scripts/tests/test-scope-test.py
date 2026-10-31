#!/usr/bin/env python3
"""Impacted-test scoping: a confident mapping, a conservative fallback to the full suite, and honest NOT RUN reporting."""
import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('test_scope', ROOT / 'scripts/lib/test_scope.py')
ts = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ts)


class Project:
    """A git repository with Uncle's layout: scripts/lib/* and scripts/tests/<name>-test.(py|sh)."""
    def __init__(self, test):
        self.dir = tempfile.TemporaryDirectory()
        test.addCleanup(self.dir.cleanup)
        self.root = Path(self.dir.name)
        (self.root / 'scripts/lib').mkdir(parents=True)
        (self.root / 'scripts/tests').mkdir(parents=True)
        for name in ('alpha', 'beta', 'gamma', 'delta', 'epsilon', 'zeta'):
            (self.root / f'scripts/lib/{name}_module.py').write_text('x = 1\n')
        for name in ('alpha', 'beta', 'gamma', 'delta', 'epsilon', 'zeta'):
            self.suite(f'{name}-checks', 'py', f'import {name}_module  # scripts/lib/{name}_module.py\n')
        self.suite('alpha-driver', 'sh', '# exercises alpha_module.py\n')
        for n in range(4):
            self.suite(f'other{n}', 'sh', 'true\n')
        (self.root / 'README.md').write_text('docs\n')
        for cmd in (['git', 'init', '-q'], ['git', 'add', '-A'],
                    ['git', '-c', 'user.name=t', '-c', 'user.email=t@e.t', '-c', 'commit.gpgsign=false', 'commit', '-qm', 'base']):
            subprocess.run(cmd, cwd=self.root, check=True, capture_output=True)

    def suite(self, name, ext, text):
        (self.root / f'scripts/tests/{name}-test.{ext}').write_text(text)

    def edit(self, path, text='x = 2\n'):
        (self.root / path).write_text(text)


class Impact(unittest.TestCase):
    def test_a_changed_module_maps_to_the_suites_that_name_it(self):
        p = Project(self)
        found = ts.impact(p.root, ['scripts/lib/alpha_module.py'])
        self.assertEqual(found['suites'], {'python': ['alpha-checks'], 'shell': ['alpha-driver']})
        self.assertTrue(found['confident'])

    def test_a_changed_test_maps_to_itself(self):
        p = Project(self)
        found = ts.impact(p.root, ['scripts/tests/beta-checks-test.py'])
        self.assertEqual(found['suites'], {'python': ['beta-checks'], 'shell': []})
        self.assertTrue(found['confident'])

    def test_a_file_no_suite_names_is_not_confident(self):
        p = Project(self)
        p.edit('scripts/lib/orphan_module.py')
        found = ts.impact(p.root, ['scripts/lib/orphan_module.py'])
        self.assertFalse(found['confident'])
        self.assertIn('named by no suite', found['reasons'][0])

    def test_documentation_nobody_names_is_not_confident(self):
        found = ts.impact(Project(self).root, ['docs/guide.md'])
        self.assertFalse(found['confident'])
        self.assertIn('documentation', found['reasons'][0])

    def test_a_hot_file_is_the_full_suite_not_an_impacted_set(self):
        p = Project(self)
        for n in range(ts.MAX_FAN_IN + 1):
            p.suite(f'hot{n}', 'sh', '# uses shared_core.py\n')
        found = ts.impact(p.root, ['scripts/lib/shared_core.py'])
        self.assertFalse(found['confident'])
        self.assertIn('full suite', found['reasons'][0])

    def test_one_unmapped_file_makes_the_whole_change_unsure(self):
        p = Project(self)
        found = ts.impact(p.root, ['scripts/lib/alpha_module.py', 'scripts/lib/orphan_module.py'])
        self.assertFalse(found['confident'])

    def test_no_changed_files_is_not_confident(self):
        self.assertFalse(ts.impact(Project(self).root, [])['confident'])

    def test_changed_files_come_from_git_and_skip_workflow_state(self):
        p = Project(self)
        p.edit('scripts/lib/alpha_module.py')
        p.edit('scripts/lib/new_module.py')
        (p.root / '.uncle/workflow').mkdir(parents=True)
        (p.root / '.uncle/workflow/state').write_text('x')
        (p.root / 'CHANGE_PLAN.md').write_text('plan')
        self.assertEqual(sorted(ts.changed_files(p.root)), ['scripts/lib/alpha_module.py', 'scripts/lib/new_module.py'])


class Rewrite(unittest.TestCase):
    def run_rewrite(self, p, commands, files):
        cmds = p.root / 'commands'
        cmds.write_text('\n'.join(commands) + '\n')
        record = ts.rewrite(p.root, cmds, p.root / 'scoped', p.root / 'scope.json', 'small', files)
        return record, (p.root / 'scoped').read_text().splitlines()

    def test_the_two_runners_get_their_impacted_suites(self):
        p = Project(self)
        record, lines = self.run_rewrite(p, ['bash scripts/run-python-tests.sh', 'bash scripts/run-shell-tests.sh'],
                                         ['scripts/lib/alpha_module.py'])
        self.assertTrue(record['applied'])
        self.assertEqual(lines, ['bash scripts/run-python-tests.sh -- alpha-checks', 'bash scripts/run-shell-tests.sh -- alpha-driver'])

    def test_a_runner_with_no_impacted_suite_is_omitted_and_reported_not_run(self):
        p = Project(self)
        record, lines = self.run_rewrite(p, ['bash scripts/run-python-tests.sh', 'bash scripts/run-shell-tests.sh'],
                                         ['scripts/tests/beta-checks-test.py'])
        self.assertEqual(lines, ['bash scripts/run-python-tests.sh -- beta-checks'])
        self.assertEqual(record['not_run_commands'], ['bash scripts/run-shell-tests.sh'])
        self.assertIn('NOT RUN (no impacted suite): `bash scripts/run-shell-tests.sh`', ts.report(p.root / 'scope.json'))

    def test_other_commands_run_exactly_as_approved(self):
        p = Project(self)
        record, lines = self.run_rewrite(p, ['node --check app.js', 'pytest -q', 'bash scripts/run-python-tests.sh'],
                                         ['scripts/lib/alpha_module.py'])
        self.assertEqual(lines, ['node --check app.js', 'pytest -q', 'bash scripts/run-python-tests.sh -- alpha-checks'])

    def test_a_plan_that_already_chose_its_suites_is_left_alone(self):
        p = Project(self)
        record, lines = self.run_rewrite(p, ['bash scripts/run-python-tests.sh -- beta-checks'], ['scripts/lib/alpha_module.py'])
        self.assertFalse(record['applied'])
        self.assertEqual(lines, ['bash scripts/run-python-tests.sh -- beta-checks'])

    def test_when_every_suite_is_impacted_the_command_stays_the_full_run(self):
        p = Project(self)
        files = ['scripts/lib/%s_module.py' % n for n in ('alpha', 'beta', 'gamma', 'delta', 'epsilon', 'zeta')]
        record, lines = self.run_rewrite(p, ['bash scripts/run-python-tests.sh'], files)
        self.assertEqual(lines, ['bash scripts/run-python-tests.sh'])
        self.assertFalse(record['applied'])

    def test_an_unsure_mapping_changes_nothing(self):
        p = Project(self)
        record, lines = self.run_rewrite(p, ['bash scripts/run-python-tests.sh'], ['scripts/lib/orphan_module.py'])
        self.assertEqual((record['applied'], lines), (False, ['bash scripts/run-python-tests.sh']))
        self.assertEqual(ts.report(p.root / 'scope.json'), '')

    def test_commands_that_would_all_be_omitted_are_not_a_scope(self):
        p = Project(self)
        record, lines = self.run_rewrite(p, ['bash scripts/run-shell-tests.sh'], ['scripts/tests/beta-checks-test.py'])
        self.assertFalse(record['applied'])
        self.assertEqual(lines, ['bash scripts/run-shell-tests.sh'])

    def test_the_report_says_what_was_not_run(self):
        p = Project(self)
        self.run_rewrite(p, ['bash scripts/run-python-tests.sh'], ['scripts/lib/alpha_module.py'])
        text = ts.report(p.root / 'scope.json')
        self.assertIn('IMPACTED subset', text)
        self.assertIn('python suites: ran 1 of 6 (alpha-checks); the other 5 were NOT RUN', text)
        self.assertIn('WORKFLOW_TEST_SCOPE=full', text)


if __name__ == '__main__':
    unittest.main()
