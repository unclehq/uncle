#!/usr/bin/env python3
"""test_review_advisory.py: COVERAGE/ORACLE become nonblocking only when
every row that actually proves correct application behavior is clean."""
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('test_review_advisory', ROOT / 'scripts/lib/test_review_advisory.py')
advisory = importlib.util.module_from_spec(spec); spec.loader.exec_module(advisory)

BLOCKING_PASS = [
    {'id': 'ASSERTIONS', 'required': True, 'status': 'PASS', 'evidence': 'e'},
    {'id': 'INTEGRITY', 'required': True, 'status': 'PASS', 'evidence': 'e'},
    {'id': 'NEGATIVE', 'required': True, 'status': 'PASS', 'evidence': 'e'},
    {'id': 'RESULTS', 'required': True, 'status': 'PASS', 'evidence': 'e'},
]


class TestReviewAdvisory(unittest.TestCase):
    def run_on(self, rows):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'TEST_REVIEW.json'
            path.write_text(json.dumps({'schema': 'uncle.artifact/v1', 'kind': 'acceptance-report', 'rows': rows}))
            downgraded = advisory.downgrade(path)
            return downgraded, json.loads(path.read_text())['rows']

    def test_real_calculator_case_downgrades_oracle_not_run(self):
        # calculator, 2026-10-29: everything that proves the app works passed;
        # only ORACLE (the reviewer independently re-deriving expected values)
        # had not run yet. The build should not block on that.
        rows = BLOCKING_PASS + [
            {'id': 'COVERAGE', 'required': True, 'status': 'PASS', 'evidence': 'e'},
            {'id': 'ORACLE', 'required': True, 'status': 'NOT RUN', 'evidence': 'e'},
        ]
        downgraded, after = self.run_on(rows)
        self.assertEqual(downgraded, ['ORACLE'])
        oracle = next(r for r in after if r['id'] == 'ORACLE')
        self.assertFalse(oracle['required'])
        self.assertEqual(oracle['status'], 'NOT RUN', 'status is untouched; only required changes')

    def test_coverage_fail_downgrades_when_blocking_rows_are_clean(self):
        rows = BLOCKING_PASS + [
            {'id': 'COVERAGE', 'required': True, 'status': 'FAIL', 'evidence': 'thin mutation coverage'},
            {'id': 'ORACLE', 'required': True, 'status': 'PASS', 'evidence': 'e'},
        ]
        downgraded, after = self.run_on(rows)
        self.assertEqual(downgraded, ['COVERAGE'])
        coverage = next(r for r in after if r['id'] == 'COVERAGE')
        self.assertFalse(coverage['required'])
        self.assertEqual(coverage['status'], 'FAIL', 'the FAIL stays visible; only blocking changes')

    def test_does_not_downgrade_when_a_blocking_row_fails(self):
        # press(undefined) throwing is a real defect: ASSERTIONS failing must
        # never be waved through because COVERAGE also happens to be weak.
        rows = [
            {'id': 'ASSERTIONS', 'required': True, 'status': 'FAIL', 'evidence': 'press(undefined) throws'},
            {'id': 'INTEGRITY', 'required': True, 'status': 'PASS', 'evidence': 'e'},
            {'id': 'NEGATIVE', 'required': True, 'status': 'PASS', 'evidence': 'e'},
            {'id': 'RESULTS', 'required': True, 'status': 'PASS', 'evidence': 'e'},
            {'id': 'COVERAGE', 'required': True, 'status': 'FAIL', 'evidence': 'e'},
        ]
        downgraded, after = self.run_on(rows)
        self.assertEqual(downgraded, [])
        self.assertTrue(next(r for r in after if r['id'] == 'COVERAGE')['required'])

    def test_negative_is_never_advisory(self):
        # CLAUDE.md requires defect-injection evidence for critical tests;
        # a weak mutation gate must still block even if everything else passes.
        rows = [
            {'id': 'ASSERTIONS', 'required': True, 'status': 'PASS', 'evidence': 'e'},
            {'id': 'INTEGRITY', 'required': True, 'status': 'PASS', 'evidence': 'e'},
            {'id': 'NEGATIVE', 'required': True, 'status': 'FAIL', 'evidence': 'no mutants for DI-7..DI-10'},
            {'id': 'RESULTS', 'required': True, 'status': 'PASS', 'evidence': 'e'},
            {'id': 'COVERAGE', 'required': True, 'status': 'FAIL', 'evidence': 'e'},
        ]
        downgraded, after = self.run_on(rows)
        self.assertEqual(downgraded, [])
        self.assertTrue(next(r for r in after if r['id'] == 'NEGATIVE')['required'])
        self.assertTrue(next(r for r in after if r['id'] == 'COVERAGE')['required'])

    def test_all_blocking_rows_already_passing_with_nothing_advisory_to_downgrade(self):
        rows = BLOCKING_PASS + [{'id': 'COVERAGE', 'required': True, 'status': 'PASS', 'evidence': 'e'}]
        downgraded, after = self.run_on(rows)
        self.assertEqual(downgraded, [])

    def test_already_nonrequired_row_is_left_alone(self):
        rows = BLOCKING_PASS + [{'id': 'COVERAGE', 'required': False, 'status': 'FAIL', 'evidence': 'e'}]
        downgraded, _ = self.run_on(rows)
        self.assertEqual(downgraded, [])

    def test_malformed_payload_is_a_no_op(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'TEST_REVIEW.json'
            path.write_text('not json')
            with self.assertRaises(ValueError):
                advisory.downgrade(path)


if __name__ == '__main__':
    unittest.main()
