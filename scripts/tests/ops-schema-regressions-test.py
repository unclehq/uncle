#!/usr/bin/env python3
"""Run 17 regressions: model-shaped edit grammars and whole-lens review counts."""
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
import adversarial_packets
import adversarial_slices
import plan_model as pm
from self_hosted_http import conforms as local_conforms
import worker_packets
import worker_schemas as ws


def conforms(value, schema):
    """Also check grammar bounds that the lightweight runtime validator omits."""
    if 'anyOf' in schema:
        for variant in schema['anyOf']:
            try:
                conforms(value, variant)
                return
            except ValueError:
                pass
        raise ValueError('No allowed operation matches')
    local_conforms(value, schema)
    if schema.get('type') == 'integer':
        if value < schema.get('minimum', value) or value > schema.get('maximum', value):
            raise ValueError('Integer outside grammar bounds')
    if schema.get('type') == 'object':
        if len(value) < schema.get('minProperties', 0):
            raise ValueError('Too few properties')
        for key, child in value.items():
            if key in schema.get('properties', {}):
                conforms(child, schema['properties'][key])
    if schema.get('type') == 'array':
        if len(value) < schema.get('minItems', 0):
            raise ValueError('Too few array items')
        for child in value:
            conforms(child, schema.get('items', {}))


NARRATIVE = '''# Project plan

## 1. Behaviors

| ID | Trigger | Observable result | Failure behavior | Requirement IDs |
|---|---|---|---|---|
| B-1 | Save | Data persists | Error shown | UB-1 |
| B-2 | Cancel | Data unchanged | Error shown | UB-2 |

## 2. Invariants

| ID | Invariant | Scope | Enforcement point | Automated test | Violation impact |
|---|---|---|---|---|---|
| I-1 | Writes are atomic | Storage | Save | tests/save.py | Lost data |

## 3. Implementation order

1. **Scaffold** — Create package.json.
   Owns: `package.json`

2. **Storage** — Implement save.
   Owns: `src/save.js`, `tests/save.py`
   Depends on: 1

## 4. Notes

Preserve this prose.

- Preserve this list item.

| Custom heading | Other column |
|---|---|
| Untyped | Cell |
'''


class EditGrammarTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        env = {k: v for k, v in os.environ.items() if not k.startswith(('WORKFLOW_', 'UNCLE_'))}
        env['UNCLE_CONFIG'] = str(self.root / 'config')
        clean_env = patch.dict(os.environ, env, clear=True)
        clean_env.start()
        self.addCleanup(clean_env.stop)
        self.plan = self.root / 'plan.json'
        self.plan.write_text(json.dumps({'schema': ws.ENVELOPE, 'kind': 'plan',
                                        'narrative': NARRATIVE}))
        self.model = pm.load_model(self.plan)
        self.schemas = {}
        for command in ('edit-ops', 'resolve-ops'):
            output = self.root / (command + '.json')
            self.assertEqual(ws.main([command, str(self.plan), str(output)]), 0)
            self.schemas[command] = json.loads(output.read_text())
        self.behavior = self.model['sections'][0]['blocks'][0]['id']
        self.invariant = self.model['sections'][1]['blocks'][0]['id']
        self.steps = self.model['sections'][2]['blocks'][0]['id']
        self.prose, self.items, self.table = self.model['sections'][3]['blocks']

    def packet(self, command, operation):
        if command == 'edit-ops':
            return {'schema': ws.ENVELOPE, 'kind': ws.EDIT_OPS_KIND,
                    'dispositions': [], 'ops': [operation]}
        return {'schema': ws.ENVELOPE, 'kind': ws.RESOLUTION_OPS_KIND,
                'resolutions': [{'group': 'G25', 'ops': [operation]}]}

    def assert_rejected(self, operation):
        for command, schema in self.schemas.items():
            with self.subTest(command=command, operation=operation):
                with self.assertRaises(ValueError):
                    conforms(self.packet(command, operation), schema)

    def assert_accepted(self, operation):
        # The grammar and the final model validator must agree on valid answers.
        pm.apply_ops(self.model, [pm.typed_op(self.model, operation)])
        for command, schema in self.schemas.items():
            with self.subTest(command=command, operation=operation):
                conforms(self.packet(command, operation), schema)

    def test_run17_behavior_title_is_rejected_and_result_is_accepted(self):
        self.assert_rejected({'op': 'insert_row', 'target': self.behavior,
                              'new': {'id': 'B-3', 'title': 'Save timeout'}})
        self.assert_accepted({'op': 'insert_row', 'target': self.behavior,
                              'new': {'id': 'B-3', 'trigger': 'Timeout', 'result': 'Error shown'}})
        self.assert_rejected({'op': 'set_fields', 'id': 'B-1', 'fields': {'title': 'Save timeout'}})
        self.assert_accepted({'op': 'set_fields', 'id': 'B-1', 'fields': {'result': 'Error shown'}})

    def test_run17_insert_row_rejects_non_row_blocks(self):
        for target in (self.steps, self.prose['id'], self.items['id'], self.table['id']):
            self.assert_rejected({'op': 'insert_row', 'target': target,
                                  'new': {'id': 'B-3', 'trigger': 'Save'}})
        self.assert_accepted({'op': 'insert_item', 'target': self.items['id'],
                              'new': {'text': 'Check recovery.'}})

    def test_run17_step_dependencies_are_integer_arrays(self):
        for invalid in ('Step 1', '1 and 2', ['1'], [True], [-1], '1, 2'):
            self.assert_rejected({'op': 'set_step', 'id': 'step-2',
                                  'fields': {'depends_on': invalid}})
        self.assert_accepted({'op': 'set_step', 'id': 'step-2', 'fields': {'depends_on': [1]}})
        self.assert_accepted({'op': 'set_step', 'id': 'step-2', 'fields': {'depends_on': []}})

    def test_run17_owns_belongs_to_steps_not_behavior_or_invariant_rows(self):
        for target, identifier in ((self.behavior, 'B-3'), (self.invariant, 'I-2')):
            self.assert_rejected({'op': 'insert_row', 'target': target,
                                  'new': {'id': identifier, 'owns': 'src/save.js'}})
        for identifier in ('B-1', 'I-1'):
            self.assert_rejected({'op': 'set_fields', 'id': identifier,
                                  'fields': {'owns': 'src/save.js'}})
        self.assert_accepted({'op': 'set_step', 'id': 'step-2',
                              'fields': {'owns': ['src/save.js', 'tests/save.py', 'src/retry.js']}})
        self.assert_accepted({'op': 'set_fields', 'id': 'I-1', 'fields': {'enforcement': 'Save transaction'}})

    def test_run17_untyped_rows_cannot_receive_fields(self):
        for identifier in (self.items['items'][0]['id'], self.table['rows'][0]['id'], self.prose['id']):
            self.assert_rejected({'op': 'set_fields', 'id': identifier, 'fields': {'result': 'Updated'}})
        for identifier in (self.items['items'][0]['id'], self.prose['id']):
            self.assert_accepted({'op': 'set_text', 'id': identifier, 'text': 'Updated prose.'})

    def test_text_and_row_edits_cannot_cross_node_kinds(self):
        for identifier in ('B-1', 'I-1', self.behavior, 's1', self.table['rows'][0]['id']):
            self.assert_rejected({'op': 'set_text', 'id': identifier, 'text': 'Overwrite row.'})
        for identifier in ('B-1', 'I-1', self.prose['id']):
            self.assert_rejected({'op': 'set_step', 'id': identifier, 'fields': {'title': 'Wrong kind'}})

    def test_missing_ids_and_wrong_parent_anchors_are_rejected(self):
        self.assert_rejected({'op': 'set_fields', 'id': 'INV-10', 'fields': {'statement': 'Missing'}})
        self.assert_rejected({'op': 'insert_row', 'target': self.behavior, 'after': 'I-1',
                              'new': {'id': 'B-3', 'result': 'Wrong parent'}})
        self.assert_accepted({'op': 'insert_row', 'target': self.behavior, 'after': 'B-1',
                              'new': {'id': 'B-3', 'result': 'Correct parent'}})

    def test_list_fields_accept_arrays_but_scalar_fields_do_not(self):
        self.assert_accepted({'op': 'set_fields', 'id': 'B-1', 'fields': {'requirements': ['UB-1', 'UB-3']}})
        self.assert_rejected({'op': 'set_fields', 'id': 'B-1', 'fields': {'result': ['Error shown']}})
        self.assert_rejected({'op': 'set_fields', 'id': 'B-1', 'fields': {'requirements': [17]}})

    def test_scope_rejects_other_existing_targets_and_stays_compact(self):
        scope = self.root / 'scope.json'
        scope.write_text(json.dumps({'ids': ['B-1']}))
        for command in self.schemas:
            output = self.root / 'scoped.json'
            self.assertEqual(ws.main([command, str(self.plan), str(output), '--scope', str(scope)]), 0)
            schema = json.loads(output.read_text())
            conforms(self.packet(command, {'op': 'set_fields', 'id': 'B-1',
                                           'fields': {'result': 'Scoped change'}}), schema)
            for identifier in ('B-2', 'I-1', 'step-2'):
                with self.assertRaises(ValueError):
                    conforms(self.packet(command, {'op': 'delete', 'id': identifier}), schema)
            self.assertLess(len(json.dumps(schema)), 14000)
            self.assertNotIn('I-1', json.dumps(schema))

    def test_empty_scope_cannot_silently_expand_to_the_entire_plan(self):
        scope = self.root / 'empty.json'
        scope.write_text('[]')
        for command in self.schemas:
            output = self.root / 'empty-schema.json'
            self.assertEqual(ws.main([command, str(self.plan), str(output), '--scope', str(scope)]), 0)
            schema = json.loads(output.read_text())
            with self.assertRaises(ValueError):
                conforms(self.packet(command, {'op': 'delete', 'id': 'B-1'}), schema)

    def test_strict_schema_environment_override_wins_over_config(self):
        (self.root / 'config').write_text('updated-plan.strict-op-schemas 1\n')
        operation = {'op': 'set_fields', 'id': 'B-1', 'fields': {'title': 'Legacy generic fields'}}
        with patch.dict(os.environ, {'WORKFLOW_UPDATED_PLAN_STRICT_OP_SCHEMAS': '0'}):
            for command in self.schemas:
                output = self.root / 'legacy.json'
                self.assertEqual(ws.main([command, str(self.plan), str(output)]), 0)
                conforms(self.packet(command, operation), json.loads(output.read_text()))


class LensJudgmentTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        (self.root / 'slices').mkdir()
        env = {k: v for k, v in os.environ.items() if not k.startswith(('WORKFLOW_', 'UNCLE_'))}
        env['UNCLE_CONFIG'] = str(self.root / 'config')
        self.clean_env = patch.dict(os.environ, env, clear=True)
        self.clean_env.start()
        self.addCleanup(self.clean_env.stop)

    def packet(self, lens, number, findings):
        path = self.root / ('slices/%s-%d.json' % (lens, number))
        path.write_text(json.dumps({'schema': worker_packets.SCHEMA, 'kind': adversarial_slices.KIND,
                                    'findings': findings}))

    def publish(self, directory):
        project = directory / 'published'
        documents = project / '.uncle/workflow/documents'
        documents.mkdir(parents=True)
        (project / '.uncle/docs').mkdir()
        worker_packets.collate(directory, documents / 'ADVERSARIAL_REVIEW_WORKERS.json',
                               adversarial_slices.KIND, list(adversarial_slices.AREAS))
        adversarial_packets.main(project)
        return json.loads((documents / 'ADVERSARIAL_REVIEW.json').read_text())

    def test_sixteen_slices_publish_twenty_whole_lens_findings_with_original_shape(self):
        whole = self.root / 'whole'
        whole.mkdir()
        for lens_number, lens in enumerate(adversarial_slices.AREAS):
            original = []
            for number in range(1, 5):
                findings = []
                for issue in range(1, 6):
                    target = 'B-%d' % (lens_number * 5 + issue)
                    summary = ('%s validation omits boundary check for %s',
                               '%s boundary validation is missing for %s',
                               '%s lacks boundary validation for %s',
                               '%s boundary check has no validation for %s')[number - 1] % (lens, target)
                    item = {'id': 'AR-%03d' % issue, 'summary': summary,
                            'severity': 'High' if number == 1 else 'Low',
                            'evidence': target + ': boundary input is accepted without validation.'}
                    findings.append(item)
                if number == 1:
                    original = copy.deepcopy(findings)
                self.packet(lens, number, findings)
            (whole / (lens + '.json')).write_text(json.dumps({
                'schema': worker_packets.SCHEMA, 'kind': adversarial_slices.KIND, 'findings': original}))
        adversarial_slices.merge(self.root, 4)
        for lens in adversarial_slices.AREAS:
            packet = json.loads((self.root / (lens + '.json')).read_text())
            self.assertEqual(len(packet['findings']), 5, lens)
            self.assertEqual(set(packet), {'schema', 'kind', 'findings'})
            for finding in packet['findings']:
                self.assertEqual(set(finding), {'id', 'summary', 'evidence', 'severity'})
                self.assertEqual(finding['severity'], 'High')
        actual, expected = self.publish(self.root), self.publish(whole)
        self.assertEqual(len(actual['findings']), 20)
        self.assertEqual(actual, expected)

    def test_default_lens_cap_keeps_strongest_late_candidates(self):
        for lens in adversarial_slices.AREAS:
            for number in range(1, 5):
                self.packet(lens, number, [
                    {'id': 'AR-%03d' % issue, 'summary': '%s issue %d in unit %d' % (lens, issue, number),
                     'evidence': 'B-%d: independent defect' % (number * 100 + issue),
                     'severity': 'Critical' if number == 4 else 'Low'} for issue in range(1, 6)])
        adversarial_slices.merge(self.root, 4)
        for lens in adversarial_slices.AREAS:
            findings = json.loads((self.root / (lens + '.json')).read_text())['findings']
            self.assertGreaterEqual(len(findings), 6)
            self.assertLessEqual(len(findings), 8)
            self.assertEqual(sum(f['severity'] == 'Critical' for f in findings), 5)
            self.assertEqual(len({f['id'] for f in findings}), len(findings))

    def distinct_packets(self, count=4):
        for lens in adversarial_slices.AREAS:
            for number in range(1, count + 1):
                self.packet(lens, number, [
                    {'id': 'AR-%03d' % issue, 'summary': '%s input validation issue %d' % (lens, issue),
                     'evidence': 'B-%d: missing boundary check' % issue, 'severity': 'High'}
                    for issue in range(1, 10)])

    def test_cap_configuration_environment_override_and_off(self):
        self.distinct_packets()
        (self.root / 'config').write_text('adversarial-review.max-findings-per-lens 4\n')
        for override, expected in ((None, 4), ('2', 2), ('0', 9)):
            env = {} if override is None else {'WORKFLOW_ADVERSARIAL_REVIEW_MAX_FINDINGS_PER_LENS': override}
            with patch.dict(os.environ, env):
                adversarial_slices.merge(self.root, 4)
            for lens in adversarial_slices.AREAS:
                self.assertEqual(len(json.loads((self.root / (lens + '.json')).read_text())['findings']), expected)

    def test_large_granularity_preserves_uncapped_lens_results(self):
        self.distinct_packets()
        (self.root / 'config').write_text('adversarial-review.max-findings-per-lens 2\n')
        adversarial_slices.merge(self.root, 4, runner='claude')
        for lens in adversarial_slices.AREAS:
            self.assertEqual(len(json.loads((self.root / (lens + '.json')).read_text())['findings']), 9)

    def test_distinct_categories_on_the_same_target_remain_separate(self):
        for lens in adversarial_slices.AREAS:
            for number in range(1, 5):
                self.packet(lens, number, [
                    {'id': 'AR-001', 'summary': lens + ' validation omits input boundary checks',
                     'evidence': 'B-1: no validation rejects negative numbers', 'severity': 'High'},
                    {'id': 'AR-002', 'summary': lens + ' concurrent saves lose persisted updates',
                     'evidence': 'B-1: simultaneous writes overwrite stored data', 'severity': 'High'}])
        adversarial_slices.merge(self.root, 4)
        for lens in adversarial_slices.AREAS:
            findings = json.loads((self.root / (lens + '.json')).read_text())['findings']
            self.assertEqual(len(findings), 2)
            self.assertIn('validation', findings[0]['summary'])
            self.assertIn('concurrent', findings[1]['summary'])


if __name__ == '__main__':
    unittest.main()
