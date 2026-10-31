#!/usr/bin/env python3
"""Run 21 regressions: new implementation steps never reserve plan numbers."""
import copy
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

LIB = Path(__file__).resolve().parents[1] / 'lib'
sys.path.insert(0, str(LIB))
import plan_model as pm
import updated_plan_ops as ops
import worker_schemas as schemas
from plan_patch import apply_patch
from self_hosted_http import conforms

NARRATIVE = '# Project plan\n\n## Implementation order\n\n' + ''.join(
    '%d. **%s** — %s.\n   Owns: `%s`\n%s\n' % (
        n, title, title, owns, '   Depends on: %d\n' % (n - 1) if n > 1 else '')
    for n, title, owns in [
        (1, 'Scaffold', 'package.json'), (2, 'Core', 'src/core.js'),
        (3, 'Unit tests', 'tests/core.test.js'), (4, 'Components', 'src/app.js'),
        (5, 'Browser tests', 'tests/browser.test.js'), (6, 'Defect injection runner', 'tests/defects.js')]
) + '## Notes\n\nUntouched prose.\n'


class NewSteps(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name)
        self.plan = {'schema': 'uncle.artifact/v1', 'kind': 'plan', 'narrative': NARRATIVE,
                     'verification_commands': 'npm test', 'protected_verification_paths': 'tests/core.test.js'}
        self.model = pm.import_markdown(NARRATIVE)
        self.target = next(b['id'] for s in self.model['sections'] for b in s['blocks'] if b['kind'] == 'steps')
        (self.directory / 'plan.json').write_text(json.dumps(self.plan))
        (self.directory / 'slices.tsv').write_text('1\tAR-1\n2\tAR-2\n')
        self.packet('1', [])
        self.packet('2', [])
        env = {k: v for k, v in os.environ.items() if not k.startswith(('UNCLE_', 'WORKFLOW_'))}
        env['UNCLE_CONFIG'] = str(self.directory / 'config')
        environment = patch.dict(os.environ, env, clear=True)
        environment.start()
        self.addCleanup(environment.stop)

    def packet(self, name, operations):
        value = {'schema': 'uncle.artifact/v1', 'kind': schemas.EDIT_OPS_KIND,
                 'dispositions': [{'finding': 'AR-' + name, 'disposition': 'Accepted', 'reason': 'r', 'plan_change': 'c'}],
                 'ops': operations}
        (self.directory / (name + '.json')).write_text(json.dumps(value))
        return value

    def insert(self, title='Regression test runner', after='step-3', depends=None):
        return {'op': 'insert_step', 'after': after,
                'new': {'title': title, 'text': 'Create the regression artifact.',
                        'owns': ['tests/' + title.lower().replace(' ', '-') + '.js'],
                        'depends_on': depends if depends is not None else [after]}}

    def merge(self, resolutions=None):
        ops.merge(self.directory / 'plan.json', self.directory / 'slices.tsv', self.directory,
                  self.directory / 'merged.json', resolutions)
        result = json.loads((self.directory / 'merged.json').read_text())
        text = apply_patch(NARRATIVE, result['patch'])
        model = pm.import_markdown(text)
        steps = pm.steps_of(model)
        self.assertEqual(pm.validate(model)[0], [])
        self.assertEqual([s['number'] for s in steps], list(range(1, len(steps) + 1)))
        self.assertEqual([s['id'] for s in steps], ['step-%d' % n for n in range(1, len(steps) + 1)])
        self.assertIn('Untouched prose.', text)
        self.assertFalse(any('could not be placed' in r['reason'] for r in result['dispositions']))
        return steps, result

    def test_run21_g19_inserts_without_colliding_with_existing_step4(self):
        self.packet('1', [self.insert()])
        steps, _ = self.merge()
        self.assertEqual([s['title'] for s in steps][2:5], ['Unit tests', 'Regression test runner', 'Components'])
        self.assertEqual(steps[3]['depends_on'], [3])
        self.assertEqual(steps[4]['depends_on'], [3])
        self.assertEqual(steps[5]['depends_on'], [5])
        self.assertEqual(steps[6]['depends_on'], [6])

    def test_legacy_insert_item_accepts_unnumbered_new_step(self):
        operation = self.insert()
        operation.update(op='insert_item', target=self.target)
        self.packet('1', [operation])
        steps, _ = self.merge()
        self.assertEqual(steps[3]['title'], 'Regression test runner')

    def test_before_and_end_placement_rewrite_existing_dependencies(self):
        before = self.insert('Setup', depends=[])
        del before['after']
        before['before'] = 'step-1'
        self.packet('1', [before])
        self.packet('2', [self.insert('Final audit', after='end', depends=['step-6'])])
        steps, _ = self.merge()
        self.assertEqual(steps[0]['title'], 'Setup')
        self.assertEqual(steps[-1]['title'], 'Final audit')
        self.assertEqual(steps[-1]['depends_on'], [7])
        self.assertEqual(steps[2]['depends_on'], [2])

    def test_packet_local_dependencies_are_namespaced_across_writers(self):
        self.packet('1', [self.insert('First baseline'),
                          self.insert('First consumer', depends=['new:1', 'step-6'])])
        self.packet('2', [self.insert('Second baseline'),
                          self.insert('Second consumer', depends=['new:1', 'step-6'])])
        steps, _ = self.merge()
        by_title = {s['title']: s for s in steps}
        for prefix in ('First', 'Second'):
            self.assertEqual(by_title[prefix + ' consumer']['depends_on'],
                             [by_title[prefix + ' baseline']['number'], by_title['Defect injection runner']['number']])

    def test_existing_step_can_depend_on_a_new_step_in_its_packet(self):
        self.packet('1', [self.insert('Baseline snapshot', 'step-5'),
                          {'op': 'set_step', 'id': 'step-6', 'fields': {'depends_on': ['new:1']}}])
        steps, _ = self.merge()
        self.assertEqual(steps[5]['title'], 'Baseline snapshot')
        self.assertEqual(steps[6]['depends_on'], [6])

    def test_run21_g22_baseline_does_not_reuse_step6_or_create_self_dependency(self):
        self.packet('1', [self.insert('Baseline snapshot', 'step-5')])
        steps, _ = self.merge()
        self.assertEqual(steps[5]['title'], 'Baseline snapshot')
        self.assertEqual(steps[5]['depends_on'], [5])
        self.assertEqual(steps[6]['title'], 'Defect injection runner')
        self.assertEqual(steps[6]['depends_on'], [5])

    def test_concurrent_groups_after_same_step_are_stable_and_keep_dependencies(self):
        first = self.insert('Regression test runner')
        second = self.insert('Baseline snapshot', depends=['step-4'])
        # Finish packet 2 first: disk creation order must not determine numbering.
        self.packet('2', [second])
        self.packet('1', [first])
        steps, output = self.merge()
        self.assertEqual([s['title'] for s in steps][2:6],
                         ['Unit tests', 'Regression test runner', 'Baseline snapshot', 'Components'])
        self.assertEqual(steps[3]['depends_on'], [3])
        self.assertEqual(steps[4]['depends_on'], [6])
        self.assertEqual(steps[5]['depends_on'], [3])
        self.assertEqual(steps[6]['depends_on'], [6])
        self.packet('1', [first])
        self.packet('2', [second])
        self.assertEqual(self.merge()[1], output)

    def test_resolver_insertion_and_writer_insertion_share_number_allocator(self):
        self.packet('1', [self.insert(), {'op': 'set_step', 'id': 'step-6', 'fields': {'text': 'first'}}])
        self.packet('2', [{'op': 'set_step', 'id': 'step-6', 'fields': {'text': 'second'}}])
        with self.assertRaises(ops.NeedsResolution) as caught:
            self.merge()
        self.assertEqual(len(caught.exception.groups), 1)
        group = caught.exception.groups[0]['id']
        reply = {'resolutions': [{'group': group, 'ops': [self.insert('Baseline snapshot', 'step-5')]}]}
        (self.directory / ('resolutions-' + group + '.json')).write_text(json.dumps(reply))
        self.assertEqual(ops.check_resolutions(self.directory / 'plan.json', self.directory), {})
        steps, _ = self.merge(self.directory)
        self.assertEqual([s['title'] for s in steps][3], 'Regression test runner')
        self.assertEqual([s['title'] for s in steps][6], 'Baseline snapshot')
        self.assertEqual(steps[6]['depends_on'], [6])
        self.assertEqual(steps[7]['depends_on'], [6])

    def test_schemas_accept_steps_without_numbers_and_reject_model_assigned_ids(self):
        packet = self.packet('1', [self.insert()])
        for schema in (schemas.edit_ops_packet(model=self.model), schemas.resolution_ops_packet(model=self.model),
                       schemas.edit_ops_packet(), schemas.resolution_ops_packet()):
            with self.subTest(kind=schema['properties']['kind']):
                value = packet if 'ops' in schema['properties'] else {
                    'schema': 'uncle.artifact/v1', 'kind': schemas.RESOLUTION_OPS_KIND,
                    'resolutions': [{'group': 'G19', 'ops': packet['ops']}]}
                conforms(value, schema)
                invalid = copy.deepcopy(value)
                operation = invalid['ops'][0] if 'ops' in invalid else invalid['resolutions'][0]['ops'][0]
                operation['new'].update(id='step-4', number=4)
                with self.assertRaises(ValueError):
                    conforms(invalid, schema)

    def test_scoped_insertion_can_reference_an_uneditable_dependency(self):
        scope = schemas.scoped_ids(self.model, ['step-3'])
        schema = schemas.edit_ops_packet(scope, model=self.model)
        packet = self.packet('1', [self.insert(depends=['step-6'])])
        conforms(packet, schema)
        packet['ops'] = [{'op': 'set_step', 'id': 'step-6', 'fields': {'text': 'outside scope'}}]
        with self.assertRaises(ValueError):
            conforms(packet, schema)

    def test_deleted_insertion_anchor_is_resolved_as_a_group(self):
        self.packet('1', [{'op': 'delete', 'id': 'step-3'},
                          {'op': 'set_step', 'id': 'step-4', 'fields': {'depends_on': [2]}}])
        self.packet('2', [self.insert(depends=['step-1'])])
        with self.assertRaises(ops.NeedsResolution) as caught:
            self.merge()
        self.assertTrue(any({e['writer'] for e in group['edits']} == {'1', '2'}
                            for group in caught.exception.groups))

    def test_deleted_new_step_dependency_is_resolved_as_a_group(self):
        self.packet('1', [{'op': 'delete', 'id': 'step-6'}])
        self.packet('2', [self.insert(depends=['step-6'])])
        with self.assertRaises(ops.NeedsResolution) as caught:
            self.merge()
        self.assertTrue(any({e['writer'] for e in group['edits']} == {'1', '2'}
                            for group in caught.exception.groups))

    def test_resolver_keeps_new_step_and_its_conflicting_consumer_together(self):
        insertion = self.insert('Baseline snapshot', 'step-5')
        consumer = {'op': 'set_step', 'id': 'step-6', 'fields': {'depends_on': ['new:1']}}
        self.packet('1', [insertion, consumer])
        self.packet('2', [{'op': 'set_step', 'id': 'step-6', 'fields': {'depends_on': [4]}}])
        with self.assertRaises(ops.NeedsResolution) as caught:
            self.merge()
        self.assertEqual(len(caught.exception.groups), 1)
        group = caught.exception.groups[0]
        self.assertTrue(any(edit['op']['op'] == 'insert_step' for edit in group['edits']))
        prompt = (self.directory / 'prompts' / ('resolve-' + group['id'] + '.md')).read_text()
        self.assertIn('new:1', prompt)
        self.assertNotIn('new:1:1', prompt)
        self.assertNotIn('_step_key', prompt)
        reply = {'resolutions': [{'group': group['id'], 'ops': [insertion, consumer]}]}
        (self.directory / ('resolutions-' + group['id'] + '.json')).write_text(json.dumps(reply))
        self.assertEqual(ops.check_resolutions(self.directory / 'plan.json', self.directory), {})
        steps, _ = self.merge(self.directory)
        self.assertEqual([s['title'] for s in steps].count('Baseline snapshot'), 1)
        self.assertEqual(steps[6]['depends_on'], [6])


if __name__ == '__main__':
    unittest.main()
