#!/usr/bin/env python3
"""The test runners default to the critical tier, and `--all` runs everything."""
import glob
import os
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts/lib'))
import cpu_jobs  # noqa: E402
import suite_tier  # noqa: E402


class TierTests(unittest.TestCase):
    def setUp(self):
        self.old = {k: os.environ.pop(k, None) for k in ('WORKFLOW_TEST_TIER', 'WORKFLOW_VERIFY_JOBS')}
        self.addCleanup(self.restore)
        self.cwd = os.getcwd()
        os.chdir(ROOT)
        self.addCleanup(os.chdir, self.cwd)
        self.files = sorted(glob.glob(str(ROOT / 'scripts/tests/*-test.py')) + glob.glob(str(ROOT / 'scripts/tests/*-test.sh')))

    def restore(self):
        for key, value in self.old.items():
            os.environ.pop(key, None)
            if value is not None:
                os.environ[key] = value

    def test_every_manifest_entry_names_a_suite_and_none_repeats(self):
        names = suite_tier.critical_names()
        present = {suite_tier.suite_name(path) for path in self.files}
        self.assertEqual([n for n in names if n not in present], [])
        self.assertEqual(len(names), len(set(names)))

    def test_default_is_the_critical_subset_and_all_is_everything(self):
        chosen = suite_tier.select(self.files)
        self.assertEqual({suite_tier.suite_name(p) for p in chosen}, set(suite_tier.critical_names()))
        self.assertLessEqual(len(chosen), len(self.files))
        os.environ['WORKFLOW_TEST_TIER'] = 'all'
        self.assertEqual(suite_tier.select(self.files), self.files)

    def test_the_tier_suite_itself_is_critical(self):
        self.assertIn('suite-tier', suite_tier.critical_names())

    def test_a_project_without_a_manifest_runs_every_suite(self):
        import tempfile
        with tempfile.TemporaryDirectory() as scratch:
            os.chdir(scratch)
            self.assertEqual(suite_tier.select(['a-test.py', 'b-test.sh']), ['a-test.py', 'b-test.sh'])

    def test_bad_tier_value_is_refused(self):
        os.environ['WORKFLOW_TEST_TIER'] = 'some'
        with self.assertRaises(ValueError):
            suite_tier.select(self.files)

    def test_all_flag_is_consumed_and_sets_the_tier(self):
        self.assertEqual(suite_tier.consume_all_flag(['4', '--all', 'x']), ['4', 'x'])
        self.assertEqual(os.environ['WORKFLOW_TEST_TIER'], 'all')
        os.environ.pop('WORKFLOW_TEST_TIER')
        self.assertEqual(suite_tier.consume_all_flag(['4']), ['4'])
        self.assertNotIn('WORKFLOW_TEST_TIER', os.environ)

    def test_test_workers_are_bounded_and_overridable(self):
        self.assertTrue(1 <= cpu_jobs.default_test_jobs() <= cpu_jobs.TEST_MAX_JOBS)
        os.environ['WORKFLOW_VERIFY_JOBS'] = '2'
        self.assertEqual(cpu_jobs.default_test_jobs(), 2)
        self.assertEqual(cpu_jobs.default_jobs(), 2)


if __name__ == '__main__':
    unittest.main()
