#!/usr/bin/env python3
"""apply_patch accepts a section heading with or without its `## ` marker (models copy the plan JSON's `7. Title`)."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'lib'))
from plan_patch import apply_patch  # noqa: E402

PLAN = '# Plan\n\n## 1. Architecture\n\nOne crate.\n\n## 7. Domain invariants\n\nI-1: old rule.\n'


class HeadingForms(unittest.TestCase):
    def test_replace_text_without_marker(self):
        for heading in ('7. Domain invariants', '## 7. Domain invariants', '  7. Domain invariants  '):
            patch = {'replace_text': [{'heading': heading, 'old': 'old rule', 'new': 'new rule'}]}
            self.assertEqual(apply_patch(PLAN, patch), PLAN.replace('old rule', 'new rule'), heading)

    def test_edit_sections_without_marker(self):
        patch = {'edit_sections': [{'heading': '1. Architecture', 'content': 'Two crates.'}]}
        self.assertEqual(apply_patch(PLAN, patch), PLAN.replace('One crate.', 'Two crates.'))

    def test_insert_anchor_without_marker(self):
        patch = {'insert_sections': [{'content': '## 8. Failure\n\nNone.', 'after': '7. Domain invariants'}]}
        self.assertTrue(apply_patch(PLAN, patch).rstrip().endswith('## 8. Failure\n\nNone.'))

    def test_missing_heading_still_fails(self):
        with self.assertRaisesRegex(ValueError, 'no existing section'):
            apply_patch(PLAN, {'replace_text': [{'heading': '9. Nope', 'old': 'x', 'new': 'y'}]})


if __name__ == '__main__':
    unittest.main()
