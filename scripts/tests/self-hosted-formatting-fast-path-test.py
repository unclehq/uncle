#!/usr/bin/env python3
"""Guard against reintroducing a second self-hosted formatting model call."""
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[2]


class SelfHostedFormattingFastPath(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = (ROOT / 'scripts/stagegate.sh').read_text(encoding='utf-8')

    def block(self, start, end):
        begin = self.source.index(start, self.source.index('run_stage()'))
        return self.source[begin:self.source.index(end, begin)]

    def test_requirements_project_plan_preflight_and_adversarial_are_driver_converted(self):
        requirements = self.block('        REQUIREMENTS)', '        PROJECT_PLAN)')
        project_plan = self.block('        PROJECT_PLAN)', '        ADVERSARIAL_REVIEW)')
        adversarial = self.block('        ADVERSARIAL_REVIEW)', '        UPDATED_PLAN)')
        preflight = self.block('        PREFLIGHT)', '        TEST_REVIEW)')
        for block, converter in (
            (requirements, 'requirements-context.py" --export-json'),
            (project_plan, 'plan_context.py" export-project-plan'),
            (adversarial, 'adversarial-context.py" --export-json'),
            (preflight, 'acceptance_context.py" --export-json'),
        ):
            self.assertIn(converter, block)
            self.assertNotIn('format_prompt=', block)

    def test_notes_are_preserved_as_canonical_fragments_without_a_formatter(self):
        implementation = self.block('        IMPLEMENT)', '        PREFLIGHT)')
        repair = self.block('        REPAIR)', '        MANUAL_CHECKLIST)')
        for block in (implementation, repair):
            self.assertIn('implementation_notes.py" append', block)
            self.assertNotIn('format_prompt=', block)

    def test_self_hosted_review_fallbacks_are_single_call(self):
        for start, end, direct_prompt in (
            ('        TEST_REVIEW)', '        REPAIR)', 'prompts/test-review.md'),
            ('        MANUAL_CHECKLIST)', '        EXECUTE_CHECKLIST)', 'prompts/manual-checklist.md'),
            ('        FINAL_AUDIT)', '        *)', 'prompts/final-audit.md'),
        ):
            block = self.block(start, end)
            self.assertIn(direct_prompt, block)
            self.assertNotIn('format_prompt=', block)
            self.assertNotIn('-investigate\n', block)


if __name__ == '__main__':
    unittest.main()
