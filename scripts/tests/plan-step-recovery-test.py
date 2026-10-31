#!/usr/bin/env python3
"""Bounded, schema-first publication recovery; all runners are stubbed."""
import copy
import json
import os
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

    def test_canonical_records_cannot_be_replaced_by_a_stale_narrative(self):
        plan = dict(title='Plan', intro='', sections=[], narrative=self.text)
        with patch.object(recovery, 'request_steps', return_value=ANSWER) as request:
            result = pm.publish_records(plan, self.root)
        request.assert_not_called()
        self.assertEqual(result, plan)

    def test_bad_answer_falls_back_once_without_rewriting(self):
        for answer in ({'steps': []}, {'steps': [{}]}, dict(steps=[dict(ANSWER['steps'][0], owns=['injected.py'])]),
                       dict(steps=[dict(ANSWER['steps'][0], depends_on=['missing'])])):
            with self.subTest(answer=answer), patch.object(recovery, 'request_steps', return_value=answer) as request:
                result = recovery.normalize_publication(self.text, self.root, 'project-plan')
                self.assertEqual(result, self.text)
                request.assert_called_once()
        with patch.object(recovery, 'request_steps', side_effect=ValueError('malformed')) as request:
            self.assertEqual(recovery.normalize_publication(self.text, self.root, 'project-plan'), self.text)
            request.assert_called_once()

    def test_empty_ownership_triggers_recovery_but_no_section_does_not(self):
        with patch.object(recovery, 'request_steps', side_effect=ValueError('unavailable')) as request:
            recovery.normalize_publication('## Implementation order\n1. Verify only.\n', self.root, 'project-plan')
            request.assert_called_once()
            recovery.normalize_publication('# Other\nStep one: irrelevant\n', self.root, 'project-plan')
            request.assert_called_once()

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

    def test_http_uses_one_constrained_completion_without_agent_turns(self):
        with patch('self_hosted.settings', return_value={'base_url': 'http://stub', 'api_key': 'fake', 'model': 'fake'}), \
                patch('self_hosted_http.constrained_completion', return_value=(json.dumps(ANSWER), 'stop', {}, 'json_schema')) as call:
            result = recovery.request_steps(BODY, self.root, 'project-plan', 'self-hosted', {}, 1024, 12)
            self.assertEqual(result, ANSWER)
            call.assert_called_once()
            self.assertEqual(call.call_args.args[2], recovery.SCHEMA)
            self.assertEqual(call.call_args.args[4], 1024)

    def test_normalization_keeps_fenced_instruction_bytes_idempotent(self):
        text = '## Implementation order\n\n### Step 0: Core\nOwns: `core.py`\n\n```python\nprint(1)\n```\n'
        normalized = plan_steps.normalize(text)
        model = pm.import_markdown(normalized)
        self.assertIn('print(1)', pm.steps_of(model)[0]['text'])
        self.assertEqual(plan_steps.normalize(normalized), normalized)


if __name__ == '__main__':
    unittest.main()
