#!/usr/bin/env python3
"""Hermetic budget/reuse regressions. Loopback stubs only; no Git or credentials."""
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('stream_fixture', Path(__file__).with_name('self-hosted-capture-stream-test.py'))
fixture = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fixture)
agent, transport = fixture.agent, fixture.transport
delta, call, reply, SCHEMA = fixture.delta, fixture.call, fixture.reply, fixture.SCHEMA
import self_hosted_performance as perf


class BudgetReuse(unittest.TestCase):
    setUp = fixture.CaptureStream.setUp
    serve = fixture.CaptureStream.serve

    def run_packet(self, values, prompt='Go', **kwargs):
        return agent.run_agent(values, prompt, agent.Policy(self.root), 32768,
                               final_schema=SCHEMA, final_name='updated_plan_edit_ops_packet', **kwargs)

    def reuse(self, **changes):
        args = dict(values=self.values, prompt='Go', policy=agent.Policy(self.root), schema=SCHEMA,
                    name='packet', limit=32768, turns=80, seconds=3600, stage=None)
        args.update(changes)
        return perf.Reuse(**args)

    def events(self, name):
        return [e for line in self.output.getvalue().splitlines() if line.startswith('{')
                for e in [json.loads(line)] if e.get('type') == 'self_hosted_' + name]

    def test_defaults_history_p90_caps_and_outcomes(self):
        for name, expected in [('edit_ops', 1024), ('review_worker_packet', 2048),
                               ('plan_outline', 4096), ('plan', 8192)]:
            self.assertEqual(perf.Budget(self.root, name, 32768).expected, expected)
        with patch.dict(os.environ, UNCLE_STATUS_STAGE='updated-plan-worker-edits-1'):
            for tokens in range(100, 1100, 100):
                b = perf.Budget(self.root, 'edit_ops', 32768)
                b.observe({'completion_tokens': tokens}, 'stop')
                b.finish('packet', 'valid')
            b = perf.Budget(self.root, 'edit_ops', 32768)
            self.assertEqual((b.expected, b.threshold), (900, 1800))
            b.observe({'completion_tokens': 30000}, 'stop')
            b.finish('', 'invalid')
            b.intervene('test')
            b.finish('packet', 'valid')
            self.assertEqual(perf.Budget(self.root, 'edit_ops', 700).expected, 700)
        rows = perf.read_json(perf.location(self.root) / 'history.json', [])
        self.assertEqual(rows[-1]['outcome'], 'retried')
        self.assertEqual(rows[-1]['deliverable_bytes'], 6)
        self.assertEqual(rows[-2]['outcome'], 'invalid')

    def runaway(self, content=False):
        # Unique text avoids the independent repetition/whitespace hard guards.
        for i in range(1000):
            fragment = ('word%04d ' % i) * 2
            item = delta(fragment) if content else {'choices': [{'delta': {'reasoning_content': fragment}}]}
            yield item

    def test_stream_budget_soft_then_success_no_tools(self):
        server = self.serve(lambda body: list(self.runaway()) if len(server.requests) == 1 else
                            [delta('{"ok":true}', reason='stop'), '[DONE]'])
        text, turns = self.run_packet(server.values)
        self.assertEqual((json.loads(text), turns), ({'ok': True}, 2))
        self.assertNotIn('tools', server.requests[-1])
        self.assertIn('only the final', server.requests[-1]['messages'][-1]['content'])
        self.assertEqual([e['action'] for e in self.events('budget_intervention')], ['soft'])
        self.assertTrue(server.disconnected.wait(1))
        rows = perf.read_json(perf.location(self.root) / 'history.json', [])
        self.assertTrue(rows[0]['estimated_output_tokens'])
        self.assertEqual(rows[0]['outcome'], 'retried')

    def test_soft_then_hard_output_cap(self):
        server = self.serve(lambda body: list(self.runaway()) if len(server.requests) == 1 else
                            [delta('{"ok":true}', reason='length'), '[DONE]'])
        with patch.object(agent, 'save_truncated', return_value=''), self.assertRaises(transport.OutputTruncated):
            self.run_packet(server.values)
        self.assertEqual(len(server.requests), 2)
        self.assertEqual([e['action'] for e in self.events('budget_intervention')], ['soft', 'hard'])

    def test_soft_then_whitespace_hard_stop_does_not_retry_again(self):
        server = self.serve(lambda body: list(self.runaway()) if len(server.requests) == 1 else [delta(' ' * 2000)])
        with self.assertRaises(transport.StreamStopped):
            self.run_packet(server.values)
        self.assertEqual(len(server.requests), 2)
        self.assertEqual([e['action'] for e in self.events('budget_intervention')], ['soft', 'hard'])

    def test_complete_packet_before_budget_stop_is_captured_once(self):
        server = self.serve([delta('{"ok":true}')] + list(self.runaway()))
        text, turns = self.run_packet(server.values)
        self.assertEqual(json.loads(text), {'ok': True})
        self.assertEqual(len(server.requests), 1)
        self.assertEqual(turns, 1)
        self.assertTrue(self.events('capture'))

    def test_final_only_budget_and_capture(self):
        server = self.serve([delta('{"ok":true}')] + list(self.runaway()))
        text, count = agent.run_document(server.values, 'Go', self.root, SCHEMA,
                                         'edit_ops', 32768, explore_first=False)
        self.assertEqual((json.loads(text), count), ({'ok': True}, 1))

    def test_final_budget_gets_one_retry_even_after_grammar_health_fallback(self):
        server = self.serve(lambda body: list(self.runaway()) if len(server.requests) == 1 else
                            [delta('{"ok":true}', reason='stop'), '[DONE]'])
        with patch.dict(os.environ, WORKFLOW_SELF_HOSTED_BUDGET_MAX_TOKENS='512'), \
                patch.object(agent, 'constraint_health', return_value={'whitespace_runaways': 2}):
            text, count = agent.run_document(server.values, 'Go', self.root, SCHEMA,
                                             'review_worker_packet', 32768, explore_first=False)
        self.assertEqual((json.loads(text), count), ({'ok': True}, 2))
        self.assertEqual(len(self.events('budget_intervention')), 1)

    def test_document_capture_after_budget_stop_uses_write_validator(self):
        server = self.serve([delta(fixture.PLAN)] + list(self.runaway()))
        policy = fixture.CaptureStream.policy(self)
        with patch.dict(os.environ, WORKFLOW_SELF_HOSTED_BUDGET_MAX_TOKENS='512'):
            agent.run_agent(server.values, 'Plan', policy, 32768)
        self.assertEqual((self.root / fixture.PATH).read_text(), fixture.PLAN)
        self.assertEqual(len(server.requests), 1)

    def test_prior_valid_delivery_is_not_regenerated_after_soft_stop(self):
        policy = fixture.CaptureStream.policy(self)
        policy.writable = set(policy.draft_checks)
        agent.run_tool(policy, 'write_file', {'path': fixture.PATH, 'content': fixture.PLAN})
        server = self.serve(list(self.runaway()))
        with patch.dict(os.environ, WORKFLOW_SELF_HOSTED_BUDGET_MAX_TOKENS='512'):
            _, turns = agent.run_agent(server.values, 'Plan', policy, 32768)
        self.assertEqual((turns, len(server.requests)), (1, 1))
        self.assertEqual((self.root / fixture.PATH).read_text(), fixture.PLAN)

    def test_repeated_reads_stop_at_three_then_final(self):
        (self.root / 'input.txt').write_text('same bytes')
        server = self.serve(lambda body: [delta(calls=[dict(call('read_file', path='input.txt'), index=0)], reason='tool_calls'), '[DONE]']
                            if body.get('tools') else [delta('{"ok":true}', reason='stop'), '[DONE]'])
        text, turns = self.run_packet(server.values)
        self.assertEqual((json.loads(text), turns), ({'ok': True}, 4))
        self.assertEqual(self.events('budget_intervention')[0]['reason'], 'repeated_tools_without_progress')

    def test_repeated_loop_ignoring_final_request_fails(self):
        server = self.serve([delta(calls=[dict(call('list_dir'), index=0)], reason='tool_calls'), '[DONE]'])
        with self.assertRaisesRegex(ValueError, 'no progress'):
            self.run_packet(server.values)
        self.assertEqual(len(server.requests), 4)

    def test_changed_tool_result_is_progress(self):
        b = perf.Budget(self.root, 'ops', 4096)
        for result in range(10):
            self.assertFalse(b.repeated([['read_file', {'path': 'x'}, str(result)]]))
        self.assertFalse(b.repeated([['read_file', {'path': 'x'}, '9']]))
        self.assertTrue(b.repeated([['read_file', {'path': 'x'}, '9']]))

    def test_exact_reuse_streams_validates_and_no_model_request(self):
        server = self.serve()
        self.assertEqual(self.run_packet(server.values)[1], 1)
        with patch.object(agent, 'conforms', wraps=agent.conforms) as validator, \
                patch('self_hosted_stream.assemble', wraps=fixture.transport.assemble_stream) as stream:
            text, turns = self.run_packet(server.values)
        self.assertEqual((json.loads(text), turns, len(server.requests)), ({'ok': True}, 0, 1))
        self.assertTrue(validator.called)
        self.assertTrue(stream.called)
        self.assertEqual(len(self.events('reuse')), 1)

    def test_reuse_publication_still_runs_driver_and_validator(self):
        hosted = fixture.hosted
        packet = '{"schema":"uncle.artifact/v1","kind":"updated-plan-edit-ops-packet","dispositions":[],"ops":[],"commands_replace":[]}'
        server = self.serve([delta(packet, reason='stop'), '[DONE]'])
        target = self.root / '.uncle/workflow/artifact-delivery/result.json'
        target.parent.mkdir(parents=True)
        target.write_text(packet)
        with patch.dict(os.environ, UNCLE_ARTIFACT_DELIVERY=str(target)), \
                patch.object(agent, 'conforms', wraps=agent.conforms) as check:
            hosted.run_opencode('agent', server.values, packet, self.root)
            # A stable existing delivery is part of the exact input snapshot.
            hosted.run_opencode('agent', server.values, packet, self.root)
            before = check.call_count
            with patch.object(Path, 'write_text', autospec=True, side_effect=Path.write_text) as publish:
                hosted.run_opencode('agent', server.values, packet, self.root)
            self.assertGreater(check.call_count, before)
            self.assertTrue(any(args.args[0] == target for args in publish.call_args_list))
        self.assertEqual(json.loads(target.read_text()), json.loads(packet))
        self.assertTrue(self.events('reuse'))

    def test_identity_sensitive_to_all_contract_fields_but_not_key(self):
        base = self.reuse().key
        self.assertIsNotNone(base)
        for change in [dict(prompt='Go\n'), dict(values=dict(self.values, model='other')),
                       dict(values=dict(self.values, base_url='http://other.invalid/v1')),
                       dict(values=dict(self.values, effort='high')),
                       dict(values=dict(self.values, _request_options={'top_p': .9})),
                       dict(schema=dict(SCHEMA, additionalProperties=False)), dict(limit=1000),
                       dict(policy=agent.Policy(self.root, shell=True)), dict(name='different'), dict(turns=3)]:
            with self.subTest(change=change):
                self.assertNotEqual(self.reuse(**change).key, base)
        self.assertEqual(self.reuse(values=dict(self.values, api_key='changed-secret')).key, base)

    def test_input_bytes_add_delete_and_generated_untracked_files_invalidate(self):
        for name in ('untracked.txt', '.uncle/docs/PLAN.md', '.uncle/workflow/input.json'):
            file = self.root / name
            file.parent.mkdir(parents=True, exist_ok=True)
            file.write_text('one')
            cache = self.reuse()
            cache.put('{"ok":true}')
            self.assertIsNotNone(self.reuse().get())
            info = file.stat()
            file.write_text('two')
            os.utime(file, ns=(info.st_atime_ns, info.st_mtime_ns))
            self.assertIsNone(self.reuse().get())
            file.unlink()
            self.assertIsNone(self.reuse().get())

    def test_changed_dynamic_read_input_misses(self):
        (self.root / 'input.txt').write_text('first')
        server = self.serve(lambda body: [delta(calls=[dict(call('read_file', path='input.txt'), index=0)], reason='tool_calls'), '[DONE]']
                            if len(body['messages']) == 2 else [delta('{"ok":true}', reason='stop'), '[DONE]'])
        self.run_packet(server.values)
        self.assertEqual(self.run_packet(server.values)[1], 0)
        (self.root / 'input.txt').write_text('second')
        self.assertGreater(self.run_packet(server.values)[1], 0)

    def test_midflight_mutation_never_saves_stale_result(self):
        cache = self.reuse()
        (self.root / 'new.txt').write_text('changed while generating')
        cache.put('{"ok":true}')
        self.assertIsNone(cache.get())

    def test_transient_read_then_revert_is_not_cached(self):
        file = self.root / 'input.txt'
        file.write_text('original')
        policy = agent.Policy(self.root)
        cache = self.reuse(policy=policy)
        file.write_text('transient input')
        agent.run_tool(policy, 'read_file', {'path': 'input.txt'})
        file.write_text('original')
        cache.put('{"ok":true}')
        self.assertIsNone(cache.get())

    def test_runner_telemetry_churn_does_not_prevent_exact_reuse(self):
        logs = self.root / '.uncle/workflow/logs'
        logs.mkdir(parents=True)
        status = self.root / '.uncle/workflow/status.jsonl'
        status.write_text('before')
        def script(body):
            (logs / 'step.jsonl').write_text('telemetry emitted during the turn')
            status.write_text('usage')
            return [delta('{"ok":true}', reason='stop'), '[DONE]']
        server = self.serve(script)
        with patch.dict(os.environ, UNCLE_STATUS_FILE=str(status)):
            self.assertEqual(self.run_packet(server.values)[1], 1)
            (logs / 'step.jsonl').write_text('new telemetry')
            self.assertEqual(self.run_packet(server.values)[1], 0)
        self.assertEqual(len(server.requests), 1)

    def test_referenced_or_observed_diagnostics_are_never_reused(self):
        file = self.root / '.uncle/workflow/logs/input.txt'
        file.parent.mkdir(parents=True)
        file.write_text('task input')
        self.assertIsNone(self.reuse(prompt='Read `.uncle/workflow/logs/input.txt`').key)
        for tool, arguments in [('read_file', {'path': '.uncle/workflow/logs/input.txt'}),
                                ('list_dir', {'path': '.uncle/workflow'}), ('grep', {'pattern': 'task'})]:
            policy = agent.Policy(self.root)
            cache = self.reuse(policy=policy)
            result = agent.run_tool(policy, tool, arguments)
            policy.reuse_observations.append((tool, arguments, perf.digest(result.encode())))
            cache.put('{"ok":true}')
            self.assertIsNone(cache.get())

    def test_invalid_cached_schema_is_a_miss_not_a_validator_bypass(self):
        server = self.serve()
        self.run_packet(server.values)
        files = [p for p in perf.location(self.root).glob('*.json') if p.name != 'history.json']
        self.assertEqual(len(files), 1)
        text = '{"ok":"wrong type"}'
        perf.atomic(files[0], dict(text=text, digest=perf.digest(text.encode())))
        self.assertEqual(self.run_packet(server.values)[1], 1)
        self.assertEqual(len(server.requests), 2)
        self.assertFalse(self.events('reuse'))

    def test_partial_tool_is_not_executed_at_budget_stop(self):
        def script(body):
            if len(server.requests) > 1:
                return [delta('{"ok":true}', reason='stop'), '[DONE]']
            return [delta(calls=[{'index': 0, 'id': 'p', 'function': {'name': 'read_file',
                                        'arguments': '{"path":"'}}])] + list(self.runaway())
        server = self.serve(script)
        with patch.object(agent, 'run_tool', side_effect=AssertionError('partial call executed')):
            self.assertEqual(json.loads(self.run_packet(server.values)[0]), {'ok': True})

    def test_history_is_bounded_and_parallel_writers_do_not_lose_rows(self):
        from concurrent.futures import ThreadPoolExecutor
        def save(i):
            b = perf.Budget(self.root, 'ops', 4096)
            b.observe({'completion_tokens': i}, 'stop')
            b.finish('packet', 'valid')
        with ThreadPoolExecutor(max_workers=4) as pool:
            list(pool.map(save, range(32)))
        path = perf.location(self.root) / 'history.json'
        rows = perf.read_json(path, [])
        self.assertEqual(len(rows), 32)
        perf.atomic(path, rows * 8)
        save(500)
        self.assertEqual(len(perf.read_json(path, [])), 256)

    def test_temperature_opt_in_and_switches(self):
        with patch.dict(os.environ, WORKFLOW_SELF_HOSTED_TEMPERATURE='0.2'):
            self.assertIsNone(self.reuse().key)
            with patch.dict(os.environ, WORKFLOW_SELF_HOSTED_REUSE_NONZERO_TEMPERATURE='on'):
                self.assertIsNotNone(self.reuse().key)
        with patch.dict(os.environ, WORKFLOW_SELF_HOSTED_RESULT_REUSE='off', WORKFLOW_SELF_HOSTED_LEARNED_BUDGETS='off'):
            self.assertIsNone(self.reuse().key)
            b = perf.Budget(self.root, 'ops', 4096)
            self.assertFalse(b.enabled)
            b.finish('x', 'valid')
            self.assertFalse(perf.location(self.root).exists())

    def test_side_effects_live_steering_and_symlinks_never_reused(self):
        for policy in (agent.Policy(self.root, write=True), agent.Policy(self.root, shell=True)):
            self.assertIsNone(self.reuse(policy=policy).key)
        self.assertIsNone(self.reuse(stage=object()).key)
        (self.root / 'target').write_text('data')
        (self.root / 'link').symlink_to('target')
        self.assertIsNone(self.reuse().key)

    def test_secret_files_never_opened_and_no_secret_persisted(self):
        # A read guard detects even attempts to hash a forbidden filename.
        read = Path.read_bytes
        def guarded(path):
            self.assertNotIn('self-hosted-keys.json', path.name)
            return read(path)
        with patch.object(Path, 'read_bytes', guarded):
            cache = self.reuse()
            cache.put('{"ok":true}')
        for file in perf.location(self.root).glob('*.json'):
            self.assertNotIn(self.values['api_key'], file.read_text())

    def test_eviction_clear_and_corrupt_entry(self):
        with patch.dict(os.environ, WORKFLOW_SELF_HOSTED_REUSE_MAX_BYTES='250'):
            first, second = self.reuse(prompt='first'), self.reuse(prompt='second')
            first.put('x' * 60)
            second.put('y' * 60)
            self.assertIsNone(first.get())
            self.assertEqual(second.get(), 'y' * 60)
            file = perf.location(self.root) / (second.key + '.json')
            file.write_text('{invalid')
            self.assertIsNone(second.get())
            second.put('z')
            subprocess.run([sys.executable, perf.__file__, 'clear', '--root', str(self.root)], check=True)
            self.assertIsNone(second.get())

    def test_hosted_runners_have_no_performance_imports(self):
        lib = Path(agent.__file__).parent
        for name in ('native_stage.py', 'native_kimi.py', 'native_opencode.py', 'app_server.py'):
            self.assertNotIn('self_hosted_performance', (lib / name).read_text())


if __name__ == '__main__':
    unittest.main()
