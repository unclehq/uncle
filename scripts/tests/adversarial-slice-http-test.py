#!/usr/bin/env python3
"""Sliced reviews deliver one constrained answer; ordinary reviewers stay unchanged."""
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'lib'))
import http_agent
import self_hosted
import self_hosted_http as transport


class SliceHttp(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        env = patch.dict(os.environ, {'UNCLE_CONFIG': str(self.root / 'config'),
                                     'UNCLE_PROJECT_ROOT': str(self.root)}, clear=True)
        env.start()
        self.addCleanup(env.stop)
        self.kind = 'adversarial-review-worker-packet'
        self.packet = {'schema': 'uncle.artifact/v1', 'kind': self.kind, 'findings': []}
        self.values = {'base_url': 'http://unused.invalid/v1', 'api_key': 'stub', 'model': 'stub'}

    def test_slice_is_one_constrained_request_without_tools(self):
        with patch.dict(os.environ, {'UNCLE_ADVERSARIAL_SLICE': '1'}), \
                patch.object(http_agent, 'chat') as chat, \
                patch.object(http_agent, 'constrained_completion',
                             return_value=(json.dumps(self.packet), 'stop', {}, 'json_schema')) as constrained:
            text, turns = self_hosted.run_http_agent('reviewer', self.values, 'Review embedded inputs.',
                                                    self.root, schema_kind=self.kind)
        self.assertEqual(json.loads(text), self.packet)
        self.assertEqual((turns, chat.call_count, constrained.call_count), (1, 0, 1))
        self.assertEqual(constrained.call_args.args[4], 4096)
        self.assertEqual(constrained.call_args.kwargs.get('skip', ()), ())

    def test_slice_cannot_write_and_legacy_delivery_can(self):
        delivery = str(self.root / 'packet.json')
        for marker, writable in (('1', False), ('', True)):
            with self.subTest(marker=marker), patch.dict(os.environ, {
                    'UNCLE_ARTIFACT_DELIVERY': delivery, 'UNCLE_ADVERSARIAL_SLICE': marker}):
                request, policy, *_ = self_hosted._http_setup('reviewer', self.values, 'Review',
                                                              self.root, False, self.kind)
                self.assertEqual(policy.write, writable)
                if marker:
                    self.assertIn('Return the packet exactly once', request)

    def test_unsliced_reviewer_keeps_exploration(self):
        reply = {'choices': [{'message': {'role': 'assistant', 'content': json.dumps(self.packet)},
                              'finish_reason': 'stop'}]}
        with patch.object(http_agent, 'chat', return_value=reply) as chat, \
                patch.object(http_agent, 'constrained_completion') as constrained:
            self_hosted.run_http_agent('reviewer', self.values, 'Review.', self.root, schema_kind=self.kind)
        self.assertEqual((chat.call_count, constrained.call_count), (1, 0))

    def test_caps_keep_stage_parent_and_environment_precedence(self):
        (self.root / 'config').write_text('adversarial-review.final-output-tokens 7000\n'
                                         'adversarial-review.reasoning-output-tokens 9000\n')
        with patch.dict(os.environ, {'UNCLE_ADVERSARIAL_SLICE': '1',
                                    'UNCLE_STATUS_STAGE': 'adversarial-review-worker-security-slice-1'}):
            self.assertEqual(transport.output_cap(32768, 'final-output-tokens'), 7000)
            self.assertEqual(transport.output_cap(32768, 'reasoning-output-tokens'), 9000)
            with patch.dict(os.environ, {'WORKFLOW_SELF_HOSTED_FINAL_OUTPUT_TOKENS': '8000'}):
                self.assertEqual(transport.output_cap(32768, 'final-output-tokens'), 8000)
            (self.root / 'config').unlink()
            self.assertEqual(transport.output_cap(32768, 'final-output-tokens'), 4096)
            self.assertEqual(transport.output_cap(32768, 'reasoning-output-tokens'), 8192)
        self.assertEqual(transport.output_cap(32768, 'reasoning-output-tokens'), 32768)


if __name__ == '__main__':
    unittest.main()
