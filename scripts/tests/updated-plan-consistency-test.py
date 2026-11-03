#!/usr/bin/env python3
"""An accepted finding that sets a value, format, limit or rule must carry through to every example of it in the writer's own rows.

Run 19: the review found the exponent format undefined, the updated plan said display text is at most 12 characters, and test row
T-4 still demanded `9.99999999e+19` (14 characters). The build then chased a result the plan forbids, and two checklist rows failed.
The writer's prompt is read as the real driver builds it."""
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts' / 'lib'))
import updated_plan_ops as ops  # noqa: E402


class WriterPrompt(unittest.TestCase):
    def test_a_slice_writer_is_told_to_carry_a_decision_through_its_examples(self):
        note = ops.SLICE_NOTE % ('AR-001', '')
        self.assertIn('every row of yours that states an example or an expected result for', note)
        self.assertIn('Change any example your own rule makes impossible', note)
        self.assertIn('a sample longer than the limit you set', note)

    def test_the_general_rules_say_it_too(self):
        text = ' '.join(ops.OPS_RULES.split())
        self.assertIn('every row you may edit that gives an example or expected result for the same thing must agree with it', text)

    def test_the_slice_rule_does_not_license_edits_to_other_writers_rows(self):
        note = ops.SLICE_NOTE % ('AR-001', '')
        self.assertIn('Never rewrite what another finding obviously owns.', note)
        self.assertIn('every row of yours', note)


if __name__ == '__main__':
    unittest.main()
