#!/usr/bin/env python3
"""Number-only plan repairs preserve the approval view and edit semantics."""
import copy
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'lib'))
import plan_context
import plan_model as pm
import artifact_json
import publish_agent_artifact as publisher
import self_hosted


TEXT = '''# Plan

Keep this prose  exactly.

## Implementation order

1. **First** — Create core.
   Owns: `core.py`

1. **Second** — Create tests.
   Owns: `test_core.py`

8. **Third** — Write docs.
   Owns: `README.md`
   Depends on: 8

## Notes

Leave these bytes alone.
'''


class Numbering(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        config = self.root / '.uncle/config'
        config.parent.mkdir()
        config.write_text('runner self-hosted\n')
        env = patch.dict(os.environ, {'UNCLE_CONFIG': str(config), 'UNCLE_STATUS_STAGE': 'project-plan-investigate'}, clear=True)
        env.start()
        self.addCleanup(env.stop)
        self.text = TEXT.replace('   Depends on: 8\n', '')
        self.plan = dict(schema='uncle.artifact/v1', kind='plan', narrative=self.text, verification_commands='true')

    def test_duplicate_without_references_preserves_all_other_bytes_and_ids(self):
        original = copy.deepcopy(self.plan)
        result = pm.publish_records(self.plan, self.root)
        self.assertEqual(result['narrative'], self.text.replace('1. **Second**', '2. **Second**').replace('8. **Third**', '3. **Third**'))
        self.assertEqual(self.plan, original)
        self.assertEqual([s['id'] for s in pm.steps_of(result)], [s['id'] for s in pm.steps_of(pm.model_of(original))])
        self.assertEqual(pm.validate(pm.model_of(result), self.root)[0], [])

    def test_unique_references_move_with_their_target(self):
        self.plan['narrative'] = self.text.replace('1. **Second**', '6. **Second**').replace('8. **Third**', '9. **Third**')
        self.plan['narrative'] = self.plan['narrative'].replace('   Owns: `README.md`', '   Owns: `README.md`\n   Depends on: 6, 1')
        result = pm.publish_records(self.plan, self.root)
        self.assertEqual(pm.steps_of(result)[2]['depends_on'], [2, 1])
        self.assertIn('   Depends on: 2, 1', result['narrative'])

    def test_ambiguous_dependency_does_not_guess(self):
        self.plan['narrative'] = self.text.replace('   Owns: `README.md`', '   Owns: `README.md`\n   Depends on: 1')
        model = pm.model_of(self.plan)
        self.assertIs(pm.renumber_steps(model, self.root), model)
        with self.assertRaisesRegex(pm.PlanError, 'used twice'):
            pm.publish_records(self.plan, self.root)

    def test_unrelated_errors_and_self_dependencies_do_not_get_repaired(self):
        for text in (TEXT, self.text.replace('`README.md`', '`../README.md`')):
            model = pm.import_markdown(text)
            self.assertIs(pm.renumber_steps(model, self.root), model)

    def test_native_and_large_runners_preserve_existing_validation(self):
        config = Path(os.environ['UNCLE_CONFIG'])
        for settings in ('runner claude\n', 'runner codex\n', 'runner self-hosted\nproject-plan.granularity large\n',
                         'runner self-hosted\nproject-plan.plan-renumber off\n'):
            config.write_text(settings)
            with self.assertRaisesRegex(pm.PlanError, 'used twice'):
                pm.publish_records(self.plan, self.root)

    def test_export_and_render_share_repaired_numbers(self):
        view = self.root / '.uncle/docs/PROJECT_PLAN.md'
        view.parent.mkdir()
        view.write_text(self.text + '\n## Verification commands\n\n```sh\ntrue\n```\n')
        result = plan_context.export_project_plan(view, self.root)
        plan_context.render_canonical(view, self.root, protected=False)
        canonical = json.loads((self.root / '.uncle/workflow/documents/PROJECT_PLAN.json').read_text())
        self.assertEqual(canonical, result)
        self.assertIn('2. **Second**', view.read_text())
        self.assertIn('3. **Third**', view.read_text())

    def test_sections_only_plan_keeps_its_shape(self):
        payload = dict(pm.model_of(self.plan), schema='uncle.artifact/v1', kind='plan', verification_commands='true')
        result = pm.publish_records(payload, self.root)
        self.assertNotIn('narrative', result)
        self.assertEqual([s['number'] for s in pm.steps_of(result)], [1, 2, 3])

    def test_indented_step_markers_preserve_whitespace(self):
        self.plan['narrative'] = self.text.replace('\n1.', '\n  1.').replace('\n8.', '\n  8.')
        result = pm.publish_records(self.plan, self.root)
        self.assertEqual(result['narrative'], self.plan['narrative'].replace('1. **Second**', '2. **Second**').replace('8. **Third**', '3. **Third**'))

    def test_shared_publisher_renders_the_normalized_canonical_packet(self):
        for stage in ('project-plan', 'updated-plan', 'change-plan', 'updated-change-plan'):
            with self.subTest(stage=stage):
                payload = dict(self.plan, protected_verification_paths='test_core.py')
                if 'change' in stage:
                    payload['kind'] = 'change-plan'
                if stage.startswith('updated'):
                    payload['dispositions'] = [{'finding': 'AR-001', 'disposition': 'Accepted', 'reason': 'Fix', 'plan_change': 'Steps'}]
                delivery = self.root / 'delivery.json'
                delivery.write_text(json.dumps(payload))
                self.assertTrue(publisher.publish(stage, 'unused', self.root, delivery))
                name = publisher.ARTIFACT[stage][0]
                canonical = artifact_json.read(self.root, name)
                render = (artifact_json.render_change_plan(canonical, require_dispositions=stage.startswith('updated'))
                          if 'change' in stage else artifact_json.render_plan(canonical, protected=stage.startswith('updated')))
                self.assertEqual((self.root / '.uncle/docs' / name).read_text(), render + '\n')
                self.assertIn('2. **Second**', render)

    def test_http_view_uses_the_project_root_configuration(self):
        with patch.dict(os.environ, {}, clear=True):
            view = self_hosted.document_response(json.dumps(self.plan), '.uncle/docs/PROJECT_PLAN.md', root=self.root)
        self.assertIn('2. **Second**', view)
        self.assertIn('3. **Third**', view)

    def test_export_uses_destination_stage_instead_of_stale_status(self):
        Path(os.environ['UNCLE_CONFIG']).write_text('runner claude\nupdated-plan.runner self-hosted\n')
        view = self.root / '.uncle/docs/UPDATED_PROJECT_PLAN.md'
        view.parent.mkdir()
        view.write_text(self.text + '\n## Verification commands\n\n```sh\ntrue\n```\n'
                        '\n## Protected verification paths\n\n```text\ntest_core.py\n```\n')
        result = plan_context.export_updated_project_plan(view, self.root)
        self.assertEqual([s['number'] for s in pm.steps_of(result)], [1, 2, 3])

    def test_apply_ops_still_allows_existing_errors_but_rejects_new_errors(self):
        model = pm.model_of(self.plan)
        second = pm.steps_of(model)[1]
        revised = pm.apply_ops(model, [{'op': 'set_step', 'id': second['id'], 'title': 'Renamed'}], self.root)
        self.assertEqual(pm.steps_of(revised)[1]['title'], 'Renamed')
        with self.assertRaises(pm.PlanError):
            pm.apply_ops(model, [{'op': 'set_step', 'id': second['id'], 'depends_on': [99]}], self.root)


if __name__ == '__main__':
    unittest.main()
