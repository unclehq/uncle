import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
spec=importlib.util.spec_from_file_location('context',Path(__file__).resolve().parents[1]/'lib/adversarial-context.py')
module=importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
CLEAN='## Overall assessment\nNo findings.\n'
FINDING='## AR-001: Missing behavior\n- Severity: High\n- References: REQ-1\n- Failure: Missing output\n- Fix: Add output\n- Verify: Assert output\n'+CLEAN.replace('No findings.','Revision required.')

class Review(unittest.TestCase):
    def test_direct_json_response_is_validated_exported_and_rendered(self):
        import json
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            review = root/'ADVERSARIAL_REVIEW.md'
            payload = {'schema': 'uncle.artifact/v1', 'kind': 'adversarial-review',
                       'findings': [{'id': 'AR-001', 'title': 'Missing behavior', 'severity': 'High',
                                     'references': 'REQ-1', 'failure': 'Missing output', 'fix': 'Add output',
                                     'verify': 'Assert output'}],
                       'overall_assessment': 'Revision required.'}
            review.write_text(json.dumps(payload))
            module.validate(review, root)
            text = review.read_text()
            self.assertIn('AR-001: Missing behavior', text)
            self.assertIn('Revision required.', text)
            stored = json.loads((root/'.uncle/workflow/documents/ADVERSARIAL_REVIEW.json').read_text())
            self.assertEqual(stored['findings'][0]['id'], 'AR-001')

    def test_json_response_wrapped_in_a_markdown_fence_still_validates(self):
        import json
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            review = root/'ADVERSARIAL_REVIEW.md'
            payload = {'schema': 'uncle.artifact/v1', 'kind': 'adversarial-review', 'findings': [],
                       'overall_assessment': 'No findings.'}
            review.write_text('```json\n' + json.dumps(payload) + '\n```')
            module.validate(review, root)
            self.assertIn('No findings.', review.read_text())

    def test_direct_json_response_rejects_missing_field(self):
        import json
        with tempfile.TemporaryDirectory() as d:
            review = Path(d)/'ADVERSARIAL_REVIEW.md'
            payload = {'schema': 'uncle.artifact/v1', 'kind': 'adversarial-review',
                       'findings': [{'id': 'AR-001', 'title': 'x', 'severity': 'High', 'references': 'REQ-1',
                                     'failure': '', 'fix': 'y', 'verify': 'z'}],
                       'overall_assessment': 'Revision required.'}
            review.write_text(json.dumps(payload))
            with self.assertRaises(ValueError):
                module.validate(review, Path(d))

    def test_json_export_and_render_round_trip(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d); docs=root/'.uncle/docs'; docs.mkdir(parents=True)
            review=docs/'ADVERSARIAL_REVIEW.md'; review.write_text(FINDING)
            module.export_json(review, root)
            module.render_json(root, review)
            self.assertTrue((root/'.uncle/workflow/documents/ADVERSARIAL_REVIEW.json').is_file())
            module.validate(review)

    def test_json_export_accepts_numbered_assessment(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d); docs=root/'.uncle/docs'; docs.mkdir(parents=True)
            review=docs/'ADVERSARIAL_REVIEW.md'
            review.write_text(FINDING.replace('## Overall assessment', '## 5. **Overall assessment**'))
            module.export_json(review, root)
            self.assertTrue((root/'.uncle/workflow/documents/ADVERSARIAL_REVIEW.json').is_file())

    def test_formats(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'review'
            for text in (CLEAN,FINDING, FINDING.replace("## Overall assessment", "## 5. Overall assessment"), CLEAN.replace("## Overall assessment", "## 5) **Overall assessment**")):
                p.write_text(text); module.validate(p)
            for text in ('Compacting report', '## Overall assessment\n\n## Another heading\nNo findings.',FINDING.replace('- Verify: Assert output\n',''),FINDING+FINDING):
                p.write_text(text)
                with self.assertRaises(ValueError): module.validate(p)

    def test_equivalent_markdown_and_missing_substantive_fields(self):
        alternate = FINDING.replace('## AR-001:', '## AR-001 (Critical) —')
        for field in ('Severity','References','Failure','Fix','Verify'):
            alternate = alternate.replace('- '+field+':', '**'+field+'**:')
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'review'
            p.write_text(alternate)
            module.validate(p)
            p.write_text(alternate.replace('**Failure**: Missing output', '**Failure**:\n1. Missing output'))
            module.validate(p)
            for text in (
                    alternate.replace('**Failure**: Missing output\n',''),
                    '## AR-014 (Low) — Observation\n**Severity**: Low\n**References**: source\n**Observation**: No fix needed.\n'+CLEAN,
                    alternate.replace('**Verify**: Assert output\n','')+'\n## Other\n- Verify: unrelated\n'):
                p.write_text(text)
                with self.assertRaises(ValueError):module.validate(p)

    def test_field_label_synonyms(self):
        # Same tolerance checklist_document.py's LABEL_SYNONYMS already gives
        # MANUAL_CHECKLIST.md: a finding fully specified under a synonym
        # label is still fully specified, not missing a required field.
        synonym = FINDING.replace('- Failure:', '- Observation:').replace(
            '- Fix:', '- Remediation:').replace('- Verify:', '- Verification:')
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / 'review'
            p.write_text(synonym)
            module.validate(p)

    def test_packet_selects_family_and_refreshes(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            (root/'.uncle/docs').mkdir(parents=True)
            (root/'.uncle/docs/PROJECT_PLAN.md').write_text('app plan')
            (root/'.uncle/docs/CHANGE_PLAN.md').write_text('change plan')
            self.assertNotIn('change plan',module.render(root,'app'))
            self.assertIn('change plan',module.render(root,'change'))
            first=module.render(root,'app')
            (root/'.uncle/docs/PROJECT_PLAN.md').write_text('changed')
            self.assertNotEqual(first,module.render(root,'app'))

    @unittest.skipUnless(shutil.which('bash'),'Bash required')
    def test_resume_does_not_regenerate(self):
        root=Path(__file__).resolve().parents[2]
        for script,nextcase,target in [('stagegate.sh','WAIT_REVIEW_ACKNOWLEDGEMENT','WAIT_REVIEW_ACKNOWLEDGEMENT'),('change-workflow.sh','WAIT_PLAN_APPROVAL','WAIT_PLAN_APPROVAL')]:
            text=(root/'scripts'/script).read_text()
            block=text.split('        VALIDATE_ADVERSARIAL_REVIEW)\n',1)[1].split('        '+nextcase+')',1)[0]
            harness=f'STATE_DIR=.\nsupervision_validation_failed() {{ :; }};\nROOT="{root}"\nverify_approval() {{ :; }}; check_document_budget() {{ :; }}; set_state() {{ echo "$1" > state; }}; run_codex() {{ exit 99; }}; run_stage() {{ exit 99; }}\ncase validate in\nvalidate)\n'+block+'esac\n'
            with tempfile.TemporaryDirectory() as d:
                (Path(d)/'.uncle/docs').mkdir(parents=True)
                p=Path(d)/'.uncle/docs/ADVERSARIAL_REVIEW.md'
                p.write_text('bad')
                for _ in range(2):
                    self.assertEqual(subprocess.run(['bash','-c',harness],cwd=d,capture_output=True).returncode,1)
                # Both drivers validate the canonical artifact; Markdown is
                # rendered only after that succeeds and is never re-ingested
                # on a resumed validation.
                documents = Path(d)/'.uncle/workflow/documents'
                documents.mkdir(parents=True)
                (documents/'ADVERSARIAL_REVIEW.json').write_text(json.dumps({
                    'schema': 'uncle.artifact/v1', 'kind': 'adversarial-review',
                    'findings': [], 'overall_assessment': 'No findings.'
                }))
                self.assertEqual(subprocess.run(['bash','-c',harness],cwd=d,capture_output=True).returncode,0)
                self.assertEqual((Path(d)/'state').read_text().strip(),target)

if __name__=='__main__': unittest.main()
