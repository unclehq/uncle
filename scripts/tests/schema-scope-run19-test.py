#!/usr/bin/env python3
"""Run 19: small writer grammars must still permit the corrections the findings need."""
import json
import os
from pathlib import Path
import statistics
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

FIXTURE = Path(__file__).with_name('fixtures') / 'run19-schema-scope.json'
# Existing editable prose or insertion containers, chosen from the finding evidence.
NEEDED = {
    1: ['MC-1', 'MC-10'], 2: ['s4.1'], 3: ['s4.1'], 4: ['MC-9'],
    5: ['MC-5', 'MC-6', 's4.1'], 6: ['s1'], 7: ['s3.1', 's4.1'],
    8: ['s3.1', 's4.1', 's5.1'], 9: ['s4.1'], 10: ['s2.2', 's3.1'],
    11: ['s3.1', 's4.1', 's5.1'], 12: ['s3.1', 's4.1', 's5.1'],
    13: ['s5.1'], 14: ['MC-1', 'MC-8', 's5.1'], 15: ['s5.1'],
    16: ['s5.1'], 17: ['s5.1'], 18: ['s5.1'], 19: ['MC-1', 's3.1'],
    20: ['s1', 's3.1'], 21: ['MC-1', 'MC-10', 's3.1'],
    22: ['s2.2'], 23: ['s3.1'], 24: ['s3.1'],
}


def generate(root, fixture):
    model = fixture['model']
    plan = root / 'plan.json'
    plan.write_text(json.dumps(dict(model, schema=ws.ENVELOPE, kind='plan')))
    base = root / 'base.md'
    findings = [f for row in fixture['writers'] for f in row['findings']]
    base.write_text(ops.EDIT_RULES + '\n## Base project plan JSON\n```json\n' + plan.read_text() +
                    '\n```\n## Adversarial review findings\n```json\n' +
                    json.dumps({'findings': findings}) + '\n```\n')
    result = []
    for row in fixture['writers']:
        output = root / ('%s.md' % row['writer'])
        ops.write_prompt(base, [f['id'] for f in row['findings']], output, owns_fields=row['writer'] == 1)
        scope_file = output.with_suffix('.scope.json')
        scope = json.loads(scope_file.read_text())
        if isinstance(scope, dict):
            scope = scope['ids']
        schema_file = root / ('%s.schema.json' % row['writer'])
        args = ['edit-ops', str(plan), str(schema_file)] + (['owner'] if row['writer'] == 1 else [])
        status = ws.main(args + ['--scope', str(scope_file)])
        if status:
            raise AssertionError('schema generation failed: %s' % row['writer'])
        schema = json.loads(schema_file.read_text())
        result.append(dict(row, scope=scope, schema=schema, after_bytes=schema_file.stat().st_size))
    return result


class Run19(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fixture = json.loads(FIXTURE.read_text())
        cls.tmp = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.tmp.cleanup)
        env = {k: v for k, v in os.environ.items() if not k.startswith(('UNCLE_', 'WORKFLOW_'))}
        env['UNCLE_CONFIG'] = str(Path(cls.tmp.name) / 'no-config')
        cls.environment = patch.dict(os.environ, env, clear=True)
        cls.environment.start()
        cls.addClassCleanup(cls.environment.stop)
        cls.rows = generate(Path(cls.tmp.name), cls.fixture)

    def test_fixture_preserves_all_24_original_writers(self):
        self.assertEqual([r['writer'] for r in self.rows], list(range(1, 25)))
        self.assertEqual(sum(r['before_bytes'] == 38117 for r in self.rows), 16)
        self.assertEqual(len({f['id'] for r in self.rows for f in r['findings']}), 24)

    def test_each_writer_schema_is_at_most_15kb(self):
        for row in self.rows:
            with self.subTest(writer=row['writer']):
                self.assertLessEqual(row['after_bytes'], 15000)

    def test_typical_writer_schema_is_at_most_6kb(self):
        self.assertLessEqual(statistics.median(r['after_bytes'] for r in self.rows), 6000)

    def test_no_writer_silently_receives_the_whole_plan(self):
        all_ids = set(pm.index(self.fixture['model']))
        for row in self.rows:
            with self.subTest(writer=row['writer']):
                self.assertTrue(set(row['scope']) < all_ids)

    def test_needed_corrections_remain_expressible(self):
        model = self.fixture['model']
        index = pm.index(model)
        for row in self.rows:
            for target in NEEDED[row['writer']]:
                with self.subTest(writer=row['writer'], target=target):
                    self.assertIn(target, row['scope'])
                    node = index[target][0]
                    if 'blocks' in node:
                        operation = {'op': 'insert_block', 'target': target,
                                     'block': {'kind': 'prose', 'text': 'Required correction.'}}
                    elif target.startswith('MC-'):
                        operation = {'op': 'set_fields', 'id': target, 'fields': {'tests': ['specific regression']}}
                    else:
                        operation = {'op': 'set_text', 'id': target, 'text': 'Required correction.'}
                    packet = {'schema': ws.ENVELOPE, 'kind': ws.EDIT_OPS_KIND,
                              'dispositions': [], 'ops': [operation]}
                    if row['writer'] == 1:
                        packet['protected_verification_paths'] = 'tests/'
                    conforms(packet, row['schema'])
                    pm.apply_ops(model, [pm.typed_op(model, operation)])

    def test_strict_schema_still_rejects_wrong_fields_and_unknown_ids(self):
        for row in self.rows:
            for operation in ({'op': 'set_text', 'id': 'does-not-exist', 'text': 'x'},
                              {'op': 'set_fields', 'id': 'MC-1', 'fields': {'invented': 'x'}}):
                with self.subTest(writer=row['writer'], operation=operation):
                    packet = {'schema': ws.ENVELOPE, 'kind': ws.EDIT_OPS_KIND,
                              'dispositions': [], 'ops': [operation]}
                    if row['writer'] == 1:
                        packet['protected_verification_paths'] = 'tests/'
                    with self.assertRaises(ValueError):
                        conforms(packet, row['schema'])


if __name__ == '__main__':
    unittest.main()
