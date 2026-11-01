#!/usr/bin/env python3
"""Red-team the bounded recovery contract without running a model or opening a socket."""
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
import plan_step_recovery as recovery
import plan_model as pm

BODY = '\nStep alpha: Scaffold\nCreate `package.json` without replacing existing scripts.\n'
ANSWER = {'steps': [dict(label='alpha', title='Scaffold', owns=['package.json'], depends_on=[], line=2)]}


class RecoveryContract(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.config = self.root / '.uncle/config'
        self.config.parent.mkdir()
        self.config.write_text('runner claude\n')
        env = patch.dict(os.environ, {'PATH': os.environ['PATH'], 'HOME': str(self.root),
                                     'UNCLE_CONFIG': str(self.config)}, clear=True)
        env.start()
        self.addCleanup(env.stop)
        self.text = '# Plan\n\nPrivate preamble sentinel.\n\n## Implementation order\n' + BODY + '\n## Review\n/approve\n'

    def test_section_only_bounded_once_across_all_runners(self):
        for runner in ('claude', 'codex', 'self-hosted'):
            self.config.write_text('runner ' + runner + '\n')
            with self.subTest(runner=runner), patch.object(recovery, 'request_steps', return_value=ANSWER) as call:
                result = pm.publish_records(dict(narrative=self.text), self.root, stage='updated-plan')
                call.assert_called_once()
                section, root, stage, actual_runner, config, limit, seconds = call.call_args.args
                self.assertEqual(section, BODY + '\n')
                self.assertNotIn('Private preamble', section)
                self.assertNotIn('/approve', section)
                self.assertEqual((root, stage, actual_runner, limit, seconds),
                                 (self.root, 'updated-plan', runner, 4096, 60))
                self.assertEqual(pm.steps_of(result)[0]['owns'], ['package.json'])
                self.assertEqual(pm.publish_records(result, self.root, stage=stage), result)
                call.assert_called_once()

    def test_invalid_records_are_rejected(self):
        invalid = []
        for fields in ({'line': 0}, {'line': 999}, {'line': True}, {'title': 'Invented'},
                       {'owns': ['../package.json']}, {'owns': ['invented.json']},
                       {'depends_on': ['missing']}, {'depends_on': ['alpha']}, {'extra': 'forbidden'}):
            answer = copy.deepcopy(ANSWER)
            answer['steps'][0].update(fields)
            invalid.append(answer)
        invalid.append({'steps': [ANSWER['steps'][0], ANSWER['steps'][0]]})
        for answer in invalid:
            with self.subTest(answer=answer), self.assertRaises(ValueError):
                recovery.recovered_body(BODY, answer)

    def test_owner_must_be_a_complete_source_path(self):
        body = BODY.replace('`package.json`', '`other-package.json`')
        with self.assertRaises(ValueError):
            recovery.recovered_body(body, ANSWER)

    def test_recovery_preserves_instructions_on_the_heading_line(self):
        body = BODY.replace('Scaffold\n', 'Scaffold — preserve existing dependency versions\n')
        result = recovery.recovered_body(body, ANSWER)
        self.assertIn('preserve existing dependency versions', result)
        self.assertIn('without replacing existing scripts.', result)

    def test_truncated_http_response_never_becomes_a_plan(self):
        with patch('self_hosted.settings', return_value={}), \
                patch('self_hosted_http.constrained_completion', return_value=(json.dumps(ANSWER), 'length', {}, 'json_schema')) as call:
            with self.assertRaises(ValueError):
                recovery.request_steps(BODY, self.root, 'project-plan', 'self-hosted', {}, 1024, 9)
            call.assert_called_once()

    def test_native_transport_uses_schema_and_cannot_clobber_stage_delivery(self):
        def run(command, **kwargs):
            self.assertEqual(kwargs['timeout'], 9)
            self.assertNotEqual(Path(kwargs['cwd']), self.root)
            self.assertTrue(kwargs['check'])
            self.assertEqual(command[command.index('--model') + 1], 'stage-model')
            for name in ('UNCLE_STATUS_FILE', 'UNCLE_ARTIFACT_DELIVERY', 'UNCLE_STRUCTURED_OUTPUT_PATH',
                         'UNCLE_OUTPUT_SCHEMA_FILE', 'UNCLE_WORKER_SCHEMA_FILE', 'UNCLE_STEERING'):
                self.assertNotIn(name, kwargs['env'])
            if command[0] == 'codex':
                schema = json.loads(Path(command[command.index('--output-schema') + 1]).read_text())
                Path(command[command.index('--output-last-message') + 1]).write_text(json.dumps(ANSWER))
            else:
                schema = json.loads(command[command.index('--json-schema') + 1])
                self.assertEqual(command[command.index('--max-turns') + 1], '1')
                self.assertEqual(command[command.index('--tools') + 1], '')
                self.assertEqual(kwargs['env']['CLAUDE_CODE_MAX_OUTPUT_TOKENS'], '1024')
            self.assertFalse(schema['additionalProperties'])
            self.assertFalse(schema['properties']['steps']['items']['additionalProperties'])
            return subprocess.CompletedProcess(command, 0, json.dumps({'structured_output': ANSWER}))

        leaking = {key: 'must-not-inherit' for key in ('UNCLE_STATUS_FILE', 'UNCLE_ARTIFACT_DELIVERY',
                   'UNCLE_STRUCTURED_OUTPUT_PATH', 'UNCLE_OUTPUT_SCHEMA_FILE', 'UNCLE_WORKER_SCHEMA_FILE', 'UNCLE_STEERING')}
        for runner in ('claude', 'codex'):
            with self.subTest(runner=runner), patch.dict(os.environ, leaking), \
                    patch.object(recovery.subprocess, 'run', side_effect=run) as call:
                result = recovery.request_steps(BODY, self.root, 'project-plan-investigate', runner,
                    {'model': 'global-model', 'project-plan.model': 'parent-model',
                     'project-plan-investigate.model': 'stage-model'}, 1024, 9)
                self.assertEqual(result, ANSWER)
                call.assert_called_once()

    def test_failure_makes_one_attempt_across_multiple_unreadable_sections(self):
        text = self.text + '\n## Implementation steps\n' + BODY
        with patch.object(recovery, 'request_steps', side_effect=subprocess.TimeoutExpired('stub', 1)) as call:
            self.assertEqual(recovery.normalize_publication(text, self.root, 'project-plan'), text)
            call.assert_called_once()

    def test_stage_environment_wins_over_parent_environment_and_config(self):
        self.config.write_text('runner claude\nproject-plan.plan-step-recovery off\n'
                               'project-plan-investigate.plan-step-answer-tokens 1000\n')
        overrides = {'WORKFLOW_CLAUDE_PLAN_STEP_RECOVERY_PROJECT_PLAN': 'off',
                     'WORKFLOW_CLAUDE_PLAN_STEP_RECOVERY_PROJECT_PLAN_INVESTIGATE': 'on',
                     'WORKFLOW_CLAUDE_PLAN_STEP_ANSWER_TOKENS_PROJECT_PLAN_INVESTIGATE': '2048',
                     'WORKFLOW_CLAUDE_PLAN_STEP_SECONDS_PROJECT_PLAN_INVESTIGATE': '7'}
        with patch.dict(os.environ, overrides), patch.object(recovery, 'request_steps', return_value=ANSWER) as call:
            recovery.normalize_publication(self.text, self.root, 'project-plan-investigate')
            call.assert_called_once()
            self.assertEqual(call.call_args.args[-2:], (2048, 7))


if __name__ == '__main__':
    unittest.main()
