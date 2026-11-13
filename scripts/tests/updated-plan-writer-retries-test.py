#!/usr/bin/env python3
"""A one-finding updated-plan writer that is asked again gets more answer room, and a rejected response is kept."""
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts' / 'lib'))
import http_agent as agent  # noqa: E402
import updated_plan_ops as ops  # noqa: E402


class Budget(unittest.TestCase):
    def budget(self, ids=('AR-1',), **env):
        clean = {k: v for k, v in os.environ.items() if not k.startswith('WORKFLOW_UPDATED_PLAN') and k != 'UNCLE_UPDATED_PLAN_ANSWER_SCALE'}
        with mock.patch.dict(os.environ, dict(clean, **env), clear=True):
            return ops.writer_budget(list(ids))

    def test_the_first_attempt_keeps_its_budget(self):
        self.assertEqual(self.budget()[1], 4096)

    def test_a_retry_gets_twice_the_room(self):
        self.assertEqual(self.budget(UNCLE_UPDATED_PLAN_ANSWER_SCALE='2')[1], 8192)
        first = self.budget(('AR-1', 'AR-2', 'AR-3'))[1]
        self.assertEqual(self.budget(('AR-1', 'AR-2', 'AR-3'), UNCLE_UPDATED_PLAN_ANSWER_SCALE='2')[1], first * 2)

    def test_the_scale_is_bounded_and_junk_is_ignored(self):
        self.assertEqual(self.budget(UNCLE_UPDATED_PLAN_ANSWER_SCALE='99')[1], 4096 * 4)
        for junk in ('0', '-3', 'x', ''):
            self.assertEqual(self.budget(UNCLE_UPDATED_PLAN_ANSWER_SCALE=junk)[1], 4096, junk)

    def test_the_turn_count_is_not_scaled(self):
        self.assertEqual(self.budget(UNCLE_UPDATED_PLAN_ANSWER_SCALE='2')[0], self.budget()[0])

    def test_both_drivers_ask_again_with_the_larger_budget(self):
        for name, launcher in (('stagegate.sh', 'updated_plan_launch_writer'), ('change-workflow.sh', 'updated_change_plan_launch_writer')):
            text = (ROOT / 'scripts' / name).read_text()
            retry = [l for l in text.splitlines() if 'SCHEMA_ATTEMPT=retry ' + launcher in l]
            self.assertEqual(len(retry), 1, name)
            self.assertIn('UNCLE_UPDATED_PLAN_ANSWER_SCALE=2', retry[0], name)
            last = [l for l in text.splitlines() if l.strip().startswith('UNCLE_UPDATED_PLAN_ANSWER_SCALE=2 ' + launcher)]
            self.assertEqual(len(last), 1, name + ' (the last try by the other delivery path)')


class Rejected(unittest.TestCase):
    def test_the_rejected_answer_and_the_error_are_kept(self):
        with tempfile.TemporaryDirectory() as directory, mock.patch.dict(
                os.environ, {'UNCLE_PROJECT_ROOT': directory, 'UNCLE_STATUS_STAGE': 'updated-plan-worker-edits-7-2'}):
            path = agent.save_rejected('schema', ValueError('$.ops[4].id must be one of\n  "B-1"'), '{"ops":[{"id":"X-9"}]}')
            text = Path(path).read_text()
            self.assertIn('rejected-updated-plan-worker-edits-7-2-schema-', path)
            self.assertIn('error: $.ops[4].id must be one of "B-1"', text)       # on one line
            self.assertIn('{"ops":[{"id":"X-9"}]}', text)
            self.assertIn(path, agent.rejection_note(path))

    def test_an_unwritable_log_directory_never_fails_the_stage(self):
        with tempfile.TemporaryDirectory() as directory:
            blocker = Path(directory, 'file')
            blocker.write_text('x')
            with mock.patch.dict(os.environ, {'UNCLE_PROJECT_ROOT': str(blocker)}):
                self.assertEqual(agent.save_rejected('json', 'bad', 'text'), '')
            self.assertEqual(agent.rejection_note(''), '')


if __name__ == '__main__':
    unittest.main()
