"""A self-hosted worker's requests turn thinking off unless the operator said otherwise; other stages are untouched."""
import os
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'lib'))
import self_hosted_http as transport

OFF = {'chat_template_kwargs': {'enable_thinking': False}}


def options(stage, config=None, env=None):
    with patch.dict(os.environ, env or {}, clear=False):
        for name in [k for k in os.environ if k.startswith('WORKFLOW_SELF_HOSTED_REQUEST_OPTIONS')]:
            if not env or name not in env:
                os.environ.pop(name, None)
        return transport.configure_request_options({}, stage, config or {})['_request_options']


class WorkerDefault(unittest.TestCase):
    def test_the_shared_list_turns_thinking_off(self):
        for stage in ('final-audit-review-worker-scope', 'test-review-worker-coverage', 'project-plan-section-behaviors',
                      'updated-plan-review-worker-ownership', 'test-review', 'final-audit', 'execute-checklist',
                      'execute-checklist-worker-2', 'requirements', 'classify-change', 'preflight-worker-x'):
            self.assertEqual(options(stage), OFF, stage)

    def test_judgment_stages_keep_thinking_on_as_on_the_other_runners(self):
        for stage in ('implementation', 'repair', 'adversarial-review', 'adversarial-review-worker-regression', 'manual-checklist',
                      'manual-checklist-review-worker-coverage', 'derive-brief', 'project-plan-stage-duties', 'final-auditor',
                      'test-reviews', 'execute-checklists', ''):
            self.assertEqual(options(stage), {}, stage)

    def test_the_operators_extra_globs_and_the_global_switch_work_as_for_the_other_runners(self):
        self.assertEqual(options('adversarial-review-worker-x', env={'WORKFLOW_THINKING_OFF_EXTRA': 'adversarial-review-*'}), OFF)
        self.assertEqual(options('implementation', env={'WORKFLOW_THINKING_OFF_EXTRA': 'unrelated-*'}), {})
        self.assertEqual(options('test-review', env={'WORKFLOW_THINKING': 'on'}), {})

    def test_a_stage_the_operator_configured_keeps_exactly_what_they_set(self):
        stage = 'test-review-worker-coverage'
        self.assertEqual(options(stage, {stage + '.request-options': '{"top_p": 0.5}'}), {'top_p': 0.5})

    def test_an_explicit_empty_object_opts_out_of_the_default(self):
        stage = 'test-review-worker-coverage'
        self.assertEqual(options(stage, {stage + '.request-options': '{}'}), {})

    def test_a_global_self_hosted_setting_counts_as_configured(self):
        self.assertEqual(options('test-review-worker-coverage', {'self-hosted.request-options': '{"top_p": 0.9}'}), {'top_p': 0.9})

    def test_an_environment_setting_counts_as_configured(self):
        self.assertEqual(options('adversarial-review-worker-x', env={'WORKFLOW_SELF_HOSTED_REQUEST_OPTIONS': '{}'}), {})

    def test_the_switch_restores_server_default_thinking(self):
        for value in ('on', '1', 'true'):
            self.assertEqual(options('test-review-worker-coverage', env={'WORKFLOW_WORKER_THINKING': value}), {}, value)

    def test_the_updated_plan_retry_path_is_unchanged(self):
        with patch.dict(os.environ, {'UNCLE_UPDATED_PLAN_CHEAP_RETRY': '1'}):
            self.assertEqual(transport.configure_request_options({}, 'updated-plan-edit-worker-3', {})['_request_options'], OFF)

    def test_an_already_resolved_snapshot_is_kept(self):
        values = {'_request_options': {'kept': True}}
        self.assertEqual(transport.configure_request_options(values, 'test-review-worker-coverage', {}), values)


if __name__ == '__main__':
    unittest.main()
