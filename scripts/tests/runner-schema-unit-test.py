#!/usr/bin/env python3
"""Strict schema conversion preserves artifacts and rejects invalid final answers."""
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'lib'))
import runner_schema as runner
import worker_schemas


class RunnerSchema(unittest.TestCase):
    def test_every_worker_schema_can_be_constrained(self):
        for schema in (worker_schemas.section_packet(), worker_schemas.section_model_packet(),
                       worker_schemas.outline_packet(), worker_schemas.edit_packet(),
                       worker_schemas.resolution_packet(), worker_schemas.edit_ops_packet(),
                       worker_schemas.resolution_ops_packet()):
            def check(node):
                if node.get('type') == 'object':
                    self.assertFalse(node['additionalProperties'])
                    self.assertEqual(node['required'], list(node['properties']))
                self.assertNotIn('const', node)
                for child in node.get('properties', {}).values():
                    check(child)
                if 'items' in node:
                    check(node['items'])
                for child in node.get('anyOf', []):
                    check(child)
            check(runner.strict_schema(schema))

    def test_nested_optional_nulls_round_trip(self):
        schema = worker_schemas.resolution_packet()
        value = {'schema': worker_schemas.ENVELOPE, 'kind': worker_schemas.RESOLUTION_KIND,
                 'resolutions': [{'group': 'g1', 'patch': None, 'commands_replace': None}]}
        expected = dict(value, resolutions=[{'group': 'g1'}])
        self.assertEqual(runner.deliver(json.dumps(value), schema), expected)
        self.assertNotIn('anyOf', schema['properties']['resolutions']['items']['properties']['patch'])

    def test_real_nullable_field_is_preserved(self):
        schema = {'type': 'object', 'properties': {'note': {'type': ['string', 'null']}}}
        self.assertEqual(runner.deliver('{"note": null}', schema), {'note': None})

    def test_anyof_optional_mapping_selects_matching_branch(self):
        schema = {'type': 'object', 'properties': {'item': {'anyOf': [
            {'type': 'object', 'properties': {'name': {'type': 'string'}}}, {'type': 'string'}]}}, 'required': ['item']}
        self.assertEqual(runner.deliver('{"item":{"name":null}}', schema), {'item': {}})
        self.assertEqual(runner.deliver('{"item":"name"}', schema), {'item': 'name'})

    def test_source_constraints_still_apply(self):
        schema = {'type': 'object', 'properties': {
            'rows': {'type': 'array', 'minItems': 1, 'items': {'type': 'string', 'maxLength': 3}}}, 'required': ['rows']}
        for value in ({'rows': []}, {'rows': ['long']}, {'rows': [1]}, {}, {'rows': None}, {'rows': ['ok'], 'extra': True}):
            with self.subTest(value=value), self.assertRaises(ValueError):
                runner.deliver(json.dumps(value), schema)

    def test_required_null_is_rejected_and_nullable_required_null_is_preserved(self):
        schema = {'type': 'object', 'properties': {'value': {'type': 'string'}}, 'required': ['value']}
        with self.assertRaises(ValueError):
            runner.deliver('{"value": null}', schema)
        schema['properties']['value']['type'] = ['string', 'null']
        self.assertEqual(runner.deliver('{"value": null}', schema), {'value': None})

    def test_unsupported_schema_falls_back(self):
        for extra in ({'patternProperties': {}}, {'$ref': '#'}, {'additionalProperties': True}):
            with self.subTest(extra=extra), self.assertRaises(ValueError):
                runner.strict_schema(dict({'type': 'object'}, **extra))

    def test_invalid_output_never_overwrites_delivery(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / 'answer.json'
            target.write_text('original')
            for text in ('{} {}', '{', '{"v":NaN}', '{"v":true}'):
                schema = {'type': 'object', 'properties': {'v': {'type': 'integer'}}, 'required': ['v']}
                with self.assertRaises(ValueError):
                    runner.deliver(text, schema, target)
                self.assertEqual(target.read_text(), 'original')

    def test_stage_parent_global_precedence(self):
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, {}, clear=True):
            config = Path(tmp) / 'config'
            config.write_text('project-plan.schema-enforce off\nrunner.schema-enforce on\n')
            os.environ['UNCLE_CONFIG'] = str(config)
            self.assertFalse(runner.enabled('requirements'))
            os.environ['WORKFLOW_RUNNER_SCHEMA_ENFORCE'] = '1'
            self.assertTrue(runner.enabled('requirements'))
            os.environ['WORKFLOW_RUNNER_SCHEMA_ENFORCE_PROJECT_PLAN'] = 'off'
            self.assertFalse(runner.enabled('requirements'))
            os.environ['WORKFLOW_RUNNER_SCHEMA_ENFORCE_REQUIREMENTS'] = 'on'
            self.assertTrue(runner.enabled('requirements'))


if __name__ == '__main__':
    unittest.main()
