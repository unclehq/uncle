#!/usr/bin/env python3
"""covers() decides whether a step's declared ownership accounts for a written
path. A step that owns a manifest also owns its lockfile -- a real merge
aborted repeatedly over `package-lock.json` beside a declared `package.json`,
which is not new scope, just an inseparable byproduct of installing what the
plan already authorized."""
import importlib.util
from pathlib import Path
import sys
import unittest

spec = importlib.util.spec_from_file_location('step_groups', Path(__file__).resolve().parents[1] / 'lib/step_groups.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
covers = module.covers


class CoversTests(unittest.TestCase):
    def test_exact_and_directory_tokens_unchanged(self):
        self.assertTrue(covers({'a.txt'}, 'a.txt'))
        self.assertFalse(covers({'a.txt'}, 'b.txt'))
        self.assertTrue(covers({'src/'}, 'src/calc.js'))
        self.assertTrue(covers({'src'}, 'src/calc.js'))
        self.assertTrue(covers({'*'}, 'anything/at/all'))

    def test_owning_a_manifest_covers_its_root_lockfile(self):
        self.assertTrue(covers({'package.json'}, 'package-lock.json'))
        self.assertTrue(covers({'package.json'}, 'yarn.lock'))
        self.assertTrue(covers({'package.json'}, 'pnpm-lock.yaml'))
        self.assertTrue(covers({'Cargo.toml'}, 'Cargo.lock'))
        self.assertTrue(covers({'pyproject.toml'}, 'poetry.lock'))
        self.assertTrue(covers({'Gemfile'}, 'Gemfile.lock'))

    def test_manifest_in_a_subdirectory_covers_the_lockfile_beside_it_only(self):
        self.assertTrue(covers({'app/package.json'}, 'app/package-lock.json'))
        self.assertFalse(covers({'app/package.json'}, 'package-lock.json'),
                          'a lockfile in a different directory is not the same install')
        self.assertFalse(covers({'package.json'}, 'app/package-lock.json'),
                          'declaring the root manifest does not reach into a subdirectory')

    def test_lockfile_inference_never_covers_an_unrelated_file(self):
        self.assertFalse(covers({'package.json'}, 'index.html'))
        self.assertFalse(covers({'package.json'}, '.gitignore'),
                          '.gitignore is not a lockfile of any manifest; it must still be declared')
        self.assertFalse(covers({'package.json'}, 'Cargo.lock'),
                          'the wrong ecosystem lockfile is not inferred')

    def test_owning_only_the_lockfile_does_not_cover_the_manifest(self):
        self.assertFalse(covers({'package-lock.json'}, 'package.json'))

    def test_glob_token_covers_matching_files_in_that_directory(self):
        self.assertTrue(covers({'scripts/tests/*.sh'}, 'scripts/tests/checklist-groups-test.sh'))
        self.assertFalse(covers({'scripts/tests/*.sh'}, 'scripts/tests/checklist-groups-test.py'),
                          'the extension must match, not just the directory')
        self.assertFalse(covers({'scripts/tests/*.sh'}, 'scripts/lib/checklist-groups-test.sh'),
                          'a glob only reaches into its own directory')
        self.assertFalse(covers({'scripts/tests/*.sh'}, 'scripts/tests/nested/checklist-groups-test.sh'),
                          'a single-star glob does not cross a path separator')


class GroupTests(unittest.TestCase):
    OWNED = {n: {'f%d' % n} for n in range(1, 10)}
    DEPS = {9: [1, 2, 3, 4, 8], 8: []}

    def test_a_dependency_splits_a_group_by_default_in_the_function(self):
        self.assertEqual(module.group(9, self.OWNED, self.DEPS), [[1, 2, 3, 4, 5, 6, 7, 8], [9]])

    def test_ignoring_dependencies_groups_by_ownership_alone(self):
        self.assertEqual(module.group(9, self.OWNED, self.DEPS, ignore_deps=True), [list(range(1, 10))])

    def test_a_shared_file_still_splits_when_dependencies_are_ignored(self):
        owned = {**self.OWNED, 9: {'f8'}}
        self.assertEqual(module.group(9, owned, self.DEPS, ignore_deps=True), [list(range(1, 9)), [9]])

    def test_a_step_that_declared_nothing_still_runs_alone(self):
        owned = {1: {'a'}, 2: set(), 3: {'c'}}
        self.assertEqual(module.group(3, owned, {}, ignore_deps=True), [[1], [2], [3]])

    def test_the_driver_ignores_dependencies_unless_told_not_to(self):
        import os, subprocess, tempfile
        with tempfile.TemporaryDirectory() as tmp:
            plan = Path(tmp) / 'plan.md'
            plan.write_text('# Plan\n\n## 12. Implementation order\n\n1. A\n   Owns: `a.js`\n2. B\n   Owns: `b.js`\n'
                            '   Depends on: 1\n')
            lib = Path(__file__).resolve().parents[1] / 'lib'
            def groups(flag):
                env = dict(os.environ, WORKFLOW_IMPLEMENT_IGNORE_DEPENDS=flag)
                out = subprocess.run([sys.executable, str(lib / 'step_groups.py'), str(plan), tmp],
                                     capture_output=True, text=True, env=env).stdout
                import json
                return json.loads(out)['groups']
            self.assertEqual(groups('1'), [[1, 2]])
            self.assertEqual(groups('0'), [[1], [2]])


if __name__ == '__main__':
    unittest.main()
