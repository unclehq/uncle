#!/usr/bin/env python3
"""Verification groups for a plan that declares none: only a build beside the unit tests."""
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

LIB = Path(__file__).resolve().parents[1] / 'lib'
sys.path.insert(0, str(LIB))
import auto_groups as g

NOINIT = ['npm ls --depth=0 >/dev/null 2>&1 || npm install', 'npx playwright install chromium', 'npm run build',
          'npx vitest run tests/unit', 'npx playwright test', 'node tests/mutations/run.mjs']


class Groups(unittest.TestCase):
    def test_a_build_beside_the_unit_tests_run_together_and_nothing_else_does(self):
        self.assertEqual(g.groups(NOINIT), [[3, 4], [5, 6]])

    def test_browser_tests_run_beside_the_mutation_runner_in_either_order(self):
        self.assertEqual(g.groups(['npm run build', 'npx playwright test', 'node tests/mutations/run.mjs']), [[2, 3]])
        self.assertEqual(g.groups(['npm run build', 'node tests/mutations/run.mjs', 'npx playwright test']), [[2, 3]])
        self.assertEqual(g.groups(['npx playwright test', 'echo mutation && true']), [])

    def test_the_order_of_the_pair_does_not_matter(self):
        self.assertEqual(g.groups(['npm ci', 'npx vitest run', 'npm run build', 'npx playwright test']), [[2, 3]])

    def test_setup_commands_are_never_grouped(self):
        self.assertEqual(g.groups(['npm install', 'npx playwright install chromium']), [])
        self.assertEqual(g.groups(['npm ci', 'pip install -r requirements.txt']), [])

    def test_browser_tests_stay_after_their_build(self):
        self.assertEqual(g.groups(['npm run build', 'npx playwright test']), [])
        self.assertEqual(g.groups(['npm run build', 'npm run test:e2e']), [])

    def test_unit_tests_run_beside_browser_tests_with_no_build_step(self):
        # A static page served directly, with no build command at all -- the
        # common shape for a small app. A unit suite reads source and opens
        # no port; a browser suite starts and tears down its own dev server
        # on its own port, so the two do not contend for anything.
        self.assertEqual(g.groups(['node --test tests/calc.test.js', 'npx playwright test tests/ui.test.js']), [[1, 2]])
        self.assertEqual(g.groups(['npx playwright test', 'npx vitest run']), [[1, 2]])

    def test_unit_beside_browser_tests_does_not_reorder_a_preceding_build(self):
        # The existing build+unit pairing already claims the unit slot; the
        # greedy pass must not also try to pair it with what follows.
        self.assertEqual(g.groups(['npm run build', 'npx vitest run', 'npx playwright test']), [[1, 2]])

    def test_a_chained_command_is_left_alone(self):
        self.assertEqual(g.groups(['npm run build && npm test', 'npx vitest run']), [])
        self.assertEqual(g.groups(['npm run build', 'npx vitest run | tee out.txt']), [])

    def test_two_unit_commands_or_two_builds_are_not_paired(self):
        self.assertEqual(g.groups(['npx vitest run a', 'npx vitest run b']), [])
        self.assertEqual(g.groups(['npm run build', 'npm run build:docs']), [])

    def test_the_rows_are_the_consecutive_ordered_positions_the_runner_accepts(self):
        rows = g.groups(['npm ci', 'npm run build', 'pytest', 'npm run build', 'jest'])
        self.assertEqual(rows, [[2, 3], [4, 5]])
        self.assertTrue(all(b == a + 1 for row in rows for a, b in zip(row, row[1:])))

    def test_the_cli_prints_rows_and_nothing_when_there_are_none(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp, 'commands')
            path.write_text('\n'.join(NOINIT) + '\n')
            out = subprocess.run([sys.executable, str(LIB / 'auto_groups.py'), str(path)], capture_output=True, text=True)
            self.assertEqual(out.stdout, '3 4\n5 6\n')
            path.write_text('npm test\n')
            self.assertEqual(subprocess.run([sys.executable, str(LIB / 'auto_groups.py'), str(path)], capture_output=True, text=True).stdout, '')


if __name__ == '__main__':
    unittest.main()
