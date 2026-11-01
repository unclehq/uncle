#!/usr/bin/env python3
"""The driver decides the operation for "add a test" / "add a defect injection" findings; the writer fills in the row's fields."""
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
import worker_schemas as ws
from self_hosted_http import conforms

NARRATIVE = '''# Project plan

## 1. Behaviors

| ID | Trigger | Observable result | Failure behavior | Requirement IDs |
|---|---|---|---|---|
| B-1 | Press 1 | Display shows 1 | none | R-1 |

## 2. Automated-test strategy

| ID | Test name | Assertion | Requirements |
|---|---|---|---|
| T-1 | digit entry | display shows 1 | R-1 |
| T-7 | operators | display shows 3 | R-1 |

| ID | Mutation | Targeted test | Expected result |
|---|---|---|---|
| DI-1 | drop digit append | tests/calc.test.js | the test fails |

## 3. Implementation order

1. **Scaffold** — Create package.json.
   Owns: `package.json`
'''


def finding(**fields):
    base = {'id': 'AR-001', 'severity': 'MEDIUM', 'title': '', 'failure': '', 'fix': 'Address in the plan.', 'references': ''}
    base.update(fields)
    return base


class Intent(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        env = {k: v for k, v in os.environ.items() if not k.startswith(('WORKFLOW_', 'UNCLE_'))}
        env['UNCLE_CONFIG'] = str(self.root / 'config')
        patcher = patch.dict(os.environ, env, clear=True)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.plan = self.root / 'plan.json'
        self.plan.write_text(json.dumps({'schema': ws.ENVELOPE, 'kind': 'plan', 'narrative': NARRATIVE}))
        self.model = pm.load_model(self.plan)

    # --- the classifier ---------------------------------------------------------------------------------------------------
    def test_a_missing_test_finding_becomes_an_insert_into_the_test_table(self):
        intent = ops.finding_intent(self.model, finding(title='No test covers Backspace in the Error state'))
        block = ops.rows_block(self.model, 'automated_test')
        self.assertEqual((intent['op'], intent['row_kind'], intent['target'], intent['label']),
                         ('insert_row', 'automated_test', block['id'], 'add_test'))
        self.assertEqual(intent['after'], 'T-7')                         # appended after the last row
        self.assertEqual(intent['new_id'], 'T-8')                        # numbered after the highest, not the count

    def test_a_defect_injection_finding_becomes_an_insert_into_the_mutation_table(self):
        intent = ops.finding_intent(self.model, finding(failure='The plan lacks a defect injection for the 12-character cap.'))
        self.assertEqual((intent['row_kind'], intent['label'], intent['new_id'], intent['after']),
                         ('mutation', 'add_defect_injection', 'DI-2', 'DI-1'))
        self.assertEqual(intent['target'], ops.rows_block(self.model, 'mutation')['id'])

    def test_a_defect_injection_wins_over_a_test_when_a_finding_says_both(self):
        intent = ops.finding_intent(self.model, finding(failure='Add a test, and add a defect injection that the test must reject.'))
        self.assertEqual(intent['row_kind'], 'mutation')

    def test_a_finding_that_says_the_plan_contradicts_itself_is_left_to_the_writer(self):
        for text in ('The tests conflict with F-1: there is no test for Error', 'T-3 contradicts the missing test T-9',
                     'Add a test: the current assertion is wrong'):
            self.assertIsNone(ops.finding_intent(self.model, finding(failure=text)), text)

    def test_a_finding_not_about_a_missing_test_is_left_to_the_writer(self):
        for text in ('Backspace semantics are unclear in the state table.', 'The component table omits C-4.',
                     'Latest results are inconsistent', ''):
            self.assertIsNone(ops.finding_intent(self.model, finding(failure=text)), text)

    def test_the_specialist_corrections_count_as_evidence(self):
        advice = [{'finding': 'AR-001', 'required_corrections': ['Add a test for the divide-by-zero recovery']}]
        self.assertIsNotNone(ops.finding_intent(self.model, finding(failure='Divide by zero recovery is unspecified'), advice))

    def test_without_the_table_there_is_nothing_to_decide(self):
        model = pm.load_model(self.plan)
        for section in model['sections']:
            section['blocks'] = [b for b in section['blocks'] if b.get('row_kind') not in ('automated_test', 'mutation')]
        self.assertIsNone(ops.finding_intent(model, finding(title='No test covers Backspace')))

    def test_a_new_id_never_collides_with_an_existing_one(self):
        intent = ops.finding_intent(self.model, finding(title='No test for Backspace'))
        self.assertNotIn(intent['new_id'], pm.index(self.model))

    # --- the schema --------------------------------------------------------------------------------------------------------
    def intent(self):
        return ops.finding_intent(self.model, finding(title='No test covers Backspace in the Error state'))

    def packet(self, intent=None):
        return ws.edit_ops_packet(None, model=self.model, intent=intent)

    def test_the_schema_allows_exactly_the_decided_insert(self):
        intent = self.intent()
        schema = self.packet(intent)['properties']['ops']
        self.assertEqual(schema['maxItems'], 1)
        good = {'op': 'insert_row', 'target': intent['target'], 'after': 'T-7',
                'new': {'id': 'T-8', 'name': 'backspace in error', 'assertion': 'display is Error', 'requirements': ['R-1']}}
        conforms([good], schema)
        conforms([], schema)                                             # rejecting or deferring the finding writes no ops
        for bad in (dict(good, after='T-1'), dict(good, new=dict(good['new'], id='T-9')), dict(good, op='set_fields'),
                    dict(good, target='s999')):
            with self.assertRaises(ValueError, msg=json.dumps(bad)[:60]):
                conforms([bad], schema)

    def test_without_an_intent_the_schema_is_unchanged(self):
        self.assertEqual(self.packet(None), self.packet())
        self.assertGreater(self.packet(None)['properties']['ops']['maxItems'], 1)

    def test_the_cli_loads_the_intent_that_sits_beside_the_scope_file(self):
        intent = self.intent()
        scope = self.root / 'w1.scope.json'
        scope.write_text(json.dumps(ws.scoped_ids(self.model, [intent['target']])))
        self.assertIsNone(ws.load_intent(str(scope)))
        scope.with_name('w1.intent.json').write_text(json.dumps(intent))
        self.assertEqual(ws.load_intent(str(scope)), intent)
        self.assertIsNone(ws.load_intent(None))
        self.assertIsNone(ws.load_intent(str(self.root / 'not-a-scope.json')))
        scope.with_name('w1.intent.json').write_text('{"op": "insert_row"}')
        self.assertIsNone(ws.load_intent(str(scope)))
        output = self.root / 'schema.json'
        scope.with_name('w1.intent.json').write_text(json.dumps(intent))
        self.assertEqual(ws.main(['edit-ops', str(self.plan), str(output), '--scope', str(scope)]), 0)
        self.assertIn('"T-8"', output.read_text())

    # --- writing the intent and enforcing it --------------------------------------------------------------------------------
    def test_a_single_deterministic_finding_gets_an_intent_file_and_the_table_in_its_scope(self):
        output = self.root / 'prompts' / 'w1.md'
        output.parent.mkdir()
        intent, scope = ops.write_intent(self.model, [finding(title='No test covers Backspace')], output, ['B-1'])
        self.assertEqual(json.loads(output.with_suffix('.intent.json').read_text()), {k: v for k, v in intent.items()})
        self.assertTrue({'B-1', intent['target'], 'T-7'} <= set(scope))

    def test_a_writer_with_two_findings_or_a_stale_file_gets_none(self):
        output = self.root / 'prompts' / 'w1.md'
        output.parent.mkdir()
        output.with_suffix('.intent.json').write_text('{"stale": true}')
        both = [finding(id='AR-1', title='No test for A'), finding(id='AR-2', title='No test for B')]
        self.assertEqual(ops.write_intent(self.model, both, output, ['B-1']), (None, ['B-1']))
        self.assertFalse(output.with_suffix('.intent.json').exists())
        none, scope = ops.write_intent(self.model, [finding(failure='unclear')], output, ['B-1'])
        self.assertIsNone(none)

    def test_a_delivered_insert_is_pinned_to_the_decided_place_and_id(self):
        intent = self.intent()
        delivery = {'dispositions': [], 'ops': [
            {'op': 'insert_row', 'target': intent['target'], 'after': 'T-1', 'new': {'id': 'T-99', 'name': 'x'}},
            {'op': 'set_fields', 'id': 'B-1', 'fields': {'failure': 'y'}}]}
        self.assertTrue(ops.pin_delivery(delivery, intent))
        self.assertEqual((delivery['ops'][0]['after'], delivery['ops'][0]['new']['id']), ('T-7', 'T-8'))
        self.assertEqual(delivery['ops'][1], {'op': 'set_fields', 'id': 'B-1', 'fields': {'failure': 'y'}})
        self.assertFalse(ops.pin_delivery(delivery, intent))             # already pinned

    def test_capture_pins_what_a_writer_delivered_using_the_intent_beside_its_prompt(self):
        intent = self.intent()
        (self.root / 'prompts').mkdir()
        (self.root / 'prompts' / 'w1.intent.json').write_text(json.dumps(intent))
        packet = self.root / 'w1.json'
        packet.write_text(json.dumps({'dispositions': [], 'ops': [
            {'op': 'insert_row', 'target': intent['target'], 'after': '', 'new': {'id': 'T-1', 'name': 'dup'}}]}))
        ops.capture_packet(packet)
        op = json.loads(packet.read_text())['ops'][0]
        self.assertEqual((op['after'], op['new']['id']), ('T-7', 'T-8'))

    def test_capture_without_an_intent_changes_nothing(self):
        packet = self.root / 'w2.json'
        body = {'dispositions': [], 'ops': [{'op': 'insert_row', 'target': 'x', 'after': '', 'new': {'id': 'T-1'}}]}
        packet.write_text(json.dumps(body))
        ops.capture_packet(packet)
        self.assertEqual(json.loads(packet.read_text()), body)


if __name__ == '__main__':
    unittest.main()
