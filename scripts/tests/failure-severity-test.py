"""Only a critical failure makes repair necessary: severity classification, the downgrade of non-critical test-review rows, and what the acceptance check then says."""
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts/lib'))
import failure_severity as fs
import acceptance_json as aj

IDS = 'COVERAGE INTEGRITY ASSERTIONS ORACLE NEGATIVE RESULTS'.split()


def report(path, **status):
    rows = [{'id': i, 'required': True, 'status': status.get(i, 'PASS'), 'evidence': 'e'} for i in IDS]
    Path(path).write_text(json.dumps({'schema': 'uncle.artifact/v1', 'kind': 'acceptance-report', 'rows': rows}))
    return path


class Severity(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())

    def green(self, rows, log=''):
        (self.tmp / 'g.tsv').write_text(''.join('%s\t%s\n' % r for r in rows))
        (self.tmp / 'g.log').write_text(log)
        return str(self.tmp / 'g.tsv'), str(self.tmp / 'g.log')

    def test_a_failing_driver_command_is_critical(self):
        self.assertIn('npx vitest run', fs.critical(*self.green([('PASS', 'npm ci'), ('REGRESSION', 'npx vitest run')])))

    def test_an_unbuildable_application_is_critical_even_when_every_row_passed(self):
        self.assertTrue(fs.critical(*self.green([('PASS', 'npm ci')], 'Could not resolve ./App.jsx')))
        self.assertTrue(fs.critical(*self.green([('PASS', 'npx vitest run')], 'No test files found')))

    def test_a_mutation_failure_and_a_clean_run_are_not_critical(self):
        self.assertEqual(fs.critical(*self.green([('PASS', 'npx vitest run'), ('MUTATION', 'node tests/mutations/run.mjs')])), '')
        self.assertEqual(fs.critical(*self.green([('PASS', 'a'), ('PREEXISTING', 'b')])), '')

    PW_ISOLATED = '$ npx playwright test\nRunning 42 tests\n  2 failed\n    theme.spec.js:32\n    keyboard.spec.js:56\n  40 passed (4.2s)\n'

    def test_a_few_failing_tests_in_a_working_application_are_isolated_not_critical(self):
        green = self.green([('PASS', 'npm run build'), ('FAIL', 'npx playwright test')], self.PW_ISOLATED)
        self.assertEqual(fs.critical(*green), '')
        self.assertEqual([c for c, _ in fs.isolated_failures(*green)], ['npx playwright test'])
        self.assertIn('2 of 42', fs.isolated_failures(*green)[0][1])
        self.assertEqual(fs.critical_items(*green), [])

    def test_a_broad_failure_is_critical(self):
        green = self.green([('FAIL', 'npx playwright test')], '$ npx playwright test\n  30 failed\n  12 passed\n')
        self.assertIn('30 of 42', fs.critical(*green))
        self.assertEqual(fs.isolated_failures(*green), [])

    def test_a_failure_with_no_test_summary_is_critical(self):
        green = self.green([('FAIL', 'npx vite build')], '$ npx vite build\nerror during build: syntax error in src/App.jsx\n')
        self.assertIn('without a test summary', fs.critical(*green))

    def test_vitest_file_counts_do_not_double_the_test_counts(self):
        log = '$ npx vitest run\n Test Files  1 failed | 2 passed (3)\n      Tests  2 failed | 148 passed (150)\n'
        green = self.green([('FAIL', 'npx vitest run')], log)
        self.assertEqual(fs.critical(*green), '')
        self.assertIn('2 of 150', fs.isolated_failures(*green)[0][1])

    def test_the_ratio_is_configurable(self):
        import os
        green = self.green([('FAIL', 'npx playwright test')], self.PW_ISOLATED)
        os.environ['WORKFLOW_CRITICAL_FAIL_RATIO'] = '0.02'
        try:
            self.assertIn('2 of 42', fs.critical(*green))
        finally:
            del os.environ['WORKFLOW_CRITICAL_FAIL_RATIO']

    def test_an_unbuildable_application_stays_critical_even_when_counts_look_small(self):
        green = self.green([('FAIL', 'npx playwright test')], '$ npx playwright test\nError when starting dev server\n  1 failed\n  41 passed\n')
        self.assertTrue(fs.critical(*green))

    def test_symptom_rows_follow_an_isolated_failure_but_not_a_critical_one(self):
        review = report(self.tmp / 'r.json', ASSERTIONS='FAIL', INTEGRITY='FAIL', RESULTS='FAIL')
        done = dict(fs.downgrade(str(review), symptoms=True))
        self.assertEqual(done['INTEGRITY'], 'ISOLATED')
        self.assertEqual(done['RESULTS'], 'ISOLATED')
        review2 = report(self.tmp / 'r2.json', INTEGRITY='FAIL', RESULTS='FAIL')
        self.assertEqual(fs.downgrade(str(review2)), [])        # without the flag they are never downgraded

    def test_scope_for_isolated_failures_repairs_nothing_and_names_what_it_left(self):
        text = fs.scope(*self.green([('FAIL', 'npx playwright test')], self.PW_ISOLATED))
        self.assertIn('(none recorded', text)
        self.assertIn('ISOLATED', text)
        self.assertIn('npx playwright test', text)

    def test_scope_lists_the_critical_failures_and_fences_off_everything_else(self):
        green = self.green([('PASS', 'npm run build'), ('FAIL', 'npx playwright test'), ('MUTATION', 'node tests/mutations/run.mjs')])
        review = report(self.tmp / 'r.json', ASSERTIONS='FAIL', COVERAGE='FAIL', NEGATIVE='NOT RUN', RESULTS='FAIL')
        text = fs.scope(green[0], green[1], str(review))
        fixed, _, left_alone = text.partition('Do NOT address')
        self.assertIn('`npx playwright test` failed', fixed)
        self.assertNotIn('npm run build', text)
        for name in ('ASSERTIONS', 'COVERAGE', 'NEGATIVE', 'RESULTS', 'node tests/mutations/run.mjs'):
            self.assertNotIn(name, fixed)
            self.assertIn(name, left_alone)
        self.assertIn('SYMPTOM', left_alone)        # RESULTS clears when the command is fixed
        self.assertIn('Do not add tests', text)

    def test_scope_names_an_unbuildable_application_when_no_command_is_marked_failed(self):
        text = fs.scope(*self.green([('PASS', 'npm ci')], 'Could not resolve ./App.jsx'))
        self.assertIn('cannot be built or served', text)

    def test_scope_cli(self):
        green = self.green([('FAIL', 'npx vitest run')])
        out = subprocess.run([sys.executable, str(ROOT / 'scripts/lib/failure_severity.py'), 'scope', *green],
                             capture_output=True, text=True, check=True).stdout
        self.assertIn('`npx vitest run` failed', out)

    def test_a_missing_record_is_not_critical(self):
        self.assertEqual(fs.critical(str(self.tmp / 'none.tsv'), str(self.tmp / 'none.log')), '')

    def test_thoroughness_rows_are_downgraded_with_their_severity(self):
        p = report(self.tmp / 'r.json', ASSERTIONS='FAIL', COVERAGE='NOT RUN', ORACLE='FAIL', NEGATIVE='FAIL')
        self.assertEqual(dict(fs.downgrade(p)), {'ASSERTIONS': 'MAJOR', 'COVERAGE': 'MAJOR', 'ORACLE': 'MINOR', 'NEGATIVE': 'MINOR'})
        rows = {r['id']: r for r in json.loads(Path(p).read_text())['rows']}
        self.assertFalse(rows['ASSERTIONS']['required'])
        self.assertEqual(rows['ASSERTIONS']['status'], 'FAIL')           # the finding itself is untouched

    def test_integrity_and_results_are_never_downgraded(self):
        p = report(self.tmp / 'r.json', INTEGRITY='BLOCKED-SETUP', RESULTS='FAIL')
        self.assertEqual(fs.downgrade(p), [])
        self.assertEqual(aj.result(p, IDS), 'REPAIR')

    def test_acceptance_accepts_the_downgrade_and_still_rejects_a_reviewer_who_drops_a_required_row(self):
        p = report(self.tmp / 'r.json', ASSERTIONS='FAIL', COVERAGE='FAIL')
        self.assertEqual(aj.result(p, IDS), 'REPAIR')
        fs.downgrade(p)
        self.assertEqual(aj.result(p, IDS), 'PASS')
        q = report(self.tmp / 'q.json', ASSERTIONS='FAIL')
        data = json.loads(Path(q).read_text())
        for r in data['rows']:
            if r['id'] == 'ASSERTIONS':
                r['required'] = False                                    # a reviewer's own opt-out, with no driver mark
        Path(q).write_text(json.dumps(data))
        self.assertEqual(aj.result(q, IDS), 'UNKNOWN')

    def test_cli(self):
        g, l = self.green([('REGRESSION', 'npm test')])
        run = lambda *a: subprocess.run([sys.executable, str(ROOT / 'scripts/lib/failure_severity.py'), *a], capture_output=True, text=True)
        out = run('critical', g, l)
        self.assertEqual((out.returncode, 'npm test' in out.stdout), (0, True))
        g, l = self.green([('PASS', 'npm test')])
        self.assertEqual(run('critical', g, l).returncode, 1)
        p = report(self.tmp / 'r.json', COVERAGE='FAIL')
        self.assertEqual(run('downgrade', str(p)).stdout.strip(), 'COVERAGE\tMAJOR')


if __name__ == '__main__':
    unittest.main()
