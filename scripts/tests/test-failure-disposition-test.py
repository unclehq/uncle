#!/usr/bin/env python3
import importlib.util
import tempfile
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('disposition', ROOT / 'scripts/lib/test_failure_disposition.py')
MODULE = importlib.util.module_from_spec(spec); spec.loader.exec_module(MODULE)


class TestFailureDisposition(unittest.TestCase):
    def test_records_failed_command_and_independent_results_evidence(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            green = root / 'green.tsv'
            green.write_text('REGRESSION\tnpm test\nPASS\tnpm run build\n')
            review = root / 'TEST_REVIEW.json'
            review.write_text('{"rows":[{"id":"RESULTS","status":"PASS","evidence":"browser smoke check passed"}]}')
            self.assertEqual(MODULE.failures(green), [{'classification':'REGRESSION','command':'npm test'}])
            self.assertEqual(MODULE.functional_evidence(review), ('ACCEPTED_WITH_FUNCTIONAL_EVIDENCE', 'browser smoke check passed'))

    def test_missing_or_failed_review_is_not_claimed_as_functional_evidence(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.assertEqual(MODULE.functional_evidence(root / 'missing.json')[0], 'UNVERIFIED')
            review = root / 'TEST_REVIEW.json'
            review.write_text('{"rows":[{"id":"RESULTS","status":"FAIL","evidence":"smoke check failed"}]}')
            self.assertEqual(MODULE.functional_evidence(review), ('UNVERIFIED', 'TEST_REVIEW RESULTS is FAIL: smoke check failed'))


if __name__ == '__main__':
    unittest.main()
