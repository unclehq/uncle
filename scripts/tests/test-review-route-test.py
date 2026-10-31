#!/usr/bin/env python3
import importlib.util
from pathlib import Path
import unittest
ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('route', ROOT / 'scripts/lib/test_review_route.py')
ROUTE = importlib.util.module_from_spec(spec); spec.loader.exec_module(ROUTE)
def report(results='PASS', marker='incomplete-handoff placeholder'):
    return {'schema':'uncle.artifact/v1','kind':'acceptance-report','narrative':marker,'rows':[{'id':'RESULTS','required':True,'status':results},{'id':'COVERAGE','required':True,'status':'FAIL','evidence':marker}]}
class TestReviewRoute(unittest.TestCase):
    fallback = {'schema':'uncle.artifact/v1','kind':'automated-test-report','commands':[{'status':'NOT RUN','output':'The implementation stage omitted its required test handoff.'}]}
    def test_routes_passing_driver_fallback(self): self.assertTrue(ROUTE.evidence_handoff_only(report(), self.fallback))
    def test_failing_driver_does_not_route(self): self.assertFalse(ROUTE.evidence_handoff_only(report('FAIL'), self.fallback))
    def test_code_failure_does_not_route(self): self.assertFalse(ROUTE.evidence_handoff_only(report(marker='calculator result is wrong'), self.fallback))
    def test_driver_owned_fallback_wording_routes(self): self.assertTrue(ROUTE.evidence_handoff_only(report(marker='Driver-owned incomplete test evidence: implementation stage omitted its required test handoff'), self.fallback))
    def test_stale_report_is_detected_without_a_repair(self):
        self.assertTrue(ROUTE.report_stale(self.fallback))
        self.assertFalse(ROUTE.report_stale({'schema':'uncle.artifact/v1','kind':'automated-test-report','commands':[{'status':'FAIL','output':'actual failure'}]}))
    def test_mutation_evidence_gap_routes_without_source_repair(self):
        packet = {'schema':'uncle.artifact/v1','kind':'acceptance-report','rows':[
            {'id':'RESULTS','required':True,'status':'PASS','evidence':'green check passed'},
            {'id':'NEGATIVE','required':True,'status':'FAIL','evidence':'Mutation proof is missing for I-1.'}]}
        self.assertTrue(ROUTE.mutation_evidence_gap(packet))
        packet['rows'][1]['evidence'] = 'Calculator returns an incorrect result.'
        self.assertFalse(ROUTE.mutation_evidence_gap(packet))
if __name__ == '__main__': unittest.main()
