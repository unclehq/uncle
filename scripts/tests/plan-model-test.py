#!/usr/bin/env python3
"""The structured plan model: import, render, validate, ops, conflicts (docs/plan-model.md)."""
import copy
import glob
import json
import os
import sys
import unittest
from pathlib import Path

LIB = Path(__file__).resolve().parents[1] / 'lib'
sys.path.insert(0, str(LIB))
import plan_model as pm

NARRATIVE = '''# Project plan

Intro line.

## 1. Observable behaviors

| ID | Trigger | Expected result | Failure behavior | Requirement IDs |
|---|---|---|---|---|
| B-1 | User clicks a digit | Digit appended | Display unchanged | UB-1, MC-1 |
| B-2 | User presses a key | Same as B-1 | Same as B-1 | UB-2 |

### 1.1 Notes

- A bullet
  continued here
1. A numbered item

## 2. Components

| ID | Name | File(s) | Responsibility |
|---|---|---|---|
| C-1 | App | `src/App.jsx`, `src/App.css` | Root |
| C-2 | Display | `src/Display.jsx` | Shows value |

## 3. Concurrency

| ID | Concern | Mechanism | Rationale |
|---|---|---|---|
| C-1 | Double click | Debounce | Avoid repeats |

## 4. Implementation order

1. **Scaffold** — Create package.json.
   Owns: `package.json`, `index.html`

2. **Core** — Write calc.
   Owns: `src/calc.js`
   Depends on: 1

3. **UI** — Write the UI.
   Owns: `src/App.jsx`
   Depends on: 1, 2

## 5. Other

| Layer | Runner |
|---|---|
| unit | vitest |

```
index.html
```
'''


def model():
    return pm.import_markdown(NARRATIVE)


def find(m, key):
    return pm.locate(m, key)[0]


class Import(unittest.TestCase):
    def test_a_known_table_becomes_typed_rows_with_canonical_fields(self):
        block = model()['sections'][0]['blocks'][0]
        self.assertEqual((block['kind'], block['row_kind']), ('rows', 'behavior'))
        self.assertEqual(block['rows'][0]['result'], 'Digit appended')    # "Expected result" is the field `result`
        self.assertEqual(block['rows'][0]['requirements'], ['UB-1', 'MC-1'])
        self.assertEqual(block['rows'][0]['id'], 'B-1')

    def test_file_lists_lose_their_markup(self):
        self.assertEqual(find(model(), 'C-1')['files'], ['src/App.jsx', 'src/App.css'])

    def test_an_unknown_table_stays_a_generic_table(self):
        block = model()['sections'][4]['blocks'][0]
        self.assertEqual((block['kind'], block['columns']), ('table', ['Layer', 'Runner']))

    def test_steps_carry_owns_and_dependencies_as_data(self):
        steps = model()['sections'][3]['blocks'][0]
        self.assertEqual(steps['kind'], 'steps')
        self.assertEqual([(s['number'], s['title'], s['owns'], s['depends_on']) for s in steps['items']],
                         [(1, 'Scaffold', ['package.json', 'index.html'], []),
                          (2, 'Core', ['src/calc.js'], [1]), (3, 'UI', ['src/App.jsx'], [1, 2])])
        self.assertEqual(steps['items'][0]['id'], 'step-1')

    def test_headings_lists_and_code_are_blocks(self):
        blocks = model()['sections'][0]['blocks']
        self.assertEqual([b['kind'] for b in blocks], ['rows', 'heading', 'list'])
        self.assertEqual([i.get('style') for i in blocks[2]['items']], [None, 'number'])   # a numbered item in a bullet list
        self.assertEqual(blocks[2]['items'][0]['text'], 'A bullet\ncontinued here')
        self.assertEqual(model()['sections'][4]['blocks'][-1]['kind'], 'code')

    def test_a_pipe_inside_a_code_span_does_not_split_the_cell(self):
        text = '## 1. T\n\n| ID | Test name | Assertion | Requirements |\n|---|---|---|---|\n| T-1 | a | matches `/x|y/` | R-1 |\n'
        row = pm.import_markdown(text)['sections'][0]['blocks'][0]['rows'][0]
        self.assertEqual((row['assertion'], row['requirements']), ('matches `/x|y/`', ['R-1']))

    def test_the_same_id_defined_twice_is_addressed_apart_and_still_shows_its_id(self):
        m = model()
        second = m['sections'][2]['blocks'][0]['rows'][0]
        self.assertEqual((second['id'], second['label']), ('s3.1/C-1', 'C-1'))
        self.assertIn('| C-1 | Double click |', pm.render(m))
        self.assertEqual(pm.validate(m), ([], []))


class Render(unittest.TestCase):
    def test_render_then_import_is_the_same_model(self):
        m = model()
        self.assertEqual(pm.import_markdown(pm.render(m)), m)

    def test_no_words_are_lost_or_added_by_a_round_trip(self):
        import collections
        self.assertEqual(collections.Counter(pm.words(NARRATIVE)), collections.Counter(pm.words(pm.render(model()))))

    def test_steps_render_in_the_form_the_scope_parser_reads(self):
        text = pm.render(model())
        self.assertIn('2. **Core** — Write calc.\n   Owns: `src/calc.js`\n   Depends on: 1', text)

    def test_an_empty_column_is_not_rendered_but_the_key_always_is(self):
        text = pm.render(model())
        self.assertNotIn('Violation impact', text)
        self.assertIn('| ID | Trigger | Observable result | Failure behavior | Requirement IDs |', text)

    def test_a_pipe_in_a_cell_is_escaped(self):
        m = model()
        find(m, 'B-1')['result'] = 'a | b'
        self.assertIn('a \\| b', pm.render(m))


class Validate(unittest.TestCase):
    def test_a_step_that_depends_on_a_missing_step_or_itself_is_an_error(self):
        m = model()
        find(m, 'step-2')['depends_on'] = [9]
        find(m, 'step-3')['depends_on'] = [3]
        errors, _ = pm.validate(m)
        self.assertEqual(len(errors), 2)

    def test_a_dependency_cycle_is_an_error(self):
        m = model()
        find(m, 'step-1')['depends_on'] = [3]
        self.assertTrue(any('cycle' in e for e in pm.validate(m)[0]))

    def test_a_duplicate_id_is_an_error(self):
        m = model()
        m['sections'][2]['blocks'][0]['rows'][0]['id'] = 'C-1'
        self.assertTrue(any("'C-1'" in e for e in pm.validate(m)[0]))


class Ops(unittest.TestCase):
    def test_set_fields_changes_only_the_named_fields(self):
        m = pm.apply_ops(model(), [{'op': 'set_fields', 'id': 'B-1', 'fields': {'failure': 'Shows NaN'}}])
        row = find(m, 'B-1')
        self.assertEqual((row['failure'], row['result']), ('Shows NaN', 'Digit appended'))

    def test_a_field_the_row_kind_does_not_have_is_refused(self):
        with self.assertRaisesRegex(pm.PlanError, 'no field'):
            pm.apply_ops(model(), [{'op': 'set_fields', 'id': 'B-1', 'fields': {'colour': 'red'}}])

    def test_an_id_that_does_not_exist_is_refused_by_name(self):
        with self.assertRaisesRegex(pm.PlanError, "'B-9'"):
            pm.apply_ops(model(), [{'op': 'set_fields', 'id': 'B-9', 'fields': {'result': 'x'}}])

    def test_insert_row_after_an_existing_row(self):
        block = model()['sections'][0]['blocks'][0]['id']
        row = {'id': 'B-3', 'trigger': 't', 'result': 'r', 'failure': 'f', 'requirements': ['UB-3'], 'verification': ''}
        m = pm.apply_ops(model(), [{'op': 'insert_row', 'block': block, 'after': 'B-1', 'row': row}])
        self.assertEqual([r['id'] for r in m['sections'][0]['blocks'][0]['rows']], ['B-1', 'B-3', 'B-2'])
        self.assertIn('| B-3 | t | r | f | UB-3 |', pm.render(m))

    def test_insert_row_with_an_id_in_use_is_refused(self):
        block = model()['sections'][0]['blocks'][0]['id']
        with self.assertRaisesRegex(pm.PlanError, 'already exists'):
            pm.apply_ops(model(), [{'op': 'insert_row', 'block': block, 'after': None, 'row': {'id': 'B-2'}}])

    def test_delete_removes_a_row_and_a_dangling_dependency_is_then_caught(self):
        m = pm.apply_ops(model(), [{'op': 'delete', 'id': 'B-2'}])
        self.assertEqual([r['id'] for r in m['sections'][0]['blocks'][0]['rows']], ['B-1'])
        with self.assertRaisesRegex(pm.PlanError, 'not another step'):
            pm.apply_ops(model(), [{'op': 'delete', 'id': 'step-1'}])

    def test_set_step_changes_owns_and_dependencies(self):
        m = pm.apply_ops(model(), [{'op': 'set_step', 'id': 'step-3', 'owns': ['src/App.jsx', 'src/main.jsx'], 'depends_on': [2]}])
        self.assertIn('Owns: `src/App.jsx`, `src/main.jsx`\n   Depends on: 2', pm.render(m))

    def test_replace_section_and_insert_section(self):
        blocks = [{'id': 's5.1', 'kind': 'prose', 'text': 'Rewritten.'}]
        m = pm.apply_ops(model(), [{'op': 'replace_section', 'section': 's5', 'blocks': blocks},
                                   {'op': 'insert_section', 'after': 's5', 'heading': '6. New', 'blocks': []}])
        text = pm.render(m)
        self.assertIn('## 5. Other\n\nRewritten.', text)
        self.assertTrue(text.rstrip().endswith('## 6. New'))

    def test_the_input_model_is_not_changed(self):
        m = model()
        before = copy.deepcopy(m)
        pm.apply_ops(m, [{'op': 'set_fields', 'id': 'B-1', 'fields': {'failure': 'x'}}])
        self.assertEqual(m, before)


class Conflicts(unittest.TestCase):
    def groups(self, *writers):
        return pm.conflicts(model(), list(writers))

    def set_(self, id_, **fields):
        return {'op': 'set_fields', 'id': id_, 'fields': fields}

    def test_different_fields_of_one_row_do_not_conflict(self):
        self.assertEqual(self.groups(('a', [self.set_('B-1', failure='x')]), ('b', [self.set_('B-1', result='y')])), [])

    def test_the_same_field_of_one_row_does(self):
        groups = self.groups(('a', [self.set_('B-1', failure='x')]), ('b', [self.set_('B-1', failure='y')]))
        self.assertEqual(len(groups), 1)
        self.assertEqual({w for w, _ in groups[0]}, {'a', 'b'})

    def test_identical_ops_from_two_writers_are_one_op(self):
        op = self.set_('B-1', failure='x')
        self.assertEqual(self.groups(('a', [op]), ('b', [dict(op)])), [])

    def test_delete_conflicts_with_an_edit_of_the_same_row(self):
        self.assertEqual(len(self.groups(('a', [{'op': 'delete', 'id': 'B-1'}]), ('b', [self.set_('B-1', failure='x')]))), 1)

    def test_replacing_a_section_conflicts_with_an_edit_inside_it(self):
        replace = {'op': 'replace_section', 'section': 's1', 'blocks': []}
        self.assertEqual(len(self.groups(('a', [replace]), ('b', [self.set_('B-1', failure='x')]))), 1)
        self.assertEqual(self.groups(('a', [replace]), ('b', [self.set_('C-2', responsibility='x')])), [])

    def test_one_writers_own_ops_never_conflict_with_each_other(self):
        self.assertEqual(self.groups(('a', [self.set_('B-1', failure='x'), self.set_('B-1', failure='y')])), [])


class SavedPlans(unittest.TestCase):
    """Every plan a run left on this machine imports without losing a word and re-imports to itself."""

    def test_round_trip(self):
        import collections
        paths = glob.glob(os.path.expanduser('~/src/**/.uncle/workflow/documents/*PLAN.json'), recursive=True)
        if not paths:
            self.skipTest('no saved plans on this machine')
        for path in paths:
            narrative = json.loads(Path(path).read_text(encoding='utf-8')).get('narrative') or ''
            if not narrative:
                continue
            m = pm.import_markdown(narrative)
            with self.subTest(path=path):
                self.assertEqual(collections.Counter(pm.words(narrative)), collections.Counter(pm.words(pm.render(m))))
                self.assertEqual(pm.import_markdown(pm.render(m)), m)
                self.assertEqual(pm.validate(m)[0], [])


class Authoring(unittest.TestCase):
    def test_flat_rows_become_typed_rows_with_ids_and_lists(self):
        block = pm.authored_block({'kind': 'rows', 'row_kind': 'behavior', 'rows': [
            {'id': 'B-1', 'trigger': 't', 'result': 'r', 'failure': 'f', 'requirements': 'UB-1, UB-2'}]}, 's6.1')
        self.assertEqual((block['rows'][0]['id'], block['rows'][0]['requirements']), ('B-1', ['UB-1', 'UB-2']))

    def test_flat_rows_accept_json_string_arrays_for_list_fields(self):
        block = pm.authored_block({'kind': 'rows', 'row_kind': 'behavior', 'rows': [
            {'id': 'B-1', 'trigger': 't', 'result': 'r', 'failure': 'f', 'requirements': ['UB-1', 'UB-2']}]}, 's6.1')
        self.assertEqual(block['rows'][0]['requirements'], ['UB-1', 'UB-2'])

    def test_a_kind_keyed_by_a_name_gets_a_generated_row_id(self):
        block = pm.authored_block({'kind': 'rows', 'row_kind': 'state_field', 'rows': [
            {'field': 'display', 'type': 'string', 'initial': '0', 'description': 'shown'}]}, 's2.1')
        self.assertEqual(block['rows'][0]['id'], 's2.1.r1')

    def test_an_id_keyed_row_without_an_id_is_refused(self):
        with self.assertRaisesRegex(pm.PlanError, 'needs an id'):
            pm.authored_block({'kind': 'rows', 'row_kind': 'behavior', 'rows': [{'trigger': 't'}]}, 's6.1')

    def test_an_empty_block_is_noise_and_is_dropped(self):
        section = pm.authored_section('6. Behaviors', [
            {'kind': 'rows', 'row_kind': 'behavior', 'rows': [{'id': 'B-1', 'trigger': 't'}]},
            {'kind': 'rows', 'row_kind': 'behavior', 'rows': []}, {'kind': 'prose', 'text': '  '}, {'kind': 'list', 'items': []}], 's6')
        self.assertEqual([b['kind'] for b in section['blocks']], ['rows'])

    def test_an_unknown_block_or_row_kind_is_refused_by_name(self):
        with self.assertRaisesRegex(pm.PlanError, "'chart'"):
            pm.authored_block({'kind': 'chart'}, 's1.1')
        with self.assertRaisesRegex(pm.PlanError, "'nonsense'"):
            pm.authored_block({'kind': 'rows', 'row_kind': 'nonsense', 'rows': [{'id': 'X-1'}]}, 's1.1')

    def test_steps_blocks_render_in_the_scope_parsers_form(self):
        block = pm.authored_block({'kind': 'steps', 'steps': [
            {'number': '1', 'title': 'Scaffold', 'text': 'x', 'owns': 'a.js, b.js', 'depends_on': ''},
            {'number': '2', 'title': 'Core', 'text': 'y', 'owns': 'c.js', 'depends_on': '1'}]}, 's12.1')
        self.assertIn('2. **Core** — y\n   Owns: `c.js`\n   Depends on: 1', pm.render_block(block))

    def test_a_flat_block_survives_flat_of_and_back(self):
        for block in model()['sections'][0]['blocks'][:1] + model()['sections'][3]['blocks']:     # a list mixing bullets and numbers is legacy-only
            again = pm.authored_block(pm.flat_of(block), block['id'])
            self.assertEqual(pm.render_block(again), pm.render_block(block))


class OneLineSteps(unittest.TestCase):
    def test_owns_at_the_end_of_a_step_line_makes_typed_steps(self):
        text = ('## 1. Order\n\n1. **Scaffold** — Create package.json. Owns: `package.json`, `index.html`\n'
                '2. **Core** — Write calc. Owns: `src/calc.js` Depends on: 1\n')
        steps = pm.import_markdown(text)['sections'][0]['blocks'][0]
        self.assertEqual(steps['kind'], 'steps')
        self.assertEqual([(s['owns'], s['depends_on']) for s in steps['items']],
                         [(['package.json', 'index.html'], []), (['src/calc.js'], [1])])

    def test_a_list_that_merely_mentions_owns_in_prose_is_not_steps(self):
        text = '## 1. Notes\n\n1. The module Owns: whatever it needs, and more text follows here.\n2. Another point.\n'
        self.assertEqual(pm.import_markdown(text)['sections'][0]['blocks'][0]['kind'], 'list')


class Sidecar(unittest.TestCase):
    def setUp(self):
        import tempfile
        self.tmp = tempfile.TemporaryDirectory()
        self.plan = Path(self.tmp.name) / 'PROJECT_PLAN.json'
        self.plan.write_text(json.dumps({'schema': 'uncle.artifact/v1', 'kind': 'plan', 'narrative': NARRATIVE}))
        self.model = Path(self.tmp.name) / 'model.json'

    def tearDown(self):
        self.tmp.cleanup()

    def test_an_authored_model_that_says_what_the_narrative_says_is_stored_beside_the_plan(self):
        authored = model()
        authored['sections'][0]['blocks'][0]['rows'][0]['id'] = 'B-1'
        self.model.write_text(json.dumps(authored))
        pm.attach(self.plan, self.model)
        self.assertEqual(pm.sidecar(self.plan).name, 'PROJECT_PLAN.model.json')
        self.assertEqual(pm.load_model(self.plan), pm.dedupe(authored))
        self.assertNotIn('sections', json.loads(self.plan.read_text()))        # the plan JSON agents read is unchanged

    def test_a_model_that_disagrees_with_the_narrative_is_not_stored(self):
        authored = model()
        authored['sections'][0]['blocks'][0]['rows'][0]['result'] = 'something else entirely'
        self.model.write_text(json.dumps(authored))
        with self.assertRaisesRegex(pm.PlanError, 'differs from the narrative'):
            pm.attach(self.plan, self.model)
        self.assertFalse(pm.sidecar(self.plan).exists())

    def test_the_agent_view_is_the_model_without_the_narrative(self):
        self.plan.write_text(json.dumps({'schema': 'uncle.artifact/v1', 'kind': 'plan', 'narrative': NARRATIVE,
                                         'verification_commands': 'npm test', 'protected_verification_paths': 'tests/a.js'}))
        out = Path(self.tmp.name) / 'view.json'
        pm.agent_view(self.plan, out)
        view = json.loads(out.read_text())
        self.assertEqual((view['kind'], view['verification_commands'], view['protected_verification_paths']),
                         ('plan-view', 'npm test', 'tests/a.js'))
        self.assertNotIn('narrative', view)
        self.assertNotIn('Digit appended |', out.read_text())          # no Markdown table anywhere in it
        self.assertEqual(view['sections'][0]['blocks'][0]['rows'][0]['id'], 'B-1')

    def test_a_sidecar_gone_stale_after_the_narrative_changed_is_ignored(self):
        self.model.write_text(json.dumps(model()))
        pm.attach(self.plan, self.model)
        self.plan.write_text(json.dumps({'narrative': NARRATIVE.replace('Digit appended', 'Digit shown')}))
        self.assertIn('Digit shown', pm.render(pm.load_model(self.plan)))


if __name__ == '__main__':
    unittest.main()
