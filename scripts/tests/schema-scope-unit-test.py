#!/usr/bin/env python3
"""Scope controls, fallback diagnostics, and inline grammar equivalence."""
import contextlib
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'lib'))
import plan_model as pm
import runner_schema
import updated_plan_ops as ops
import worker_schemas as ws
from self_hosted_http import conforms

MODEL = {'title': 'Plan', 'intro': '', 'sections': [
    {'id': 's1', 'heading': '1. Storage recovery', 'blocks': [
        {'id': 's1.1', 'kind': 'prose', 'text': 'Retry failed storage operations.'}]},
    {'id': 's2', 'heading': '2. Request recovery', 'blocks': [
        {'id': 's2.1', 'kind': 'prose', 'text': 'Retry failed requests.'}]},
    {'id': 's3', 'heading': '3. Rendering', 'blocks': [
        {'id': 's3.1', 'kind': 'prose', 'text': 'Render the dashboard.'}]},
]}


class ScopeControls(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.config = Path(self.tmp.name) / 'config'
        env = {key: value for key, value in os.environ.items() if not key.startswith(('UNCLE_', 'WORKFLOW_'))}
        env['UNCLE_CONFIG'] = str(self.config)
        clean = patch.dict(os.environ, env, clear=True)
        clean.start()
        self.addCleanup(clean.stop)

    def test_keyword_fallback_is_bounded_and_keeps_the_best_section(self):
        self.config.write_text('updated-plan.scope-sections 1\n')
        self.assertEqual(ops.finding_scope(MODEL, [{'failure': 'Storage retry failed'}]), ['s1', 's1.1'])

    def test_each_finding_gets_a_scope_even_when_another_finding_names_an_id(self):
        self.config.write_text('updated-plan.scope-sections 1\n')
        scope = ops.finding_scope(MODEL, [{'location': 's1.1'}, {'failure': 'Rendering dashboard is missing.'}])
        self.assertEqual(scope, ['s1', 's1.1', 's3', 's3.1'])

    def test_stage_environment_overrides_family_environment_and_config(self):
        self.config.write_text('updated-change-plan.scope-sections 3\nupdated-plan.scope-sections 3\n')
        with patch.dict(os.environ, {'UNCLE_PLAN_KIND': 'change-plan',
                                   'WORKFLOW_UPDATED_PLAN_SCOPE_SECTIONS': '2',
                                   'WORKFLOW_UPDATED_CHANGE_PLAN_SCOPE_SECTIONS': '1'}):
            self.assertEqual(ops.finding_scope(MODEL, [{'failure': 'Storage retry failed'}]), ['s1', 's1.1'])

    def test_invalid_limit_is_rejected(self):
        with patch.dict(os.environ, {'WORKFLOW_UPDATED_PLAN_SCOPE_SECTIONS': '0'}):
            with self.assertRaisesRegex(ops.Conflict, 'must be positive'):
                ops.finding_scope(MODEL, [])

    def test_whole_plan_fallback_has_exactly_one_diagnostic(self):
        output = io.StringIO()
        with contextlib.redirect_stderr(output):
            scope = ops.finding_scope(MODEL, [{'failure': 'Quux xyzzy'}])
        self.assertEqual(set(scope), set(pm.index(MODEL)))
        self.assertEqual(len(output.getvalue().splitlines()), 1)
        self.assertIn('whole-plan scope', output.getvalue())

    def test_legacy_scope_switch_preserves_the_full_id_set(self):
        with patch.dict(os.environ, {'WORKFLOW_UPDATED_PLAN_FINDING_SCOPES': '0'}):
            self.assertEqual(set(ops.finding_scope(MODEL, [{'location': 's1.1'}])), set(pm.index(MODEL)))

    def test_numeric_section_citation_preserves_contents(self):
        self.assertEqual(ops.finding_scope(MODEL, [{'location': 'section 2'}]), ['s2', 's2.1'])

    def test_extensionless_file_location_finds_its_declared_owner(self):
        model = {'sections': [
            {'id': 's1', 'heading': 'Step 1: Container — Owns: `Dockerfile`, `.gitignore`', 'blocks': [
                {'id': 's1.1', 'kind': 'prose', 'text': 'Configure the image.'}]},
            MODEL['sections'][1]]}
        for path in ('Dockerfile', '.gitignore'):
            self.assertEqual(ops.finding_scope(model, [{'location': {'path': path}}]), ['s1', 's1.1'])

    def test_step_heading_includes_its_whole_body_but_not_closing_sections(self):
        model = {'sections': [{'id': 's1', 'heading': 'Step 1: Storage', 'blocks': [
            {'id': 's1.1', 'kind': 'prose', 'text': 'Create storage.'},
            {'id': 's1.2', 'kind': 'code', 'text': 'save()', 'lang': 'python'},
            {'id': 's1.3', 'kind': 'prose', 'text': '# Non-goals'},
            {'id': 's1.4', 'kind': 'prose', 'text': 'Remote storage.'}]}]}
        self.assertEqual(ops.finding_scope(model, [{'failure': 'Step 1 needs a retry.'}]), ['s1', 's1.1', 's1.2'])

    def test_unplaceable_resolver_uses_evidence_without_unlocking_every_section(self):
        group = ops.op_group([('writer', {'op': 'invalid', 'why': 'missing id',
                                        'flat': {'op': 'set_text', 'id': 'missing',
                                                 'text': 'Storage recovery retries'}})], MODEL)
        context = json.loads(group['context'])
        self.assertIn('s1.1', context)
        self.assertNotIn('s3.1', context)

    def test_minimal_schema_preserves_validation_and_codex_strict_conversion(self):
        schema = ws.model_op(MODEL, ['s1', 's1.1'])
        compact = ws._minimal(schema)
        self.assertLess(len(json.dumps(compact)), len(json.dumps(schema)))
        for operation in (
            {'op': 'set_text', 'id': 's1.1', 'text': ''},
            {'op': 'insert_block', 'target': 's1', 'block': {'kind': 'prose', 'text': ''}},
            {'op': 'delete', 'id': 's3.1'},
            {'op': 'set_text', 'id': 1, 'text': 'bad'},
            {'op': 'insert_block', 'target': 's1', 'block': {'kind': 'prose', 'lang': 'bad', 'text': ''}},
        ):
            outcomes = []
            for form in (schema, compact):
                try:
                    conforms(operation, form)
                    outcomes.append(True)
                except ValueError:
                    outcomes.append(False)
            self.assertEqual(outcomes[0], outcomes[1], operation)
        packet = ws.edit_ops_packet(['s1', 's1.1'], model=MODEL)
        self.assertEqual(runner_schema.strict_schema(packet)['type'], 'object')
        self.assertNotIn('$ref', json.dumps(packet))


if __name__ == '__main__':
    unittest.main()
