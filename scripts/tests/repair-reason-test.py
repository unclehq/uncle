#!/usr/bin/env python3
"""repair_reason.py: the repair trigger is explained from the driver's own records."""
import json
import os
import subprocess
import sys
import tempfile
import unittest

SCRIPT = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'lib', 'repair_reason.py')
H = 'a' * 64
G = 'b' * 64


def run(state, source, attempt='2', limit='4'):
    return subprocess.run([sys.executable, '-B', SCRIPT, state, source, attempt, limit], capture_output=True, text=True, check=True).stdout


class Reason(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp()
        self.state = os.path.join(self.root, 'workflow')
        self.docs = os.path.join(self.root, 'docs')
        os.makedirs(self.state)
        os.makedirs(self.docs)

    def write(self, path, text):
        with open(path, 'w') as handle:
            handle.write(text)

    def test_checklist_failure_names_the_failing_rows(self):
        self.write(os.path.join(self.docs, 'VERIFICATION_REPORT.md'),
                   '# R\n\n## Acceptance gate\n\n| ID | Required | Status | Evidence |\n|---|---|---|---|\n'
                   '| MC-1 | YES | PASS | ok |\n| MC-2 | YES | FAIL | button does nothing |\n')
        out = run(self.state, 'checklist-fail')
        self.assertIn('Manual checklist checks failed', out)
        self.assertIn('**MC-2** FAIL: button does nothing', out)
        self.assertNotIn('MC-1', out)

    def test_green_check_lists_each_failing_command(self):
        self.write(os.path.join(self.state, 'green-check.tsv'), 'PASS\tnpm run build\nFAIL\tnpx vitest run\nMUTATION\tnode tests/mutations/run.mjs\n')
        out = run(self.state, os.path.join(self.state, 'green-check.md'))
        self.assertIn('Repair attempt 2 of 4', out)
        self.assertIn('`npx vitest run` failed', out)
        self.assertNotIn('npm run build', out)
        # the mutation check is not critical: it is named, but as something repair will not touch
        repaired, _, left_alone = out.partition('Not repaired')
        self.assertNotIn('run.mjs', repaired)
        self.assertIn('node tests/mutations/run.mjs', left_alone)

    def test_critical_failures_are_repaired_and_thoroughness_rows_are_left_alone(self):
        self.write(os.path.join(self.state, 'green-check.tsv'), 'FAIL\tnpx playwright test\n')
        os.makedirs(os.path.join(self.state, 'documents'))
        self.write(os.path.join(self.state, 'documents', 'TEST_REVIEW.json'), json.dumps({'rows': [
            {'id': 'ASSERTIONS', 'status': 'FAIL', 'required': True, 'evidence': 'two specs fail'},
            {'id': 'NEGATIVE', 'status': 'NOT RUN', 'required': True, 'evidence': 'no mutants'},
            {'id': 'RESULTS', 'status': 'FAIL', 'required': True, 'evidence': 'driver failed'},
            {'id': 'ORACLE', 'status': 'PASS', 'required': True, 'evidence': 'fine'}]}))
        out = run(self.state, '.uncle/docs/TEST_REVIEW.md')
        repaired, _, left_alone = out.partition('Not repaired')
        self.assertIn('`npx playwright test` failed', repaired)
        self.assertNotIn('ASSERTIONS', repaired)
        for ident in ('ASSERTIONS', 'NEGATIVE', 'RESULTS'):
            self.assertIn(ident, left_alone)
        self.assertNotIn('ORACLE', out)

    def test_severity_all_restores_the_unfiltered_list(self):
        self.write(os.path.join(self.state, 'green-check.tsv'), 'FAIL\tnpx playwright test\n')
        self.write(os.path.join(self.docs, 'TEST_REVIEW.md'),
                   '| ID | Required | Status | Evidence |\n|---|---|---|---|\n| ASSERTIONS | YES | FAIL | weak |\n')
        env = dict(os.environ, WORKFLOW_REPAIR_SEVERITY='all')
        out = subprocess.run([sys.executable, '-B', SCRIPT, self.state, '.uncle/docs/TEST_REVIEW.md', '1', '4'],
                             capture_output=True, text=True, check=True, env=env).stdout
        self.assertIn('ASSERTIONS', out)
        self.assertNotIn('Not repaired', out)

    def test_test_review_lists_failed_required_rows_only(self):
        self.write(os.path.join(self.docs, 'TEST_REVIEW.md'),
                   '| ID | Required | Status | Evidence |\n|---|---|---|---|\n| ASSERTIONS | YES | FAIL | no mutation evidence |\n| ORACLE | YES | PASS | fine |\n')
        out = run(self.state, '.uncle/docs/TEST_REVIEW.md')
        self.assertIn('ASSERTIONS', out)
        self.assertIn('no mutation evidence', out)
        self.assertNotIn('ORACLE', out)

    def test_integrity_names_the_changed_protected_files(self):
        self.write(os.path.join(self.state, 'verification-integrity.log'),
                   '--- a\n+++ b\n-%s\ttests/a.test.js\n+%s\ttests/a.test.js\n-%s\ttests/gone.test.js\n+ABSENT\ttests/new.js\n' % (H, G, H))
        out = run(self.state, os.path.join(self.state, 'VERIFICATION_INTEGRITY.md'))
        self.assertIn('`tests/a.test.js` -- content changed', out)
        self.assertIn('`tests/gone.test.js` -- deleted', out)
        self.assertIn('protected verification input changed', out)

    def test_notes_say_when_a_previous_repair_changed_nothing_and_when_tests_are_frozen(self):
        self.write(os.path.join(self.state, 'REPAIR_BRIEF.md'), 'x')
        self.write(os.path.join(self.state, 'tests.lock'), 'x')
        out = run(self.state, os.path.join(self.state, 'green-check.md'))
        self.assertIn('previous repair changed none', out)
        self.assertIn('The tests stage is active', out)

    def test_a_final_audit_repairs_the_critical_finding_and_names_what_it_leaves(self):
        os.makedirs(os.path.join(self.state, 'documents'))
        self.write(os.path.join(self.state, 'documents', 'FINAL_AUDIT.json'), json.dumps({'findings': [
            {'id': 'FA-001', 'severity': 'CRITICAL', 'evidence': 'the build fails', 'required_correction': 'fix the import'},
            {'id': 'FA-002', 'severity': 'MEDIUM', 'evidence': 'MC-101 BLOCKED-HUMAN', 'required_correction': 'record a waiver'},
            {'id': 'FA-003', 'severity': 'LOW', 'evidence': 'wording', 'required_correction': 'edit'}]}))
        out = run(self.state, '.uncle/docs/FINAL_AUDIT.md')
        repaired, _, left_alone = out.partition('Not repaired')
        self.assertIn('FA-001', repaired)
        for ident in ('FA-002', 'FA-003'):
            self.assertNotIn(ident, repaired)
            self.assertIn(ident, left_alone)

    def test_an_unknown_source_still_explains_itself(self):
        out = run(self.state, 'something-new')
        self.assertIn('Trigger recorded as `something-new`', out)
        self.assertIn('No individual item could be extracted', out)


if __name__ == '__main__':
    unittest.main()
