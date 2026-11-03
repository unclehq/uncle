#!/usr/bin/env python3
"""The final audit is told how to judge the waiver an unattended run records for a check that waits on a person.

Unattended, nobody is there to sign a BLOCKED-HUMAN row and a person reviews the PR or the finished application, so the driver waives
those rows with a reason that says so (acceptance-gate.sh). The audit must read that as acceptable and non-blocking while still
naming the requirement as unverified, and it must not read it as an excuse for a check a machine could run."""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[2]


def text(relative):
    return ' '.join((ROOT / relative).read_text(encoding='utf-8').split())


class AuditPrompts(unittest.TestCase):
    def test_both_audits_accept_a_deferral_as_non_blocking(self):
        for name in ('prompts/final-audit.md', 'prompts/change/final-audit.md'):
            t = text(name)
            self.assertIn('deferred to the person who reviews the PR or the finished application', t, name)
            self.assertIn('Accept it, as a non-blocking issue', t, name)

    def test_both_audits_still_name_the_requirement_as_unverified(self):
        for name in ('prompts/final-audit.md', 'prompts/change/final-audit.md'):
            t = text(name)
            self.assertIn('name the requirement as unverified and never call it passed', t, name)

    def test_neither_audit_excuses_a_check_a_machine_could_run(self):
        for name in ('prompts/final-audit.md', 'prompts/change/final-audit.md'):
            self.assertIn('It does not excuse a check', text(name), name)
            self.assertIn('a defect the report shows', text(name), name)

    def test_the_lens_worker_rates_it_medium_and_leaves_an_unwaived_row_high(self):
        t = text('prompts/change/final-audit-review-worker.md')
        self.assertIn('carries a waiver saying it was deferred to the person who reviews the PR or the finished application is Medium, not High', t)
        self.assertIn('a row with no waiver stays High', t)
        self.assertIn('never count it as passed', t)
        self.assertIn('A waiver does not excuse a check a machine could have performed', t)

    def test_the_gate_writes_the_wording_the_audit_prompts_look_for(self):
        gate = text('scripts/lib/acceptance-gate.sh')
        self.assertIn('Deferred to the person who reviews the PR or the finished application.', gate)
        self.assertIn('so it was not assessed here.', gate)
        self.assertIn('WORKFLOW_UNATTENDED_HUMAN_WAIVER', gate)


if __name__ == '__main__':
    unittest.main()
