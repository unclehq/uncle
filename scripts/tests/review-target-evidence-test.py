#!/usr/bin/env python3
"""Shared references do not prove that two review failures are duplicates."""
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'lib'))
from adversarial_slices import same_issue


class TargetEvidence(unittest.TestCase):
    def test_distinct_validation_failures_with_identical_references_remain_separate(self):
        for evidence in ('B-1', 'B-1, UB-1', 'B-1: input validation is unspecified.'):
            left = {'summary': 'Input validation accepts NaN and corrupts totals',
                    'evidence': evidence, 'severity': 'high'}
            right = {'summary': 'Input validation lacks payload size limit and exhausts memory',
                     'evidence': evidence, 'severity': 'high'}
            with self.subTest(evidence=evidence):
                self.assertFalse(same_issue(left, right))
                self.assertFalse(same_issue(right, left))


if __name__ == '__main__':
    unittest.main()
