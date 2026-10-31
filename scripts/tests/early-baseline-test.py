#!/usr/bin/env python3
"""Detecting a project's own test commands without a model, and splitting an approved list into what ran early and what did not."""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('early_baseline', ROOT / 'scripts/lib/early_baseline.py')
eb = importlib.util.module_from_spec(spec)
spec.loader.exec_module(eb)


def project(test, files):
    d = tempfile.TemporaryDirectory()
    test.addCleanup(d.cleanup)
    for name, text in files.items():
        path = Path(d.name) / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
    return d.name


class Detect(unittest.TestCase):
    def test_uncles_own_runners(self):
        p = project(self, {'scripts/run-python-tests.sh': '', 'scripts/run-shell-tests.sh': ''})
        self.assertEqual(eb.detect(p), ['bash scripts/run-python-tests.sh', 'bash scripts/run-shell-tests.sh'])

    def test_the_runners_win_over_a_generic_pytest_config(self):
        p = project(self, {'scripts/run-python-tests.sh': '', 'pytest.ini': '[pytest]\n'})
        self.assertEqual(eb.detect(p), ['bash scripts/run-python-tests.sh'])

    def test_npm_needs_a_real_test_script(self):
        self.assertEqual(eb.detect(project(self, {'package.json': json.dumps({'scripts': {'test': 'vitest run'}})})), ['npm test'])
        placeholder = 'echo "Error: no test specified" && exit 1'
        self.assertEqual(eb.detect(project(self, {'package.json': json.dumps({'scripts': {'test': placeholder}})})), [])
        self.assertEqual(eb.detect(project(self, {'package.json': json.dumps({'scripts': {'build': 'vite build'}})})), [])
        self.assertEqual(eb.detect(project(self, {'package.json': '{not json'})), [])

    def test_make_go_cargo_and_pytest(self):
        self.assertEqual(eb.detect(project(self, {'Makefile': 'build:\n\ttrue\ntest:\n\tpytest\n'})), ['make test'])
        self.assertEqual(eb.detect(project(self, {'Makefile': 'build:\n\ttrue\n'})), [])
        self.assertEqual(eb.detect(project(self, {'go.mod': 'module x\n'})), ['go test ./...'])
        self.assertEqual(eb.detect(project(self, {'Cargo.toml': '[package]\n'})), ['cargo test'])
        for files in ({'pytest.ini': ''}, {'tox.ini': ''}, {'pyproject.toml': '[tool.pytest.ini_options]\n'},
                      {'setup.cfg': '[tool:pytest]\n'}):
            self.assertEqual(eb.detect(project(self, files)), ['pytest'], files)

    def test_an_unrecognised_project_detects_nothing(self):
        self.assertEqual(eb.detect(project(self, {'README.md': 'x'})), [])
        self.assertEqual(eb.detect('/no/such/project'), [])


class Partition(unittest.TestCase):
    def files(self, approved, early):
        d = tempfile.TemporaryDirectory()
        self.addCleanup(d.cleanup)
        a, e = Path(d.name) / 'a', Path(d.name) / 'e'
        a.write_text('\n'.join(approved) + '\n')
        e.write_text('\n'.join(early) + '\n')
        return a, e

    def test_covered_and_remaining_in_approved_order(self):
        a, e = self.files(['npm install', 'npm test', 'bash scripts/run-python-tests.sh'], ['bash scripts/run-python-tests.sh', 'npm test'])
        self.assertEqual(eb.partition(a, e), (['npm test', 'bash scripts/run-python-tests.sh'], ['npm install']))
        self.assertFalse(eb.covers(a, e))

    def test_whitespace_does_not_defeat_a_match(self):
        a, e = self.files(['bash  scripts/run-python-tests.sh  '], ['bash scripts/run-python-tests.sh'])
        self.assertTrue(eb.covers(a, e))

    def test_everything_covered(self):
        a, e = self.files(['npm test'], ['npm test', 'make test'])
        self.assertTrue(eb.covers(a, e))
        self.assertEqual(eb.partition(a, e), (['npm test'], []))

    def test_an_empty_approved_list_is_not_covered(self):
        a, e = self.files([], ['npm test'])
        self.assertFalse(eb.covers(a, e))

    def test_a_command_that_differs_at_all_is_not_covered(self):
        a, e = self.files(['npm test -- --watch=false'], ['npm test'])
        self.assertEqual(eb.partition(a, e), ([], ['npm test -- --watch=false']))


if __name__ == '__main__':
    unittest.main()
