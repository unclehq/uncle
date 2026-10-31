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

    def test_the_driver_builds_every_lens_from_this_file(self):
        driver = (ROOT / 'scripts/stagegate.sh').read_text(encoding='utf-8')
        self.assertIn('prompts/change/test-review-worker-investigate.md', driver)

    def test_the_finalize_prompt_is_not_capped_here(self):
        # The finalize pass writes the JSON row the driver validates; its own contract governs its length.
        finalize = (ROOT / 'prompts/change/test-review-worker-finalize.md').read_text(encoding='utf-8')
        self.assertNotIn('at most 250 words', finalize)


if __name__ == '__main__':
    unittest.main()
