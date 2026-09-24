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
    fallback = 'The implementation stage omitted its required test handoff.'
    def test_routes_passing_driver_fallback(self): self.assertTrue(ROUTE.evidence_handoff_only(report(), self.fallback))
    def test_failing_driver_does_not_route(self): self.assertFalse(ROUTE.evidence_handoff_only(report('FAIL'), self.fallback))
    def test_code_failure_does_not_route(self): self.assertFalse(ROUTE.evidence_handoff_only(report(marker='calculator result is wrong'), self.fallback))
    def test_driver_owned_fallback_wording_routes(self): self.assertTrue(ROUTE.evidence_handoff_only(report(marker='Driver-owned incomplete test evidence: implementation stage omitted its required test handoff'), self.fallback))
    def test_driver_ingests_current_fast_path_before_routing(self):
        driver = (ROOT / 'scripts/stagegate.sh').read_text()
        start = driver.index('VALIDATE_TEST_REVIEW)')
        block = driver[start:driver.index('\n        REPAIR)', start)]
        self.assertIn('acceptance_context.py" .uncle/docs/TEST_REVIEW.md', block)
        self.assertLess(block.index('acceptance_context.py" .uncle/docs/TEST_REVIEW.md'),
                        block.index('test_review_route.py'))
    def test_stale_repair_is_reclassified_as_evidence_reconciliation(self):
        driver = (ROOT / 'scripts/stagegate.sh').read_text()
        start = driver.index('        REPAIR)\n            # A run that reached REPAIR')
        block = driver[start:driver.index('            verify_approval', start)]
        self.assertIn('Repair reclassified as incomplete test-evidence handoff', block)
        self.assertIn('set_state IMPLEMENT', block)
if __name__ == '__main__': unittest.main()
