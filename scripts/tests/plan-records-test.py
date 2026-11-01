#!/usr/bin/env python3
"""Canonical plan records and write-time invariants, without Git or model calls."""
import copy
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

LIB = Path(__file__).resolve().parents[1] / 'lib'
sys.path.insert(0, str(LIB))
import artifact_json
import plan_context
import plan_model as pm
import plan_ownership_gap as gap
import plan_records as records

FIXTURES = Path(__file__).resolve().parent / 'fixtures/plan-records'


def model():
    return {'title': 'Plan', 'intro': '', 'sections': [
        {'id': 's1', 'heading': 'Implementation order', 'blocks': [
            {'id': 's1.1', 'kind': 'steps', 'items': [
                {'id': 'step-0', 'number': 0, 'title': 'Scaffold', 'text': 'Create package.',
                 'owns': ['package.json'], 'depends_on': []},
                {'id': 'step-5', 'number': 5, 'title': 'Tests', 'text': 'Create tests.',
                 'owns': ['tests/a.js'], 'depends_on': [0]}]}]}],
        'protected_verification_paths': ['package-lock.json', 'tests/a.js']}


class Records(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        env = patch.dict(os.environ, WORKFLOW_PLAN_RECORDS='1', UNCLE_CONFIG=str(self.root / '.uncle/config'))
        env.start()
        self.addCleanup(env.stop)
        self.state = self.root / '.uncle/workflow'
        self.doc = self.state / 'documents/PROJECT_PLAN.json'
        self.doc.parent.mkdir(parents=True)
        self.plan = self.root / '.uncle/docs/PROJECT_PLAN.md'
        self.plan.parent.mkdir(parents=True)
        self.plan.write_text('stale approval view: no ownership here\n')
        self.payload = dict(model(), schema='uncle.artifact/v1', kind='plan',
                            narrative='stale narrative: no ownership here', verification_commands='true')
        self.doc.write_text(json.dumps(self.payload))

    def shell(self, fn, plan=None):
        env = {k: v for k, v in os.environ.items() if k != 'STATE_DIR'}
        return subprocess.run(['bash', '-c', '. "$1/plan-scope.sh"; "$2" "$3"', 'test',
                               str(LIB), fn, str(plan or self.plan)], cwd=self.root, env=env,
                              text=True, capture_output=True)

    def test_canonical_ownership_and_dependencies_ignore_stale_markdown(self):
        self.assertEqual(self.shell('plan_step_owns').stdout.splitlines(), ['1\tpackage.json', '2\ttests/a.js'])
        self.assertEqual(self.shell('plan_step_depends').stdout, '2\t1\n')
        self.assertIn('**Tests**', self.shell('plan_steps').stdout)
        self.assertEqual(self.shell('plan_step_owns', self.doc).stdout.splitlines(),
                         ['1\tpackage.json', '2\ttests/a.js'])

    def test_records_work_without_the_rendered_file(self):
        self.plan.unlink()
        self.assertEqual(self.shell('plan_step_depends').stdout, '2\t1\n')

    def test_empty_ownership_never_falls_back_to_stale_markdown(self):
        for step in pm.steps_of(self.payload):
            step['owns'] = []
        self.doc.write_text(json.dumps(self.payload))
        self.plan.write_text('## Implementation order\n\n1. Stale Owns: `stale.js`\n')
        self.assertEqual(self.shell('plan_step_owns').stdout, '')

    def test_explicit_empty_records_never_restore_stale_steps(self):
        self.payload['sections'] = []
        self.payload['protected_verification_paths'] = []
        self.payload['narrative'] = '## Implementation order\n\n1. Owns: `stale.js`\n'
        self.doc.write_text(json.dumps(self.payload))
        self.assertEqual(self.shell('plan_steps').stdout, '')
        self.assertEqual(self.shell('plan_step_owns').stdout, '')

    def test_custom_state_directory_and_absolute_paths(self):
        other = self.root / 'other-state'
        self.state.rename(other)
        self.assertEqual(gap.unowned_protected_paths(self.plan, self.root, ['tests/a.js'], other), [])
        self.assertEqual(records.canonical_path(self.plan, other), other / 'documents/PROJECT_PLAN.json')

    def test_gap_reads_structured_paths_and_owners(self):
        self.assertEqual(gap.load_protected_paths(self.plan, self.state), ['package-lock.json', 'tests/a.js'])
        with patch.object(gap.subprocess, 'run', side_effect=AssertionError('no Markdown subprocess')):
            self.assertEqual(gap.unowned_protected_paths(self.plan, self.root, ['tests/a.js']), [])
            self.assertEqual(gap.unowned_protected_paths(self.plan, self.root, ['tests/missing.js']), ['tests/missing.js'])

    def test_step_groups_reads_records_directly(self):
        env = dict(os.environ, WORKFLOW_IMPLEMENT_IGNORE_DEPENDS='0')
        result = subprocess.run([sys.executable, '-I', str(LIB / 'step_groups.py'), str(self.plan), str(self.root)],
                                env=env, text=True, capture_output=True, check=True)
        self.assertEqual(json.loads(result.stdout)['groups'], [[1], [2]])

    def test_canonical_scope_reads_typed_rows(self):
        self.payload['sections'].append({'id': 's2', 'heading': 'Change-impact table', 'blocks': [
            {'id': 's2.1', 'kind': 'rows', 'row_kind': 'change_impact', 'rows': [
                {'id': 'r1', 'component': 'src/app.js', 'coverage': '`tests/a.js`'}]}]})
        self.doc.write_text(json.dumps(self.payload))
        self.assertEqual(self.shell('plan_scope_files').stdout.splitlines(), ['src/app.js', 'tests/a.js'])

    def test_legacy_sidecar_is_used_only_while_it_matches(self):
        m = model()
        self.doc.write_text(json.dumps({'narrative': pm.render(m)}))
        pm.sidecar(self.doc).write_text(json.dumps(m))
        self.assertEqual(self.shell('plan_step_depends').stdout, '2\t1\n')
        self.doc.write_text(json.dumps({'narrative': '## Implementation order\n\n1. Owns: `legacy.js`\n'}))
        self.assertIsNone(records.load(self.plan))
        self.assertEqual(self.shell('plan_step_owns').stdout, '1\tlegacy.js\n')

    def test_corrupt_canonical_data_is_an_error(self):
        self.doc.write_text('{broken')
        self.assertNotEqual(self.shell('plan_step_owns').returncode, 0)
        with self.assertRaisesRegex(ValueError, 'cannot read protected paths'):
            gap.load_protected_paths(self.plan, self.state)

    def test_legacy_json_narrative_precedes_rendered_markdown(self):
        self.doc.write_text(json.dumps({'narrative': '## Implementation order\n\n1. Owns: `legacy.js`\n'}))
        self.assertEqual(self.shell('plan_step_owns').stdout, '1\tlegacy.js\n')

    def test_legacy_markdown_protected_paths(self):
        self.doc.unlink()
        self.plan.write_text('## Protected verification paths\n\n```text\ntests/a.js\n```\n')
        self.assertEqual(gap.load_protected_paths(self.plan, self.state), ['tests/a.js'])


class Invariants(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        env = patch.dict(os.environ, WORKFLOW_PLAN_RECORDS='1', UNCLE_CONFIG=str(self.root / '.uncle/config'))
        env.start()
        self.addCleanup(env.stop)

    def test_dependency_edges_across_blocks_and_forward_references(self):
        m = model()
        first = m['sections'][0]['blocks'][0]
        m['sections'][0]['blocks'].append({'id': 's1.2', 'kind': 'steps', 'items': [first['items'].pop()]})
        steps = pm.steps_of(m)
        steps[0]['depends_on'], steps[1]['depends_on'] = [5], []
        self.assertEqual(pm.validate(m, self.root)[0], [])
        self.assertEqual(records.step_data(m)[2], {1: {2}, 2: set()})

    def test_cycle_and_missing_reference_name_one_edge_to_remove(self):
        for deps, message in [([5], 'cycle'), ([99], 'remove 99')]:
            with self.subTest(deps=deps), self.assertRaisesRegex(pm.PlanError, message):
                pm.apply_ops(model(), [{'op': 'set_step', 'id': 'step-0', 'depends_on': deps}], self.root)

    def test_invalid_owns_rejected_without_mutating_original(self):
        for token in ['tests/', '../escape.js', '/absolute.js', 'added to tests/a.js', '`tests/a.js`']:
            m = model()
            before = copy.deepcopy(m)
            with self.subTest(token=token), self.assertRaisesRegex(pm.PlanError, 'step-5 owns: replace'):
                pm.apply_ops(m, [{'op': 'set_step', 'id': 'step-5', 'owns': [token]}], self.root)
            self.assertEqual(m, before)

    def test_prose_ownership_diagnostic_is_bounded(self):
        with self.assertRaises(pm.PlanError) as caught:
            pm.apply_ops(model(), [{'op': 'set_step', 'id': 'step-5', 'owns': ['prose ' * 1000]}], self.root)
        self.assertLess(len(str(caught.exception)), 180)

    def test_existing_directory_requires_glob(self):
        (self.root / 'tests').mkdir()
        with self.assertRaisesRegex(pm.PlanError, 'directory/\\*\\*'):
            pm.apply_ops(model(), [{'op': 'set_step', 'id': 'step-5', 'owns': ['tests']}], self.root)

    def test_removing_last_protected_owner_is_rejected_with_small_fix(self):
        with self.assertRaisesRegex(pm.PlanError, 'set_step <creator-id> owns: add tests/a.js'):
            pm.apply_ops(model(), [{'op': 'set_step', 'id': 'step-5', 'owns': ['tests/b.js']}], self.root)

    def test_existing_untracked_file_needs_no_creator(self):
        (self.root / 'tests').mkdir()
        (self.root / 'tests/a.js').write_text('test')
        revised = pm.apply_ops(model(), [{'op': 'set_step', 'id': 'step-5', 'owns': []}], self.root)
        self.assertEqual(pm.steps_of(revised)[1]['owns'], [])

    def test_wildcard_reconcile_does_not_create_protected_files(self):
        m = model()
        pm.steps_of(m)[1]['owns'] = ['*']
        self.assertIn('has no creator', pm.validate(m, self.root)[0][0])

    def test_file_globs_and_protected_directories(self):
        m = model()
        pm.steps_of(m)[1]['owns'] = ['tests/*.js']
        m['protected_verification_paths'] += ['tests/']
        self.assertEqual(pm.validate(m, self.root)[0], [])

    def test_duplicate_step_numbers_are_rejected_across_blocks(self):
        m = model()
        pm.steps_of(m)[1]['number'] = 0
        self.assertIn('number 0 is used twice', pm.validate(m, self.root)[0][0])

    def test_dependency_arrays_and_invalid_values(self):
        op = pm.typed_op(model(), {'op': 'set_step', 'id': 'step-5', 'fields': {'depends_on': [0]}})
        self.assertEqual(op['depends_on'], [0])
        for value in ([True], ['0'], 'after step 99', '-1'):
            with self.subTest(value=value), self.assertRaisesRegex(pm.PlanError, 'depends_on: use'):
                pm.dependency_list(value)

    def test_publish_records_preserves_rendered_bytes_and_carries_fields(self):
        m = model()
        payload = dict(m, schema='uncle.artifact/v1', kind='plan', narrative=pm.render(m),
                       protected_verification_paths='package-lock.json\ntests/a.js', verification_commands='true')
        before = artifact_json.render_plan(payload)
        published = pm.publish_records(payload, self.root)
        self.assertEqual(artifact_json.render_plan(published), before)
        self.assertEqual(pm.model_of(published)['protected_verification_paths'], ['package-lock.json', 'tests/a.js'])

    def test_merge_hook_uses_final_protected_contract_without_rendering(self):
        result = {'kind': 'plan', 'patch': {}, 'protected_verification_paths': 'tests/a.js'}
        published = pm.publish_records(result, self.root, model=model())
        self.assertEqual(published['protected_verification_paths'], 'tests/a.js')
        self.assertNotIn('narrative', published)
        self.assertEqual(published['sections'], model()['sections'])
        with self.assertRaisesRegex(pm.PlanError, 'has no creator'):
            pm.publish_records(dict(result, protected_verification_paths='tests/b.js'), self.root, model=model())

    def test_all_plan_publishers_store_records_through_artifact_writer(self):
        payload = {'schema': 'uncle.artifact/v1', 'kind': 'plan', 'narrative': pm.render(model())}
        target = artifact_json.write(self.root, 'PROJECT_PLAN.md', payload)
        self.assertEqual(pm.steps_of(json.loads(target.read_text()))[1]['owns'], ['tests/a.js'])
        before = target.read_bytes()
        payload['protected_verification_paths'] = 'tests/missing.js'
        with self.assertRaisesRegex(pm.PlanError, 'tests/missing.js'):
            artifact_json.write(self.root, 'PROJECT_PLAN.md', payload)
        self.assertEqual(target.read_bytes(), before)

    def test_project_plan_export_writes_records_before_any_render_change(self):
        path = self.root / 'PROJECT_PLAN.md'
        path.write_text(pm.render(model()) + '\n## Verification commands\n\n```sh\ntrue\n```\n')
        before = path.read_bytes()
        payload = plan_context.export_project_plan(path, self.root)
        self.assertEqual(pm.steps_of(payload)[1]['depends_on'], [0])
        self.assertEqual(path.read_bytes(), before)
        self.assertEqual(artifact_json.read(self.root, path.name)['sections'], payload['sections'])

    def test_invalid_typed_plan_is_rejected_before_writing_either_file(self):
        payload = dict(model(), schema='uncle.artifact/v1', kind='plan', narrative=pm.render(model()),
                       verification_commands='true', protected_verification_paths='tests/missing.js')
        path = self.root / 'PROJECT_PLAN.md'
        path.write_text(json.dumps(payload))
        before = path.read_bytes()
        with self.assertRaisesRegex(pm.PlanError, 'tests/missing.js'):
            plan_context.ingest_plan(path, self.root)
        self.assertEqual(path.read_bytes(), before)
        self.assertFalse(artifact_json.path(self.root, path.name).exists())

    def test_recursive_globs_cover_nested_protected_files(self):
        m = model()
        pm.steps_of(m)[1]['owns'] = ['tests/**']
        m['protected_verification_paths'] = ['tests/nested/a.js']
        self.assertEqual(pm.validate(m, self.root)[0], [])
        pm.steps_of(m)[1]['owns'] = ['tests/*']
        self.assertIn('has no creator', pm.validate(m, self.root)[0][0])

    def test_numbered_nonstep_lists_keep_nested_items(self):
        blocks = pm.parse_blocks('1. First\n   - Nested\n2. Second', 's1')
        self.assertEqual(len(blocks[0]['items']), 3)
        self.assertEqual(blocks[0]['items'][1]['style'], 'bullet')

    def test_config_switch_env_precedes_config_and_defaults_enabled(self):
        config = self.root / '.uncle/config'
        config.parent.mkdir()
        with patch.dict(os.environ, {}, clear=True):
            self.assertTrue(pm.records_enabled(self.root))
            config.write_text('workflow.plan-records 0\n')
            self.assertFalse(pm.records_enabled(self.root))
            self.assertNotIn('sections', pm.publish_records({'narrative': pm.render(model())}, self.root))
            with patch.dict(os.environ, WORKFLOW_PLAN_RECORDS='1'):
                self.assertTrue(pm.records_enabled(self.root))
            config.write_text('workflow.plan-records 1\n')
            with patch.dict(os.environ, WORKFLOW_PLAN_RECORDS='0'):
                self.assertFalse(pm.records_enabled(self.root))
                self.assertIsNone(records.load(self.root / 'unused.json'))
            with patch.dict(os.environ, UNCLE_CONFIG=str(config)):
                self.assertTrue(pm.records_enabled(self.root / 'other-root'))



class SavedRuns(unittest.TestCase):
    def test_run_11_heading_steps_and_additional_ownership(self):
        plan = json.loads((FIXTURES / 'run-11.json').read_text())
        m = pm.with_protected(pm.import_markdown(plan['narrative']), plan)
        self.assertEqual(len(pm.steps_of(m)), 6)
        self.assertIn('.eslintrc.cjs', pm.steps_of(m)[0]['owns'])
        with tempfile.TemporaryDirectory() as root:
            self.assertEqual(pm.validate(m, root)[0], [])
        self.assertEqual(pm.steps_of(pm.import_markdown(pm.render(m))), pm.steps_of(m))

    def test_run_12_duplicate_numbers_are_real_errors_and_missing_test_stays_visible(self):
        plan = json.loads((FIXTURES / 'run-12.json').read_text())
        m = pm.with_protected(pm.import_markdown(plan['narrative']), plan)
        with tempfile.TemporaryDirectory() as root:
            self.assertTrue(any('number 1 is used twice' in e for e in pm.validate(m, root)[0]))
            self.assertIn('tests/useKeyboard.test.js', pm.ownership_errors(m, root)[0])
        self.assertTrue(any('tests/calcReducer.test.js' in step['owns'] for step in pm.steps_of(m)))


if __name__ == '__main__':
    unittest.main()
