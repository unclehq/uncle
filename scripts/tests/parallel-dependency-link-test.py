"""A later-wave worker must be able to run what it writes, so its sandbox is linked to the project's installed dependencies.

The link must never read as something the step wrote: an undeclared file makes the merge refuse the whole group, which sends
the build back to a serial implementation several minutes long."""
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


def make(project_has_modules=True):
    folder = Path(tempfile.mkdtemp())
    project, sandbox = folder / 'project', folder / 'sandbox'
    project.mkdir()
    sandbox.mkdir()
    (project / 'package.json').write_text('{}')
    (sandbox / 'package.json').write_text('{}')
    if project_has_modules:
        (project / 'node_modules' / 'vitest').mkdir(parents=True)
        (project / 'node_modules' / 'vitest' / 'index.js').write_text('module.exports = 1')
    return project, sandbox


class LinkDependencies(unittest.TestCase):
    def run_group(self, worker_body, link):
        """A real worker, run through the executor in a plain project that has dependencies installed."""
        project, _ = make()
        (project / 'a.txt').write_text('base\n')
        worker = project / 'worker.sh'
        worker.write_text('#!/usr/bin/env bash\nset -euo pipefail\n%s\nprintf done > a.txt\n'
                          'mkdir -p .uncle/workflow/parallel/notes\nprintf h > .uncle/workflow/parallel/notes/step-1.md\n' % worker_body)
        request = {'project': str(project), 'owned': {'1': ['a.txt']}, 'steps': [
            {'number': 1, 'log': str(project / 'one.log'), 'note': '.uncle/workflow/parallel/notes/step-1.md',
             'command': ['bash', str(worker)]}]}
        path = project / 'request.json'
        path.write_text(json.dumps(request))
        env = {k: v for k, v in os.environ.items() if k != 'UNCLE_LINK_DEPENDENCIES'}
        if link:
            env['UNCLE_LINK_DEPENDENCIES'] = '1'
        result = subprocess.run([sys.executable, str(ROOT / 'scripts/lib/parallel_steps.py'), str(path)], cwd=project, env=env,
                                text=True, capture_output=True, timeout=30)
        return result, project

    def test_a_group_that_did_not_ask_gets_no_dependencies(self):
        result, project = self.run_group('test ! -e node_modules', link=False)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual((project / 'a.txt').read_text(), 'done')

    def test_a_group_that_asked_can_read_the_installed_dependencies(self):
        result, project = self.run_group('test -L node_modules\ntest "$(cat node_modules/vitest/index.js)" = "module.exports = 1"', link=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual((project / 'a.txt').read_text(), 'done')

    def test_the_link_does_not_make_the_merge_refuse_the_group(self):
        """Merged with the link in place: no undeclared file, nothing copied into the project."""
        result, project = self.run_group('test -L node_modules', link=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue((project / 'node_modules' / 'vitest' / 'index.js').exists())
        self.assertFalse((project / 'node_modules').is_symlink())

    def test_the_sandbox_sees_the_projects_installed_dependencies(self):
        project, sandbox = make()
        parallel_steps.link_dependencies(project, sandbox)
        self.assertTrue((sandbox / 'node_modules').is_symlink())
        self.assertEqual((sandbox / 'node_modules' / 'vitest' / 'index.js').read_text(), 'module.exports = 1')

    def test_a_project_with_nothing_installed_gets_no_link(self):
        project, sandbox = make(project_has_modules=False)
        parallel_steps.link_dependencies(project, sandbox)
        self.assertFalse((sandbox / 'node_modules').exists() or (sandbox / 'node_modules').is_symlink())

    def test_a_directory_the_sandbox_already_has_is_left_alone(self):
        project, sandbox = make()
        (sandbox / 'node_modules').mkdir()
        (sandbox / 'node_modules' / 'own.txt').write_text('mine')
        parallel_steps.link_dependencies(project, sandbox)
        self.assertFalse((sandbox / 'node_modules').is_symlink())
        self.assertTrue((sandbox / 'node_modules' / 'own.txt').exists())

    def test_linking_twice_is_harmless(self):
        project, sandbox = make()
        parallel_steps.link_dependencies(project, sandbox)
        parallel_steps.link_dependencies(project, sandbox)
        self.assertTrue((sandbox / 'node_modules').is_symlink())

    def test_the_link_is_not_a_file_the_step_wrote(self):
        project, sandbox = make()
        before = parallel_steps.snapshot(sandbox, project)
        parallel_steps.link_dependencies(project, sandbox)
        after = parallel_steps.snapshot(sandbox, project)
        self.assertEqual(parallel_steps.changed(before, after, project), set())
        self.assertFalse([rel for rel in after if rel.startswith('node_modules')])

    def test_a_file_the_step_writes_beside_the_link_is_still_seen(self):
        project, sandbox = make()
        parallel_steps.link_dependencies(project, sandbox)
        before = parallel_steps.snapshot(sandbox, project)
        (sandbox / 'tests').mkdir()
        (sandbox / 'tests' / 'a.test.js').write_text('x')
        after = parallel_steps.snapshot(sandbox, project)
        self.assertEqual(parallel_steps.changed(before, after, project), {'tests/a.test.js'})


if __name__ == '__main__':
    unittest.main()
