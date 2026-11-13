#!/usr/bin/env python3
"""A row of a generic table (one that matches no row kind) is edited whole through `set_fields` with `cells`."""
import copy
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts' / 'lib'))
import plan_model as pm  # noqa: E402
import worker_schemas as ws  # noqa: E402

MODEL = {'title': 'T', 'intro': '', 'sections': [{'heading': '15. Risks', 'id': 's15', 'blocks': [
    {'id': 's15.1', 'kind': 'table', 'columns': ['ID', 'Risk', 'Mitigation'], 'rows': [
        {'id': 's15.1.r1', 'cells': ['R-1', 'one', 'fix one']},
        {'id': 's15.1.r2', 'cells': ['R-2', 'two', 'fix two']}]}]}]}


def edit(fields, row='s15.1.r2'):
    return pm.typed_op(MODEL, {'op': 'set_fields', 'id': row, 'fields': fields})


class TableCells(unittest.TestCase):
    def test_cells_replace_the_whole_row_and_touch_nothing_else(self):
        out = pm.apply_ops(copy.deepcopy(MODEL), [edit({'cells': ['R-2', 'two!', 'fix two!']})])
        rows = out['sections'][0]['blocks'][0]['rows']
        self.assertEqual(rows[1]['cells'], ['R-2', 'two!', 'fix two!'])
        self.assertEqual(rows[0]['cells'], ['R-1', 'one', 'fix one'])
        self.assertEqual(pm.validate(out), ([], []))

    def test_a_pipe_string_and_a_short_row_are_fitted_to_the_columns(self):
        self.assertEqual(edit({'cells': '| R-2 | a | b |'})['fields']['cells'], ['R-2', 'a', 'b'])
        self.assertEqual(edit({'cells': ['R-2', 'only']})['fields']['cells'], ['R-2', 'only', ''])

    def test_named_fields_on_a_generic_row_are_refused_with_the_way_out(self):
        for fields in ({'result': 'x'}, {'cells': ['a'], 'result': 'x'}):
            with self.assertRaisesRegex(pm.PlanError, 'only field is cells.*ID, Risk, Mitigation'):
                edit(fields)

    def test_the_strict_schema_offers_cells_for_table_rows_only(self):
        schema = ws.edit_ops_packet(['s15', 's15.1', 's15.1.r1', 's15.1.r2'], model=MODEL, generic_model=MODEL)
        variants = [v['properties'] for v in schema['properties']['ops']['items']['anyOf'] if v['properties']['op'].get('const') == 'set_fields']
        self.assertEqual([v['id']['enum'] for v in variants], [['s15.1.r1', 's15.1.r2']])
        self.assertEqual(list(variants[0]['fields']['properties']), ['cells'])

    def test_a_row_can_be_added_to_a_generic_table_after_a_named_row(self):
        op = pm.typed_op(MODEL, {'op': 'insert_row', 'target': 's15.1', 'after': 's15.1.r1', 'new': {'cells': ['R-9', 'nine', 'fix nine']}})
        out = pm.apply_ops(copy.deepcopy(MODEL), [op])
        rows = out['sections'][0]['blocks'][0]['rows']
        self.assertEqual([r['cells'][0] for r in rows], ['R-1', 'R-9', 'R-2'])
        self.assertEqual(len({r['id'] for r in rows}), 3)
        self.assertTrue(rows[1]['id'].startswith('s15.1.r'))
        self.assertEqual(pm.validate(out), ([], []))

    def test_a_new_generic_row_with_named_fields_is_refused(self):
        with self.assertRaisesRegex(pm.PlanError, 'has only cells'):
            pm.typed_op(MODEL, {'op': 'insert_row', 'target': 's15.1', 'after': '', 'new': {'risk': 'x'}})

    def test_the_strict_schema_offers_inserting_into_a_generic_table(self):
        schema = ws.edit_ops_packet(['s15', 's15.1', 's15.1.r1', 's15.1.r2'], model=MODEL, generic_model=MODEL)
        inserts = [v['properties'] for v in schema['properties']['ops']['items']['anyOf'] if v['properties']['op'].get('const') == 'insert_row']
        self.assertEqual([(v['target'].get('const') or v['target'].get('enum'), v['after']['enum']) for v in inserts],
                         [('s15.1', ['', 's15.1.r1', 's15.1.r2'])])
        self.assertEqual(list(inserts[0]['new']['properties']), ['cells'])

    def test_the_loose_schema_allows_cells_too(self):
        generic = ws._op(['s15.1.r1'])['anyOf'][0]['properties']['fields']['properties']
        self.assertEqual(generic['cells']['type'], 'array')
        new = ws._op(['s15.1.r1'])['anyOf'][0]['properties']['new']['properties']
        self.assertEqual(new['cells']['type'], 'array')


if __name__ == '__main__':
    unittest.main()
