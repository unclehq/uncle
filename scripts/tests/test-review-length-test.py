#!/usr/bin/env python3
"""The test-review investigate report is capped: its length is the call's cost (a report five times longer took five times as long)."""
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


class InvestigateReportLength(unittest.TestCase):
    def prompt(self):
        return (ROOT / 'prompts/change/test-review-worker-investigate.md').read_text(encoding='utf-8')

    def test_the_report_has_a_word_budget_and_says_why(self):
        text = ' '.join(self.prompt().split())
        self.assertRegex(text, r'at most 250 words')
        self.assertIn('Length is the cost of this call', text)

    def test_the_cap_sits_with_the_report_instructions_not_after_the_row_heading(self):
        text = self.prompt()
        self.assertLess(text.index('at most 250 words'), text.index('what you read and checked'))
        self.assertLess(text.index('what you read and checked'), text.index('## Assigned acceptance-gate row'))


if __name__ == '__main__':
    unittest.main()
