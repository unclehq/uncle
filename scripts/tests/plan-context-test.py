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

    def test_markdown_plan_is_left_alone(self):
        with tempfile.TemporaryDirectory() as d:
            plan = Path(d)/'PROJECT_PLAN.md'
            plan.write_text('# A hand-written plan\n\nNo JSON here.\n')
            self.assertFalse(module.ingest_plan(plan, Path(d), protected=False))
            self.assertEqual(plan.read_text(), '# A hand-written plan\n\nNo JSON here.\n')

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

    def test_fenced_json_plan_still_ingests(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            plan = root/'PROJECT_PLAN.md'
            payload = {'schema': 'uncle.artifact/v1', 'kind': 'plan', 'verification_commands': 'pytest'}
            plan.write_text('```json\n' + json.dumps(payload) + '\n```')
            self.assertTrue(module.ingest_plan(plan, root, protected=False))


if __name__ == '__main__':
    unittest.main()
