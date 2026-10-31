#!/usr/bin/env python3
"""Updated-plan fan-out on the plan model: writers answer with ops that name ids (updated_plan_ops.py)."""
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

LIB = Path(__file__).resolve().parents[1] / 'lib'
sys.path.insert(0, str(LIB))
import plan_model as pm
import updated_plan_ops as ops
import updated_plan_synthesis_prompt as PROMPT
import worker_schemas as WS
from plan_patch import apply_patch

NARRATIVE = '''# Project plan

## 1. Observable behaviors

| ID | Trigger | Observable result | Failure behavior | Requirement IDs |
|---|---|---|---|---|
| B-1 | User clicks a digit | Digit appended | Display unchanged | UB-1 |
| B-2 | User presses a key | Same as B-1 | Same as B-1 | UB-2 |

## 2. Implementation order

1. **Scaffold** — Create package.json.
   Owns: `package.json`

2. **Core** — Write calc.
   Owns: `src/calc.js`
   Depends on: 1

## 3. Notes

Untouched prose, kept byte for byte.
'''
COMMANDS = 'npm test\nnpx vitest run'
PLAN = {'schema': 'uncle.artifact/v1', 'kind': 'plan', 'narrative': NARRATIVE, 'verification_commands': COMMANDS,
        'protected_verification_paths': 'tests/a.test.js'}


def row(finding):
    return {'finding': finding, 'disposition': 'Accepted', 'reason': 'r', 'plan_change': 'c'}


def set_fields(id_, **fields):
    return {'op': 'set_fields', 'id': id_, 'fields': fields}


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        (self.dir / 'plan.json').write_text(json.dumps(PLAN))
        (self.dir / 'slices.tsv').write_text('1\tAR-1\n2\tAR-2\n')

    def tearDown(self):
        self.tmp.cleanup()

    def deliver(self, name, finding, *operations, **extra):
        packet = {'dispositions': [row(finding)], 'ops': list(operations)}
        packet.update(extra)
        (self.dir / ('%s.json' % name)).write_text(json.dumps(packet))

    def merge(self, resolutions=None):
        args = [self.dir / 'plan.json', self.dir / 'slices.tsv', self.dir, self.dir / 'out.json']
        ops.merge(*args, *([resolutions] if resolutions else []))
        return json.loads((self.dir / 'out.json').read_text())

    def narrative_after(self, result):
        return apply_patch(NARRATIVE, result['patch'])


class Merge(Base):
    def test_edits_to_different_rows_merge_into_a_section_patch(self):
        self.deliver('1', 'AR-1', set_fields('B-1', failure='Shows NaN'))
        self.deliver('2', 'AR-2', set_fields('B-2', result='Digit replaced'))
        result = self.merge()
        text = self.narrative_after(result)
        self.assertIn('| B-1 | User clicks a digit | Digit appended | Shows NaN | UB-1 |', text)
        self.assertIn('| B-2 | User presses a key | Digit replaced | Same as B-1 | UB-2 |', text)
        self.assertEqual([e['heading'] for e in result['patch']['edit_sections']], ['## 1. Observable behaviors'])
        self.assertIn('Untouched prose, kept byte for byte.', text)

    def test_different_fields_of_one_row_do_not_need_a_resolver(self):
        self.deliver('1', 'AR-1', set_fields('B-1', failure='Shows NaN'))
        self.deliver('2', 'AR-2', set_fields('B-1', result='Digit replaced'))
        text = self.narrative_after(self.merge())
        self.assertIn('| B-1 | User clicks a digit | Digit replaced | Shows NaN | UB-1 |', text)

    def test_a_list_field_is_written_as_a_string_and_stored_as_a_list(self):
        self.deliver('1', 'AR-1', set_fields('B-1', requirements='UB-1, MC-1'))
        self.deliver('2', 'AR-2')
        self.assertIn('| UB-1, MC-1 |', self.narrative_after(self.merge()))

    def test_insert_row_delete_and_step_edits(self):
        block = pm.import_markdown(NARRATIVE)['sections'][0]['blocks'][0]['id']
        self.deliver('1', 'AR-1', {'op': 'insert_row', 'target': block, 'after': 'B-1',
                                   'new': {'id': 'B-3', 'trigger': 't', 'result': 'r', 'failure': 'f', 'requirements': 'UB-3'}},
                     {'op': 'delete', 'id': 'B-2'})
        self.deliver('2', 'AR-2', {'op': 'set_step', 'id': 'step-2', 'fields': {'owns': 'src/calc.js, src/util.js', 'depends_on': '1'}})
        text = self.narrative_after(self.merge())
        self.assertIn('| B-3 | t | r | f | UB-3 |', text)
        self.assertNotIn('B-2', text)
        self.assertIn('Owns: `src/calc.js`, `src/util.js`', text)

    def test_the_same_edit_from_two_writers_is_one_edit(self):
        edit = set_fields('B-1', failure='Shows NaN')
        self.deliver('1', 'AR-1', edit)
        self.deliver('2', 'AR-2', dict(edit))
        self.assertIn('Shows NaN', self.narrative_after(self.merge()))

    def test_a_writer_that_wrote_a_text_patch_is_refused(self):
        self.deliver('1', 'AR-1', patch={'replace_text': [{'heading': '## 1.', 'old': 'a', 'new': 'b'}]})
        self.deliver('2', 'AR-2')
        with self.assertRaisesRegex(ops.Conflict, 'text patch'):
            self.merge()

    def test_a_missing_disposition_is_refused(self):
        (self.dir / '1.json').write_text(json.dumps({'dispositions': [], 'ops': []}))
        self.deliver('2', 'AR-2')
        with self.assertRaisesRegex(ops.Conflict, 'without a disposition'):
            self.merge()

    def test_command_edits_still_merge_and_the_owner_supplies_protected_paths(self):
        self.deliver('1', 'AR-1', commands_replace=[{'old': 'npm test', 'new': 'npm run test'}])
        self.deliver('2', 'AR-2')
        result = self.merge()
        self.assertEqual(result['verification_commands'], 'npm run test\nnpx vitest run')
        self.assertEqual(result['protected_verification_paths'], 'tests/a.test.js')


class DerivedPaths(Base):
    """calculator-local: the base plan named no protected paths and no writer did, the whole ops result was thrown away and the
    one-call fallback failed on a text patch.  The plan's own test files and configs are the protected paths."""
    def plan_without_paths(self, narrative_extra=''):
        plan = dict(PLAN, narrative=NARRATIVE + narrative_extra)
        plan['protected_verification_paths'] = ''
        (self.dir / 'plan.json').write_text(json.dumps(plan))

    def test_they_are_derived_from_the_plans_test_files_and_runner_configs(self):
        self.plan_without_paths('\nTests: `tests/calc.test.js`, `tests/e2e/ui.spec.js`, vitest.config.js, package-lock.json, dist/app.test.js\n')
        self.deliver('1', 'AR-1')
        self.deliver('2', 'AR-2')
        result = self.merge()
        self.assertEqual(result['protected_verification_paths'].splitlines(),
                         ['tests/calc.test.js', 'tests/e2e/ui.spec.js', 'vitest.config.js'])

    def test_a_plan_that_names_no_test_file_is_still_refused(self):
        self.plan_without_paths()
        self.deliver('1', 'AR-1')
        self.deliver('2', 'AR-2')
        with self.assertRaisesRegex(ops.Conflict, 'names no test files'):
            self.merge()

    def test_the_derivation_leaves_out_outputs_lockfiles_and_hidden_paths(self):
        found = ops.derive_protected_paths('see `.test-out/a.spec.js`, ../x.test.js, node_modules/y.test.js, tests/ok.test.js, package.json')
        self.assertEqual(found, 'tests/ok.test.js')

    def test_driver_contract_derives_paths_from_the_merged_model_not_stale_base_text(self):
        self.plan_without_paths('\nTests: `tests/old.spec.js`\n')
        self.deliver('1', 'AR-1',
                     {'op': 'set_text', 'id': 's3.1',
                      'text': 'Tests: `tests/e2e/current.spec.js`'},
                     {'op': 'set_step', 'id': 'step-2',
                      'fields': {'owns': 'src/calc.js, tests/e2e/current.spec.js'}})
        self.deliver('2', 'AR-2')
        result = self.merge()
        self.assertEqual(result['protected_verification_paths'], 'tests/e2e/current.spec.js')


class Resolve(Base):
    def conflict(self):
        self.deliver('1', 'AR-1', set_fields('B-1', failure='first'))
        self.deliver('2', 'AR-2', set_fields('B-1', failure='second'))
        with self.assertRaises(ops.NeedsResolution) as caught:
            self.merge()
        return caught.exception.groups

    def answer(self, *operations, group='G1'):
        (self.dir / ('resolutions-%s.json' % group)).write_text(json.dumps(
            {'resolutions': [{'group': group, 'ops': list(operations)}]}))

    def test_the_same_field_changed_twice_goes_to_a_resolver_that_sees_the_current_row(self):
        groups = self.conflict()
        self.assertEqual((groups[0]['kind'], len(groups[0]['edits'])), ('ops', 2))
        prompt = (self.dir / 'prompts' / 'resolve-G1.md').read_text()
        self.assertIn('"failure": "Display unchanged"', prompt)       # the row as it is now
        self.assertIn('updated-plan-resolution-ops-packet', prompt)

    def test_a_resolution_replaces_the_group_and_the_rest_merges(self):
        self.conflict()
        self.answer(set_fields('B-1', failure='resolved'))
        self.assertIn('resolved', self.narrative_after(self.merge(self.dir)))

    def test_a_resolver_answer_naming_a_missing_id_is_caught_with_a_reason_and_asked_again(self):
        self.conflict()
        self.answer(set_fields('B-9', failure='x'))
        bad = ops.check_resolutions(self.dir / 'plan.json', self.dir)
        self.assertEqual(list(bad), ['G1'])
        self.assertIn("'B-9'", bad['G1'])
        self.assertIn('previous answer was rejected', (self.dir / 'prompts' / 'resolve-G1.retry.md').read_text())

    def test_a_good_resolver_answer_passes_the_check(self):
        self.conflict()
        self.answer(set_fields('B-1', failure='ok'))
        self.assertEqual(ops.check_resolutions(self.dir / 'plan.json', self.dir), {})

    def test_after_the_retry_an_unusable_answer_is_left_out_and_recorded(self):
        self.conflict()
        self.answer(set_fields('B-1', failure='kept'), set_fields('B-9', failure='x'))
        result = self.merge(self.dir)
        self.assertIn('kept', self.narrative_after(result))
        self.assertTrue([d for d in result['dispositions'] if 'could not be placed' in d['reason']])

    def test_a_dropped_edit_marks_only_the_findings_of_the_writers_who_wrote_it(self):
        (self.dir / 'slices.tsv').write_text('1\tAR-1\n2\tAR-2\n3\tAR-3\n')
        self.deliver('3', 'AR-3', set_fields('B-2', result='unrelated'))
        self.conflict()
        self.answer(set_fields('B-1', failure='kept'), set_fields('B-9', failure='x'))
        result = self.merge(self.dir)
        noted = {d['finding'] for d in result['dispositions'] if 'could not be placed' in d['reason']}
        self.assertEqual(noted, {'AR-1', 'AR-2'})

    def test_a_resolver_repeating_an_insert_another_writer_made_loses_nothing_and_marks_nothing(self):
        block = pm.import_markdown(NARRATIVE)['sections'][0]['blocks'][0]['id']
        insert = {'op': 'insert_row', 'target': block, 'after': 'B-1',
                  'new': {'id': 'B-3', 'trigger': 't', 'result': 'r', 'failure': 'f', 'requirements': 'UB-3'}}
        self.deliver('1', 'AR-1', set_fields('B-2', failure='a'), insert)
        self.deliver('2', 'AR-2', set_fields('B-2', failure='b'))
        with self.assertRaises(ops.NeedsResolution):
            self.merge()
        self.answer(set_fields('B-2', failure='c'), insert)
        result = self.merge(self.dir)
        text = self.narrative_after(result)
        self.assertEqual(text.count('| B-3 |'), 1)
        self.assertIn('| B-2 | User presses a key | Same as B-1 | c | UB-2 |', text)
        self.assertFalse([d for d in result['dispositions'] if 'could not be placed' in d['reason']])

    def test_an_edit_naming_an_id_that_does_not_exist_goes_to_a_resolver(self):
        self.deliver('1', 'AR-1', set_fields('B-9', failure='x'))
        self.deliver('2', 'AR-2')
        with self.assertRaises(ops.NeedsResolution) as caught:
            self.merge()
        edit = caught.exception.groups[0]['edits'][0]
        self.assertIn("'B-9'", edit['problem'])

    def test_a_field_the_row_does_not_have_goes_to_a_resolver(self):
        self.deliver('1', 'AR-1', set_fields('B-1', colour='red'))
        self.deliver('2', 'AR-2')
        with self.assertRaises(ops.NeedsResolution) as caught:
            self.merge()
        self.assertIn('has no field', caught.exception.groups[0]['edits'][0]['problem'])

    def test_two_writers_changing_a_command_the_same_way_differently_go_to_a_command_group(self):
        self.deliver('1', 'AR-1', commands_replace=[{'old': 'npm test', 'new': 'npm run a'}])
        self.deliver('2', 'AR-2', commands_replace=[{'old': 'npm test', 'new': 'npm run b'}])
        with self.assertRaises(ops.NeedsResolution) as caught:
            self.merge()
        self.assertEqual(caught.exception.groups[0]['kind'], 'command')
        self.assertIn('npm test', (self.dir / 'prompts' / 'resolve-G1.md').read_text())

    def test_the_cli_exits_3_for_overlap_5_for_a_bad_answer_and_0_when_merged(self):
        self.conflict()
        cli = [sys.executable, str(LIB / 'updated_plan_ops.py')]
        merge = cli + ['merge', str(self.dir / 'plan.json'), str(self.dir / 'slices.tsv'), str(self.dir), str(self.dir / 'o.json')]
        self.assertEqual(subprocess.run(merge, capture_output=True).returncode, 3)
        self.answer(set_fields('B-9', failure='x'))
        check = subprocess.run(cli + ['check', str(self.dir / 'plan.json'), str(self.dir)], capture_output=True, text=True)
        self.assertEqual((check.returncode, check.stdout.split()), (5, ['G1']))
        self.answer(set_fields('B-1', failure='ok'))
        self.assertEqual(subprocess.run(merge + [str(self.dir)], capture_output=True).returncode, 0)


class Prompt(unittest.TestCase):
    def sealed(self):
        review = {'schema': 'uncle.artifact/v1', 'kind': 'adversarial-review', 'findings': [
            {'id': 'AR-1', 'severity': 'high', 'title': 't', 'failure': 'f', 'fix': 'x'}]}
        workers = {'schema': 'uncle.artifact/v1', 'kind': 'updated-plan-worker-packets', 'workers': [], 'findings': []}
        return PROMPT.prompt(PLAN, review, workers)

    def test_the_writer_prompt_carries_the_model_and_ops_not_the_text_patch(self):
        with tempfile.TemporaryDirectory() as tmp:
            base, out = Path(tmp, 'base.md'), Path(tmp, 'out.md')
            base.write_text(self.sealed())
            ops.write_prompt(base, ['AR-1'], out, owns_fields=True)
            text = out.read_text()
        self.assertIn('## Plan model (JSON)', text)
        self.assertIn('"id":"B-1"', text)
        self.assertIn('updated-plan-edit-ops-packet', text)
        self.assertIn('`ops` is an array of edits', text)
        self.assertNotIn('replace_text', text)
        self.assertNotIn('## Base project plan JSON', text)
        self.assertNotIn('Existing sections in the base plan', text)
        self.assertNotIn('Untouched prose', text.split('## Plan model (JSON)')[0])     # the Markdown plan is not in the prompt
        self.assertIn('protected_verification_paths', text)

    def test_the_findings_reach_the_writer_as_json_not_a_markdown_table(self):
        text = self.sealed()
        self.assertIn('"required_plan_change"', text)
        self.assertIn('"id": "AR-1"', text)
        findings = text.split('## Adversarial review findings')[1]
        self.assertNotIn('| id | severity |', findings)
        self.assertNotIn('|---|', findings)

    def test_a_deciding_writer_is_told_to_check_its_findings_and_one_after_specialists_is_not(self):
        review = {'schema': 'uncle.artifact/v1', 'kind': 'adversarial-review', 'findings': [{'id': 'AR-1', 'fix': 'x'}]}
        workers = {'schema': 'uncle.artifact/v1', 'kind': 'updated-plan-worker-packets', 'workers': [], 'findings': []}
        with tempfile.TemporaryDirectory() as tmp:
            for label, given, expected in (('decide', None, True), ('after specialists', workers, False)):
                base, out = Path(tmp, 'base.md'), Path(tmp, 'out.md')
                base.write_text(PROMPT.prompt(PLAN, review, given))
                ops.write_prompt(base, ['AR-1'], out)
                self.assertEqual('You decide each finding yourself' in out.read_text(), expected, label)
        self.assertIn('`Rejected`', ops.DECIDE_NOTE)

    def test_a_base_prompt_in_another_shape_is_refused_so_the_driver_falls_back(self):
        with tempfile.TemporaryDirectory() as tmp:
            Path(tmp, 'base.md').write_text('nothing useful')
            with self.assertRaises(ops.Conflict):
                ops.write_prompt(Path(tmp, 'base.md'), ['AR-1'], Path(tmp, 'out.md'))


class Schemas(unittest.TestCase):
    def properties(self, schema):
        properties = {}
        for variant in schema['anyOf']:
            for key, value in variant['properties'].items():
                target = properties.setdefault(key, {})
                if 'enum' in value:
                    target.setdefault('enum', []).extend(value['enum'])
                if 'properties' in value:
                    target.setdefault('properties', {}).update(value['properties'])
        return properties

    def test_the_writer_schema_lists_the_ids_and_has_no_text_patch(self):
        with tempfile.TemporaryDirectory() as tmp:
            plan = Path(tmp, 'plan.json')
            plan.write_text(json.dumps(PLAN))
            out = Path(tmp, 'schema.json')
            self.assertEqual(WS.main(['edit-ops', str(plan), str(out)]), 0)
            schema = json.loads(out.read_text())
        self.assertEqual(schema['properties']['kind'], {'const': WS.EDIT_OPS_KIND})
        self.assertNotIn('patch', schema['properties'])
        item = self.properties(schema['properties']['ops']['items'])
        self.assertIn('B-1', item['id']['enum'])
        self.assertIn('step-2', item['id']['enum'])
        self.assertNotIn('B-9', item['id']['enum'])
        self.assertIn('', item['after']['enum'])
        self.assertIn('failure', item['fields']['properties'])
        self.assertNotIn('pattern', json.dumps(schema))

    def test_the_static_forms_are_registered_for_a_local_grammar(self):
        self.assertIn(WS.EDIT_OPS_KIND, WS.STATIC)
        self.assertIn(WS.RESOLUTION_OPS_KIND, WS.STATIC)
        self.assertEqual(WS.STATIC[WS.EDIT_OPS_KIND]['required'][:3], ['schema', 'kind', 'dispositions'])

    def test_the_resolver_schema_lists_the_ids(self):
        with tempfile.TemporaryDirectory() as tmp:
            plan = Path(tmp, 'plan.json')
            plan.write_text(json.dumps(PLAN))
            out = Path(tmp, 'schema.json')
            self.assertEqual(WS.main(['resolve-ops', str(plan), str(out)]), 0)
            schema = json.loads(out.read_text())
        item = self.properties(schema['properties']['resolutions']['items']['properties']['ops']['items'])
        self.assertIn('B-2', item['id']['enum'])


class Reconcile(Base):
    """The deciders edit first; one reconciler then adds only what the specialists asked for and no edit meets."""

    def late(self, *operations):
        path = self.dir / 'reconcile.json'
        path.write_text(json.dumps({'dispositions': [], 'ops': list(operations)}))
        return path

    def merge_with_late(self, path):
        import os
        os.environ['UNCLE_LATE_OPS'] = str(path)
        try:
            return self.merge()
        finally:
            del os.environ['UNCLE_LATE_OPS']

    def test_a_late_edit_that_nothing_else_touches_is_added(self):
        self.deliver('1', 'AR-1', set_fields('B-1', failure='decided'))
        self.deliver('2', 'AR-2')
        result = self.merge_with_late(self.late(set_fields('B-2', failure='from a specialist')))
        text = self.narrative_after(result)
        self.assertIn('| B-1 | User clicks a digit | Digit appended | decided | UB-1 |', text)
        self.assertIn('from a specialist', text)

    def test_a_late_edit_to_a_field_a_decider_changed_is_dropped(self):
        self.deliver('1', 'AR-1', set_fields('B-1', failure='decided'))
        self.deliver('2', 'AR-2')
        text = self.narrative_after(self.merge_with_late(self.late(set_fields('B-1', failure='overwrite'))))
        self.assertIn('decided', text)
        self.assertNotIn('overwrite', text)

    def test_an_unusable_late_edit_costs_nothing_and_a_missing_file_is_ignored(self):
        self.deliver('1', 'AR-1', set_fields('B-1', failure='decided'))
        self.deliver('2', 'AR-2')
        text = self.narrative_after(self.merge_with_late(self.late(set_fields('B-9', failure='x'))))
        self.assertIn('decided', text)
        import os
        os.environ['UNCLE_LATE_OPS'] = str(self.dir / 'nothing-here.json')
        try:
            self.assertIn('decided', self.narrative_after(self.merge()))
        finally:
            del os.environ['UNCLE_LATE_OPS']

    def test_the_reconcile_prompt_shows_the_decided_ops_and_the_corrections_and_owns_no_finding(self):
        self.deliver('1', 'AR-1', set_fields('B-1', failure='decided'))
        self.deliver('2', 'AR-2')
        advisors = self.dir / 'advisors.json'
        advisors.write_text(json.dumps({'findings': [{'id': 'AR-1', 'required_corrections': ['Add a case to T-5'],
                                                      'gaps': ['g'], 'risks': ['r'], 'sources': ['verification']}]}))
        review = {'schema': 'uncle.artifact/v1', 'kind': 'adversarial-review', 'findings': [{'id': 'AR-1'}]}
        base_prompt = self.dir / 'base.md'
        base_prompt.write_text(PROMPT.prompt(PLAN, review, None))
        out = self.dir / 'reconcile.md'
        ops.write_reconcile_prompt(base_prompt, self.dir / 'slices.tsv', self.dir, advisors, out)
        text = out.read_text()
        self.assertIn('"failure": "decided"', text)
        self.assertIn('Add a case to T-5', text)
        self.assertIn('You decide no finding', text)
        self.assertNotIn('You own exactly these findings', text)
        self.assertIn('updated-plan-edit-ops-packet', text)
        self.assertNotIn('Collated specialist corrections', text.split('## Plan model (JSON)')[1].split('## Your task')[0])

    def test_the_sealed_prompt_can_be_built_before_any_specialist_has_spoken(self):
        review = {'schema': 'uncle.artifact/v1', 'kind': 'adversarial-review', 'findings': [{'id': 'AR-1', 'fix': 'x'}]}
        text = PROMPT.prompt(PLAN, review, None)
        self.assertIn('"required_plan_change": "x"', text)
        self.assertNotIn('Collated specialist corrections', text)


if __name__ == '__main__':
    unittest.main()
