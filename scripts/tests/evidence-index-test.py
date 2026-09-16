from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import sys
import tempfile
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'lib'))
from evidence_index import packet

class Index(unittest.TestCase):
    def test_audit_index_refreshes_claims_and_marks_missing_files(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d); state=root/'.uncle/workflow';state.mkdir(parents=True)
            report=root/'VERIFICATION_REPORT.md'
            report.write_text('| ID | Required | Status | Evidence |\n|---|---|---|---|\n| MC-H-1 | YES | PASS | `tests/page.py:12` |\n')
            (state/'delivery-summary.tsv').write_text('id\tstatus\n')
            for family in ('app','change'):
                text=packet(root,state,'final-audit',family)
                self.assertIn('Dedicated audit evidence index',text)
                path=state/'handoffs'/f'audit-evidence-{family}.json'
                data=json.loads(path.read_text())
                self.assertEqual(data['claims'][0]['id'],'MC-H-1')
                self.assertEqual(data['claims'][0]['line'],3)
                self.assertIn('UNRESOLVED',data['claims'][0]['mapping'])
                self.assertTrue(data['files']['@delivery-summary.tsv']['header_only'])
                self.assertEqual(data['files']['@plan-recovery.json']['status'],'missing or unreadable')
            report.unlink()
            packet(root,state,'final-audit','app')
            data=json.loads((state/'handoffs/audit-evidence-app.json').read_text())
            self.assertEqual(data['claims'],[])

    def test_refresh_reuse_and_delete(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d); state=root/'.uncle/workflow'; brief=root/'REQUIREMENTS.md'
            brief.write_text('AC-1 first')
            packet(root,state,'requirements')
            packet(root,state,'requirements')
            snapshot=state/'evidence-index/stages/requirements-app.json'
            self.assertEqual(json.loads(snapshot.read_text())['changed'],[])
            self.assertGreater(json.loads(snapshot.read_text())['excerpt_cache_hits'],0)
            brief.write_text('AC-1 other') # Same size, different contents.
            self.assertIn('AC-1 other',packet(root,state,'requirements'))
            self.assertIn('REQUIREMENTS.md',json.loads(snapshot.read_text())['changed'])
            brief.unlink()
            text=packet(root,state,'requirements')
            self.assertNotIn('AC-1 other',text)
            self.assertIn('missing or unreadable',text)

    def test_base_excludes_implementation_and_configuration(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d); state=root/'.uncle/workflow'
            (root/'CHANGE_SPEC.md').write_text('AC-1 frozen')
            (root/'VERIFICATION_REPORT.md').write_text('LIVE RESULT')
            (root/'package.json').write_text('LIVE CONFIG')
            text=packet(root,state,'manual-checklist-base','change')
            self.assertIn('frozen',text)
            self.assertNotIn('LIVE',text)

    def test_concurrent_stages_and_bounds(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);state=root/'.uncle/workflow'
            (root/'REQUIREMENTS.md').write_text('AC-1 input\n'*10000)
            stages=['requirements','project-plan','adversarial-review']
            with ThreadPoolExecutor(max_workers=3) as pool:
                results=list(pool.map(lambda stage:packet(root,state,stage),stages))
            self.assertTrue(all(len(x.encode())<18000 for x in results))
            for f in (state/'evidence-index/objects').glob('*.json'):
                self.assertIn('sha256',json.loads(f.read_text()))

if __name__=='__main__':unittest.main()
