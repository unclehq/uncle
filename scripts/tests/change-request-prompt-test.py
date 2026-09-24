#!/usr/bin/env python3
"""Regression coverage for binding the selected change request into handoffs."""
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[2]


class ChangeRequestPromptTest(unittest.TestCase):
    def test_change_request_is_bound_for_planning_and_review_handoffs(self):
        source = (ROOT / 'scripts/change-workflow.sh').read_text(encoding='utf-8')
        start = source.index('bind_change_request_source()')
        end = source.index('\nrun_claude()', start)
        binding = source[start:end]
        for stage in ('baseline', 'change-spec', 'change-plan', 'updated-change-plan',
                      'adversarial-review', 'manual-checklist'):
            self.assertIn(stage, binding)
        self.assertIn('The exact selected change request follows.', binding)
        self.assertIn('cat "$DOCUMENT_BUDGET_SOURCE"', binding)
        self.assertIn('bind_change_request_source "$effective_prompt" "$log_name"', source)
        self.assertIn('bind_change_request_source "$prompt_file" "$log_name"', source)

    def test_generated_request_is_the_selected_input(self):
        source = (ROOT / 'scripts/change-workflow.sh').read_text(encoding='utf-8')
        self.assertIn('DOCUMENT_BUDGET_SOURCE="$(generated_input_path CHANGE_REQUEST.md)"', source)
        self.assertIn('Selected path: %s', source)


if __name__ == '__main__':
    unittest.main()
