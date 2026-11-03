"""A worker that writes into the live project root instead of its sandbox skips the ownership check the merge relies on.

About half the workers in live runs 3, 5 and 6 did exactly that. The detector reports it and names the files; it must never fail
a group, because the driver also touches the project root and a false alarm would cost a serial implementation."""
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


def run_group(body):
    """One real worker in a plain project. `body` is bash; PROJECT is the live project root."""
    project = Path(tempfile.mkdtemp())
    (project / 'a.txt').write_text('base\n')
    worker = project / 'worker.sh'
    worker.write_text('#!/usr/bin/env bash\nset -euo pipefail\nPROJECT="%s"\n%s\n'
                      'mkdir -p .uncle/workflow/parallel/notes\nprintf h > .uncle/workflow/parallel/notes/step-1.md\n'
                      % (project, body))
    (project / '.uncle/workflow/logs').mkdir(parents=True)          # where the driver keeps worker logs, outside what is watched
    request = {'project': str(project), 'owned': {'1': ['a.txt', 'tests/own.test.js']}, 'steps': [
        {'number': 1, 'log': str(project / '.uncle/workflow/logs/one.log'), 'note': '.uncle/workflow/parallel/notes/step-1.md',
         'command': ['bash', str(worker)]}]}
    path = project / 'request.json'
    path.write_text(json.dumps(request))
    env = {k: v for k, v in os.environ.items() if k != 'UNCLE_LINK_DEPENDENCIES'}
    result = subprocess.run([sys.executable, str(ROOT / 'scripts/lib/parallel_steps.py'), str(path)], cwd=project, env=env,
                            text=True, capture_output=True, timeout=30)
    summary = json.loads(result.stdout.strip().splitlines()[-1]) if result.returncode == 0 else None
    return result, project, summary


class LeakDetector(unittest.TestCase):
    def test_a_worker_that_stays_in_its_sandbox_reports_nothing(self):
        result, project, summary = run_group('printf done > a.txt')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotIn('live project root', result.stderr)
        self.assertEqual(summary['leaks'], {})
        self.assertEqual((project / 'a.txt').read_text(), 'done')

    def test_a_write_to_the_project_root_in_the_workers_own_paths_is_named(self):
        result, project, summary = run_group('mkdir -p "$PROJECT/tests"; printf leaked > "$PROJECT/tests/own.test.js"')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('Step 1 wrote to the live project root instead of its sandbox, in its own declared paths', result.stderr)
        self.assertIn('tests/own.test.js', result.stderr)
        self.assertEqual(summary['leaks'], {'1': ['tests/own.test.js']})

    def test_a_write_to_a_path_nobody_declared_is_named_as_unowned(self):
        result, project, summary = run_group('printf stray > "$PROJECT/stray.js"')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('outside every declared path', result.stderr)
        self.assertIn('stray.js', result.stderr)
        self.assertEqual(summary['leaks'], {'unowned': ['stray.js']})

    def test_reporting_never_fails_the_group(self):
        """The group still merges: a report, not a verdict."""
        result, project, summary = run_group('printf stray > "$PROJECT/stray.js"; printf done > a.txt')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual((project / 'a.txt').read_text(), 'done')
        self.assertEqual(summary['merged'], [1])

    def test_a_change_to_a_file_the_project_already_had_is_a_leak_too(self):
        result, project, summary = run_group('printf changed > "$PROJECT/a.txt"')
        self.assertEqual(summary['leaks'], {'1': ['a.txt']})


class ProjectLeaks(unittest.TestCase):
    def test_a_file_in_two_workers_paths_is_named_for_both(self):
        found = parallel_steps.project_leaks({}, {'shared.js': 'x'}, {1: {'shared.js'}, 2: {'shared.js'}})
        self.assertEqual(found, {1: ['shared.js'], 2: ['shared.js']})

    def test_nothing_changed_is_nothing_reported(self):
        self.assertEqual(parallel_steps.project_leaks({'a': 'x'}, {'a': 'x'}, {1: {'a'}}), {})


if __name__ == '__main__':
    unittest.main()
