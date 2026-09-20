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


if __name__ == '__main__':
    unittest.main()
