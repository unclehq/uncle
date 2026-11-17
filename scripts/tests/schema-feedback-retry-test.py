#!/usr/bin/env python3
"""Schema-feedback retry in the http_agent final-answer loop, ID enums dropped from wire schemas (issue 286)."""
import contextlib
import copy
import io
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts/lib'))
import http_agent as agent
import self_hosted as hosted
import worker_schemas as WS

GOOD = {'schema': 'uncle.artifact/v1', 'kind': WS.EDIT_OPS_KIND, 'ops': [], 'dispositions': []}
BAD = dict(GOOD, ops='wrong')
DONE = {'choices': [{'message': {'role': 'assistant', 'content': 'done', 'tool_calls': []}, 'finish_reason': 'stop'}],
        'usage': {'prompt_tokens': 10, 'completion_tokens': 1}}
SECRET = 'SENTINEL-SECRET-8f3a'
LOCAL_PATH = '/Users/someone/private/project/file.json'


class Base(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.values = {'model': 'stub', 'base_url': 'http://unused.invalid/v1', 'api_key': 'never-used'}
        capture = contextlib.redirect_stdout(io.StringIO())
        capture.__enter__()
        self.addCleanup(capture.__exit__, None, None, None)
        err = contextlib.redirect_stderr(io.StringIO())
        err.__enter__()
        self.addCleanup(err.__exit__, None, None, None)

    def run_writer(self, texts, bounded=False, retries=None, mode='json_schema', replies=(), validator_error=None):
        delivery = self.root / '.uncle/workflow/edits/1.json'
        env = {'UNCLE_CONFIG': str(self.root / 'absent'), 'UNCLE_PROJECT_ROOT': str(self.root),
               'UNCLE_ARTIFACT_DELIVERY': str(delivery), 'UNCLE_STATUS_STAGE': 'updated-plan-worker-edits-1'}
        if bounded:
            env['UNCLE_UPDATED_PLAN_ANSWER_TOKENS'] = '4096'
        if retries is not None:
            env['UNCLE_SCHEMA_FEEDBACK_RETRIES'] = retries
        sent = []
        queue = list(texts)

        def fake(values, messages, *args, **kwargs):
            sent.append(copy.deepcopy(messages))
            text = queue.pop(0) if len(queue) > 1 else queue[0]
            return text, 'stop', {}, mode
        with patch.dict(os.environ, env, clear=True), \
                patch.object(agent, 'constrained_completion', side_effect=fake) as constrained, \
                patch.object(agent, 'interruptible_chat', side_effect=[DONE, AssertionError('repair turn must not run')]) as repair:
            try:
                answer, _ = hosted.run_opencode('agent', self.values, json.dumps(GOOD | {'ops': 'wrong'}), self.root)
                error = None
            except (ValueError, AssertionError) as caught:
                answer, error = None, str(caught)
        return answer, error, constrained.call_count, sent, max(0, repair.call_count - 1)


class FeedbackRetry(Base):
    def test_schema_failure_retries_at_most_twice_without_repair(self):
        answer, error, calls, _, repairs = self.run_writer([json.dumps(BAD)])
        self.assertIsNone(answer)
        self.assertIn('violates the artifact schema', error or '')
        self.assertLessEqual(calls, 3)
        self.assertEqual(calls, 3)
        self.assertEqual(repairs, 0)

    def test_a_valid_second_answer_is_returned(self):
        answer, error, calls, _, _ = self.run_writer([json.dumps(BAD), json.dumps(GOOD)])
        self.assertIsNone(error)
        self.assertEqual(calls, 2)
        self.assertEqual(json.loads(answer)['ops'], [])

    def test_retry_environment_parsing_table(self):
        table = {None: 3, '': 3, '0': 1, '1': 2, '2': 3, '-1': 3, '3': 3, '99': 3, 'abc': 3, '1.5': 3, ' 1 ': 2}
        for value, expected in table.items():
            with self.subTest(value=value):
                _, _, calls, _, _ = self.run_writer([json.dumps(BAD)], retries=value)
                self.assertEqual(calls, expected)

    def test_malformed_json_keeps_the_existing_repair_path(self):
        delivery = self.root / '.uncle/workflow/edits/1.json'
        env = {'UNCLE_CONFIG': str(self.root / 'absent'), 'UNCLE_PROJECT_ROOT': str(self.root),
               'UNCLE_ARTIFACT_DELIVERY': str(delivery), 'UNCLE_STATUS_STAGE': 'updated-plan-worker-edits-1'}
        with patch.dict(os.environ, env, clear=True), \
                patch.object(agent, 'constrained_completion', return_value=('{"ops": [', 'stop', {}, 'json_schema')) as constrained, \
                patch.object(agent, 'interruptible_chat', side_effect=[DONE, RuntimeError('repair turn reached')]) as chat:
            with self.assertRaisesRegex(RuntimeError, 'repair turn reached'):
                hosted.run_opencode('agent', self.values, json.dumps(BAD), self.root)
        self.assertEqual(constrained.call_count, 1)
        self.assertEqual(chat.call_count, 2)   # the work, then the existing repair turn (no feedback retry)


class BoundedWriters(Base):
    def test_bounded_writer_makes_one_request_whatever_the_variable(self):
        for value in (None, '2', '1'):
            with self.subTest(value=value):
                _, error, calls, _, repairs = self.run_writer([json.dumps(BAD)], bounded=True, retries=value)
                self.assertIn('violates the artifact schema', error or '')
                self.assertEqual(calls, 1)
                self.assertEqual(repairs, 0)


class Sanitization(Base):
    def test_feedback_never_carries_values_paths_or_raw_exception_text(self):
        leaky = ValueError('bad value %s at %s' % (SECRET, LOCAL_PATH))
        real = WS.__dict__.get('validate')
        bad = json.dumps(dict(BAD, ops=SECRET))
        with patch.object(agent, 'save_rejected', return_value=None):
            with patch.dict(os.environ, {}, clear=False):
                _, _, calls, sent, _ = self.run_writer([bad])
        self.assertGreaterEqual(calls, 2)
        for messages in sent[1:]:
            retry_text = json.dumps(messages[len(sent[0]):])
            self.assertNotIn(SECRET, retry_text)
            self.assertNotIn(LOCAL_PATH, retry_text)
            self.assertNotIn('/Users/', retry_text)
        del leaky, real

    def test_a_validator_exception_with_secret_and_path_is_not_echoed(self):
        raiser = ValueError('rejected %s in %s' % (SECRET, LOCAL_PATH))
        with patch.object(agent, 'validate_final', side_effect=raiser, create=True), \
                patch.object(WS, 'validate_packet', side_effect=raiser, create=True):
            _, _, calls, sent, _ = self.run_writer([json.dumps(BAD)])
        for messages in sent[1:]:
            tail = json.dumps(messages[len(sent[0]):])
            self.assertNotIn(SECRET, tail)
            self.assertNotIn(LOCAL_PATH, tail)


def enum_values(node):
    if isinstance(node, dict):
        if 'enum' in node:
            yield node['enum']
        for child in node.values():
            yield from enum_values(child)
    elif isinstance(node, list):
        for child in node:
            yield from enum_values(child)


class IdEnums(unittest.TestCase):
    def test_no_enum_carries_the_supplied_ids_for_any_set_size(self):
        for size in (1, 8, 9):
            ids = ['ZZID-%d' % n for n in range(size)]
            with self.subTest(size=size):
                schema = WS._op(ids=ids)
                for values in enum_values(schema):
                    self.assertFalse(set(values) & set(ids), values)

    def test_the_empty_set_adds_no_id_enum(self):
        for values in enum_values(WS._op(ids=[])):
            self.assertFalse([v for v in values if str(v).startswith('ZZID')])


if __name__ == '__main__':
    unittest.main()
