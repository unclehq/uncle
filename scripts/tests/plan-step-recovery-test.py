#!/usr/bin/env python3
"""Bounded, schema-first publication recovery; all runners are stubbed."""
import contextlib
import io
import json
import os
import shutil
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'lib'))
import plan_model as pm
import plan_step_recovery as recovery
import plan_steps

BODY = '\nStep one: Core\nCreate the core.\nFiles: `src/core.py`\n\nStep two: Tests\nKeep /approve available.\nFiles: `tests/core.py`\n'
ANSWER = {'steps': [
    dict(label='one', title='Core', owns=['src/core.py'], depends_on=[], line=2),
    dict(label='two', title='Tests', owns=['tests/core.py'], depends_on=['one'], line=6)]}


class Recovery(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.config = self.root / '.uncle/config'
        self.config.parent.mkdir()
        self.config.write_text('runner claude\n')
        env = patch.dict(os.environ, {'UNCLE_CONFIG': str(self.config), 'PATH': os.environ['PATH']}, clear=True)
        env.start()
        self.addCleanup(env.stop)
        self.text = '# Plan\n\nOutside  unchanged.\n\n## Implementation order\n' + BODY + '\n## Review\n/approve\n'

    def test_once_and_only_section_then_no_call_on_republication(self):
        with patch.object(recovery, 'request_steps', return_value=ANSWER) as request:
            result = pm.publish_records(dict(narrative=self.text), self.root)
            request.assert_called_once()
            self.assertEqual(request.call_args.args[0], BODY + '\n')
            self.assertEqual([step['owns'] for step in pm.steps_of(result)], [['src/core.py'], ['tests/core.py']])
            self.assertEqual(pm.steps_of(result)[1]['depends_on'], [1])
            self.assertIn('Create the core.', result['narrative'])
            self.assertIn('Keep /approve available.', result['narrative'])
            self.assertTrue(result['narrative'].endswith('\n## Review\n/approve\n'))
            self.assertEqual(pm.publish_records(result, self.root), result)
            request.assert_called_once()

    def test_metadata_only_legacy_packet_still_reads_markdown_steps(self):
        import plan_records
        plan = self.root / 'PLAN.md'
        plan.write_text('## Implementation order\n1. Core Owns: `core.py`\n')
        packet = plan.with_suffix('.json')
        packet.write_text(json.dumps(dict(protected_verification_paths='core.py')))
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            self.assertEqual(plan_records.main(['owns', str(plan)]), 0)
        self.assertEqual(output.getvalue(), '1\tcore.py\n')
        packet.write_text(json.dumps(dict(narrative='', protected_verification_paths='core.py')))
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            self.assertEqual(plan_records.main(['owns', str(plan)]), 0)
        self.assertEqual(output.getvalue(), '')

    def test_canonical_records_cannot_be_replaced_by_a_stale_narrative(self):
        plan = dict(title='Plan', intro='', sections=[], narrative=self.text)
        with patch.object(recovery, 'request_steps', return_value=ANSWER) as request:
            result = pm.publish_records(plan, self.root)
        request.assert_not_called()
        self.assertEqual(result, plan)

    def test_bad_answer_falls_back_once_without_rewriting(self):
        for answer in ({'steps': []}, {'steps': [{}]}, dict(steps=[dict(ANSWER['steps'][0], owns=['injected.py'])]),
                       dict(steps=[dict(ANSWER['steps'][0], depends_on=['missing'])])):
            shutil.rmtree(self.root / '.uncle/workflow/plan-step-recovery', ignore_errors=True)
            with self.subTest(answer=answer), patch.object(recovery, 'request_steps', return_value=answer) as request:
                result = recovery.normalize_publication(self.text, self.root, 'project-plan')
                self.assertEqual(result, self.text)
                request.assert_called_once()
        shutil.rmtree(self.root / '.uncle/workflow/plan-step-recovery', ignore_errors=True)
        with patch.object(recovery, 'request_steps', side_effect=ValueError('malformed')) as request:
            self.assertEqual(recovery.normalize_publication(self.text, self.root, 'project-plan'), self.text)
            request.assert_called_once()

    def test_empty_ownership_triggers_recovery_but_no_section_does_not(self):
        with patch.object(recovery, 'request_steps', side_effect=ValueError('unavailable')) as request:
            recovery.normalize_publication('## Implementation order\n1. Verify only.\n', self.root, 'project-plan')
            request.assert_called_once()
            recovery.normalize_publication('# Other\nStep one: irrelevant\n', self.root, 'project-plan')
            request.assert_called_once()

    def test_preview_and_publication_share_one_success_or_failure(self):
        for answer in (ANSWER, {'steps': []}):
            shutil.rmtree(self.root / '.uncle/workflow/plan-step-recovery', ignore_errors=True)
            with self.subTest(answer=answer), patch.object(recovery, 'request_steps', return_value=answer) as request:
                first = recovery.normalize_publication(self.text, self.root, 'project-plan-investigate')
                second = recovery.normalize_publication(self.text, self.root, 'project-plan')
                self.assertEqual(first, second)
                request.assert_called_once()

    def test_recovery_cannot_omit_a_source_step(self):
        with self.assertRaisesRegex(ValueError, 'omitted'):
            recovery.recovered_body(BODY, {'steps': ANSWER['steps'][:1]})

    def test_stage_config_and_environment_precedence(self):
        self.config.write_text('runner claude\nproject-plan.plan-step-recovery off\n')
        with patch.object(recovery, 'request_steps', return_value=ANSWER) as request:
            self.assertEqual(recovery.normalize_publication(self.text, self.root, 'project-plan-investigate'), self.text)
            request.assert_not_called()
            with patch.dict(os.environ, WORKFLOW_CLAUDE_PLAN_STEP_RECOVERY_PROJECT_PLAN='on'):
                recovery.normalize_publication(self.text, self.root, 'project-plan-investigate')
            request.assert_called_once()
        with patch.dict(os.environ, WORKFLOW_CLAUDE_PLAN_STEP_NORMALIZE='off'):
            self.assertEqual(recovery.normalize_publication(self.text, self.root, 'project-plan'), self.text)

    def test_native_schema_flags_and_isolated_working_directory(self):
        def run(command, **kwargs):
            self.assertNotEqual(Path(kwargs['cwd']), self.root)
            self.assertEqual(kwargs['timeout'], 12)
            self.assertIn(BODY, kwargs['input'])
            if command[0] == 'codex':
                self.assertIn('--output-schema', command)
                destination = Path(command[command.index('--output-last-message') + 1])
                destination.write_text(json.dumps(ANSWER))
                return subprocess.CompletedProcess(command, 0, '')
            self.assertIn('--json-schema', command)
            self.assertIn('--tools', command)
            return subprocess.CompletedProcess(command, 0, json.dumps({'structured_output': ANSWER}))
        for runner in ('claude', 'codex'):
            with self.subTest(runner=runner), patch.object(recovery.subprocess, 'run', side_effect=run) as call:
                self.assertEqual(recovery.request_steps(BODY, self.root, 'project-plan', runner, {}, 1024, 12), ANSWER)
                call.assert_called_once()

    def test_other_runner_adapters_receive_schema_and_return_event_json(self):
        def run(command, **kwargs):
            self.assertIn('Required JSON schema:', kwargs['input'])
            self.assertEqual(json.loads(kwargs['input'].split('Required JSON schema:\n')[1]), recovery.SCHEMA)
            events = [{'type': 'assistant', 'message': {'content': [{'type': 'text', 'text': json.dumps(ANSWER)}]}},
                      {'type': 'result', 'result': json.dumps(ANSWER)}]
            return subprocess.CompletedProcess(command, 0, '\n'.join(json.dumps(event) for event in events))
        for runner in ('kimi',):
            with self.subTest(runner=runner), patch.object(recovery.subprocess, 'run', side_effect=run) as call:
                self.assertEqual(recovery.request_steps(BODY, self.root, 'project-plan', runner, {}, 1024, 12), ANSWER)
                call.assert_called_once()

    def test_self_hosted_aliases_use_self_hosted_option_precedence(self):
        for runner in ('opencode', 'aider'):
            self.config.write_text('runner ' + runner + '\nself-hosted.plan-step-recovery off\n')
            with self.subTest(runner=runner), patch.object(recovery, 'request_steps') as request:
                self.assertEqual(recovery.normalize_publication(self.text, self.root, 'project-plan'), self.text)
                request.assert_not_called()

    def test_http_uses_one_constrained_completion_without_agent_turns(self):
        with patch('self_hosted.settings', return_value={'base_url': 'http://stub', 'api_key': 'fake', 'model': 'fake'}), \
                patch('self_hosted_http.constrained_completion', return_value=(json.dumps(ANSWER), 'stop', {}, 'json_schema')) as call:
            result = recovery.request_steps(BODY, self.root, 'project-plan', 'self-hosted', {}, 1024, 12)
            self.assertEqual(result, ANSWER)
            call.assert_called_once()
            self.assertEqual(call.call_args.args[2], recovery.SCHEMA)
            self.assertEqual(call.call_args.args[4], 1024)

    def test_http_recovery_does_not_retry_lost_connections(self):
        import self_hosted_http as transport
        def completion(*args, **kwargs):
            self.assertLessEqual(transport.connect_timeout(), 3)
            return transport.post('http://stub/v1/chat/completions', 'fake', {}, 3)
        with patch('self_hosted.settings', return_value={}), \
                patch.object(transport, 'constrained_completion', side_effect=completion), \
                patch.object(transport, '_request', side_effect=transport.NetworkLost('lost')) as request, \
                patch.object(transport, '_outage_mark'), patch.object(transport.time, 'sleep') as sleep:
            with self.assertRaises(transport.NetworkLost):
                recovery.request_steps(BODY, self.root, 'project-plan', 'self-hosted', {}, 1024, 3)
            request.assert_called_once()
            sleep.assert_not_called()
        with transport.connection_scope():
            self.assertIsNone(transport._connections().reconnect_seconds)
            self.assertEqual(transport.connect_timeout(), 15)

    def test_normalization_keeps_fenced_instruction_bytes_idempotent(self):
        text = '## Implementation order\n\n### Step 0: Core\nOwns: `core.py`\n\n```python\nprint(1)\n```\n'
        normalized = plan_steps.normalize(text)
        model = pm.import_markdown(normalized)
        self.assertIn('print(1)', pm.steps_of(model)[0]['text'])
        self.assertEqual(plan_steps.normalize(normalized), normalized)


if __name__ == '__main__':
    unittest.main()
