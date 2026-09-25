#!/usr/bin/env python3
"""Manual checklist workers must receive a bounded, named JSON input set."""
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


class ManualChecklistWorkerInputs(unittest.TestCase):
    def test_application_workers_name_only_canonical_json_inputs(self):
        text = (ROOT / 'scripts/stagegate.sh').read_text()
        start = text.index('run_manual_checklist_panel()')
        end = text.index('\n}\n', start) + 2
        block = text[start:end]
        for name in ('REQUIREMENTS_INTERPRETATION.json', 'PROJECT_PLAN.json',
                     'UPDATED_PROJECT_PLAN.json', 'ADVERSARIAL_REVIEW.json',
                     'TEST_REVIEW.json'):
            self.assertIn(name, block)
        self.assertIn('Do not inspect any rendered Markdown view', block)
        self.assertIn('Manual-checklist worker $lens returned an invalid packet; retrying that worker once.', block)
        self.assertIn('Do not ask a question, discuss prior checklist documents', block)

    def test_change_base_and_delta_workers_name_their_json_evidence(self):
        text = (ROOT / 'scripts/change-workflow.sh').read_text()
        start = text.index('run_checklist_panel()')
        end = text.index('\n}\n', start) + 2
        block = text[start:end]
        for name in ('BASELINE_REPORT.json', 'CHANGE_SPEC.json', 'CHANGE_PLAN.json',
                     'ADVERSARIAL_REVIEW.json', 'IMPLEMENTATION_NOTES.json',
                     'CHANGE_TEST_REPORT.json', 'TEST_REVIEW.json'):
            self.assertIn(name, block)
        self.assertIn('if [[ "$kind" == base ]]', block)
        self.assertIn('Checklist worker $lens returned an invalid packet; retrying that worker once.', block)
        self.assertIn('manual_checklist_packets.py" validate', block)
        self.assertIn('self-hosted runner detected; running lens workers serially', block)
        self.assertIn('[[ "$(uncle_stage_runner manual-checklist)" == self-hosted ]]', block)

    def test_compact_gate_never_describes_unnamed_manual_inputs(self):
        text = (ROOT / 'scripts/lib/gates.sh').read_text()
        self.assertIn("manual-checklist-review-worker-*)", text)
        self.assertIn('canonical JSON evidence paths listed below under Canonical inputs', text)


if __name__ == '__main__':
    unittest.main()
