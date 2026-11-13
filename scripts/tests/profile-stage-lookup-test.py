#!/usr/bin/env python3
"""Every stage the shell routes through the implementation row resolves to the same profile, model and endpoint in the runner, for
all three profiles: the local model (self-hosted), AWS Bedrock and the Anthropic API.

The runs that found this: tests-harness and repair-investigate fell back to plain self-hosted ('requires an http(s) Base URL')
because the Python lookup did not mirror the shell's stage inheritance. The fix is shared code; this keeps it shared."""
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts' / 'lib'))
import self_hosted  # noqa: E402

PROFILES = {
    'self-hosted': dict(
        config='{r}.runner self-hosted\n{r}.model qwen3-coder\n{r}.base_url http://localhost:8000/v1\n',
        env={'UNCLE_SELF_HOSTED_API_KEY': 'local'}, profile=None, model='qwen3-coder', base='http://localhost:8000/v1'),
    'aws-bedrock': dict(
        config='{r}.runner aws-bedrock\n{r}.model us.anthropic.claude-sonnet-4\naws-bedrock.region us-east-1\n',
        env={'UNCLE_AWS_BEDROCK_API_KEY': 'tok-abc123'}, profile='aws-bedrock', model='us.anthropic.claude-sonnet-4',
        base='https://bedrock-runtime.us-east-1.amazonaws.com'),
    'anthropic-api': dict(
        config='{r}.runner anthropic-api\n{r}.model claude-sonnet-5-5\n',
        env={'UNCLE_ANTHROPIC_API_KEY': 'sk-ant-test-0123'}, profile='anthropic-api', model='claude-sonnet-5-5',
        base='https://api.anthropic.com'),
}
# The stages the shell runs under another stage's row: tests under implementation, repair inheriting implementation, the
# investigation passes and the parallel steps under their parent, and a plan section under project-plan.
UNDER_IMPLEMENTATION = ('implementation', 'implementation-investigate', 'implementation-step-3', 'tests', 'tests-harness', 'tests-unit',
                        'tests-e2e', 'tests-mutation', 'repair', 'repair-investigate')
UNDER_PROJECT_PLAN = ('project-plan', 'project-plan-investigate', 'project-plan-section-tests', 'project-plan-stage-duties')


class StageLookup(unittest.TestCase):
    def settings(self, spec, config, stage):
        with tempfile.TemporaryDirectory() as directory:
            Path(directory, '.uncle').mkdir()
            path = Path(directory, '.uncle', 'config')
            path.write_text(config)
            clean = {k: v for k, v in os.environ.items() if not k.startswith(('UNCLE_', 'WORKFLOW_', 'AWS_', 'ANTHROPIC_', 'OPENAI_', 'SEREN_'))}
            with mock.patch.dict(os.environ, dict(clean, **spec['env']), clear=True):
                return self_hosted.settings(str(path), stage)

    def check(self, spec, values, stage):
        self.assertEqual(values.get('_profile'), spec['profile'], stage)
        self.assertEqual((values['model'], values['base_url']), (spec['model'], spec['base']), stage)

    def test_only_the_implementation_row_is_configured(self):
        for name, spec in PROFILES.items():
            config = spec['config'].format(r='implementation') + spec['config'].format(r='project-plan')
            for stage in UNDER_IMPLEMENTATION + UNDER_PROJECT_PLAN:
                with self.subTest(profile=name, stage=stage):
                    self.check(spec, self.settings(spec, config, stage), stage)

    def test_repair_keeps_its_own_model_but_inherits_the_runner_and_endpoint(self):
        for name, spec in PROFILES.items():
            config = spec['config'].format(r='implementation') + 'repair.model repair-only-model\n'
            for stage in ('repair', 'repair-investigate'):
                with self.subTest(profile=name, stage=stage):
                    values = self.settings(spec, config, stage)
                    self.assertEqual(values.get('_profile'), spec['profile'])
                    self.assertEqual(values['model'], 'repair-only-model')
                    self.assertEqual(values['base_url'], spec['base'])

    def test_an_explicit_repair_runner_wins(self):
        spec = PROFILES['aws-bedrock']
        config = (spec['config'].format(r='implementation') + 'repair.runner self-hosted\nrepair.model local-fix\n'
                  'repair.base_url http://localhost:9000/v1\n')
        with mock.patch.dict(os.environ, {'UNCLE_SELF_HOSTED_API_KEY': 'local'}):
            values = self.settings(dict(spec, env=dict(spec['env'], UNCLE_SELF_HOSTED_API_KEY='local')), config, 'repair-investigate')
        self.assertNotIn('_profile', values)
        self.assertEqual((values['model'], values['base_url']), ('local-fix', 'http://localhost:9000/v1'))

    def test_a_stage_of_another_profile_is_not_pulled_into_implementations(self):
        # project-plan on a different profile than implementation: each keeps its own.
        bedrock, local = PROFILES['aws-bedrock'], PROFILES['self-hosted']
        config = bedrock['config'].format(r='implementation') + local['config'].format(r='project-plan')
        env = dict(bedrock['env'], **local['env'])
        self.assertEqual(self.settings(dict(bedrock, env=env), config, 'tests-harness').get('_profile'), 'aws-bedrock')
        self.assertIsNone(self.settings(dict(local, env=env), config, 'project-plan-section-tests').get('_profile'))


if __name__ == '__main__':
    unittest.main()
