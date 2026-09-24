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
    def test_driver_routes_only_canonical_json_before_reconciliation(self):
        driver = (ROOT / 'scripts/stagegate.sh').read_text()
        start = driver.index('VALIDATE_TEST_REVIEW)')
        block = driver[start:driver.index('\n        REPAIR)', start)]
        self.assertNotIn('acceptance_context.py" .uncle/docs/TEST_REVIEW.md', block)
        self.assertIn('acceptance_json.py', block)
        self.assertIn('documents/AUTOMATED_TEST_REPORT.json', block)
        self.assertNotIn('test_review_route.py" "$STATE_DIR/documents/TEST_REVIEW.json" .uncle/docs/AUTOMATED_TEST_REPORT.md', block)
        transition = driver[driver.index('acceptance_transition() {'):driver.index('\n}\n', driver.index('acceptance_transition() {'))]
        self.assertIn('canonical="$STATE_DIR/documents/$(basename "${report%.md}").json"', transition)
        self.assertIn('acceptance_json.py', transition)
        self.assertIn('supervision_artifact="$canonical"', transition)
    def test_stale_checklist_handoff_is_reclassified_as_evidence_reconciliation(self):
        driver = (ROOT / 'scripts/stagegate.sh').read_text()
        start = driver.index('        VALIDATE_CHECKLIST)')
        block = driver[start:driver.index('        FINAL_AUDIT)', start)]
        self.assertIn('checklist-evidence-handoff-attempted', block)
        self.assertIn('--report-stale', block)
        self.assertIn('set_state IMPLEMENT', block)
    def test_stale_report_is_detected_without_a_repair(self):
        self.assertTrue(ROUTE.report_stale(self.fallback))
        self.assertFalse(ROUTE.report_stale({'schema':'uncle.artifact/v1','kind':'automated-test-report','commands':[{'status':'FAIL','output':'actual failure'}]}))
if __name__ == '__main__': unittest.main()
