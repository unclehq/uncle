#!/usr/bin/env python3
"""Updated-plan edit schemas stay within the optional-property budget, the pair form reads back as the dict form,
and a response that says its schema was relaxed is reported as such and repaired once (issue 268)."""
import contextlib
import importlib.util
import io
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts/lib'))
import http_agent as agent
import plan_model as pm
import self_hosted as hosted
import self_hosted_http as transport
import worker_schemas as WS

spec = importlib.util.spec_from_file_location('ops_fixture', Path(__file__).with_name('updated-plan-ops-test.py'))
fixture = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fixture)

LIMIT = 24
TABLE_PLAN = dict(fixture.PLAN, narrative=fixture.NARRATIVE + '\n## 4. Matrix\n\n| Area | Owner |\n|---|---|\n| UI | Ann |\n| API | Bo |\n')


def optional_count(schema):
    """Properties not listed as required, counted over every subschema (each anyOf variant, each nested object)."""
    if isinstance(schema, list):
        return sum(optional_count(item) for item in schema)
    if not isinstance(schema, dict):
        return 0
    own = schema.get('properties')
    total = len([k for k in own if k not in schema.get('required', [])]) if isinstance(own, dict) else 0
    return total + sum(optional_count(value) for value in schema.values())


def id_enums(schema, found=None):
    """Every enum offered for an `id`, `target` or `after` property."""
    found = [] if found is None else found
    if isinstance(schema, dict):
        for key, value in schema.items():
            if key in ('id', 'target', 'after') and isinstance(value, dict) and 'enum' in value:
                found.append((key, value['enum']))
            id_enums(value, found)
    elif isinstance(schema, list):
        for value in schema:
            id_enums(value, found)
    return found


class Schemas(unittest.TestCase):
    def setUp(self):
        self.model = pm.model_of(fixture.PLAN)
        self.ids = sorted(pm.index(self.model))

    def shapes(self):
        block = next(b for s in self.model['sections'] for b in s['blocks'] if b['kind'] == 'rows')
        intent = {'op': 'insert_row', 'target': block['id'], 'after': block['rows'][0]['id'],
                  'row_kind': block['row_kind'], 'new_id': 'B-3'}
        return {
            'ids list': WS.edit_ops_packet(ids=self.ids),
            'plan model': WS.edit_ops_packet(ids=self.ids, model=self.model),
            'generic op on a plan model': WS.edit_ops_packet(ids=self.ids, generic_model=self.model),
            'kind only': WS.edit_ops_packet(),
            'intent': WS.edit_ops_packet(ids=self.ids, model=self.model, intent=intent),
            'resolution on a plan model': WS.resolution_ops_packet(ids=self.ids, model=self.model),
            'resolution kind only': WS.resolution_ops_packet(ids=self.ids),
        }

    def test_no_edit_schema_has_more_than_24_optional_properties(self):
        for name, schema in self.shapes().items():
            with self.subTest(name):
                self.assertLessEqual(optional_count(schema), LIMIT)

    def test_the_counter_rejects_a_schema_over_the_limit(self):
        wide = {'type': 'object', 'properties': {'p%d' % n: {'type': 'string'} for n in range(LIMIT + 1)}, 'required': []}
        self.assertGreater(optional_count(wide), LIMIT)
        self.assertEqual(optional_count({'type': 'object', 'properties': {'a': {}}, 'required': ['a']}), 0)

    def test_the_id_enums_still_restrict_what_an_op_may_name(self):
        for name, schema in (('ids list', WS.edit_ops_packet(ids=self.ids)), ('plan model', WS.edit_ops_packet(ids=self.ids, model=self.model))):
            enums = id_enums(schema)
            with self.subTest(name):
                self.assertTrue(enums)
                for key, values in enums:
                    self.assertLessEqual(set(values) - {'', 'end'}, set(self.ids), key)
        generic = WS.edit_ops_packet(ids=self.ids)['properties']['ops']['items']['anyOf'][0]['properties']
        self.assertEqual(generic['id']['enum'], self.ids)
        self.assertEqual(generic['target']['enum'], self.ids)
        self.assertEqual(generic['after']['enum'], self.ids + [''])

    def test_fields_and_new_are_required_arrays_of_pairs(self):
        generic = WS.edit_ops_packet(ids=self.ids)['properties']['ops']['items']['anyOf'][0]['properties']
        for key in ('fields', 'new'):
            item = generic[key]['items']
            self.assertEqual(item['required'], ['name', 'value'])
            self.assertEqual(set(item['properties']), {'name', 'value'})
            self.assertEqual(generic[key]['maxItems'], len(item['properties']['name']['enum']))
        self.assertIn('cells', generic)


class Pairs(unittest.TestCase):
    def setUp(self):
        self.model = pm.model_of(fixture.PLAN)

    @staticmethod
    def pairs(**fields):
        return [{'name': k, 'value': v} for k, v in fields.items()]

    def same(self, op, **payload):
        as_dict = dict(op, **{k: v for k, v in payload.items()})
        as_pairs = dict(op, **{k: self.pairs(**v) for k, v in payload.items()})
        self.assertEqual(pm.typed_op(self.model, as_pairs), pm.typed_op(self.model, as_dict))
        return pm.typed_op(self.model, as_pairs)

    def test_set_fields_pairs_equal_the_dict(self):
        typed = self.same({'op': 'set_fields', 'id': 'B-1'}, fields={'failure': 'Shows NaN', 'result': 'Digit shown'})
        self.assertEqual(typed['fields'], {'failure': 'Shows NaN', 'result': 'Digit shown'})

    def test_step_fields_pairs_equal_the_dict(self):
        step = pm.steps_of(self.model)[1]['id']
        typed = self.same({'op': 'set_step', 'id': step}, fields={'title': 'Core!', 'owns': 'src/a.js, src/b.js', 'depends_on': 'step-1'})
        self.assertEqual(typed['owns'], ['src/a.js', 'src/b.js'])

    def test_insert_row_pairs_equal_the_dict(self):
        block = next(b for s in self.model['sections'] for b in s['blocks'] if b['kind'] == 'rows')
        base = {'op': 'insert_row', 'target': block['id'], 'after': block['rows'][0]['id']}
        typed = self.same(base, new={'id': 'B-9', 'trigger': 'T', 'result': 'R', 'failure': 'F'})
        self.assertEqual(typed['row']['result'], 'R')

    def test_a_repeated_name_keeps_the_last_value(self):
        flat = {'op': 'set_fields', 'id': 'B-1', 'fields': self.pairs(result='first') + self.pairs(result='second')}
        self.assertEqual(pm.typed_op(self.model, flat)['fields'], {'result': 'second'})

    def test_a_dict_still_passes_through_unchanged(self):
        flat = {'op': 'set_fields', 'id': 'B-1', 'fields': {'result': 'x'}}
        self.assertEqual(pm.typed_op(self.model, flat)['fields'], {'result': 'x'})
        self.assertEqual(flat['fields'], {'result': 'x'})        # the caller's op is not rewritten in place

    def test_malformed_pairs_are_a_plan_error(self):
        for bad in ([{'name': 'result'}], [{'name': 'result', 'value': 1}], ['result'], [{'name': 'result', 'value': 'x', 'extra': 'y'}]):
            with self.subTest(bad), self.assertRaises(pm.PlanError):
                pm.typed_op(self.model, {'op': 'set_fields', 'id': 'B-1', 'fields': bad})

    def test_more_pairs_than_field_names_or_an_oversized_value_is_rejected(self):
        count = pm.PAIR_LIMITS['fields'][0]
        with self.assertRaisesRegex(pm.PlanError, 'at most %d' % count):
            pm.typed_op(self.model, {'op': 'set_fields', 'id': 'B-1', 'fields': self.pairs(result='x') * (count + 1)})
        with self.assertRaisesRegex(pm.PlanError, 'at most 8000'):
            pm.typed_op(self.model, {'op': 'set_fields', 'id': 'B-1', 'fields': self.pairs(result='x' * 8001)})

    def test_top_level_cells_are_a_generic_table_row(self):
        model = pm.model_of(TABLE_PLAN)
        block = next(b for s in model['sections'] for b in s['blocks'] if b['kind'] == 'table')
        row = block['rows'][0]['id']
        nested = pm.typed_op(model, {'op': 'set_fields', 'id': row, 'fields': {'cells': ['UI', 'Cy']}})
        self.assertEqual(pm.typed_op(model, {'op': 'set_fields', 'id': row, 'fields': [], 'cells': ['UI', 'Cy']}), nested)
        self.assertEqual(pm.typed_op(model, {'op': 'set_fields', 'id': row, 'cells': ['UI', 'Cy']}), nested)
        insert = pm.typed_op(model, {'op': 'insert_row', 'target': block['id'], 'new': [], 'cells': ['Ops', 'Di']})
        self.assertEqual(insert, pm.typed_op(model, {'op': 'insert_row', 'target': block['id'], 'new': {'cells': ['Ops', 'Di']}}))
        self.assertEqual(insert['row']['cells'], ['Ops', 'Di'])

    def test_cells_given_twice_are_rejected_not_merged(self):
        model = pm.model_of(TABLE_PLAN)
        block = next(b for s in model['sections'] for b in s['blocks'] if b['kind'] == 'table')
        with self.assertRaisesRegex(pm.PlanError, 'cells given twice'):
            pm.typed_op(model, {'op': 'set_fields', 'id': block['rows'][0]['id'], 'fields': {'cells': ['a', 'b']}, 'cells': ['c', 'd']})


class Headers(unittest.TestCase):
    URL = 'http://unused.invalid/v1'

    def complete(self, headers):
        values = {'model': 'stub', 'base_url': self.URL, 'api_key': 'k'}
        data = {'choices': [{'message': {'content': '{}'}, 'finish_reason': 'stop'}], 'usage': {}}
        caps = {'modes': ['json_schema'], 'rejected': set()}
        with patch.object(transport, 'capabilities', return_value=caps), \
                patch.object(transport, '_via_http1', return_value=(200, 'OK', headers, data)), \
                patch.dict(os.environ, {'UNCLE_CONFIG': '/nonexistent'}):
            return transport.constrained_completion(values, [{'role': 'user', 'content': 'x'}], {'type': 'object'}, 'n', 50)

    def test_a_relaxed_header_marks_the_mode(self):
        self.assertEqual(self.complete({'x-seren-schema-relaxed': 'true'})[3], 'json_schema_relaxed')

    def test_any_non_empty_value_counts_even_a_strange_one(self):
        self.assertEqual(self.complete({'x-seren-schema-relaxed': ' 0 '})[3], 'json_schema_relaxed')

    def test_no_header_leaves_the_mode_alone(self):
        self.assertEqual(self.complete({})[3], 'json_schema')

    def test_an_empty_or_blank_header_leaves_the_mode_alone(self):
        for value in ('', '   '):
            self.assertEqual(self.complete({'x-seren-schema-relaxed': value})[3], 'json_schema', repr(value))

    def test_the_check_header_alone_never_relaxes(self):
        self.assertEqual(self.complete({'x-seren-schema-check': 'failed'})[3], 'json_schema')

    def test_a_relaxed_response_does_not_leak_into_the_next_call(self):
        self.assertEqual(self.complete({'x-seren-schema-relaxed': '1'})[3], 'json_schema_relaxed')
        self.assertEqual(self.complete({})[3], 'json_schema')


class BoundedWriter(unittest.TestCase):
    PACKET = {'schema': 'uncle.artifact/v1', 'kind': WS.EDIT_OPS_KIND, 'ops': 'wrong', 'dispositions': []}

    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.values = {'model': 'stub', 'base_url': 'http://unused.invalid/v1', 'api_key': 'never-used'}
        capture = contextlib.redirect_stdout(io.StringIO())
        capture.__enter__()
        self.addCleanup(capture.__exit__, None, None, None)

    def reply(self, text='done', calls=()):
        return {'choices': [{'message': {'role': 'assistant', 'content': text, 'tool_calls': list(calls)}, 'finish_reason': 'stop'}],
                'usage': {'prompt_tokens': 10, 'completion_tokens': 1}}

    def run_writer(self, text, mode, bounded=True, replies=()):
        delivery = self.root / '.uncle/workflow/edits/1.json'
        env = {'UNCLE_CONFIG': str(self.root / 'absent'), 'UNCLE_PROJECT_ROOT': str(self.root),
               'UNCLE_ARTIFACT_DELIVERY': str(delivery), 'UNCLE_STATUS_STAGE': 'updated-plan-worker-edits-1'}
        if bounded:
            env['UNCLE_UPDATED_PLAN_ANSWER_TOKENS'] = '4096'
        with patch.dict(os.environ, env, clear=True), \
                patch.object(agent, 'constrained_completion', return_value=(text, 'stop', {}, mode)) as constrained, \
                patch.object(agent, 'interruptible_chat', side_effect=list(replies)) as chat:
            try:
                answer, _ = hosted.run_opencode('agent', self.values, json.dumps(self.PACKET), self.root)
                error = None
            except ValueError as caught:
                answer, error = None, str(caught)
        return answer, error, chat.call_count, constrained.call_count

    def repair_replies(self):
        edit = {'id': 'stub', 'type': 'function', 'function': {'name': 'edit_file', 'arguments': json.dumps(
            {'path': '.uncle/workflow/http-answer-repair.json', 'old_string': '"ops": "wrong"', 'new_string': '"ops": []'})}}
        return [self.reply(calls=[edit]), self.reply('Fixed.')]

    def test_a_relaxed_invalid_bounded_reply_is_repaired_once(self):
        answer, error, chats, generations = self.run_writer(json.dumps(self.PACKET), 'json_schema_relaxed', replies=self.repair_replies())
        self.assertIsNone(error)
        self.assertEqual(json.loads(answer)['ops'], [])
        self.assertEqual((chats, generations), (2, 1))

    def test_the_relaxed_mode_is_named_in_the_repair_request(self):
        with patch.object(agent, 'run_agent', wraps=agent.run_agent) as run:
            self.run_writer(json.dumps(self.PACKET), 'json_schema_relaxed', replies=self.repair_replies())
        prompts = [call.args[1] for call in run.call_args_list if 'Targeted schema repair' in call.args[1]]
        self.assertEqual(len(prompts), 1)
        self.assertIn('(json_schema_relaxed constraint)', prompts[0])

    def test_a_non_relaxed_bounded_reply_is_not_repaired(self):
        answer, error, chats, generations = self.run_writer(json.dumps(self.PACKET), 'json_schema')
        self.assertIn('violates the artifact schema (json_schema constraint)', error)
        self.assertEqual((chats, generations), (0, 1))

    def test_a_relaxed_reply_that_is_not_an_object_is_not_repaired(self):
        for text in ('[1, 2]', 'null', 'plain words', '"text"'):
            with self.subTest(text):
                answer, error, chats, _ = self.run_writer(text, 'json_schema_relaxed')
                self.assertIsNotNone(error)
                self.assertEqual(chats, 0)

    def test_a_non_bounded_writer_is_still_repaired(self):
        answer, error, chats, _ = self.run_writer(json.dumps(self.PACKET), 'json_schema', bounded=False, replies=[self.reply()] + self.repair_replies())
        self.assertIsNone(error, error)
        self.assertEqual(json.loads(answer)['ops'], [])
        self.assertEqual(chats, 3)      # the agent's own turn, then the two repair turns


if __name__ == '__main__':
    unittest.main()
