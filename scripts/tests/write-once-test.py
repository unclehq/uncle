#!/usr/bin/env python3
"""Offline write-once delivery, repair and metadata contracts; no model or signer."""
import contextlib
import importlib.util
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts/lib'))
import http_agent as agent
import self_hosted as hosted
import self_hosted_http as transport
import updated_plan_ops as ops
import updated_plan_synthesis_prompt as synthesis
import worker_schemas
from plan_patch import apply_patch

spec = importlib.util.spec_from_file_location('ops_fixture', Path(__file__).with_name('updated-plan-ops-test.py'))
fixture = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fixture)


class WriteOnce(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        env = patch.dict(os.environ, {'UNCLE_CONFIG': str(self.root / 'absent'),
                                     'UNCLE_PROJECT_ROOT': str(self.root)}, clear=True)
        env.start()
        self.addCleanup(env.stop)
        self.output = io.StringIO()
        capture = contextlib.redirect_stdout(self.output)
        capture.__enter__()
        self.addCleanup(capture.__exit__, None, None, None)
        self.values = {'model': 'stub', 'base_url': 'http://unused.invalid/v1', 'api_key': 'never-used'}

    def call(self, name, **args):
        return {'id': 'stub', 'type': 'function', 'function': {'name': name, 'arguments': json.dumps(args, ensure_ascii=False)}}

    def reply(self, text='done', calls=(), tokens=1, reason='stop'):
        return {'choices': [{'message': {'role': 'assistant', 'content': text, 'tool_calls': list(calls)},
                             'finish_reason': reason}], 'usage': {'prompt_tokens': 10, 'completion_tokens': tokens}}

    def events(self):
        return [json.loads(line) for line in self.output.getvalue().splitlines() if line.startswith('{')]

    def test_planner_one_write_then_precise_edit_and_identical_document(self):
        path = '.uncle/workflow/project-plan-investigation.md'
        bad = '# Project plan\n\nAll required content stays.\n\n## Verification commands\n```sh\n# TODO\n```\n'
        good = bad.replace('# TODO', 'python3 tests/check.py')
        with patch.dict(os.environ, UNCLE_STATUS_STAGE='project-plan-investigate'):
            prompt, policy, _, _, _, _ = hosted._http_setup('agent', {}, 'Plan.', self.root, True, None)
            replies = [self.reply(calls=[self.call('write_file', path=path, content=bad)]),
                       self.reply(calls=[self.call('read_file', path=path)]),
                       self.reply(calls=[self.call('edit_file', path=path, old_string='# TODO', new_string='python3 tests/check.py')]),
                       self.reply('Complete.')]
            seen = []
            def chat(*args):
                messages = args[2]
                seen.append(json.loads(json.dumps(messages)))
                if len(seen) == 2:
                    self.assertFalse((self.root / path).exists())
                return replies.pop(0)
            with patch.object(agent, 'interruptible_chat', side_effect=chat):
                agent.run_agent(self.values, prompt, policy, 4096)
        self.assertEqual((self.root / path).read_text(), good)
        hosted.validate_plan(good, protected=False)
        names = [tool['name'] for event in self.events() for tool in event['tools']]
        self.assertEqual(names.count('write_file'), 1)
        self.assertEqual(names.count('edit_file'), 1)
        feedback = seen[1][-1]['content']
        self.assertIn('verification commands', feedback)
        self.assertIn('edit_file', feedback)
        self.assertNotIn('All required content stays.', feedback)
        self.assertIn('# TODO', seen[2][-1]['content'])
        self.assertIn('draft already supplied', agent.run_tool(policy, 'write_file', {'path': path, 'content': good}))
        self.assertEqual((self.root / path).read_text(), good)

    def test_bad_planner_cannot_finish_or_replace_valid_delivery(self):
        path = '.uncle/workflow/project-plan-investigation.md'
        good = '# Project plan\n## Verification commands\n```sh\ntrue\n```\n'
        policy = agent.Policy(self.root, write=True, drafts={path: lambda s: hosted.validate_plan(s, False)})
        replies = [self.reply(calls=[self.call('write_file', path=path, content=good)]),
                   self.reply(calls=[self.call('edit_file', path=path, old_string='true', new_string='# skipped')]), self.reply()]
        with patch.object(agent, 'interruptible_chat', side_effect=replies):
            with self.assertRaisesRegex(ValueError, 'Unrepaired draft.*verification commands'):
                agent.run_agent(self.values, 'plan', policy, 4096)
        self.assertEqual((self.root / path).read_text(), good)

    def test_canonical_plan_retry_uses_edits_and_preserves_checks(self):
        bad = dict(schema='uncle.artifact/v1', kind='plan', narrative='Complete plan.', verification_commands='# missing')
        path = '.uncle/workflow/plan-repair.json'
        replies = [self.reply(calls=[self.call('read_file', path=path)]),
                   self.reply(calls=[self.call('edit_file', path=path, old_string='# missing', new_string='python3 tests/check.py')]),
                   self.reply('Repaired.')]
        with patch.object(hosted, 'run_http_agent', return_value=(json.dumps(bad), 1)) as initial, \
                patch.object(agent, 'interruptible_chat', side_effect=replies) as repair:
            hosted.run_opencode('agent', self.values, 'Make a plan.', self.root, stage='project-plan')
        self.assertEqual(initial.call_count, 1)
        self.assertEqual(repair.call_count, 3)
        self.assertIn('Targeted validation repair', repair.call_args.args[2][1]['content'])
        hosted.validate_plan((self.root / '.uncle/docs/PROJECT_PLAN.md').read_text(), False)
        plan = json.loads((self.root / '.uncle/workflow/documents/PROJECT_PLAN.json').read_text())
        self.assertEqual(plan['narrative'], bad['narrative'])
        self.assertEqual(plan['verification_commands'], 'python3 tests/check.py')

    def test_schema_invalid_plan_is_repaired_without_regeneration(self):
        bad = dict(schema='uncle.artifact/v1', kind='plan', narrative='Keep exactly.', verification_commands=42)
        path = '.uncle/workflow/http-answer-repair.json'
        replies = [self.reply(json.dumps(bad)),
                   self.reply(calls=[self.call('edit_file', path=path, old_string='42', new_string='"true"')]),
                   self.reply('Fixed.')]
        with patch.object(agent, 'interruptible_chat', side_effect=replies), \
                patch.object(agent, 'constrained_completion', side_effect=AssertionError('full regeneration')):
            answer, requests = agent.run_agent(self.values, 'plan', agent.Policy(self.root), 4096,
                                               final_schema=hosted.artifact_schema('plan'), final_name='plan')
        self.assertEqual(json.loads(answer), dict(bad, verification_commands='true'))
        self.assertEqual(requests, 3)
        self.assertEqual([t['name'] for e in self.events() for t in e['tools']], ['edit_file'])

    def test_edit_writer_generates_ops_once_and_assembly_is_identical(self):
        narrative = fixture.NARRATIVE + '\n## 4. Untouched reference\n\n' + 'Preserve every requirement. ' * 2000 + '\n'
        plan = dict(fixture.PLAN, narrative=narrative)
        base = self.root / 'base.md'
        base.write_text(synthesis.prompt(plan, {'findings': []}, None))
        prompt_file = self.root / 'writer.md'
        ops.write_prompt(base, ['AR-1', 'AR-2'], prompt_file)
        packet = {'schema': 'uncle.artifact/v1', 'kind': worker_schemas.EDIT_OPS_KIND,
                  'dispositions': [fixture.row('AR-1'), fixture.row('AR-2')],
                  'ops': [fixture.set_fields('B-1', failure='Shows NaN'), fixture.set_fields('B-2', result='Digit replaced')]}
        delivery = self.root / '.uncle/workflow/edits/1.json'
        with patch.dict(os.environ, UNCLE_ARTIFACT_DELIVERY=str(delivery), UNCLE_STATUS_STAGE='updated-plan-worker-edits-1'), \
                patch.object(agent, 'interruptible_chat', return_value=self.reply(json.dumps(packet), tokens=125)) as chat, \
                patch.object(agent, 'constrained_completion', side_effect=AssertionError('second generation')):
            answer, turns = hosted.run_opencode('agent', self.values, prompt_file.read_text(), self.root)
        self.assertEqual((turns, chat.call_count), (1, 1))
        self.assertEqual(json.loads(answer), packet)
        self.assertEqual(json.loads(delivery.read_text()), packet)
        self.assertEqual({t['function']['name'] for t in chat.call_args.args[3]}, {'read_file', 'list_dir', 'grep'})
        self.assertIn('HTTP delivery contract', chat.call_args.args[2][1]['content'])
        self.assertNotIn('narrative', packet)
        self.assertLess(len(json.dumps(packet['ops'])), 200)
        (self.root / 'plan.json').write_text(json.dumps(plan))
        (delivery.parent / 'slices.tsv').write_text('1\tAR-1,AR-2\n')
        merged = self.root / 'merged.json'
        ops.merge(self.root / 'plan.json', delivery.parent / 'slices.tsv', delivery.parent, merged)
        result = json.loads(merged.read_text())
        # B-2 columns are trigger, result, failure; replace only the result.
        expected = narrative.replace('| Display unchanged |', '| Shows NaN |').replace('| User presses a key | Same as B-1 |', '| User presses a key | Digit replaced |')
        self.assertEqual(apply_patch(narrative, result['patch']), expected)
        self.assertEqual(result['verification_commands'], fixture.COMMANDS)
        self.assertEqual(result['protected_verification_paths'], fixture.PLAN['protected_verification_paths'])

    def test_invalid_ops_packet_is_not_published(self):
        packet = {'schema': 'uncle.artifact/v1', 'kind': worker_schemas.EDIT_OPS_KIND, 'ops': 'wrong', 'dispositions': []}
        delivery = self.root / '.uncle/workflow/edits/1.json'
        with patch.dict(os.environ, UNCLE_ARTIFACT_DELIVERY=str(delivery)), \
                patch.object(agent, 'interruptible_chat', return_value=self.reply(json.dumps(packet))), \
                patch.object(agent, 'constrained_completion', return_value=(json.dumps(packet), 'stop', {}, 'json_schema')):
            with self.assertRaisesRegex(ValueError, 'violates the artifact schema'):
                hosted.run_opencode('agent', self.values, json.dumps(packet), self.root)
        self.assertFalse(delivery.exists())


if __name__ == '__main__':
    unittest.main()
