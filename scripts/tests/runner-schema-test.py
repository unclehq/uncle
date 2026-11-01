#!/usr/bin/env python3
"""Runner schema contracts through disposable CLI stubs; no model calls or Git fixtures."""
import copy
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts/lib'))
import structured_output
import worker_schemas
import project_plan_sections


STUB = r'''#!/usr/bin/env python3
import json, os, sys
from pathlib import Path
args = sys.argv[1:]
if '--help' in args:
    print('exec --json --output-schema FILE --output-last-message FILE'
          if os.environ.get('STUB_SUPPORT', '1') == '1' else 'exec --json')
    raise SystemExit(0)
Path(os.environ['STUB_ARGV']).write_text(json.dumps(args))
if '--output-schema' in args:
    Path(os.environ['STUB_SCHEMA']).write_text(Path(args[args.index('--output-schema') + 1]).read_text())
answer = os.environ.get('STUB_ANSWER', '{"answer":"ok"}')
def emit(value): print(json.dumps(value), flush=True)
if 'app-server' in args:
    for line in sys.stdin:
        request = json.loads(line)
        with Path(os.environ['STUB_RPC']).open('a') as log:
            log.write(json.dumps(request) + '\n')
        method, params = request.get('method'), request.get('params', {})
        result = {}
        if method == 'thread/start':
            result = {'thread': {'id': 'stub-thread'}}
        elif method == 'turn/start':
            rejection = os.environ.get('STUB_REJECT_NATIVE')
            if rejection and 'outputSchema' in params:
                emit({'id': request['id'], 'error': {'code': -32602, 'message': rejection}})
                continue
            if 'outputSchema' in params:
                Path(os.environ['STUB_SCHEMA']).write_text(json.dumps(params['outputSchema']))
            result = {'turn': {'id': 'stub-turn'}}
        if 'id' in request:
            emit({'id': request['id'], 'result': result})
        if method == 'turn/start':
            emit({'method': 'item/completed', 'params': {'item': {
                'type': 'agentMessage', 'id': 'note', 'phase': 'commentary', 'text': 'Working.'}}})
            emit({'method': 'item/completed', 'params': {'item': {
                'type': 'agentMessage', 'id': 'final', 'phase': 'final_answer', 'text': answer}}})
            emit({'method': 'turn/completed', 'params': {'turn': {'id': 'stub-turn', 'status': 'completed'}}})
    raise SystemExit(0)
if '--output-last-message' in args and os.environ.get('STUB_WRITE', '1') == '1':
    Path(args[args.index('--output-last-message') + 1]).write_text(answer)
if Path(sys.argv[0]).name == 'cline':
    emit({'type': 'agent_event', 'event': {'type': 'content_end', 'contentType': 'text', 'text': answer}})
    emit({'type': 'run_result', 'finishReason': 'completed', 'iterations': 1})
else:
    sys.stdin.read()
    emit({'type': 'thread.started', 'thread_id': 'stub'})
    emit({'type': 'turn.started'})
    emit({'type': 'item.completed', 'item': {'type': 'agent_message', 'text': 'Working on the packet.'}})
    emit({'type': 'item.completed', 'item': {'type': 'agent_message', 'text': answer}})
    if os.environ.get('STUB_COMPLETE', '1') == '1':
        emit({'type': 'turn.completed', 'usage': {'input_tokens': 10, 'output_tokens': 5}})
raise SystemExit(int(os.environ.get('STUB_EXIT', '0')))
'''


def object_schema(properties, required=()):
    return {'type': 'object', 'properties': properties, 'required': list(required),
            'additionalProperties': False}


SIMPLE = object_schema({'answer': {'type': 'string'}}, ['answer'])


class RunnerSchema(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='uncle runner schema ')
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name)
        for name in ('codex',):
            stub = self.directory / name
            stub.write_text(STUB)
            stub.chmod(0o755)
        self.source = self.directory / 'original schema.json'
        self.delivery = self.directory / 'artifact delivery.json'
        self.log = self.directory / 'events.jsonl'

    def run_runner(self, schema=SIMPLE, answer=None, runner='codex', config='', native=False, **extra):
        env = {key: value for key, value in os.environ.items()
               if not key.startswith(('UNCLE_', 'WORKFLOW_', 'STAGEGATE_', 'STUB_'))}
        env.update(WORKFLOW_CODEX_CMD=str(self.directory / 'codex'),
                   UNCLE_PROJECT_ROOT=str(self.directory),
                   UNCLE_CONFIG=str(self.directory / 'config'),
                   UNCLE_STATUS_STAGE='updated-plan-worker-edits-1',
                   STUB_ARGV=str(self.directory / 'argv.json'),
                   STUB_RPC=str(self.directory / 'rpc.jsonl'),
                   STUB_SCHEMA=str(self.directory / 'strict.json'))
        (self.directory / 'config').write_text(config)
        if schema is not None:
            self.source.write_text(json.dumps(schema))
            env.update(UNCLE_OUTPUT_SCHEMA_FILE=str(self.source),
                       UNCLE_STRUCTURED_OUTPUT_PATH=str(self.delivery))
        if answer is not None:
            env['STUB_ANSWER'] = answer if isinstance(answer, str) else json.dumps(answer)
        env.update(extra)
        command = ['bash', str(ROOT / 'scripts' / ('agent-' + runner + '.sh'))]
        if native:
            env.update(UNCLE_RUNNER_REUSE='0', UNCLE_STEERING='1', WORKFLOW_NATIVE_STAGE_SECONDS='10')
            command = [sys.executable, '-B', str(ROOT / 'scripts/lib/native_stage.py'),
                       '--runner', runner, '--side', 'agent', '--stage', env['UNCLE_STATUS_STAGE'], '--']
        done = subprocess.run(command + ['-p', '--output-format', 'stream-json'],
                              input='Deliver the requested packet.', text=True, capture_output=True,
                              cwd=self.directory, env=env, timeout=30)
        self.log.write_text(done.stdout)
        self.argv = json.loads((self.directory / 'argv.json').read_text())
        self.events = [json.loads(line) for line in done.stdout.splitlines() if line.startswith('{')]
        self.result = next((item for item in reversed(self.events) if item.get('type') == 'result'), {})
        return done

    def assert_delivered(self, expected):
        self.assertTrue(self.delivery.exists(), self.result)
        self.assertEqual(json.loads(self.delivery.read_text()), expected)
        self.assertEqual(self.result.get('structured_output'), expected)
        self.assertEqual(structured_output.extract(self.log), expected)
        self.assertEqual(self.events[-1]['type'], 'result')
        self.assertEqual(sum(event.get('type') == 'result' for event in self.events), 1)

    def assert_strict_objects(self, schema):
        if isinstance(schema, dict):
            if schema.get('type') == 'object' or 'properties' in schema:
                self.assertIs(schema.get('additionalProperties'), False)
                self.assertEqual(set(schema.get('required', [])), set(schema.get('properties', {})))
            for value in schema.values():
                self.assert_strict_objects(value)
        elif isinstance(schema, list):
            for item in schema:
                self.assert_strict_objects(item)

    def test_no_schema_keeps_original_cli_and_result(self):
        done = self.run_runner(schema=None)
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertNotIn('--output-schema', self.argv)
        self.assertNotIn('--output-last-message', self.argv)
        self.assertNotIn('structured_output', self.result)
        self.assertFalse(self.delivery.exists())

    def test_schema_flag_capture_and_claude_extraction_contract(self):
        done = self.run_runner()
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertIn('--output-schema', self.argv)
        self.assertIn('--output-last-message', self.argv)
        self.assert_delivered({'answer': 'ok'})
        self.assertEqual(json.loads(self.source.read_text()), SIMPLE)
        self.assertEqual(self.result['usage']['input_tokens'], 10)
        self.assertEqual(self.result['usage']['output_tokens'], 5)

    def test_optional_nested_fields_round_trip_without_null_placeholders(self):
        row = object_schema({'label': {'type': 'string'}, 'note': {'type': 'string'}}, ['label'])
        schema = object_schema({'rows': {'type': 'array', 'items': row},
                                'optional': object_schema({'flag': {'type': 'boolean'}})}, ['rows'])
        done = self.run_runner(schema, {'rows': [{'label': 'one', 'note': None},
                                                 {'label': 'two', 'note': 'keep'}], 'optional': None})
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assert_strict_objects(json.loads((self.directory / 'strict.json').read_text()))
        self.assert_delivered({'rows': [{'label': 'one'}, {'label': 'two', 'note': 'keep'}]})
        self.assertEqual(json.loads(self.source.read_text()), schema)

    def test_required_nullable_field_is_not_deleted(self):
        schema = object_schema({'answer': {'type': ['string', 'null']}}, ['answer'])
        done = self.run_runner(schema, {'answer': None})
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assert_delivered({'answer': None})

    def test_original_optional_nullable_field_keeps_explicit_null(self):
        schema = object_schema({'answer': {'type': ['string', 'null']}})
        done = self.run_runner(schema, {'answer': None})
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assert_delivered({'answer': None})

    def test_large_final_packet_is_delivered_without_truncation(self):
        answer = {'answer': 'x' * 20000}
        done = self.run_runner(answer=answer)
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assert_delivered(answer)

    def test_false_zero_and_empty_values_are_not_deleted(self):
        schema = object_schema({'flag': {'type': 'boolean'}, 'count': {'type': 'integer'},
                                'text': {'type': 'string'}, 'rows': {'type': 'array', 'items': {'type': 'string'}}})
        answer = {'flag': False, 'count': 0, 'text': '', 'rows': []}
        done = self.run_runner(schema, answer)
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assert_delivered(answer)

    def test_real_packet_round_trip_and_existing_consumer_validation(self):
        heading = project_plan_sections.expected_headings('design')[0]
        schema = worker_schemas.section_packet([heading])
        expected = {'schema': 'uncle.artifact/v1', 'kind': worker_schemas.SECTION_KIND,
                    'sections': [{'heading': heading, 'body': 'Updated design.'}]}
        answer = dict(expected)
        for key in schema['properties']:
            if key not in answer:
                answer[key] = None
        done = self.run_runner(schema, answer)
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assert_delivered(expected)
        self.assertEqual(project_plan_sections.render_packet('design', structured_output.extract(self.log)),
                         project_plan_sections.render_packet('design', expected))
        self.assert_strict_objects(json.loads((self.directory / 'strict.json').read_text()))

    def test_env_opt_out_omits_schema_flags(self):
        done = self.run_runner(WORKFLOW_RUNNER_SCHEMA_ENFORCE='0')
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertNotIn('--output-schema', self.argv)
        self.assertFalse(self.delivery.exists())

    def test_parent_stage_config_opt_out(self):
        done = self.run_runner(config='updated-plan.schema-enforce off\n')
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertNotIn('--output-schema', self.argv)

    def test_environment_overrides_stage_config(self):
        done = self.run_runner(config='updated-plan.schema-enforce off\n', WORKFLOW_RUNNER_SCHEMA_ENFORCE='1')
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertIn('--output-schema', self.argv)
        self.assert_delivered({'answer': 'ok'})

    def test_exact_worker_config_overrides_parent(self):
        done = self.run_runner(config='updated-plan.schema-enforce off\nupdated-plan-worker-edits-1.schema-enforce on\n')
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertIn('--output-schema', self.argv)

    def test_unsupported_cli_falls_back_with_one_line_note(self):
        done = self.run_runner(STUB_SUPPORT='0')
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertNotIn('--output-schema', self.argv)
        self.assertNotIn('structured_output', self.result)
        self.assertEqual(len(done.stderr.strip().splitlines()), 1)

    def test_unsupported_schema_falls_back_without_mutating_original(self):
        schema = object_schema({'answer': {'type': 'string'}})
        schema['patternProperties'] = {'^extra': {'type': 'string'}}
        done = self.run_runner(schema)
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertNotIn('--output-schema', self.argv)
        self.assertEqual(len(done.stderr.strip().splitlines()), 1)
        self.assertEqual(json.loads(self.source.read_text()), schema)
        self.assertFalse(self.delivery.exists())

    def test_cli_failure_cannot_deliver_an_apparently_valid_packet(self):
        done = self.run_runner(STUB_EXIT='7')
        self.assertEqual(done.returncode, 7, done.stderr)
        self.assertNotIn('structured_output', self.result)
        self.assertFalse(self.delivery.exists())

    def test_missing_completed_turn_cannot_deliver(self):
        done = self.run_runner(STUB_COMPLETE='0')
        self.assertNotEqual(done.returncode, 0)
        self.assertNotIn('structured_output', self.result)
        self.assertFalse(self.delivery.exists())

    def test_malformed_or_schema_invalid_output_is_not_delivered(self):
        for answer in ('{"answer":', '{"answer":"ok"}{"answer":"again"}',
                       '{}', '{"answer":null}', '{"answer":4}', '{"answer":"ok","extra":1}'):
            with self.subTest(answer=answer):
                done = self.run_runner(answer=answer)
                self.assertNotEqual(done.returncode, 0, done.stdout)
                self.assertNotIn('structured_output', self.result)
                self.assertFalse(self.delivery.exists())

    def test_constraints_removed_for_strict_mode_are_still_validated(self):
        schema = copy.deepcopy(SIMPLE)
        schema['properties']['answer']['minLength'] = 3
        done = self.run_runner(schema, {'answer': 'x'})
        self.assertNotEqual(done.returncode, 0, done.stdout)
        self.assertFalse(self.delivery.exists())

    def test_failed_validation_preserves_existing_delivery(self):
        original = '{"answer":"previous valid delivery"}\n'
        self.delivery.write_text(original)
        done = self.run_runner(answer={'answer': 4})
        self.assertNotEqual(done.returncode, 0, done.stdout)
        self.assertEqual(self.delivery.read_text(), original)
        self.assertNotIn('structured_output', self.result)

    def test_native_tui_schema_uses_rpc_and_same_delivery_contract(self):
        schema = object_schema({'answer': {'type': 'string'}, 'optional': {'type': 'string'}}, ['answer'])
        done = self.run_runner(schema, {'answer': 'ok', 'optional': None}, native=True)
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertIn('app-server', self.argv)
        self.assert_strict_objects(json.loads((self.directory / 'strict.json').read_text()))
        self.assert_delivered({'answer': 'ok'})
        requests = [json.loads(line) for line in (self.directory / 'rpc.jsonl').read_text().splitlines()]
        turn = next(request for request in requests if request.get('method') == 'turn/start')
        self.assertIn('outputSchema', turn['params'])

    def test_native_tui_opt_out_preserves_rpc_without_output_schema(self):
        done = self.run_runner(native=True, WORKFLOW_RUNNER_SCHEMA_ENFORCE='0')
        self.assertEqual(done.returncode, 0, done.stderr)
        requests = [json.loads(line) for line in (self.directory / 'rpc.jsonl').read_text().splitlines()]
        turn = next(request for request in requests if request.get('method') == 'turn/start')
        self.assertNotIn('outputSchema', turn['params'])
        self.assertNotIn('structured_output', self.result)
        self.assertFalse(self.delivery.exists())

    def test_native_tui_invalid_final_cannot_deliver(self):
        done = self.run_runner(answer={'answer': 4}, native=True)
        self.assertNotEqual(done.returncode, 0, done.stdout)
        self.assertNotIn('structured_output', self.result)
        self.assertFalse(self.delivery.exists())

    def test_native_unsupported_schema_field_falls_back_without_losing_the_turn(self):
        done = self.run_runner(native=True, STUB_REJECT_NATIVE='Unknown field outputSchema')
        self.assertEqual(done.returncode, 0, done.stderr)
        requests = [json.loads(line) for line in (self.directory / 'rpc.jsonl').read_text().splitlines()]
        turns = [request for request in requests if request.get('method') == 'turn/start']
        self.assertEqual(len(turns), 2)
        self.assertIn('outputSchema', turns[0]['params'])
        self.assertNotIn('outputSchema', turns[1]['params'])
        self.assertIn('Deliver the requested packet.', turns[1]['params']['input'][0]['text'])
        self.assertNotIn('structured_output', self.result)
        self.assertFalse(self.delivery.exists())
        self.assertEqual(len(done.stderr.strip().splitlines()), 1)

    def test_native_unrelated_error_is_not_retried_without_schema(self):
        done = self.run_runner(native=True, STUB_REJECT_NATIVE='Model unavailable')
        self.assertNotEqual(done.returncode, 0, done.stdout)
        requests = [json.loads(line) for line in (self.directory / 'rpc.jsonl').read_text().splitlines()]
        turns = [request for request in requests if request.get('method') == 'turn/start']
        self.assertEqual(len(turns), 1)
        self.assertIn('outputSchema', turns[0]['params'])
        self.assertNotIn('structured_output', self.result)

    def test_both_driver_capability_gates_advertise_codex_and_preserve_other_runners(self):
        script = '''
source "$ROOT/scripts/lib/stage-runtime.sh"
stage_runner_config_name() { printf '%s\\n' "$1"; }
uncle_resolve_stage_runner() { UNCLE_RESOLVED_RUNNER="$TEST_RUNNER"; }
stage_agent_cmd() { printf '%s\\n' "$TEST_COMMAND"; }
"$TEST_GATE" updated-plan-worker-edits-1
'''
        env = {key: value for key, value in os.environ.items()
               if not key.startswith(('UNCLE_', 'WORKFLOW_', 'STAGEGATE_'))}
        env.update(ROOT=str(ROOT), UNCLE_PROJECT_ROOT=str(self.directory),
                   UNCLE_CONFIG=str(self.directory / 'config'), WORKFLOW_CODEX_CMD=str(self.directory / 'codex'))
        (self.directory / 'config').write_text('')
        for gate in ('app_stage_supports_structured_output', 'change_stage_supports_structured_output'):
            for runner, command, supported in (
                    ('codex', str(ROOT / 'scripts/agent-codex.sh'), True),
                    ('claude', '/stub/claude', True),
                    ('self-hosted', '/stub/self-hosted', False), ('codex', '/stub/custom', False)):
                with self.subTest(gate=gate, runner=runner, command=command):
                    done = subprocess.run(['bash', '-c', script], cwd=self.directory,
                                          env=dict(env, TEST_GATE=gate, TEST_RUNNER=runner, TEST_COMMAND=command),
                                          text=True, capture_output=True, timeout=30)
                    self.assertEqual(done.returncode == 0, supported, done.stderr)


if __name__ == '__main__':
    unittest.main()
