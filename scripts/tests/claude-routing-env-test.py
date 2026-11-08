#!/usr/bin/env python3
"""A claude stage must authenticate with the operator's login, not a gateway or provider override left in the shell."""
import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'lib'))
import native_stage  # noqa: E402
import parallel_steps  # noqa: E402
import claude_env  # noqa: E402

ROUTING = {
    'ANTHROPIC_BASE_URL': 'https://bedrock-gateway.example/v1',
    'AWS_BEARER_TOKEN_BEDROCK': 'bedrock-api-test',
    'CLAUDE_CODE_USE_BEDROCK': '1',
    'ANTHROPIC_CUSTOM_HEADERS': 'x-test: 1',
}
UNRELATED = {'AWS_REGION': 'us-east-2', 'PATH': os.environ.get('PATH', '')}


def stage(runner):
    with mock.patch.dict(os.environ, {**ROUTING, **UNRELATED}):
        return native_stage.Stage(runner, 'builder', 'requirements', ['-p', 'x'], prompt='p')


class ClaudeRoutingEnv(unittest.TestCase):
    def test_claude_stage_drops_every_routing_variable(self):
        env = stage('claude').env
        self.assertEqual([k for k in ROUTING if k in env], [])

    def test_claude_stage_keeps_unrelated_environment(self):
        env = stage('claude').env
        for key, value in UNRELATED.items():
            self.assertEqual(env.get(key), value)

    def test_other_runners_keep_their_provider_settings(self):
        env = stage('codex').env
        self.assertEqual({k: env.get(k) for k in ROUTING}, ROUTING)

    def test_every_listed_variable_is_actually_dropped(self):
        with mock.patch.dict(os.environ, {k: 'v' for k in native_stage.CLAUDE_ROUTING_ENV}):
            env = native_stage.Stage('claude', 'builder', 'requirements', ['-p', 'x'], prompt='p').env
        self.assertEqual([k for k in native_stage.CLAUDE_ROUTING_ENV if k in env], [])


class ParallelStepEnv(unittest.TestCase):
    def step_env(self, runner):
        step = {'env': {'UNCLE_RESOLVED_RUNNER': runner} if runner is not None else {}}
        with mock.patch.dict(os.environ, {**ROUTING, **UNRELATED}):
            return parallel_steps.step_env(step)

    def test_claude_step_drops_routing_variables(self):
        for runner in ('claude', None):
            env = self.step_env(runner)
            self.assertEqual([k for k in ROUTING if k in env], [], runner)
            self.assertEqual(env.get('AWS_REGION'), 'us-east-2')

    def test_self_hosted_step_keeps_them(self):
        env = self.step_env('self-hosted')
        self.assertEqual({k: env.get(k) for k in ROUTING}, ROUTING)

    def test_shared_list_covers_the_variables_the_operator_hit(self):
        for key in ('ANTHROPIC_BASE_URL', 'AWS_BEARER_TOKEN_BEDROCK', 'CLAUDE_CODE_USE_BEDROCK'):
            self.assertIn(key, claude_env.CLAUDE_ROUTING_ENV)


if __name__ == '__main__':
    unittest.main()
