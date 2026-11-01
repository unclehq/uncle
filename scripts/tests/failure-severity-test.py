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
