#!/usr/bin/env python3
"""Scoping evidence must survive real prompt construction and preserve typed edits."""
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'lib'))
import plan_model as pm
import updated_plan_ops as ops
import updated_plan_synthesis_prompt as synthesis
import worker_schemas as ws
from self_hosted_http import conforms

MODEL = {'title': 'Plan', 'intro': '', 'sections': [
    {'id': 's1', 'heading': 'Interface rendering', 'blocks': [
        {'id': 's1.1', 'kind': 'prose', 'text': 'Render the dashboard.'}]},
    {'id': 's2', 'heading': 'Timeout recovery', 'blocks': [
        {'id': 's2.1', 'kind': 'prose', 'text': 'Retry timed out requests.'}]},
    {'id': 's3', 'heading': 'Persistence', 'blocks': [
        {'id': 's3.1', 'kind': 'rows', 'row_kind': 'behavior', 'rows': [
            {'id': 'B-7', 'trigger': 'Save', 'result': 'Saved', 'failure': 'Retry', 'requirements': ['UB-7']},
            {'id': 'B-8', 'trigger': 'Cancel', 'result': 'Closed', 'failure': 'Retry', 'requirements': ['UB-8']}]}]},
    {'id': 's4', 'heading': 'Step 1: Export — Owns: `src/export.py`', 'blocks': [
        {'id': 's4.1', 'kind': 'prose', 'text': 'Write exported documents.'}]},
    {'id': 's5', 'heading': 'Deployment', 'blocks': [
        {'id': 's5.1', 'kind': 'prose', 'text': 'Publish the release.'}]},
]}


class Evidence(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        env = {k: v for k, v in os.environ.items() if not k.startswith(('UNCLE_', 'WORKFLOW_'))}
        env['UNCLE_CONFIG'] = str(self.root / 'config')
        environment = patch.dict(os.environ, env, clear=True)
        environment.start()
        self.addCleanup(environment.stop)

    def scope(self, model=None, **fields):
        model = MODEL if model is None else model
        finding = dict(id='AR-001', severity='HIGH', title='Missing contract',
                       failure='The operation has no defined contract.', fix='Specify the contract.')
        finding.update(fields)
        plan = dict(model, schema=ws.ENVELOPE, kind='plan', narrative=pm.render(model))
        review = {'schema': ws.ENVELOPE, 'kind': 'adversarial-review', 'findings': [finding]}
        base, output = self.root / 'base.md', self.root / 'writer.md'
        base.write_text(synthesis.prompt(plan, review, None))
        ops.write_prompt(base, ['AR-001'], output)
        scope = json.loads(output.with_suffix('.scope.json').read_text())
        return scope['ids'] if isinstance(scope, dict) else scope

    def test_review_location_reaches_scope_even_when_failure_has_no_ids(self):
        scope = self.scope(location={'section': 'Timeout recovery'})
        self.assertIn('s2.1', scope)
        self.assertNotIn('s5.1', scope)

    def test_nested_review_file_location_reaches_owning_step(self):
        scope = self.scope(location={'path': 'src/export.py', 'line': 10})
        self.assertIn('s4.1', scope)
        self.assertNotIn('s5.1', scope)

    def test_reference_does_not_hide_another_citation_in_failure(self):
        scope = self.scope(references='B-7', failure='src/export.py lacks the required output contract.')
        self.assertIn('B-7', scope)
        self.assertIn('s4.1', scope)
        self.assertNotIn('B-8', scope)

    def test_relative_file_location_is_not_hidden_by_an_explicit_row(self):
        scope = self.scope(references='B-7', location={'path': './src/export.py'})
        self.assertIn('B-7', scope)
        self.assertIn('s4.1', scope)
        self.assertNotIn('B-8', scope)

    def test_requirement_reference_selects_its_behavior_without_sibling_rows(self):
        scope = self.scope(references='Requirement UB-7 is not fulfilled.')
        self.assertIn('B-7', scope)
        self.assertIn('s3.1', scope)
        self.assertNotIn('B-8', scope)

    def test_heading_reference_selects_contents_without_other_sections(self):
        scope = self.scope(references='Timeout recovery needs a retry limit.')
        self.assertIn('s2.1', scope)
        self.assertNotIn('s5.1', scope)

    def test_explicit_row_can_still_insert_a_sibling_without_editing_existing_sibling(self):
        scope = self.scope(references='B-7')
        self.assertIn('B-7', scope)
        self.assertNotIn('B-8', scope)
        schema = ws.edit_ops_packet(scope, model=MODEL)
        packet = {'schema': ws.ENVELOPE, 'kind': ws.EDIT_OPS_KIND, 'dispositions': [], 'ops': [
            {'op': 'insert_row', 'target': 's3.1', 'after': 'B-7',
             'new': {'id': 'B-9', 'trigger': 'Retry', 'requirements': ['UB-7']}}]}
        conforms(packet, schema)
        pm.apply_ops(MODEL, [pm.typed_op(MODEL, packet['ops'][0])])
        packet['ops'] = [{'op': 'set_fields', 'id': 'B-8', 'fields': {'result': 'Changed'}}]
        with self.assertRaises(ValueError):
            conforms(packet, schema)

    def test_resolver_context_does_not_expand_ancestors_to_siblings(self):
        group = ops.op_group([('writer-1', {'op': 'set_fields', 'id': 'B-7', 'fields': {'result': 'Changed'}})], MODEL)
        context = json.loads(group['context'])
        self.assertIn('B-7', context)
        self.assertIn('s3.1', context)
        self.assertNotIn('B-8', context)
        self.assertNotIn('s5.1', context)

    def test_numbered_typed_step_citation_does_not_include_sibling_steps(self):
        model = {'title': 'Plan', 'intro': '', 'sections': [
            {'id': 's1', 'heading': 'Implementation order', 'blocks': [
                {'id': 's1.1', 'kind': 'steps', 'items': [
                    {'id': 'step-1', 'number': 1, 'title': 'Core', 'text': 'Create core.',
                     'owns': ['src/core.py'], 'depends_on': []},
                    {'id': 'step-2', 'number': 2, 'title': 'UI', 'text': 'Create UI.',
                     'owns': ['src/ui.py'], 'depends_on': [1]}]}]}]}
        scope = self.scope(model=model, references='Step 2 has no dependency declared.')
        self.assertIn('step-2', scope)
        self.assertIn('s1.1', scope)
        self.assertNotIn('step-1', scope)

    def test_keyword_fallback_does_not_unlock_every_section(self):
        scope = self.scope(failure='A timeout leaves pending work stuck forever; recovery must retry.')
        self.assertIn('s2.1', scope)
        self.assertLess(len({s['id'] for s in MODEL['sections']} & set(scope)), len(MODEL['sections']))


if __name__ == '__main__':
    unittest.main()
