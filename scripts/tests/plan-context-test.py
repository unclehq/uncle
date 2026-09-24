import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

spec = importlib.util.spec_from_file_location('plan_context', Path(__file__).resolve().parents[1]/'lib/plan_context.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class PlanContext(unittest.TestCase):
    def test_json_project_plan_is_ingested_and_exported(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            plan = root/'PROJECT_PLAN.md'
            payload = {'schema': 'uncle.artifact/v1', 'kind': 'plan', 'narrative': '## Architecture\n\nA calculator.',
                       'verification_commands': 'python3 -m pytest'}
            plan.write_text(json.dumps(payload))
            self.assertTrue(module.ingest_plan(plan, root, protected=False))
            text = plan.read_text()
            self.assertIn('## Architecture', text)
            self.assertIn('## Verification commands', text)
            self.assertNotIn('Protected verification paths', text)
            stored = json.loads((root/'.uncle/workflow/documents/PROJECT_PLAN.json').read_text())
            self.assertEqual(stored['verification_commands'], 'python3 -m pytest')

    def test_raw_approved_json_plan_can_be_mirrored_without_rewriting_it(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d); plan = root/'PROJECT_PLAN.md'
            raw = json.dumps({'schema': 'uncle.artifact/v1', 'kind': 'plan',
                              'narrative': '## Architecture\n\nStable.', 'verification_commands': 'pytest'})
            plan.write_text(raw)
            self.assertTrue(module.canonicalize_json_plan(plan, root, protected=False))
            self.assertEqual(plan.read_text(), raw)
            self.assertTrue((root/'.uncle/workflow/documents/PROJECT_PLAN.json').is_file())

    def test_markdown_plan_is_left_alone(self):
        with tempfile.TemporaryDirectory() as d:
            plan = Path(d)/'PROJECT_PLAN.md'
            plan.write_text('# A hand-written plan\n\nNo JSON here.\n')
            self.assertFalse(module.ingest_plan(plan, Path(d), protected=False))
            self.assertEqual(plan.read_text(), '# A hand-written plan\n\nNo JSON here.\n')

    def test_approved_markdown_project_plan_exports_before_json_only_handoff(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d); plan = root/'PROJECT_PLAN.md'
            plan.write_text('## Architecture\n\nStatic app.\n\n## Verification commands\n\n```sh\npytest\n```\n')
            payload = module.export_project_plan(plan, root)
            self.assertEqual(payload['verification_commands'], 'pytest')
            canonical = json.loads((root/'.uncle/workflow/documents/PROJECT_PLAN.json').read_text())
            self.assertEqual(canonical['narrative'], '## Architecture\n\nStatic app.')

    def test_project_plan_export_accepts_top_level_verification_heading(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d); plan = root/'PROJECT_PLAN.md'
            plan.write_text('# Architecture\n\nStatic app.\n\n# Verification commands\n\n```sh\npytest\n```\n')
            payload = module.export_project_plan(plan, root)
            self.assertEqual(payload['verification_commands'], 'pytest')
            self.assertTrue((root/'.uncle/workflow/documents/PROJECT_PLAN.json').is_file())

    def test_investigation_is_deterministically_materialized_as_project_plan_json(self):
        # The self-hosted planner writes this Markdown investigation once.
        # Its final JSON is mechanical: preserve every non-command section
        # and lift the exact fenced command block, without another model turn.
        with tempfile.TemporaryDirectory() as d:
            root = Path(d); plan = root/'PROJECT_PLAN.md'
            plan.write_text('# Project plan investigation\n\n## Architecture\n\nStatic app.\n\n'
                            '## Verification commands\n\n```sh\npytest -q\n```\n', encoding='utf-8')
            payload = module.export_project_plan(plan, root)
            self.assertEqual(payload['verification_commands'], 'pytest -q')
            self.assertEqual(payload['narrative'], '# Project plan investigation\n\n## Architecture\n\nStatic app.')
            module.render_canonical(plan, root, protected=False)
            rendered = plan.read_text(encoding='utf-8')
            self.assertIn('## Architecture', rendered)
            self.assertIn('```sh\npytest -q\n```', rendered)

    def test_updated_plan_requires_protected_paths(self):
        with tempfile.TemporaryDirectory() as d:
            plan = Path(d)/'UPDATED_PROJECT_PLAN.md'
            payload = {'schema': 'uncle.artifact/v1', 'kind': 'plan', 'verification_commands': 'pytest'}
            plan.write_text(json.dumps(payload))
            with self.assertRaises(ValueError):
                module.ingest_plan(plan, Path(d), protected=True)

    def test_plan_with_dispositions_renders_the_review_table(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            plan = root/'UPDATED_PROJECT_PLAN.md'
            payload = {'schema': 'uncle.artifact/v1', 'kind': 'plan', 'verification_commands': 'pytest',
                       'protected_verification_paths': 'tests/',
                       'dispositions': [{'finding': 'AR-001', 'disposition': 'Accepted', 'reason': 'valid gap',
                                        'plan_change': 'added rollback step'}]}
            plan.write_text(json.dumps(payload))
            self.assertTrue(module.ingest_plan(plan, root, protected=True))
            text = plan.read_text()
            self.assertIn('| AR-001 | Accepted | valid gap | added rollback step |', text)

    def test_json_change_spec_is_ingested_and_exported(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            spec_doc = root/'CHANGE_SPEC.md'
            payload = {'schema': 'uncle.artifact/v1', 'kind': 'change-spec', 'narrative': '## Summary\n\nChange it.',
                       'acceptance_criteria': [{'id': 'AC-1', 'criterion': 'Chat composer', 'verification': 'UI check'}]}
            spec_doc.write_text(json.dumps(payload))
            self.assertTrue(module.ingest_change_spec(spec_doc, root))
            text = spec_doc.read_text()
            self.assertIn('| AC-1 | Chat composer | UI check |', text)
            stored = json.loads((root/'.uncle/workflow/documents/CHANGE_SPEC.json').read_text())
            self.assertEqual(stored['acceptance_criteria'][0]['id'], 'AC-1')

    def test_wrong_kind_is_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            spec_doc = Path(d)/'CHANGE_SPEC.md'
            spec_doc.write_text(json.dumps({'schema': 'uncle.artifact/v1', 'kind': 'plan'}))
            with self.assertRaises(ValueError):
                module.ingest_change_spec(spec_doc, Path(d))

    def test_initial_change_plan_needs_no_verification_commands_or_dispositions(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            plan = root/'CHANGE_PLAN.md'
            payload = {'schema': 'uncle.artifact/v1', 'kind': 'change-plan', 'narrative': '## Selected technical approach\n\nDo it.'}
            plan.write_text(json.dumps(payload))
            self.assertTrue(module.ingest_change_plan(plan, root, require_dispositions=False))
            text = plan.read_text()
            self.assertIn('## Selected technical approach', text)
            self.assertNotIn('Disposition', text)
            stored = json.loads((root/'.uncle/workflow/documents/CHANGE_PLAN.json').read_text())
            self.assertEqual(stored['narrative'], payload['narrative'])

    def test_updated_change_plan_requires_dispositions(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            plan = root/'CHANGE_PLAN.md'
            payload = {'schema': 'uncle.artifact/v1', 'kind': 'change-plan', 'narrative': '## Selected technical approach\n\nDo it.'}
            plan.write_text(json.dumps(payload))
            with self.assertRaises(ValueError):
                module.ingest_change_plan(plan, root, require_dispositions=True)

    def test_unreviewed_change_plan_renders_from_canonical_json(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d); plan = root/'CHANGE_PLAN.md'
            payload = {'schema': 'uncle.artifact/v1', 'kind': 'change-plan',
                       'narrative': '## Scope\n\nBefore review.'}
            plan.write_text(json.dumps(payload))
            module.ingest_change_plan(plan, root, require_dispositions=False)
            plan.write_text('edited render only')
            self.assertTrue(module.render_canonical(plan, root, change=True, require_dispositions=False))
            self.assertIn('Before review.', plan.read_text())

    def test_updated_change_plan_with_dispositions_renders_the_table(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            plan = root/'CHANGE_PLAN.md'
            payload = {'schema': 'uncle.artifact/v1', 'kind': 'change-plan', 'narrative': '## Selected technical approach\n\nDo it.',
                       'dispositions': [{'finding': 'AR-001', 'disposition': 'Accepted', 'reason': 'valid gap',
                                        'plan_change': 'added rollback step'}]}
            plan.write_text(json.dumps(payload))
            self.assertTrue(module.ingest_change_plan(plan, root, require_dispositions=True))
            text = plan.read_text()
            self.assertIn('| AR-001 | Accepted | valid gap | added rollback step |', text)

    def test_rendered_markdown_cannot_change_canonical_updated_plan(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d); plan = root/'UPDATED_PROJECT_PLAN.md'
            payload = {'schema': 'uncle.artifact/v1', 'kind': 'plan', 'narrative': '## Architecture\n\nCanonical.',
                       'verification_commands': 'pytest', 'protected_verification_paths': 'tests'}
            plan.write_text(json.dumps(payload))
            module.ingest_plan(plan, root, protected=True)
            expected = plan.read_text()
            plan.write_text('malicious rendered markdown edit', encoding='utf-8')
            self.assertTrue(module.render_canonical(plan, root, protected=True))
            self.assertEqual(plan.read_text(), expected)

    def test_change_plan_wrong_kind_is_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            plan = Path(d)/'CHANGE_PLAN.md'
            plan.write_text(json.dumps({'schema': 'uncle.artifact/v1', 'kind': 'plan', 'narrative': 'x'}))
            with self.assertRaises(ValueError):
                module.ingest_change_plan(plan, Path(d))

    def test_json_baseline_report_is_ingested_and_exported(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            report = root/'BASELINE_REPORT.md'
            payload = {'schema': 'uncle.artifact/v1', 'kind': 'baseline-report',
                       'narrative': '## Change-request summary\n\nFix the bug.',
                       'verification_commands': 'pytest\nnpm test',
                       'parallel_groups': '1 2'}
            report.write_text(json.dumps(payload))
            self.assertTrue(module.ingest_baseline_report(report, root))
            text = report.read_text()
            self.assertIn('## Exact build and test commands executed', text)
            self.assertIn('pytest', text)
            self.assertIn('## Parallel verification groups', text)
            self.assertIn('1 2', text)
            stored = json.loads((root/'.uncle/workflow/documents/BASELINE_REPORT.json').read_text())
            self.assertEqual(stored['verification_commands'], 'pytest\nnpm test')

    def test_baseline_report_requires_verification_commands(self):
        with tempfile.TemporaryDirectory() as d:
            report = Path(d)/'BASELINE_REPORT.md'
            report.write_text(json.dumps({'schema': 'uncle.artifact/v1', 'kind': 'baseline-report',
                                           'narrative': 'x'}))
            with self.assertRaises(ValueError):
                module.ingest_baseline_report(report, Path(d))

    def test_markdown_baseline_report_is_left_alone(self):
        with tempfile.TemporaryDirectory() as d:
            report = Path(d)/'BASELINE_REPORT.md'
            report.write_text('# A hand-written baseline\n\nNo JSON here.\n')
            self.assertFalse(module.ingest_baseline_report(report, Path(d)))
            self.assertEqual(report.read_text(), '# A hand-written baseline\n\nNo JSON here.\n')

    def test_baseline_report_export_from_rendered_markdown(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            report = root/'BASELINE_REPORT.md'
            report.write_text('Narrative text.\n\n## Exact build and test commands executed\n\n'
                               '```sh\npytest\n```\n\n## Parallel verification groups\n\n```text\n1 2\n```\n')
            payload = module.export_baseline_report(report, root)
            self.assertEqual(payload['verification_commands'], 'pytest')
            self.assertEqual(payload['parallel_groups'], '1 2')
            stored = json.loads((root/'.uncle/workflow/documents/BASELINE_REPORT.json').read_text())
            self.assertEqual(stored['narrative'], 'Narrative text.')

    def test_fenced_json_plan_still_ingests(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            plan = root/'PROJECT_PLAN.md'
            payload = {'schema': 'uncle.artifact/v1', 'kind': 'plan', 'verification_commands': 'pytest'}
            plan.write_text('```json\n' + json.dumps(payload) + '\n```')
            self.assertTrue(module.ingest_plan(plan, root, protected=False))


if __name__ == '__main__':
    unittest.main()
