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
            (root/'.uncle/docs').mkdir(parents=True, exist_ok=True)
            report=root/'.uncle/docs/VERIFICATION_REPORT.md'
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

    def test_updated_plan_investigate_inherits_updated_plans_evidence_list(self):
        # The investigate/format split added "updated-plan-investigate" as
        # its own log_name; without a mapping here it silently fell back to
        # the generic default list (REQUIREMENTS.md, UPDATED_PROJECT_PLAN.md,
        # CHANGE_SPEC.md, CHANGE_PLAN.md -- the wrong family's documents)
        # instead of updated-plan's own tailored one (REQUIREMENTS.md,
        # REQUIREMENTS_INTERPRETATION.md, PROJECT_PLAN.md,
        # ADVERSARIAL_REVIEW.md), a silent evidence-quality regression rather
        # than a hard failure. The investigate call, which does all the
        # reading, must get the same tailored list as updated-plan itself.
        with tempfile.TemporaryDirectory() as d:
            root = Path(d); state = root/'.uncle/workflow'
            (root/'.uncle/docs').mkdir(parents=True, exist_ok=True)
            (root/'.uncle/docs/PROJECT_PLAN.md').write_text('# Project plan\n')
            (root/'.uncle/docs/ADVERSARIAL_REVIEW.md').write_text('# Adversarial review\n')
            updated_plan = packet(root, state, 'updated-plan')
            investigate = packet(root, state, 'updated-plan-investigate')
            self.assertIn('PROJECT_PLAN.md', updated_plan)
            self.assertIn('PROJECT_PLAN.md', investigate)
            self.assertIn('ADVERSARIAL_REVIEW.md', investigate)
            self.assertNotIn('CHANGE_SPEC.md', investigate)

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

    def test_single_line_document_excerpt_is_not_truncated_to_250_chars(self):
        # Every JSON-migrated doc (PROJECT_PLAN.md, UPDATED_PROJECT_PLAN.md,
        # REQUIREMENTS_INTERPRETATION.md, ...) is stored as one line. The
        # per-matched-line excerpt cap (250 chars) was written for ordinary
        # multi-line Markdown, where a matched line is naturally short; for a
        # single-line document the entire multi-KB file IS that one matched
        # line, so it was silently cut to 250 chars on every read.
        with tempfile.TemporaryDirectory() as d:
            root = Path(d); state = root/'.uncle/workflow'
            (root/'.uncle/docs').mkdir(parents=True, exist_ok=True)
            # One line, comfortably over PRELOAD_FILE_LIMIT so this exercises
            # the excerpt path rather than the complete-file preload path.
            # An AC-1 marker near the start makes the line match the
            # excerpt-selection regex; MARK_1000 sits well past the old
            # 250-char cutoff but inside the 1800-char whole-text fallback.
            line = 'AC-1 start ' + ('x' * 980) + ' MARK_1000 ' + ('y' * 4000)
            self.assertGreater(len(line), 4096)
            (root/'.uncle/docs/PROJECT_PLAN.md').write_text(line)
            text = packet(root, state, 'adversarial-review')
            self.assertIn('MARK_1000', text)

    def test_single_line_document_over_preload_limit_is_still_preloaded_whole(self):
        # A single-line document has no usable partial view: the model's own
        # Read tool truncates by line, and the excerpt cache's whole-text
        # fallback is capped at 1800 chars. Preloading the complete file
        # (bypassing PRELOAD_FILE_LIMIT for single-line files specifically)
        # is the only way a stage sees content past that point.
        with tempfile.TemporaryDirectory() as d:
            root = Path(d); state = root/'.uncle/workflow'
            (root/'.uncle/docs').mkdir(parents=True, exist_ok=True)
            from evidence_index import PRELOAD_FILE_LIMIT
            tail_marker = 'MARK_TAIL_' + ('z' * 100)
            line = 'AC-1 ' + ('x' * (PRELOAD_FILE_LIMIT + 2000)) + ' ' + tail_marker
            self.assertGreater(len(line), PRELOAD_FILE_LIMIT)
            (root/'.uncle/docs/PROJECT_PLAN.md').write_text(line)
            text = packet(root, state, 'adversarial-review')
            self.assertIn('### Complete static input:', text)
            self.assertIn(tail_marker, text)

    def test_small_declared_inputs_are_preloaded_for_every_runner(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d); state=root/'.uncle/workflow'
            (root/'REQUIREMENTS.md').write_text('AC-1 static input')
            text=packet(root,state,'requirements')
            self.assertIn('Preloaded static stage inputs',text)
            self.assertIn('Complete static input: REQUIREMENTS.md',text)
            self.assertIn('do not call Read for that file',text)

    def test_base_excludes_implementation_and_configuration(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d); state=root/'.uncle/workflow'
            (root/'.uncle/docs').mkdir(parents=True, exist_ok=True)
            (root/'.uncle/docs/CHANGE_SPEC.md').write_text('AC-1 frozen')
            (root/'.uncle/docs/VERIFICATION_REPORT.md').write_text('LIVE RESULT')
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
