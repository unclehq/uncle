#!/usr/bin/env python3
"""Small, bounded edit writers and structural repair; no model, network or Git."""
import json
import os
import subprocess
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'lib'))
import updated_plan_ops as ops
import updated_plan_synthesis_prompt as synthesis
import plan_model as pm
import artifact_json
import structured_output
import http_agent
import self_hosted_http as transport
from self_hosted_stream import StreamStopped
from worker_schemas import edit_ops_packet
from plan_ownership_gap import unowned_protected_paths


class Slicing(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        env = patch.dict(os.environ, {'UNCLE_CONFIG': str(self.root / 'config'),
                                     'UNCLE_PROJECT_ROOT': str(self.root)}, clear=True)
        env.start()
        self.addCleanup(env.stop)
        self.plan = {'schema': 'uncle.artifact/v1', 'kind': 'plan',
                     'narrative': '# Plan\n\n## Implementation order\n\n'
                                  '1. **Core** — Write keyboard.\n   Owns: `src/useKeyboard.js`\n\n'
                                  '2. **Unit tests** — Write tests.\n   Owns: `tests/core.test.js`\n\n'
                                  '## Notes\n\nKeep this byte for byte.\n',
                     'verification_commands': 'npm test', 'protected_verification_paths': 'tests/useKeyboard.test.js',
                     'dispositions': [{'finding': 'AR-009', 'disposition': 'Accepted', 'reason': 'Missing test',
                                       'plan_change': 'Add tests/useKeyboard.test.js to Step 2 Owns list.'}]}
        self.path = self.root / '.uncle/workflow/documents/UPDATED_PROJECT_PLAN.json'
        self.path.parent.mkdir(parents=True)
        self.directory = self.root / 'repair'
        self.view = self.root / '.uncle/docs/UPDATED_PROJECT_PLAN.md'
        self.view.parent.mkdir(parents=True)
        self.save()

    def save(self):
        self.path.write_text(json.dumps(self.plan))
        self.view.write_text(artifact_json.render_plan(self.plan, protected=True))

    def prepare(self):
        return ops.prepare_structure_repair(self.path, self.root, self.directory,
                                            'a protected verification path with no owning implementation step')

    def test_group_size_is_a_ceiling_even_above_twenty_writers(self):
        ids = ['AR-%03d' % i for i in range(101)]
        groups = ops.slices(ids)
        self.assertEqual([i for _, group in groups for i in group], ids)
        self.assertEqual(max(len(group) for _, group in groups), 2)
        (self.root / 'config').write_text('updated-plan.group-size 3\n')
        self.assertEqual(max(len(group) for _, group in ops.slices(ids)), 3)
        with patch.dict(os.environ, {'WORKFLOW_UPDATED_PLAN_GROUP_SIZE': '4'}):
            self.assertEqual(max(len(group) for _, group in ops.slices(ids)), 4)
        with patch.dict(os.environ, {'WORKFLOW_UPDATED_PLAN_GROUP_SIZE': '0'}):
            with self.assertRaises(ValueError):
                ops.slices(ids)

    def test_change_config_and_legacy_environment_precedence(self):
        (self.root / 'config').write_text('updated-plan.group-size 3\nupdated-change-plan.group-size 4\n')
        with patch.dict(os.environ, {'UNCLE_PLAN_KIND': 'change-plan'}):
            self.assertEqual(ops.option('group-size', 2), 4)
            with patch.dict(os.environ, {'WORKFLOW_UPDATED_PLAN_GROUP_SIZE': '2'}):
                self.assertEqual(ops.option('group-size', 3), 2)
        with patch.dict(os.environ, {'WORKFLOW_UPDATED_PLAN_EDIT_SLICE': '5'}):
            self.assertEqual(ops.option('group-size', 2), 5)

    def test_answer_cap_scales_and_explicit_http_cap_wins(self):
        self.assertEqual(ops.writer_budget(['a']), (3, 4096))
        self.assertEqual(ops.writer_budget(['a', 'b']), (3, 6144))
        with patch.dict(os.environ, {'UNCLE_STATUS_STAGE': 'updated-plan-worker-edits-1',
                                     'UNCLE_UPDATED_PLAN_ANSWER_TOKENS': '6144'}):
            self.assertEqual(transport.turn_output_tokens(32768), 6144)
            (self.root / 'config').write_text('updated-plan.turn-output-tokens 5000\n')
            self.assertEqual(transport.turn_output_tokens(32768), 5000)
            with patch.dict(os.environ, {'WORKFLOW_SELF_HOSTED_TURN_OUTPUT_TOKENS': '7000'}):
                self.assertEqual(transport.turn_output_tokens(32768), 7000)
        (self.root / 'config').write_text('updated-plan.writer-turns 2\nupdated-plan.ops-per-finding 8\n')
        self.assertEqual(ops.writer_budget(['a', 'b']), (2, 10240))

    def test_large_unit_runners_keep_their_usual_turns(self):
        # Claude/Codex default to large units: no driver turn limit unless configured.
        self.assertEqual(ops.writer_budget(['a'], 'large'), (0, 4096))
        (self.root / 'config').write_text('updated-plan.writer-turns 5\n')
        self.assertEqual(ops.writer_budget(['a'], 'large'), (5, 4096))

    def test_prefetched_prompt_contains_plan_commands_and_only_assigned_findings(self):
        review = {'findings': [{'id': 'AR-001', 'fix': 'Keyboard change'}, {'id': 'AR-002', 'fix': 'Other change'}]}
        path, output = self.root / 'prompt', self.root / 'writer'
        path.write_text(synthesis.prompt(self.plan, review, None))
        ops.write_prompt(path, ['AR-001'], output)
        text = output.read_text()
        self.assertIn('src/useKeyboard.js', text)
        self.assertIn('npm test', text)
        self.assertIn('Keyboard change', text)
        self.assertNotIn('Other change', text.split('## Assigned findings and corrections')[1])
        self.assertIn('Do not read files, run commands or investigate', text)

    def packet(self, operations=None):
        return {'schema': 'uncle.artifact/v1', 'kind': 'updated-plan-edit-ops-packet',
                'dispositions': [], 'ops': operations or []}

    def test_first_packet_capture_still_validates_schema(self):
        packet = self.packet()
        raw = json.dumps(packet)
        for suffix in ('\n' + json.dumps(dict(packet, ops=[{'op': 'delete', 'id': 'wrong'}])), '\nAll done.'):
            self.assertEqual(json.loads(http_agent.answer_already_given(raw + suffix, edit_ops_packet())), packet)
            p = self.root / 'packet.json'
            p.write_text(raw + suffix)
            ops.capture_packet(p)
            self.assertEqual(json.loads(p.read_text()), packet)
        self.assertEqual(json.loads(http_agent.answer_already_given('```json\n' + raw + '\n' + raw + '\n```', edit_ops_packet())), packet)
        invalid = json.dumps(dict(packet, ops='not an array')) + '\nDone.'
        self.assertIsNone(http_agent.answer_already_given(invalid, edit_ops_packet()))
        with self.assertRaises(ValueError):
            ops.first_packet('{broken ' + raw)

    def test_native_reply_recovery_takes_the_first_ops_packet(self):
        first = self.packet([{'op': 'set_step', 'id': 'step-1', 'fields': {'text': 'first'}}])
        second = self.packet()
        log = self.root / 'events.jsonl'
        log.write_text(json.dumps({'type': 'result', 'result': json.dumps(first) + '\n' + json.dumps(second) + '\nDone.'}) + '\n')
        self.assertEqual(structured_output.recover(log), first)

    def test_resolver_trailing_text_uses_the_existing_semantic_checks(self):
        (self.root / 'slices.tsv').write_text('1\tAR-1\n2\tAR-2\n')
        for n in (1, 2):
            packet = self.packet([{'op': 'set_step', 'id': 'step-1', 'fields': {'text': str(n)}}])
            packet['dispositions'] = [{'finding': 'AR-%d' % n, 'disposition': 'Accepted', 'reason': 'r', 'plan_change': 'c'}]
            (self.root / ('%d.json' % n)).write_text(json.dumps(packet))
        args = [self.path, self.root / 'slices.tsv', self.root, self.root / 'merged.json']
        with self.assertRaises(ops.NeedsResolution):
            ops.merge(*args)
        resolution = {'resolutions': [{'group': 'G1', 'ops': [{'op': 'set_step', 'id': 'step-1', 'fields': {'text': 'merged'}}]}]}
        (self.root / 'resolutions-G1.json').write_text(json.dumps(resolution) + '\n' + json.dumps({'resolutions': []}))
        self.assertEqual(ops.check_resolutions(self.path, self.root), {})
        ops.merge(*args, self.root)
        self.assertIn('merged', (self.root / 'merged.json').read_text())
        resolution['resolutions'][0]['ops'][0]['id'] = 'step-999'
        (self.root / 'resolutions-G1.json').write_text(json.dumps(resolution) + '\nDone.')
        self.assertIn('G1', ops.check_resolutions(self.path, self.root))

    def test_structural_repair_schema_can_edit_missing_protected_paths(self):
        self.assertNotIn('protected_verification_paths', edit_ops_packet()['properties'])
        with patch.dict(os.environ, {'UNCLE_UPDATED_PLAN_STRUCTURE_REPAIR': '1'}):
            schema = edit_ops_packet()
            self.assertIn('protected_verification_paths', schema['properties'])
            self.assertNotIn('protected_verification_paths', schema['required'])
            http_agent.conforms(dict(self.packet(), protected_verification_paths='tests/core.test.js'), schema)
            # The HTTP adapter registers its schemas at process start, with the worker environment.
            code = ('import sys; sys.path.insert(0, sys.argv[1]); import self_hosted; '
                    'assert "protected_verification_paths" in '
                    'self_hosted.artifact_schema("updated-plan-edit-ops-packet")["properties"]')
            subprocess.run([sys.executable, '-I', '-c', code, str(Path(ops.__file__).parent)], check=True)

    def test_answer_cap_exits_without_retrying_the_group_inside_http(self):
        values = {'base_url': 'http://unused.invalid/v1', 'api_key': 'stub', 'model': 'stub'}
        with patch.dict(os.environ, {'UNCLE_UPDATED_PLAN_ANSWER_TOKENS': '6144'}), \
                patch.object(http_agent, 'chat', side_effect=StreamStopped('answer_cap')) as chat:
            with self.assertRaises(StreamStopped):
                http_agent.run_agent(values, 'No investigation', http_agent.Policy(self.root), 32768, turns=3)
            self.assertEqual(chat.call_count, 1)

    def test_tool_turn_cap_delivers_once_after_three_tools(self):
        values = {'base_url': 'http://unused.invalid/v1', 'api_key': 'stub', 'model': 'stub'}
        os.environ['WORKFLOW_SELF_HOSTED_WRITER_SCHEMA_FIRST'] = 'off'  # the tool-loop fallback
        (self.root / 'input').write_text('data')
        responses = []
        for i in range(3):
            responses.append({'choices': [{'message': {'role': 'assistant', 'content': '', 'tool_calls': [
                {'id': str(i), 'type': 'function', 'function': {'name': 'read_file',
                 'arguments': json.dumps({'path': 'input', 'offset': i})}}]}, 'finish_reason': 'tool_calls'}]})
        responses.append({'choices': [{'message': {'role': 'assistant', 'content': json.dumps(self.packet())},
                                        'finish_reason': 'stop'}]})
        with patch.object(http_agent, 'chat', side_effect=responses) as chat:
            text, turns = http_agent.run_agent(values, 'Deliver', http_agent.Policy(self.root), 32768,
                                               turns=3, final_schema=edit_ops_packet())
        self.assertEqual(turns, 4)
        self.assertEqual(json.loads(text), self.packet())
        self.assertIsNone(chat.call_args.args[2])  # closing turn offers no tools

    def test_exhausted_writer_does_not_open_another_schema_repair_loop(self):
        values = {'base_url': 'http://unused.invalid/v1', 'api_key': 'stub', 'model': 'stub'}
        os.environ['WORKFLOW_SELF_HOSTED_WRITER_SCHEMA_FIRST'] = 'off'  # the tool-loop fallback
        (self.root / 'input').write_text('data')
        responses = [
            {'choices': [{'message': {'role': 'assistant', 'content': '', 'tool_calls': [
                {'id': 'read', 'type': 'function', 'function': {'name': 'read_file', 'arguments': '{"path":"input"}'}}]},
                          'finish_reason': 'tool_calls'}]},
            {'choices': [{'message': {'role': 'assistant', 'content': json.dumps(dict(self.packet(), ops='invalid'))},
                          'finish_reason': 'stop'}]}]
        with patch.dict(os.environ, {'UNCLE_UPDATED_PLAN_ANSWER_TOKENS': '4096'}), \
                patch.object(http_agent, 'chat', side_effect=responses) as chat:
            with self.assertRaisesRegex(ValueError, 'exhausted its turns'):
                http_agent.run_agent(values, 'Deliver', http_agent.Policy(self.root), 32768,
                                     turns=1, final_schema=edit_ops_packet())
            self.assertEqual(chat.call_count, 2)
        responses[-1]['choices'][0]['message']['content'] = ''
        with patch.dict(os.environ, {'UNCLE_UPDATED_PLAN_ANSWER_TOKENS': '4096'}), \
                patch.object(http_agent, 'chat', side_effect=responses) as chat:
            with self.assertRaisesRegex(ValueError, 'exhausted its turns'):
                http_agent.run_agent(values, 'Deliver', http_agent.Policy(self.root), 32768,
                                     turns=1, final_schema=edit_ops_packet())
            self.assertEqual(chat.call_count, 2)

    def test_bounded_writer_answers_with_one_schema_constrained_request(self):
        # Run 13: 10 of 22 writers wrote off-schema chat drafts and failed repairing them.
        # With every input prefetched, the packet comes from one grammar-constrained request.
        values = {'base_url': 'http://unused.invalid/v1', 'api_key': 'stub', 'model': 'stub'}
        usage = {'prompt_tokens': 10, 'completion_tokens': 5}
        with patch.dict(os.environ, {'UNCLE_UPDATED_PLAN_ANSWER_TOKENS': '4096'}), \
                patch.object(http_agent, 'chat') as chat, \
                patch.object(http_agent, 'constrained_completion',
                             return_value=(json.dumps(self.packet()), 'stop', usage, 'json_schema')) as constrained:
            text, turns = http_agent.run_agent(values, 'Deliver', http_agent.Policy(self.root), 32768,
                                               turns=3, final_schema=edit_ops_packet())
        self.assertEqual(json.loads(text), self.packet())
        self.assertEqual((turns, chat.call_count, constrained.call_count), (1, 0, 1))
        self.assertEqual(constrained.call_args.kwargs.get('skip', ()), ())  # grammar modes first

    def test_schema_first_is_only_for_bounded_writers_and_can_be_turned_off(self):
        values = {'base_url': 'http://unused.invalid/v1', 'api_key': 'stub', 'model': 'stub'}
        reply = {'choices': [{'message': {'role': 'assistant', 'content': json.dumps(self.packet())},
                              'finish_reason': 'stop'}]}
        for env in ({}, {'UNCLE_UPDATED_PLAN_ANSWER_TOKENS': '4096', 'WORKFLOW_SELF_HOSTED_WRITER_SCHEMA_FIRST': 'off'}):
            with self.subTest(env=env), patch.dict(os.environ, env), \
                    patch.object(http_agent, 'chat', return_value=reply) as chat, \
                    patch.object(http_agent, 'constrained_completion') as constrained:
                text, _ = http_agent.run_agent(values, 'Deliver', http_agent.Policy(self.root), 32768,
                                               turns=3, final_schema=edit_ops_packet())
            self.assertEqual(json.loads(text), self.packet())
            self.assertEqual((chat.call_count, constrained.call_count), (1, 0))

    def test_disposition_assignment_beats_source_pair_and_preserves_contract(self):
        self.assertEqual(self.prepare(), 0)
        result = json.loads((self.directory / 'repaired.json').read_text())
        steps = ops.implementation_steps(pm.model_of(result))
        self.assertNotIn('tests/useKeyboard.test.js', steps[0]['owns'])
        self.assertIn('tests/useKeyboard.test.js', steps[1]['owns'])
        for key in ('verification_commands', 'protected_verification_paths', 'dispositions'):
            self.assertEqual(result[key], self.plan[key])
        self.assertIn('Keep this byte for byte.', result['narrative'])
        self.assertEqual(len(json.loads((self.directory / 'automatic-ops.json').read_text())), 1)

    def test_unique_source_pair_without_disposition(self):
        self.plan['dispositions'] = []
        self.save()
        self.assertEqual(self.prepare(), 0)
        result = json.loads((self.directory / 'repaired.json').read_text())
        self.assertIn('tests/useKeyboard.test.js', ops.implementation_steps(pm.model_of(result))[0]['owns'])

    def test_legacy_inline_steps_with_nested_bullets_like_run12(self):
        self.plan['narrative'] = ('# Plan\n\n## Implementation order\n\n'
            '1. **Core** — Owns: `src/useKeyboard.js`\n  - Creates source.\n'
            '1. Add build script.\n'
            '2. **Unit tests** — Owns: `tests/core.test.js`\n  - Tests every key.\n')
        self.save()
        self.assertEqual(self.prepare(), 0)
        result = json.loads((self.directory / 'repaired.json').read_text())
        repaired = self.root / 'repaired.md'
        repaired.write_text(artifact_json.render_plan(result, protected=True))
        self.assertEqual(unowned_protected_paths(repaired, self.root, self.plan['protected_verification_paths'].splitlines()), [])
        # With canonical plan records the repair edits the step's ownership field; a legacy
        # text-only plan gets the equivalent text edit. Either way it is one small op.
        repair = json.loads((self.directory / 'automatic-ops.json').read_text())
        self.assertEqual(len(repair), 1)
        self.assertIn(repair[0]['op'], ('set_step', 'set_text'))

    def test_ambiguous_ownership_uses_scoped_ops_and_rejects_unrelated_edits(self):
        self.plan['dispositions'] = []
        self.plan['protected_verification_paths'] = 'tests/unknown.test.js'
        self.save()
        self.assertEqual(self.prepare(), 3)
        prompt = (self.directory / 'prompt.md').read_text()
        self.assertIn('tests/unknown.test.js', prompt)
        self.assertNotIn('Keep this byte for byte.', prompt)
        valid = self.packet([{'op': 'set_step', 'id': 'step-2',
                              'fields': {'owns': 'tests/core.test.js, tests/unknown.test.js'}}])
        (self.directory / 'packet.json').write_text(json.dumps(valid) + '\nDone.')
        ops.apply_structure_repair(self.directory, self.root)
        result = json.loads((self.directory / 'repaired.json').read_text())
        self.assertEqual(result['dispositions'], [])
        valid['ops'][0]['fields']['owns'] = 'tests/unknown.test.js'
        (self.directory / 'packet.json').write_text(json.dumps(valid))
        with self.assertRaisesRegex(ValueError, 'unrelated paths'):
            ops.apply_structure_repair(self.directory, self.root)

    def test_conflicting_disposition_steps_are_not_guessed(self):
        self.plan['dispositions'][0]['plan_change'] += ' Or assign it to Step 1.'
        self.save()
        self.assertEqual(self.prepare(), 3)
        self.assertEqual(json.loads((self.directory / 'automatic-ops.json').read_text()), [])


if __name__ == '__main__':
    unittest.main()
