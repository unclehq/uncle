#!/usr/bin/env python3
"""The driver records its own verification results as the test report, in place of the implementation stage's placeholder."""
import json
import sys
import tempfile
import unittest
from pathlib import Path

LIB = Path(__file__).resolve().parents[1] / 'lib'
sys.path.insert(0, str(LIB))
import test_report as tr

PLACEHOLDER = {'schema': 'uncle.artifact/v1', 'kind': 'automated-test-report',
               'commands': [{'command': 'Implementation handoff', 'status': 'NOT RUN', 'requirements': [],
                             'output': 'The implementation stage omitted its required test handoff; no command result is inferred.'}],
               'coverage_gaps': ['x'], 'next_action': 'Run the approved verification commands.'}
LOG = '''
$ npm run build
vite v5 building for production... built in 1.2s

$ npx vitest run tests/unit
 Test Files  1 passed (1)

$ node tests/mutations/run.mjs
mutation DI-3 survived
'''


class FromGreen(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        (self.root / '.uncle/workflow/documents').mkdir(parents=True)
        (self.root / '.uncle/docs').mkdir(parents=True)
        self.tsv = self.root / 'current.tsv'
        self.tsv.write_text('0\tnpm run build\n0\tnpx vitest run tests/unit\n1\tnode tests/mutations/run.mjs\n')
        self.log = self.root / 'green.log'
        self.log.write_text(LOG)
        self.report = self.root / '.uncle/workflow/documents/AUTOMATED_TEST_REPORT.json'

    def test_pending_verification_replaces_stale_results_without_claiming_passes(self):
        state = self.root / '.uncle/workflow'
        (state/'green-background.pending').touch()
        (state/'green-check.commands').write_text('npm run build\nnpm test\n')
        self.assertTrue(tr.from_green(self.root, 'application', self.tsv, self.log))
        report = json.loads(self.report.read_text())
        self.assertEqual([r['status'] for r in report['commands']], ['NOT RUN', 'NOT RUN'])
        # Publishing final classifications while the pending marker is still
        # present must replace the placeholder with the actual command results.
        (state/'green-check.tsv').write_text('PASS\tnpm run build\n')
        self.assertTrue(tr.from_green(self.root, 'application', self.tsv, self.log))
        self.assertEqual(json.loads(self.report.read_text())['commands'][0]['status'], 'PASS')

    def tearDown(self):
        self.tmp.cleanup()

    def write(self, payload):
        self.report.write_text(json.dumps(payload))

    def test_a_missing_report_or_the_placeholder_becomes_the_drivers_results(self):
        self.assertTrue(tr.from_green(self.root, 'application', self.tsv, self.log))
        report = json.loads(self.report.read_text())
        self.assertEqual([(c['command'], c['status']) for c in report['commands']],
                         [('npm run build', 'PASS'), ('npx vitest run tests/unit', 'PASS'), ('node tests/mutations/run.mjs', 'FAIL')])
        self.assertIn('built in 1.2s', report['commands'][0]['output'])
        self.assertIn('mutation DI-3 survived', report['commands'][2]['output'])
        self.assertEqual(len(report['coverage_gaps']), 1)
        self.assertIn('node tests/mutations/run.mjs', report['coverage_gaps'][0])
        self.assertIn('| node tests/mutations/run.mjs | FAIL |', (self.root / '.uncle/docs/AUTOMATED_TEST_REPORT.md').read_text())

    def test_the_placeholder_is_replaced_and_the_stale_marker_is_gone(self):
        self.write(PLACEHOLDER)
        self.assertTrue(tr.from_green(self.root, 'application', self.tsv, self.log))
        text = self.report.read_text().lower()
        self.assertNotIn('implementation stage omitted', text)

    def test_a_report_the_implementation_wrote_for_real_is_kept(self):
        real = dict(PLACEHOLDER, commands=[{'command': 'npx vitest run', 'status': 'PASS', 'requirements': ['R-1'], 'output': 'ok'}])
        self.write(real)
        self.assertFalse(tr.from_green(self.root, 'application', self.tsv, self.log))
        self.assertEqual(json.loads(self.report.read_text())['commands'][0]['requirements'], ['R-1'])

    def test_a_report_the_driver_wrote_is_refreshed_by_the_next_run(self):
        tr.from_green(self.root, 'application', self.tsv, self.log)
        self.tsv.write_text('0\tnpm run build\n0\tnpx vitest run tests/unit\n0\tnode tests/mutations/run.mjs\n')
        self.assertTrue(tr.from_green(self.root, 'application', self.tsv, self.log))
        report = json.loads(self.report.read_text())
        self.assertEqual([c['status'] for c in report['commands']], ['PASS', 'PASS', 'PASS'])
        self.assertEqual((report['coverage_gaps'], report['next_action']), ([], 'None.'))

    def test_no_results_means_no_report_is_written(self):
        self.tsv.write_text('')
        self.assertFalse(tr.from_green(self.root, 'application', self.tsv, self.log))
        self.assertFalse(self.report.exists())

    def test_a_command_with_no_output_still_has_a_non_empty_output(self):
        self.log.write_text('')
        tr.from_green(self.root, 'application', self.tsv, self.log)
        self.assertTrue(all(c['output'] for c in json.loads(self.report.read_text())['commands']))

    def test_the_review_router_no_longer_sees_an_evidence_handoff_gap(self):
        sys.path.insert(0, str(LIB))
        import test_review_route as route
        self.write(PLACEHOLDER)
        review = {'schema': 'uncle.artifact/v1', 'kind': 'acceptance-report', 'narrative': 'implementation stage omitted its required test handoff',
                  'rows': [{'id': 'RESULTS', 'required': True, 'status': 'PASS', 'evidence': 'x'},
                           {'id': 'COVERAGE', 'required': True, 'status': 'FAIL', 'evidence': 'incomplete-handoff placeholder'}]}
        self.assertTrue(route.evidence_handoff_only(review, json.loads(self.report.read_text())))
        tr.from_green(self.root, 'application', self.tsv, self.log)
        self.assertFalse(route.evidence_handoff_only(review, json.loads(self.report.read_text())))


class Routing(unittest.TestCase):
    """The test review is sent back through the implementation stage only for a documentation gap, never for a failing command."""

    def test_every_evidence_route_is_guarded_by_a_green_suite(self):
        text = (LIB.parent / 'stagegate.sh').read_text()
        for marker in ('test-evidence-handoff-attempted', 'test-mutation-evidence-attempted'):
            routes = [line for line in text.splitlines() if 'if [[ ! -e "$STATE_DIR/%s" ]]' % marker in line]
            self.assertEqual(len(routes), 2, marker)       # VALIDATE_TEST_REVIEW and REPAIR
            for line in routes:
                self.assertIn('green_regressions "$GREEN_CLASS")" -eq 0', line, marker)

    def test_the_driver_records_its_report_right_after_the_green_check(self):
        text = (LIB.parent / 'stagegate.sh').read_text()
        self.assertLess(text.index('            run_green_check_auto || true\n            collect_background_preflight'),
                        text.index('test_report.py" from-green . application'))

    def test_the_mutation_gap_router_still_recognises_a_review_that_asks_for_proof(self):
        sys.path.insert(0, str(LIB))
        import test_review_route as route
        review = {'schema': 'uncle.artifact/v1', 'kind': 'acceptance-report', 'rows': [
            {'id': 'RESULTS', 'required': True, 'status': 'PASS', 'evidence': 'ok'},
            {'id': 'NEGATIVE', 'required': True, 'status': 'FAIL', 'evidence': 'no mutation proof: tests do not fail on defects'}]}
        self.assertTrue(route.mutation_evidence_gap(review))


if __name__ == '__main__':
    unittest.main()
