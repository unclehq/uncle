import importlib.util
from pathlib import Path
import tempfile
import subprocess
import shutil
import unittest
spec = importlib.util.spec_from_file_location('audit_context', Path(__file__).resolve().parents[1]/'lib/final-audit-context.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
HEADER = '## Findings\n\n| ID | Evidence | Required correction | Blocks |\n|---|---|---|---|\n'

class Audit(unittest.TestCase):
    def test_json_response_is_validated_exported_and_rendered(self):
        import json
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            p = root/'audit.md'
            payload = {'schema': 'uncle.artifact/v1', 'kind': 'final-audit',
                       'findings': [{'id': 'FA-1', 'severity': 'blocking', 'evidence': 'x', 'blocks': 'YES',
                                     'affected_requirement': 'AC-1', 'required_correction': 'fix it'}],
                       'verdict': 'NOT READY'}
            p.write_text(json.dumps(payload))
            module.validate(p, root)
            text = p.read_text()
            self.assertIn('FA-1', text)
            self.assertIn('AC-1', text)
            self.assertTrue(text.rstrip().endswith('NOT READY'))
            stored = json.loads((root/'.uncle/workflow/documents/FINAL_AUDIT.json').read_text())
            self.assertEqual(stored['findings'][0]['id'], 'FA-1')

    def test_json_response_wrapped_in_a_markdown_fence_still_validates(self):
        import json
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            p = root/'audit.md'
            payload = {'schema': 'uncle.artifact/v1', 'kind': 'final-audit', 'findings': [], 'verdict': 'READY'}
            p.write_text('```json\n' + json.dumps(payload) + '\n```')
            module.validate(p, root)
            self.assertTrue(p.read_text().rstrip().endswith('READY'))

    def test_json_response_clean_audit_is_ready(self):
        import json
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            p = root/'audit.md'
            p.write_text(json.dumps({'schema': 'uncle.artifact/v1', 'kind': 'final-audit', 'findings': [], 'verdict': 'READY'}))
            module.validate(p, root)
            self.assertTrue(p.read_text().rstrip().endswith('READY'))
            self.assertNotIn('NOT READY', p.read_text().rstrip().splitlines()[-1])

    def test_json_response_rejects_ready_with_blocking_finding(self):
        import json
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            p = root/'audit.md'
            payload = {'schema': 'uncle.artifact/v1', 'kind': 'final-audit',
                       'findings': [{'id': 'FA-1', 'severity': 'blocking', 'evidence': 'x', 'blocks': 'YES',
                                     'required_correction': 'fix it'}], 'verdict': 'READY'}
            p.write_text(json.dumps(payload))
            with self.assertRaises(ValueError):
                module.validate(p, root)

    def test_json_response_wrong_schema_is_rejected(self):
        import json
        with tempfile.TemporaryDirectory() as d:
            p = Path(d)/'audit.md'
            p.write_text(json.dumps({'schema': 'uncle.artifact/v1', 'kind': 'adversarial-review'}))
            with self.assertRaises(ValueError):
                module.validate(p, Path(d))

    def test_unparseable_response_becomes_a_valid_blocking_audit(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d)/'audit.md'
            module.fallback(p, 'missing verdict')
            module.validate(p)
            self.assertIn('AUDIT-FORMAT', p.read_text())
            self.assertTrue(p.read_text().endswith('NOT READY\n'))

    def test_formats(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d)/'audit.md'
            for text in [HEADER+'\nConclusion: READY\n', HEADER+'| FA-1 | file:1 | repair | YES |\n\nConclusion: NOT READY\n', HEADER+'\nREADY\n', HEADER+'| FA-1 | file:1 | repair | YES |\n\nNOT READY\n']:
                p.write_text(text)
                module.validate(p)
            for text in ['READY', HEADER+'| FA-1 | file:1 | repair | YES |\nREADY\n', HEADER+'\nNOT READY\n', HEADER+'| FA-1 | x | y | maybe |\nREADY\n']:
                p.write_text(text)
                with self.assertRaises((ValueError, IndexError)):
                    module.validate(p)

    def test_wrong_heading_and_column_are_normalized_in_place(self):
        # Twice reproduced on a real run: a well-formed six-row findings
        # table under `# Final audit` instead of `## Findings`, with a
        # `Correction` column instead of `Required correction`. Two separate
        # retries (this file's own driver-side one, and self_hosted.py's
        # generic invalid-document retry) reproduced the identical wrong
        # shape a second time, so this fixes it deterministically instead.
        with tempfile.TemporaryDirectory() as d:
            p = Path(d)/'audit.md'
            p.write_text(
                '# Final audit\n\n'
                '| ID | Finding | Evidence | Correction | Blocks |\n'
                '|---|---|---|---|---|\n'
                '| FA-1 | Missing browser evidence | MC-1 | Run it in a browser | YES |\n\n'
                'NOT READY\n')
            module.validate(p)
            fixed = p.read_text()
            self.assertIn('## Findings', fixed)
            self.assertIn('Required correction', fixed)
            self.assertIn('FA-1', fixed)
            self.assertIn('Missing browser evidence', fixed)
            self.assertIn('Run it in a browser', fixed)
            self.assertTrue(fixed.rstrip().endswith('NOT READY'))
            module.validate(p)  # already normalized; validates again unchanged

    def test_wrong_column_alone_is_normalized_even_with_the_heading_already_present(self):
        # Reproduced on a separate real run from the one above: this time
        # `## Findings` was already correct, and only the column name was
        # wrong. The first fix's early return on "heading already there"
        # skipped the column check entirely and let this exact failure
        # through a second time.
        with tempfile.TemporaryDirectory() as d:
            p = Path(d)/'audit.md'
            p.write_text(
                '## Findings\n\n'
                '| ID | Finding | Evidence | Correction | Blocks |\n'
                '|---|---|---|---|---|\n'
                '| FA-1 | Missing test coverage | tests/App.test.jsx:8 | Add a test | YES |\n\n'
                'NOT READY\n')
            module.validate(p)
            fixed = p.read_text()
            self.assertEqual(fixed.count('## Findings'), 1, 'must not duplicate an already-present heading')
            self.assertIn('Required correction', fixed)
            self.assertIn('Add a test', fixed)
            self.assertTrue(fixed.rstrip().endswith('NOT READY'))

    def test_bold_header_and_bold_column_are_tolerated(self):
        # Bolding table headers is a recurring model habit this codebase
        # already tolerates elsewhere (checklist_document.py's
        # LABEL_SYNONYMS, envelope.py's SEVERITY_FIELD); matching a column
        # name is about its content, not its markup.
        with tempfile.TemporaryDirectory() as d:
            p = Path(d)/'audit.md'
            p.write_text(
                '## Findings\n\n'
                '| **ID** | **Finding** | **Evidence** | **Correction** | **Blocks** |\n'
                '|---|---|---|---|---|\n'
                '| FA-1 (High) | Missing test coverage | tests/App.test.jsx:8 | Add a test | YES |\n\n'
                'NOT READY\n')
            module.validate(p)
            fixed = p.read_text()
            self.assertIn('Required correction', fixed)
            self.assertIn('Add a test', fixed)

    def test_normalization_never_masks_a_genuine_defect(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d)/'audit.md'
            p.write_text('# Final audit\n\nJust prose, no table at all.\n\nNOT READY\n')
            with self.assertRaises(ValueError):
                module.validate(p)
            self.assertEqual(p.read_text(), '# Final audit\n\nJust prose, no table at all.\n\nNOT READY\n')

    def test_complete_prose_findings_are_rendered_without_a_model_retry(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d)/'audit.md'
            p.write_text('## Findings\n\n### F1: stale diff\n- **Evidence**: diff is stale\n- **Correction**: regenerate it\n- **Blocks**: YES — evidence is unreliable\n\n## Verdict\n\nNOT READY — stale evidence\n')
            module.validate(p)
            fixed = p.read_text()
            self.assertIn('| F1 | Unspecified | diff is stale Blocks rationale: evidence is unreliable |', fixed)
            self.assertTrue(fixed.rstrip().endswith('NOT READY'))

    @unittest.skipUnless(shutil.which('bash'), 'Bash required')
    def test_saved_validation_does_not_invoke_reviewer(self):
        root = Path(__file__).resolve().parents[2]
        for script in ('stagegate.sh', 'change-workflow.sh'):
            source = (root/'scripts'/script).read_text()
            block = source.split('        VALIDATE_AUDIT)\n', 1)[1].split('        WAIT_AUDIT_OVERRIDE)', 1)[0]
            with tempfile.TemporaryDirectory() as d:
                path = Path(d)
                (path/'.uncle/docs').mkdir(parents=True)
                (path/'verification.manifest').write_text('snapshot')
                preamble = f'ROOT="{root}"\nSTATE_DIR=.\nVERDICT_FILE=verdict\nDIFF_GATE=0\nAUDIT_GATE=1\n'
                preamble += 'require_file() { test -s "$1"; }; check_verification_inputs() { :; }; hash_file() { echo hash; }; classify_audit_verdict() { echo READY; }; set_state() { echo "$1" > state; }; change_pr_engine() { :; }; git() { return 1; }; run_codex() { exit 99; }; run_stage() { exit 99; };\n'
                harness = preamble + 'case VALIDATE_AUDIT in\nVALIDATE_AUDIT)\n' + block + 'esac\n'
                audit = path/'.uncle/docs/FINAL_AUDIT.md'
                audit.write_text('malformed')
                for _ in range(2):
                    result = subprocess.run(['bash', '-c', harness], cwd=d, capture_output=True)
                    self.assertEqual(result.returncode, 0, result.stderr)
                    # A malformed saved audit is rendered as a blocking
                    # driver-owned audit; validation never invokes a model.
                    self.assertNotIn(b'run_codex', result.stderr)
                audit.write_text(HEADER+'\nREADY\n')
                result = subprocess.run(['bash', '-c', harness], cwd=d, capture_output=True)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual((path/'state').read_text().strip(), 'COMPLETE')

    def test_packet_refreshes(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            (root/'.uncle/docs').mkdir(parents=True)
            p=root/'.uncle/docs/VERIFICATION_REPORT.md'
            p.write_text('old evidence')
            first=module.render(root,root/'.uncle/workflow')
            p.write_text('new evidence')
            second=module.render(root,root/'.uncle/workflow')
            self.assertIn('new evidence',second)
            self.assertNotEqual(first,second)

if __name__=='__main__': unittest.main()
