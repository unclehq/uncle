#!/usr/bin/env python3
"""Bounded writer failures never open prompt fallback or a schema-repair tool loop."""
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'lib'))
import http_agent as agent
import self_hosted_http as transport
import self_hosted
import updated_plan_ops as ops
from self_hosted_performance import ACTIVE
from self_hosted_stream import StreamStopped
from worker_schemas import edit_ops_packet


class BoundedWriter(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        env = patch.dict(os.environ, {
            'UNCLE_CONFIG': str(self.root / 'config'),
            'UNCLE_PROJECT_ROOT': str(self.root),
            'UNCLE_STATUS_STAGE': 'updated-plan-worker-edits-14',
            'UNCLE_UPDATED_PLAN_ANSWER_TOKENS': '4096',
            'WORKFLOW_SELF_HOSTED_RESULT_REUSE': 'off',
        }, clear=True)
        env.start()
        self.addCleanup(env.stop)
        self.values = {'base_url': 'http://unused.invalid/v1', 'api_key': 'stub', 'model': 'stub'}
        self.packet = {'schema': 'uncle.artifact/v1', 'kind': 'updated-plan-edit-ops-packet',
                       'dispositions': [], 'ops': []}
        self.valid = (json.dumps(self.packet), 'stop', {}, 'json_schema')
        chat = patch.object(agent, 'chat', side_effect=AssertionError('unexpected tool/repair loop'))
        self.chat = chat.start()
        self.addCleanup(chat.stop)
        network = patch.object(transport, 'compatible_post', side_effect=AssertionError('unexpected network'))
        network.start()
        self.addCleanup(network.stop)

    def run_writer(self, **kwargs):
        self.chat.reset_mock()
        return agent.run_agent(self.values, 'Deliver the packet for AR-014.', agent.Policy(self.root),
                               32768, turns=3, final_schema=edit_ops_packet(),
                               final_name='updated_plan_edit_ops_packet', **kwargs)

    def assert_no_repair(self):
        self.chat.assert_not_called()
        self.assertFalse((self.root / '.uncle/workflow/http-answer-repair.json').exists())

    def test_run15_answer_cap_never_reaches_invalid_prompt_draft(self):
        # Run 15 writer 14: ~16 KB capped grammar output, then an invalid ~1.4 KB
        # prompt draft entered repair_answer while all its siblings had finished.
        skips = []
        def completion(*args, **kwargs):
            skips.append(kwargs.get('skip', ()))
            if skips[-1]:
                return '{"ops":' + ' ' * 1400, 'stop', {}, 'prompt'
            raise StreamStopped('answer_cap', byte_count=16384, usage={'completion_tokens': 4096})
        with patch.object(agent, 'constrained_completion', side_effect=completion):
            with self.assertRaisesRegex(StreamStopped, 'answer_cap'):
                self.run_writer()
        self.assertIn(len(skips), (1, 2))
        self.assertTrue(all(skip == () for skip in skips))
        self.assert_no_repair()

    def test_cap_retry_can_deliver_a_valid_grammar_packet(self):
        with patch.object(agent, 'constrained_completion',
                          side_effect=[StreamStopped('answer_cap'), self.valid]) as completion:
            text, count = self.run_writer()
        self.assertEqual((json.loads(text), count), (self.packet, 2))
        self.assertEqual([call.kwargs.get('skip', ()) for call in completion.call_args_list], [(), ()])
        self.assert_no_repair()

    def test_repeated_stream_failures_stop_after_at_most_two_grammar_requests(self):
        for reason in ('answer_cap', 'repetition', 'whitespace', 'incomplete_stream', 'learned_budget'):
            with self.subTest(reason=reason), patch.object(agent, 'constrained_completion',
                    side_effect=StreamStopped(reason)) as completion:
                with self.assertRaisesRegex(StreamStopped, reason):
                    self.run_writer()
                self.assertIn(completion.call_count, (1, 2))
                self.assertTrue(all(call.kwargs.get('skip', ()) == () for call in completion.call_args_list))
                self.assert_no_repair()

    def test_mixed_runaways_share_one_grammar_retry(self):
        for reasons in (('repetition', 'answer_cap'), ('whitespace', 'repetition'), ('answer_cap', 'whitespace')):
            with self.subTest(reasons=reasons), patch.object(agent, 'constrained_completion',
                    side_effect=[StreamStopped(reasons[0]), StreamStopped(reasons[1]), self.valid]) as completion:
                with self.assertRaisesRegex(StreamStopped, reasons[1]):
                    self.run_writer()
                self.assertEqual(completion.call_count, 2)
                self.assert_no_repair()

    def test_length_never_falls_back_to_prompt(self):
        for text in (' ' * 4096, '{"ops":[', self.valid[0]):
            with self.subTest(text=text[:30]), patch.object(agent, 'save_truncated', return_value=''), \
                    patch.object(agent, 'constrained_completion',
                                 return_value=(text, 'length', {}, 'json_schema')) as completion:
                with self.assertRaisesRegex(transport.OutputTruncated, 'limit|length|incomplete'):
                    self.run_writer()
                self.assertIn(completion.call_count, (1, 2))
                self.assertTrue(all(call.kwargs.get('skip', ()) == () for call in completion.call_args_list))
                self.assert_no_repair()

    def test_invalid_json_fails_locally_without_repair(self):
        for text in ('{"ops":', self.valid[0] + '\n' + self.valid[0], 'not JSON', ''):
            with self.subTest(text=text), patch.object(agent, 'constrained_completion',
                    return_value=(text, 'stop', {}, 'json_schema')) as completion:
                with self.assertRaisesRegex(ValueError, 'not valid JSON|invalid JSON'):
                    self.run_writer()
                self.assertEqual(completion.call_count, 1)
                self.assert_no_repair()

    def test_off_schema_packet_fails_locally_without_repair(self):
        for packet in (dict(self.packet, ops='invalid'), {}, dict(self.packet, extra=True)):
            with self.subTest(packet=packet), patch.object(agent, 'constrained_completion',
                    return_value=(json.dumps(packet), 'stop', {}, 'json_schema')) as completion:
                with self.assertRaisesRegex(ValueError, 'schema'):
                    self.run_writer()
                self.assertEqual(completion.call_count, 1)
                self.assert_no_repair()

    def test_invalid_output_after_grammar_retry_cannot_enter_repair(self):
        with patch.object(agent, 'constrained_completion', side_effect=[StreamStopped('repetition'),
                          ('{"ops":', 'stop', {}, 'json_schema')]) as completion:
            with self.assertRaisesRegex(ValueError, 'not valid JSON|invalid JSON'):
                self.run_writer()
        self.assertEqual(completion.call_count, 2)
        self.assert_no_repair()

    def test_failure_restores_parent_budget_and_records_usage(self):
        budget = Mock(soft=False, enabled=True)
        token = ACTIVE.set(budget)
        self.addCleanup(ACTIVE.reset, token)
        usage, seen = {}, []
        def completion(*args, **kwargs):
            seen.append(ACTIVE.get())
            raise StreamStopped('answer_cap', usage={'prompt_tokens': 10, 'completion_tokens': 4096})
        with patch.object(agent, 'constrained_completion', side_effect=completion):
            with self.assertRaisesRegex(StreamStopped, 'answer_cap'):
                self.run_writer(usage=usage)
        self.assertTrue(all(value is None for value in seen))
        self.assertIs(ACTIVE.get(), budget)
        self.assertEqual(usage['output_tokens'], 4096 * len(seen))
        self.assertEqual(usage['input_tokens'], 10 * len(seen))
        self.assert_no_repair()

    def test_success_retains_packet_and_one_request(self):
        with patch.object(agent, 'constrained_completion', return_value=self.valid) as completion:
            text, count = self.run_writer()
        self.assertEqual((text, count), (self.valid[0], 1))
        self.assertEqual(completion.call_count, 1)
        self.assert_no_repair()

    def test_unbounded_stage_retains_prompt_fallback(self):
        del os.environ['UNCLE_UPDATED_PLAN_ANSWER_TOKENS']
        with patch.object(agent, 'save_truncated', return_value=''), \
                patch.object(agent, 'constrained_completion', side_effect=[
                    ('{', 'length', {}, 'json_schema'), self.valid]) as completion:
            text, count = agent.run_agent(self.values, 'Deliver.', agent.Policy(self.root), 32768,
                                          turns=0, final_schema=edit_ops_packet())
        self.assertEqual((json.loads(text), count), (self.packet, 2))
        self.assertEqual([call.kwargs.get('skip', ()) for call in completion.call_args_list],
                         [(), transport.GRAMMAR_MODES])

    def test_config_opt_out_and_environment_override_preserve_tool_path(self):
        (self.root / 'config').write_text('self-hosted.writer-schema-first off\n')
        reply = {'choices': [{'message': {'role': 'assistant', 'content': self.valid[0]}, 'finish_reason': 'stop'}]}
        with patch.object(agent, 'chat', return_value=reply) as chat, \
                patch.object(agent, 'constrained_completion', return_value=self.valid) as completion:
            self.assertEqual(json.loads(self.run_writer()[0]), self.packet)
            self.assertEqual((chat.call_count, completion.call_count), (1, 0))
            with patch.dict(os.environ, WORKFLOW_SELF_HOSTED_WRITER_SCHEMA_FIRST='on'):
                self.assertEqual(json.loads(self.run_writer()[0]), self.packet)
            self.assertEqual((chat.call_count, completion.call_count), (1, 1))

    def resolver_prompt(self):
        return ops.resolver_prompt({'id': 'G1', 'kind': 'ops',
            'context': '{"B-1":{"failure":"unchanged"}}',
            'edits': [{'writer': '1', 'op': {'op': 'set_fields', 'id': 'B-1', 'fields': {'failure': 'first'}}},
                      {'writer': '2', 'op': {'op': 'set_fields', 'id': 'B-1', 'fields': {'failure': 'second'}}}]},
            [{'writer': '1', 'plan_change': 'Keep keyboard behavior.'},
             {'writer': '2', 'plan_change': 'Handle missing input.'}])

    def test_resolver_adapter_uses_prefetched_schema_once_and_preserves_packet(self):
        packet = {'schema': 'uncle.artifact/v1', 'kind': 'updated-plan-resolution-ops-packet',
                  'resolutions': [{'group': 'G1', 'ops': [
                      {'op': 'set_fields', 'id': 'B-1', 'fields': {'failure': 'MERGED'}}]}]}
        for stage in ('updated-plan-worker-resolve-G1', 'updated-change-plan-worker-resolve-G1-retry'):
            with self.subTest(stage=stage), patch.dict(os.environ, {
                    'UNCLE_STATUS_STAGE': stage, 'UNCLE_ARTIFACT_DELIVERY': str(self.root / 'delivery.json')}), \
                    patch.object(agent, 'constrained_completion',
                                 return_value=(json.dumps(packet), 'stop', {}, 'json_schema')) as completion:
                text, count = self_hosted.run_opencode('agent', self.values, self.resolver_prompt(), self.root, stage=stage)
                self.assertEqual((json.loads(text), count), (packet, 1))
                self.assertEqual((self.root / 'delivery.json').read_text(), text)
                self.assertEqual(completion.call_count, 1)
                self.assertEqual(completion.call_args.args[2:4],
                                 (self_hosted.artifact_schema('updated-plan-resolution-ops-packet'),
                                  'updated_plan_resolution_ops_packet'))
                request = json.dumps(completion.call_args.args[1])
                for expected in ('unchanged', 'first', 'second', 'Keep keyboard behavior.', 'Handle missing input.'):
                    self.assertIn(expected, request)
                self.assert_no_repair()

    def test_resolver_failure_never_publishes_or_enters_repair(self):
        delivery = self.root / 'delivery.json'
        delivery.write_text('previous packet')
        failures = [(StreamStopped('answer_cap'), 'answer_cap'),
                    (('{"resolutions":', 'stop', {}, 'json_schema'), 'not valid JSON'),
                    (('{"resolutions":"invalid"}', 'stop', {}, 'json_schema'), 'schema')]
        for stage in ('updated-plan-worker-resolve-G1', 'updated-change-plan-worker-resolve-G1'):
            for result, cause in failures:
                def completion(*args, **kwargs):
                    if isinstance(result, Exception):
                        raise result
                    return result
                with self.subTest(stage=stage, cause=cause), patch.dict(os.environ, {
                        'UNCLE_STATUS_STAGE': stage, 'UNCLE_ARTIFACT_DELIVERY': str(delivery)}), \
                        patch.object(agent, 'constrained_completion', side_effect=completion) as request:
                    with self.assertRaisesRegex(ValueError, cause):
                        self_hosted.run_opencode('agent', self.values, self.resolver_prompt(), self.root, stage=stage)
                    self.assertEqual(delivery.read_text(), 'previous packet')
                    self.assertIn(request.call_count, (1, 2))
                    self.assert_no_repair()


if __name__ == '__main__':
    unittest.main()
