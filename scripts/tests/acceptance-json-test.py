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

if __name__ == '__main__': unittest.main()
