"""The driver normalizes .gitignore in every worker sandbox; that is not a write any step made.

Live run 9: the scaffold worker dropped `.uncle`, every later-wave sandbox got it back from the driver, five correct workers were each
blamed for an undeclared `.gitignore`, the whole wave was refused ("Nothing was merged"), and one serial agent redid the work, which
cost three minutes. A project rule a worker really adds or removes must still count."""
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts/lib'))
import parallel_steps  # noqa: E402


def run_group(body, owned=('a.txt',), gitignore='node_modules\ndist\n'):
    """One real worker in a plain project whose .gitignore holds `gitignore`."""
    project = Path(tempfile.mkdtemp())
    (project / 'a.txt').write_text('base\n')
    (project / '.gitignore').write_text(gitignore)
    (project / '.uncle/workflow/logs').mkdir(parents=True)
    worker = project / 'worker.sh'
    worker.write_text('#!/usr/bin/env bash\nset -euo pipefail\nPROJECT="%s"\n%s\n'
                      'mkdir -p .uncle/workflow/parallel/notes\nprintf h > .uncle/workflow/parallel/notes/step-1.md\n' % (project, body))
    request = {'project': str(project), 'owned': {'1': list(owned)}, 'steps': [
        {'number': 1, 'log': str(project / '.uncle/workflow/logs/one.log'),
         'note': '.uncle/workflow/parallel/notes/step-1.md', 'command': ['bash', str(worker)]}]}
    path = project / 'request.json'
    path.write_text(json.dumps(request))
    env = {k: v for k, v in os.environ.items() if k != 'UNCLE_LINK_DEPENDENCIES'}
    result = subprocess.run([sys.executable, str(ROOT / 'scripts/lib/parallel_steps.py'), str(path)], cwd=project, env=env,
                            text=True, capture_output=True, timeout=30)
    return result, project


class WorkerSandbox(unittest.TestCase):
    def test_the_drivers_own_ignore_line_is_not_a_write(self):
        result, project = run_group('printf ".uncle\\n" >> .gitignore; printf done > a.txt')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotIn('did not declare', result.stderr)
        self.assertEqual((project / 'a.txt').read_text(), 'done')

    def test_the_canonical_managed_block_is_not_a_write_either(self):
        result, project = run_group('printf ".uncle/*\\n!.uncle/docs/\\n" >> .gitignore; printf done > a.txt')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotIn('did not declare', result.stderr)

    def test_a_rule_of_the_workers_own_still_counts_as_a_write(self):
        result, project = run_group('printf "secret.txt\\n" >> .gitignore; printf done > a.txt')
        self.assertEqual(result.returncode, 3, result.stderr)
        self.assertIn('wrote files it did not declare: .gitignore', result.stderr)

    def test_a_managed_line_with_a_rule_of_the_workers_own_still_counts(self):
        result, project = run_group('printf ".uncle\\nsecret.txt\\n" >> .gitignore; printf done > a.txt')
        self.assertEqual(result.returncode, 3, result.stderr)

    def test_removing_a_project_rule_still_counts(self):
        result, project = run_group('printf "node_modules\\n" > .gitignore; printf done > a.txt')
        self.assertEqual(result.returncode, 3, result.stderr)
        self.assertIn('.gitignore', result.stderr)

    def test_a_step_that_owns_the_ignore_file_can_still_change_it(self):
        result, project = run_group('printf "secret.txt\\n" >> .gitignore', owned=('.gitignore',))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('secret.txt', (project / '.gitignore').read_text())

    def test_the_launch_manifest_merges_when_the_ignore_file_hides_the_driver_directory(self):
        """Run 19: the worker wrote .uncle/launch.json, the scaffold's .gitignore held `.uncle`, and nothing was merged."""
        body = 'mkdir -p .uncle; printf "{}" > .uncle/launch.json; printf ".uncle\\n" >> .gitignore; printf done > a.txt'
        result, project = run_group(body, owned=('a.txt', '.uncle/launch.json', '.gitignore'))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual((project / '.uncle/launch.json').read_text(), '{}')

    def test_the_launch_manifest_merges_with_no_ignore_rule_for_the_directory(self):
        result, project = run_group('mkdir -p .uncle; printf "{}" > .uncle/launch.json; printf done > a.txt',
                                    owned=('a.txt', '.uncle/launch.json'))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual((project / '.uncle/launch.json').read_text(), '{}')

    def test_other_driver_files_are_still_not_merged(self):
        body = 'mkdir -p .uncle; printf x > .uncle/scratch.txt; printf ".uncle\\n" >> .gitignore; printf done > a.txt'
        result, project = run_group(body, owned=('a.txt',))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse((project / '.uncle/scratch.txt').exists())

    def test_a_group_of_workers_each_getting_the_line_still_merges(self):
        """Run 9's case: several sandboxes, each given `.uncle` by the driver, none of them owning .gitignore."""
        project = Path(tempfile.mkdtemp())
        (project / '.gitignore').write_text('node_modules\n')
        (project / '.uncle/workflow/logs').mkdir(parents=True)
        steps, owned = [], {}
        for n in (1, 2, 3):
            (project / ('f%d.txt' % n)).write_text('base\n')
            worker = project / ('w%d.sh' % n)
            worker.write_text('#!/usr/bin/env bash\nset -euo pipefail\nprintf ".uncle\\n" >> .gitignore\nprintf done%d > f%d.txt\n'
                              'mkdir -p .uncle/workflow/parallel/notes\nprintf h > .uncle/workflow/parallel/notes/step-%d.md\n' % (n, n, n))
            steps.append({'number': n, 'log': str(project / ('.uncle/workflow/logs/s%d.log' % n)),
                          'note': '.uncle/workflow/parallel/notes/step-%d.md' % n, 'command': ['bash', str(worker)]})
            owned[str(n)] = ['f%d.txt' % n]
        path = project / 'request.json'
        path.write_text(json.dumps({'project': str(project), 'owned': owned, 'steps': steps}))
        result = subprocess.run([sys.executable, str(ROOT / 'scripts/lib/parallel_steps.py'), str(path)], cwd=project,
                                text=True, capture_output=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual([(project / ('f%d.txt' % n)).read_text() for n in (1, 2, 3)], ['done1', 'done2', 'done3'])


class LeakDetectorAndIgnore(unittest.TestCase):
    def test_the_drivers_append_to_the_project_ignore_file_is_not_reported_as_a_leak(self):
        """The driver appends `.uncle` to the project's own .gitignore between stages, sometimes while a group runs."""
        result, project = run_group('printf ".uncle\\n" >> "$PROJECT/.gitignore"; printf done > a.txt')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotIn('live project root', result.stderr)
        self.assertEqual(json.loads(result.stdout.strip().splitlines()[-1])['leaks'], {})

    def test_a_project_rule_written_to_the_live_ignore_file_is_still_reported(self):
        result, project = run_group('printf "secret.txt\\n" >> "$PROJECT/.gitignore"; printf done > a.txt')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('live project root', result.stderr)
        self.assertEqual(json.loads(result.stdout.strip().splitlines()[-1])['leaks'], {'unowned': ['.gitignore']})

    def test_project_leaks_skips_a_path_it_is_told_to_ignore(self):
        found = parallel_steps.project_leaks({}, {'.gitignore': 'x', 'src/a.js': 'y'}, {1: {'src/a.js'}}, ignore=('.gitignore',))
        self.assertEqual(found, {1: ['src/a.js']})

    def test_project_leaks_still_reports_it_by_default(self):
        found = parallel_steps.project_leaks({}, {'.gitignore': 'x'}, {1: {'src/a.js'}})
        self.assertEqual(found, {'unowned': ['.gitignore']})


class ManagedIgnoreOnly(unittest.TestCase):
    def test_adding_the_bare_uncle_line(self):
        self.assertTrue(parallel_steps.managed_ignore_only('node_modules\n', 'node_modules\n.uncle\n'))

    def test_adding_the_canonical_block(self):
        self.assertTrue(parallel_steps.managed_ignore_only('dist\n', 'dist\n.uncle/*\n!.uncle/docs/\n'))

    def test_no_change_at_all(self):
        self.assertTrue(parallel_steps.managed_ignore_only('a\n', 'a\n'))

    def test_a_project_rule_added(self):
        self.assertFalse(parallel_steps.managed_ignore_only('a\n', 'a\nsecret\n'))

    def test_a_project_rule_removed(self):
        self.assertFalse(parallel_steps.managed_ignore_only('a\nb\n', 'a\n'))

    def test_a_rule_replaced(self):
        self.assertFalse(parallel_steps.managed_ignore_only('a\n', 'b\n.uncle\n'))

    def test_a_missing_baseline_or_a_missing_file_is_never_excused(self):
        self.assertFalse(parallel_steps.managed_ignore_only(None, 'a\n'))
        self.assertFalse(parallel_steps.managed_ignore_only('a\n', None))


if __name__ == '__main__':
    unittest.main()
