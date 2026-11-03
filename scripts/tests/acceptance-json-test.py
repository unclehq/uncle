#!/usr/bin/env python3
import importlib.util
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('acceptance_json', ROOT / 'scripts/lib/acceptance_json.py')
acceptance = importlib.util.module_from_spec(spec); spec.loader.exec_module(acceptance)

class AcceptanceJsonTests(unittest.TestCase):
    def check(self, rows):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'review.json'
            path.write_text(__import__('json').dumps({'schema':'uncle.artifact/v1','kind':'acceptance-report','rows':rows}))
            return acceptance.result(path, ('COVERAGE', 'RESULTS'))
    def test_pass(self): self.assertEqual('PASS', self.check([{'id':'COVERAGE','required':True,'status':'PASS','evidence':'e'}, {'id':'RESULTS','required':True,'status':'PASS','evidence':'e'}]))
    def test_failure_routes_repair(self): self.assertEqual('REPAIR', self.check([{'id':'COVERAGE','required':True,'status':'FAIL','evidence':'e'}, {'id':'RESULTS','required':True,'status':'PASS','evidence':'e'}]))
    def test_missing_expected_is_unknown(self): self.assertEqual('UNKNOWN', self.check([{'id':'RESULTS','required':True,'status':'PASS','evidence':'e'}]))

    def ids(self, rows, status):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'review.json'
            path.write_text(__import__('json').dumps({'schema':'uncle.artifact/v1','kind':'acceptance-report','rows':rows}))
            return acceptance.ids(path, status)

    def test_a_not_run_row_is_the_row_behind_a_blocked_setup_result(self):
        # Run: the only open row said NOT RUN, so the stage was BLOCKED-SETUP but the list of rows to act on (or, unattended, to waive)
        # was empty, and the driver paused with nothing to do and exited 1.
        rows = [{'id':'MC-1','required':True,'status':'PASS','evidence':'e'}, {'id':'MC-102','required':True,'status':'NOT RUN','evidence':'e'}]
        self.assertEqual('BLOCKED-SETUP', self.check([{'id':'COVERAGE','required':True,'status':'PASS','evidence':'e'},
                                                      {'id':'RESULTS','required':True,'status':'NOT RUN','evidence':'e'}]))
        self.assertEqual('MC-102', self.ids(rows, 'BLOCKED-SETUP'))

    def test_every_status_that_makes_a_result_blocked_setup_is_listed_with_it(self):
        rows = [{'id': 'A', 'required': True, 'status': s, 'evidence': 'e'} for s in ('BLOCKED', 'BLOCKED-SETUP', 'NOT RUN', 'N/A')]
        self.assertEqual(['A', 'A', 'A', 'A'], self.ids(rows, 'BLOCKED-SETUP').split('\n'))

    def test_other_statuses_are_still_matched_exactly(self):
        rows = [{'id': 'H', 'required': True, 'status': 'BLOCKED-HUMAN', 'evidence': 'e'},
                {'id': 'S', 'required': True, 'status': 'NOT RUN', 'evidence': 'e'},
                {'id': 'O', 'required': False, 'status': 'NOT RUN', 'evidence': 'e'}]
        self.assertEqual('H', self.ids(rows, 'BLOCKED-HUMAN'))
        self.assertEqual('S', self.ids(rows, 'BLOCKED-SETUP'))      # an optional row is never listed

    def test_rendered_evidence_with_a_pipe_passes_the_shell_validator(self):
        # A grep pattern like 'eval\\(|new Function' in evidence used to render as an
        # escaped pipe that acceptance.sh still split on: the renderer's own output
        # was rejected with "a row with 5 cells, not 4" and stopped a whole run.
        import subprocess
        artifact_json = importlib.util.module_from_spec(importlib.util.spec_from_file_location('artifact_json', ROOT / 'scripts/lib/artifact_json.py'))
        artifact_json.__spec__.loader.exec_module(artifact_json)
        rows = [{'id': 'COVERAGE', 'required': True, 'status': 'FAIL', 'evidence': "grep -E 'eval\\(|new Function' src returned a match"},
                {'id': 'RESULTS', 'required': True, 'status': 'PASS', 'evidence': 'a | b | c'}]
        text = artifact_json.render_acceptance({'rows': rows})
        self.assertIn('&#124;', text)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'TEST_REVIEW.md'
            path.write_text(text, encoding='utf-8')
            out = subprocess.run(['bash', '-c', '. "$1"; acceptance_problem "$2"; acceptance_row_status "$2" COVERAGE',
                                  'x', str(ROOT / 'scripts/lib/acceptance.sh'), str(path)],
                                 capture_output=True, text=True).stdout
        self.assertNotIn('cells, not 4', out)
        self.assertIn('the table parses', out)
        self.assertTrue(out.strip().endswith('FAIL'), out)

if __name__ == '__main__': unittest.main()
