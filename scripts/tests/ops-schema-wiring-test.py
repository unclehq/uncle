#!/usr/bin/env python3
"""A scoped grammar reaches the self-hosted request without using a model."""
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

LIB = Path(__file__).resolve().parents[1] / 'lib'
sys.path.insert(0, str(LIB))
import self_hosted
import worker_schemas as ws
from self_hosted_http import conforms


class Wiring(unittest.TestCase):
    def test_http_setup_uses_the_exact_scoped_schema(self):
        model = {'sections': [{'id': 's1', 'heading': 'Notes', 'blocks': [
            {'id': 's1.1', 'kind': 'prose', 'text': 'Current text'}]}]}
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            schema = ws.edit_ops_packet(['s1.1'], model=model)
            source = root / 'schema.json'
            source.write_text(json.dumps(schema))
            for variable in ('UNCLE_OUTPUT_SCHEMA_FILE', 'UNCLE_WORKER_SCHEMA_FILE'):
                with self.subTest(variable=variable), patch.dict(os.environ, {variable: str(source),
                        'UNCLE_CONFIG': str(root / 'config')}, clear=True):
                    result = self_hosted._http_setup('agent', {}, 'Edit the supplied text.', root, False, ws.EDIT_OPS_KIND)
                    self.assertEqual(result[2], schema)
                    with self.assertRaisesRegex(ValueError, 'packet kind'):
                        self_hosted._http_setup('agent', {}, 'Resolve.', root, False, ws.RESOLUTION_OPS_KIND)

    def test_empty_and_unknown_scopes_have_a_valid_empty_ops_array(self):
        model = {'sections': [{'id': 's1', 'heading': 'Notes', 'blocks': []}]}
        for ids in ([], ['missing']):
            schema = ws.edit_ops_packet(ids, model=model)
            self.assertEqual(schema['properties']['ops']['maxItems'], 0)
            packet = {'schema': ws.ENVELOPE, 'kind': ws.EDIT_OPS_KIND, 'dispositions': [], 'ops': []}
            conforms(packet, schema)
            with self.assertRaises(ValueError):
                conforms(dict(packet, ops=[{'op': 'delete', 'id': 'missing'}]), schema)
            self.assertNotIn('"enum": []', json.dumps(schema))

    def test_scope_adds_containers_without_other_rows(self):
        model = {'sections': [{'id': 's1', 'heading': 'Behaviors', 'blocks': [
            {'id': 's1.1', 'kind': 'rows', 'row_kind': 'behavior', 'rows': [
                {'id': 'B-1'}, {'id': 'B-2'}]}]}]}
        self.assertEqual(ws.scoped_ids(model, ['B-1']), ['B-1', 's1', 's1.1'])
        self.assertEqual(ws.scoped_ids(model, ['s1.1']), ['B-1', 'B-2', 's1', 's1.1'])


if __name__ == '__main__':
    unittest.main()
