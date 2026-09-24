#!/usr/bin/env python3
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[2]


class CompactProjectPlanPrompt(unittest.TestCase):
    def test_project_plan_bypasses_generic_gates_and_evidence_index(self):
        source = (ROOT / 'scripts/lib/gates.sh').read_text()
        start = source.index('    # Review-parent synthesis')
        end = source.index('\n    local is_plan=', start)
        compact = source[start:end]
        self.assertIn('project-plan|change-plan|updated-plan', compact)
        self.assertIn('project-plan-investigate)', compact)
        self.assertIn('completed investigation and REQUIREMENTS_INTERPRETATION JSON', compact)
        self.assertIn('approved BASELINE_REPORT and CHANGE_SPEC', compact)
        self.assertIn('Do not inspect project source,', compact)
        self.assertIn('return 0', compact)

    def test_adversarial_workers_receive_only_named_canonical_inputs(self):
        app = (ROOT / 'scripts/stagegate.sh').read_text()
        change = (ROOT / 'scripts/change-workflow.sh').read_text()
        self.assertIn('REQUIREMENTS_INTERPRETATION.json` and `.uncle/workflow/documents/PROJECT_PLAN.json', app)
        self.assertIn('CHANGE_PLAN.json` and `.uncle/workflow/documents/CHANGE_SPEC.json', change)
        worker = (ROOT / 'prompts/change/adversarial-review-worker.md').read_text()
        self.assertIn('Return exactly one JSON object', worker)


if __name__ == '__main__':
    unittest.main()
