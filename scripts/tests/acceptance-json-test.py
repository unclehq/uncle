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
