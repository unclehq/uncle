#!/usr/bin/env python3
"""The plan-stage worker packets: schemas, rendering, schema-checked extraction, local-model registration."""
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

LIB = Path(__file__).resolve().parents[1] / 'lib'
sys.path.insert(0, str(LIB))
import project_plan_sections as sections
import structured_output
import updated_plan_edits as edits
import worker_schemas as schemas
W = schemas


def validate(value, schema, path='$'):
    """The subset of JSON Schema these schemas use; returns a list of violations."""
    problems = []
    if 'const' in schema and value != schema['const']:
        problems.append('%s: expected %r' % (path, schema['const']))
    if 'enum' in schema and value not in schema['enum']:
        problems.append('%s: %r not in enum' % (path, value))
    kind = schema.get('type')
    if kind == 'object':
        if not isinstance(value, dict):
            return ['%s: not an object' % path]
        for key in schema.get('required', []):
            if key not in value:
                problems.append('%s: missing %s' % (path, key))
        for key, child in value.items():
            if key not in schema['properties']:
                if schema.get('additionalProperties') is False:
                    problems.append('%s: unexpected %s' % (path, key))
            else:
                problems += validate(child, schema['properties'][key], '%s.%s' % (path, key))
    elif kind == 'array':
        if not isinstance(value, list):
            return ['%s: not an array' % path]
        if len(value) < schema.get('minItems', 0) or len(value) > schema.get('maxItems', 10 ** 9):
            problems.append('%s: bad length' % path)
        for index, item in enumerate(value):
            problems += validate(item, schema['items'], '%s[%d]' % (path, index))
    elif kind == 'string':
        if not isinstance(value, str):
            return ['%s: not a string' % path]
        if len(value) < schema.get('minLength', 0) or len(value) > schema.get('maxLength', 10 ** 9):
            problems.append('%s: bad string length' % path)
    elif kind == 'boolean' and not isinstance(value, bool):
        problems.append('%s: not a boolean' % path)
    return problems


def packet(name='behaviors', **extra):
    row = {'schema': 'uncle.artifact/v1', 'kind': schemas.SECTION_KIND,
           'sections': [{'heading': sections.expected_headings(name)[0], 'body': '| B-1 |'}]}
    if sections.trace_letters(name):
        row['trace'] = [{'kind': sections.trace_letters(name)[0], 'requirement': 'R-1', 'ids': ['B-1']}]
    row.update(extra)
    return row


class SectionSchema(unittest.TestCase):
    def schema(self, name):
        return schemas.section_packet(sections.expected_headings(name), sections.trace_letters(name))

    def test_a_worker_may_only_name_its_own_headings(self):
        schema = self.schema('behaviors')
        self.assertEqual(validate(packet('behaviors'), schema), [])
        stolen = packet('behaviors')
        stolen['sections'][0]['heading'] = '## 7. Domain invariants'
        self.assertTrue(validate(stolen, schema))
        self.assertTrue(validate(packet('behaviors', sections=[{'heading': 'Overview', 'body': 'x'}]), schema))

    def test_extra_fields_and_missing_ones_are_refused(self):
        schema = self.schema('behaviors')
        self.assertTrue(validate(packet('behaviors', note='x'), schema))
        self.assertTrue(validate({'schema': 'uncle.artifact/v1', 'kind': schemas.SECTION_KIND}, schema))
        self.assertTrue(validate(packet('behaviors', sections=[]), schema))

    def test_trace_is_required_only_from_workers_that_report_it(self):
        self.assertIn('trace', self.schema('behaviors')['required'])
        self.assertNotIn('trace', self.schema('design')['properties'])
        self.assertEqual(sections.trace_letters('behaviors'), 'B')
        self.assertEqual(sections.trace_letters('checks'), 'M')
        self.assertEqual(sections.trace_letters('design'), '')
        with_trace = packet('behaviors', trace=[{'kind': 'B', 'requirement': 'R-1', 'ids': ['B-1']}])
        self.assertEqual(validate(with_trace, self.schema('behaviors')), [])
        self.assertTrue(validate(packet('behaviors', trace=[{'kind': 'T', 'requirement': 'R-1', 'ids': ['T-1']}]),
                                 self.schema('behaviors')))

    def test_a_worker_that_owes_a_trace_cannot_leave_it_empty(self):
        schema = self.schema('behaviors')
        self.assertTrue(validate(packet('behaviors', trace=[]), schema))
        self.assertEqual(validate(packet('behaviors'), schema), [])
        self.assertEqual(schemas.section_packet(sections.expected_headings('design'))['properties'].get('trace'), None)

    def test_every_worker_has_a_usable_schema(self):
        for name in sections.WORKERS:
            schema = self.schema(name)
            json.dumps(schema)
            self.assertEqual(schema['properties']['kind']['const'], schemas.SECTION_KIND)

    def test_the_cli_writes_the_schema_for_a_worker(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / 's.json'
            subprocess.run([sys.executable, '-B', str(LIB / 'worker_schemas.py'), 'section', 'commands', str(out)], check=True)
            heads = json.loads(out.read_text())['properties']['sections']['items']['properties']['heading']['enum']
            self.assertIn('## Verification commands', heads)
            self.assertIn('## Parallel verification groups', heads)
            self.assertEqual(subprocess.run([sys.executable, '-B', str(LIB / 'worker_schemas.py'), 'section', 'nope', str(out)],
                                            capture_output=True).returncode, 1)


class Render(unittest.TestCase):
    def test_a_packet_becomes_the_section_file_the_assembler_reads(self):
        text = sections.render_packet('behaviors', packet(
            'behaviors', trace=[{'kind': 'B', 'requirement': 'R-1', 'ids': ['B-1', 'B-2']},
                                {'kind': 'M', 'requirement': 'R-2', 'ids': ['M-1']}]))
        self.assertTrue(text.startswith('## 6. Observable behaviors\n\n| B-1 |'))
        data, body = sections.trace_lines(text)
        self.assertEqual(data, {'B': {'R-1': ['B-1', 'B-2']}, 'M': {'R-2': ['M-1']}})
        self.assertNotIn('trace', body)

    def test_a_bad_packet_is_refused(self):
        for bad in ({}, packet(sections=[]), packet(sections=[{'heading': 'no hashes', 'body': 'x'}]),
                    packet(sections=[{'heading': '## 6. Observable behaviors', 'body': '  '}]),
                    dict(packet(), kind='other')):
            with self.assertRaises(ValueError):
                sections.render_packet('behaviors', bad)

    def test_malformed_trace_entries_are_dropped_not_trusted(self):
        text = sections.render_packet('behaviors', packet('behaviors', trace=[
            {'kind': 'B', 'requirement': 'not an id', 'ids': ['B-1']}, {'kind': 'B', 'requirement': 'R-1', 'ids': ['junk']}]))
        self.assertNotIn('trace', text)

    def test_the_prompt_names_a_json_answer_and_one_packet_kind(self):
        import re
        base = 'BASE'
        for json_mode in (False, True):
            text = sections.build_prompt('behaviors', '/d', base, json_mode=json_mode)
            self.assertEqual('Write call' in text, not json_mode)
        text = sections.build_prompt('behaviors', '/d', base, json_mode=True)
        self.assertEqual(set(re.findall(r'"kind"\s*:\s*"([a-z-]+)"', text)), {schemas.SECTION_KIND})
        self.assertIn('`trace`', text)
        self.assertNotIn('<!-- trace', text)


class EditSchemas(unittest.TestCase):
    HEADINGS = ['## 1. Overview', '## 2. Invariants']

    def edit(self, **extra):
        row = {'schema': 'uncle.artifact/v1', 'kind': schemas.EDIT_KIND,
               'dispositions': [{'finding': 'AR-1', 'disposition': 'Accepted', 'reason': 'r', 'plan_change': 'c'}],
               'patch': {'replace_text': [{'heading': '## 1. Overview', 'old': 'a', 'new': 'b'}]}}
        row.update(extra)
        return row

    def test_an_edit_can_only_target_a_section_the_plan_has(self):
        schema = schemas.edit_packet(self.HEADINGS)
        self.assertEqual(validate(self.edit(), schema), [])
        bad = self.edit(patch={'replace_text': [{'heading': '## 9. Nowhere', 'old': 'a', 'new': 'b'}]})
        self.assertTrue(validate(bad, schema))

    def test_a_writer_cannot_write_the_commands_whole(self):
        schema = schemas.edit_packet(self.HEADINGS)
        self.assertTrue(validate(self.edit(verification_commands='npm test'), schema))
        self.assertEqual(validate(self.edit(commands_replace=[{'old': 'a', 'new': 'b'}]), schema), [])

    def test_only_the_owner_writes_the_protected_paths(self):
        self.assertTrue(validate(self.edit(protected_verification_paths='a'), schemas.edit_packet(self.HEADINGS)))
        owner = schemas.edit_packet(self.HEADINGS, owner=True)
        self.assertEqual(validate(self.edit(protected_verification_paths='tests/a.js'), owner), [])
        self.assertTrue(validate(self.edit(), owner))

    def test_dispositions_are_the_four_the_workflow_knows(self):
        row = self.edit()
        row['dispositions'][0]['disposition'] = 'Maybe'
        self.assertTrue(validate(row, schemas.edit_packet(self.HEADINGS)))

    def test_a_resolution_names_its_group_and_a_patch(self):
        schema = schemas.resolution_packet(self.HEADINGS)
        ok = {'schema': 'uncle.artifact/v1', 'kind': schemas.RESOLUTION_KIND, 'resolutions': [
            {'group': 'G1', 'patch': {'replace_text': [{'heading': '## 2. Invariants', 'old': 'a', 'new': 'b'}]}}]}
        self.assertEqual(validate(ok, schema), [])
        self.assertTrue(validate(dict(ok, resolutions=[]), schema))
        self.assertTrue(validate(dict(ok, resolutions=[{'patch': {}}]), schema))

    def test_a_writer_packet_is_what_the_merge_reads(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            plan = {'schema': 'uncle.artifact/v1', 'kind': 'plan', 'narrative': '# P\n\n## 1. Overview\nalpha beta\n',
                    'verification_commands': 'npm test\n# Frozen verification paths: tests/a.js'}
            (tmp / 'plan.json').write_text(json.dumps(plan))
            (tmp / 'slices.tsv').write_text('1\tAR-1\n')
            packet_ = self.edit(protected_verification_paths='tests/a.js',
                                patch={'replace_text': [{'heading': '## 1. Overview', 'old': 'alpha', 'new': 'b'}]})
            (tmp / '1.json').write_text(json.dumps(packet_))
            edits.merge(tmp / 'plan.json', tmp / 'slices.tsv', tmp, tmp / 'out.json')
            self.assertEqual(json.loads((tmp / 'out.json').read_text())['dispositions'][0]['finding'], 'AR-1')

    def test_the_writer_prompt_names_only_the_writer_kind(self):
        import re
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp) / 'b.md'
            base.write_text('SEALED\n\n```json\n{"schema":"uncle.artifact/v1","kind":"plan","dispositions":[],"patch":{}}\n```\n')
            for owner in (True, False):
                out = Path(tmp) / 'o.md'
                edits.write_prompt(base, ['AR-1'], out, owns_fields=owner)
                kinds = set(re.findall(r'"kind"\s*:\s*"([a-z-]+)"', out.read_text()))
                self.assertEqual(kinds, {schemas.EDIT_KIND})
                self.assertEqual('protected_verification_paths":"..."' in out.read_text(), owner)

    def test_the_resolver_prompt_names_only_the_resolution_kind(self):
        import re
        text = edits.resolver_prompt([{'id': 'G1', 'kind': 'text', 'heading': '## 1. Overview', 'context': 'x',
                                       'edits': [{'writer': '1'}], 'refs': [], 'avoid': []}], [])
        self.assertEqual(set(re.findall(r'"kind"\s*:\s*"([a-z-]+)"', text)), {schemas.RESOLUTION_KIND})


class LocalModels(unittest.TestCase):
    """A self-hosted adapter enforces the schema of the one `"kind"` its prompt names."""

    def test_the_kinds_are_registered_with_the_adapter(self):
        import self_hosted
        for kind in (schemas.SECTION_KIND, schemas.EDIT_KIND, schemas.RESOLUTION_KIND):
            schema = self_hosted.artifact_schema(kind)
            self.assertIsNotNone(schema, kind)
            self.assertEqual(schema['properties']['kind']['const'], kind)
            self.assertEqual(self_hosted.reviewer_artifact_kind('contract {"kind":"%s"} end' % kind), kind)

    def test_the_adapter_schema_stays_inside_what_grammar_servers_accept(self):
        import self_hosted

        def walk(node):
            if isinstance(node, dict):
                self.assertNotIn('pattern', node)
                self.assertNotIn('$ref', node)
                for value in node.values():
                    walk(value)
            elif isinstance(node, list):
                for value in node:
                    walk(value)
        for kind in (schemas.SECTION_KIND, schemas.EDIT_KIND, schemas.RESOLUTION_KIND):
            walk(self_hosted.artifact_schema(kind))

    def test_every_string_and_list_is_bounded(self):
        import self_hosted

        def walk(node, name=''):
            if isinstance(node, dict):
                if node.get('type') == 'string' and 'enum' not in node and 'const' not in node:
                    self.assertIn('maxLength', node, name)
                if node.get('type') == 'array':
                    self.assertIn('maxItems', node, name)
                for key, value in node.items():
                    walk(value, key)
            elif isinstance(node, list):
                for value in node:
                    walk(value, name)
        for kind in (schemas.SECTION_KIND, schemas.EDIT_KIND, schemas.RESOLUTION_KIND):
            walk(self_hosted.artifact_schema(kind))


class Extraction(unittest.TestCase):
    def log(self, tmp, *events):
        path = Path(tmp) / 'l.jsonl'
        path.write_text('\n'.join(json.dumps(e) for e in events) + '\n')
        return path

    def test_the_validated_object_on_the_result_event_is_taken(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = self.log(tmp, {'type': 'assistant', 'message': {'content': [{'type': 'text', 'text': 'hello'}]}},
                           {'type': 'result', 'result': 'text', 'structured_output': {'a': 1}})
            self.assertEqual(structured_output.extract(log), {'a': 1})

    def test_the_tool_call_is_the_fallback_when_the_result_has_none(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = self.log(tmp, {'type': 'assistant', 'message': {'content': [
                {'type': 'tool_use', 'name': 'StructuredOutput', 'input': {'b': 2}}]}}, {'type': 'result', 'result': ''})
            self.assertEqual(structured_output.extract(log), {'b': 2})

    def test_chat_text_is_never_taken_as_the_object(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = self.log(tmp, {'type': 'assistant', 'message': {'content': [{'type': 'text', 'text': '{"c": 3}'}]}},
                           {'type': 'result', 'result': '{"c": 3}'})
            self.assertIsNone(structured_output.extract(log))
            out = Path(tmp) / 'o.json'
            cli = [sys.executable, '-B', str(LIB / 'structured_output.py'), 'extract', str(log), str(out)]
            self.assertEqual(subprocess.run(cli, capture_output=True).returncode, 1)
            self.assertFalse(out.exists())
        self.assertIsNone(structured_output.extract('/nonexistent/log'))

    def test_the_cli_writes_the_object(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = self.log(tmp, {'type': 'result', 'structured_output': {'d': 4}})
            out = Path(tmp) / 'o.json'
            subprocess.run([sys.executable, '-B', str(LIB / 'structured_output.py'), 'extract', str(log), str(out)], check=True)
            self.assertEqual(json.loads(out.read_text()), {'d': 4})


class LocalGrammarKind(unittest.TestCase):
    def test_a_worker_prompt_quoting_its_base_document_still_names_its_packet_kind(self):
        import self_hosted
        prompt = ('Base plan:\n```json\n{"kind": "plan", "narrative": "x"}\n```\n'
                  'Answer with `{"schema":"uncle.artifact/v1","kind":"updated-plan-edit-worker-packet"}`')
        self.assertEqual(self_hosted.reviewer_artifact_kind(prompt), 'updated-plan-edit-worker-packet')

    def test_two_foreign_kinds_still_name_nothing(self):
        import self_hosted
        self.assertIsNone(self_hosted.reviewer_artifact_kind('"kind": "plan" and "kind": "change-plan"'))


class SynthesisSchema(unittest.TestCase):
    def build(self, kind, mode):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / 's.json'
            subprocess.run([sys.executable, '-B', str(LIB / 'worker_schemas.py'), 'synthesis', kind, mode, str(out)], check=True)
            return json.loads(out.read_text())

    def test_the_single_call_updated_plan_is_schema_forced(self):
        schema = self.build('plan', 'protected')
        self.assertEqual(set(schema['required']), {'schema', 'kind', 'dispositions', 'patch'})
        self.assertNotIn('verification_commands', schema['properties'])
        self.assertNotIn('protected_verification_paths', schema['properties'])
        self.assertNotIn('narrative', schema['properties'])        # a patch, never the whole plan again
        self.assertNotIn('"pattern"', json.dumps(schema))

    def test_a_change_plan_has_no_protected_paths(self):
        schema = self.build('change-plan', 'plain')
        self.assertEqual(set(schema['required']), {'schema', 'kind', 'dispositions', 'patch'})


class BlockSchemas(unittest.TestCase):
    def schema(self, name):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / 's.json'
            self.assertEqual(W.main(['section-model', name, str(out)]), 0)
            return json.loads(out.read_text())

    def test_a_worker_schema_lists_its_titles_and_trace_kinds(self):
        schema = self.schema('behaviors')
        heading = schema['properties']['sections']['items']['properties']['heading']['enum']
        self.assertEqual(heading, ['6. Observable behaviors'])
        handling = self.schema('handling')['properties']['sections']['items']['properties']['heading']['enum']
        self.assertEqual(handling, ['8. Failure handling', '9. Concurrency model'])
        self.assertEqual(schema['properties']['kind'], {'const': W.SECTION_MODEL_KIND})
        self.assertIn('trace', schema['required'])

    def test_a_block_is_flat_and_closed_with_every_row_kind_offered(self):
        block = self.schema('tests')['properties']['sections']['items']['properties']['blocks']['items']
        self.assertIs(block['additionalProperties'], False)
        self.assertEqual(set(block['properties']['row_kind']['enum']), {'automated_test'})
        other = self.schema('defects')['properties']['sections']['items']['properties']['blocks']['items']
        self.assertEqual(set(other['properties']['row_kind']['enum']), {'mutation'})
        third = self.schema('obligations')['properties']['sections']['items']['properties']['blocks']['items']
        self.assertEqual(set(third['properties']['row_kind']['enum']), {'obligation'})
        self.assertIn('failure', block['properties']['rows']['items']['properties'])
        self.assertNotIn('pattern', json.dumps(block))

    def test_a_worker_with_no_typed_table_cannot_write_rows_or_steps(self):
        kinds = self.schema('closing')['properties']['sections']['items']['properties']['blocks']['items']['properties']['kind']['enum']
        self.assertEqual(kinds, ['prose', 'heading', 'code', 'list', 'table'])
        steps = self.schema('steps')['properties']['sections']['items']['properties']['blocks']['items']['properties']['kind']['enum']
        self.assertIn('steps', steps)

    def test_the_requirements_schema_is_the_interpretation_with_every_section_required(self):
        import subprocess, sys, tempfile, json
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / 'requirements.json'
            done = subprocess.run([sys.executable, str(Path(W.__file__)), 'requirements', str(out)], capture_output=True, text=True)
            self.assertEqual(done.returncode, 0, done.stderr)
            schema = json.loads(out.read_text())
        sections = schema['properties']['sections']
        self.assertEqual(schema['properties']['kind'], {'const': 'requirements-interpretation'})
        self.assertIn('failure_behaviors', sections['required'])
        self.assertEqual(len(sections['required']), 10)

    def test_the_outline_schema_is_the_outline(self):
        schema = self.schema('outline')
        self.assertEqual(schema['properties']['kind'], {'const': W.OUTLINE_KIND})
        self.assertEqual(set(schema['required']) - {'schema', 'kind'},
                         {'stack', 'components', 'steps', 'requirement_map'})

    def test_both_kinds_are_registered_for_a_local_grammar(self):
        self.assertIn(W.SECTION_MODEL_KIND, W.STATIC)
        self.assertIn(W.OUTLINE_KIND, W.STATIC)


if __name__ == '__main__':
    unittest.main()
