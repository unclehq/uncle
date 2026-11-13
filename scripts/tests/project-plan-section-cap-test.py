#!/usr/bin/env python3
"""A project-plan section that stops on its output cap is run again with more room, and the fallback to Markdown is announced.

The run that found this: the tests section of a web app (5.6k characters of dense JSON) hit the 4096-token cap and exited 2. A worker
that exits non-zero had no retry, so the whole typed plan was abandoned for the single-pass Markdown plan, silently, and the model
later imported from that Markdown had a section the Markdown has no `##` heading for, which failed the updated-plan merge."""
import os
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts' / 'lib'))
import self_hosted_http as http  # noqa: E402

SECTION = 'project_plan_section_model_packet'
STAGE = 'project-plan-section-tests'


def cap(artifact, stage=STAGE, limit=65536, option='turn-output-tokens', **env):
    clean = {k: v for k, v in os.environ.items() if not k.startswith(('WORKFLOW_', 'UNCLE_'))}
    with tempfile.TemporaryDirectory() as directory, mock.patch.dict(
            os.environ, dict(clean, UNCLE_STATUS_STAGE=stage, UNCLE_CONFIG=str(Path(directory, 'absent')), **env), clear=True):
        return http.output_cap(limit, option, artifact)


class Cap(unittest.TestCase):
    def test_a_section_packet_gets_room_for_a_real_section(self):
        self.assertEqual(cap(SECTION), 16384)
        self.assertEqual(cap('project_plan_section_worker_packet'), 16384)

    def test_the_mechanical_packets_keep_their_small_cap(self):
        self.assertEqual(cap('updated_plan_edit_ops_packet', stage='updated-plan-worker-edits-1'), 4096)
        self.assertEqual(cap('project_plan_outline_packet', stage='project-plan-section-outline'), 4096)
        self.assertEqual(cap('implementation_notes', stage='implementation'), 32768)

    def test_a_rerun_gets_the_scale_and_it_is_bounded(self):
        self.assertEqual(cap(SECTION, UNCLE_PLAN_SECTION_ANSWER_SCALE='2'), 32768)
        self.assertEqual(cap(SECTION, UNCLE_PLAN_SECTION_ANSWER_SCALE='99'), 65536)       # 4x, then the stage ceiling
        for junk in ('0', '-2', 'x', ''):
            self.assertEqual(cap(SECTION, UNCLE_PLAN_SECTION_ANSWER_SCALE=junk), 16384, junk)

    def test_the_scale_touches_nothing_else(self):
        self.assertEqual(cap('updated_plan_edit_ops_packet', stage='updated-plan-worker-edits-1', UNCLE_PLAN_SECTION_ANSWER_SCALE='4'), 4096)
        self.assertEqual(cap(SECTION, option='reasoning-output-tokens', UNCLE_PLAN_SECTION_ANSWER_SCALE='4'),
                         cap(SECTION, option='reasoning-output-tokens'))

    def test_an_explicit_operator_cap_still_wins_over_the_default(self):
        self.assertEqual(cap(SECTION, WORKFLOW_SELF_HOSTED_TURN_OUTPUT_TOKENS='8000'), 8000)
        self.assertEqual(cap(SECTION, WORKFLOW_SELF_HOSTED_TURN_OUTPUT_TOKENS='8000', UNCLE_PLAN_SECTION_ANSWER_SCALE='2'), 16000)


def function(source, name):
    match = re.search(r'(?ms)^%s\(\) \{\n.*?^\}\n' % re.escape(name), source)
    assert match, name
    return match.group(0)


class Driver(unittest.TestCase):
    source = (ROOT / 'scripts' / 'stagegate.sh').read_text()

    def run_bash(self, body, log_text=''):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            (base / 'logs').mkdir()
            (base / 'sections').mkdir()
            (base / 'logs' / 'project-plan-section-tests.log').write_text(log_text)
            names = ('project_plan_section_capped', 'project_plan_section_rerun_capped', 'project_plan_section_record_failure')
            script = ('LOG_DIR="%s/logs"; D="%s/sections"\n' % (base, base) + '\n'.join(function(self.source, n) for n in names) + '\n' + body)
            done = subprocess.run(['bash', '-c', script], cwd=base, capture_output=True, text=True, timeout=60)
            failed = base / 'sections' / 'failed-sections'
            done.failed_sections = failed.read_text() if failed.exists() else ''
            return done, base

    def test_only_a_cap_stop_is_recognised(self):
        done, _ = self.run_bash('project_plan_section_capped tests && echo capped', 'cause: Model output reached the limit of 4096 tokens for one turn')
        self.assertEqual(done.stdout.strip(), 'capped')
        done, _ = self.run_bash('project_plan_section_capped tests && echo capped; echo end', 'cause: Model API rejected every request form')
        self.assertEqual(done.stdout.strip(), 'end')

    def test_the_rerun_doubles_the_room_keeps_the_first_attempt_and_reports_its_result(self):
        body = ('project_plan_section_run() { echo "scale=${UNCLE_PLAN_SECTION_ANSWER_SCALE:-1} args=$*"; return 0; }\n'
                'project_plan_section_rerun_capped tests "$D" local; echo "rc=$?"\n'
                'cat "$LOG_DIR/project-plan-section-tests.log"; ls "$LOG_DIR"')
        done, _ = self.run_bash(body, 'cause: Model output reached the limit of 4096 tokens')
        self.assertIn('once more with twice the room', done.stdout)
        self.assertIn('scale=2 args=tests', done.stdout)
        self.assertIn('rc=0', done.stdout)
        self.assertIn('project-plan-section-tests.attempt1.log', done.stdout)
        failing = 'project_plan_section_run() { return 3; }\nproject_plan_section_rerun_capped tests "$D" local; echo "rc=$?"'
        done, _ = self.run_bash(failing)
        self.assertIn('rc=3', done.stdout)

    def test_a_failed_section_is_recorded_with_its_cause(self):
        done, _ = self.run_bash('project_plan_section_record_failure tests "$D"; project_plan_section_record_failure other "$D"',
                                'Launching agent\n[done] error\n  cause: Model output reached the limit of 4096 tokens for one turn\n')
        lines = done.failed_sections.splitlines()
        self.assertEqual(lines[0], 'tests: Model output reached the limit of 4096 tokens for one turn')
        self.assertTrue(lines[1].startswith('other: exited with an error'))

    def test_both_section_paths_use_the_rerun_and_the_fallback_is_announced(self):
        settle = function(self.source, 'project_plan_section_settle')
        self.assertIn('project_plan_section_rerun_capped', settle)
        self.assertEqual(self.source.count('project_plan_section_rerun_capped "$name"'), 2)      # settle (all paths) and the bounded slot
        self.assertIn('did not complete; falling back to the single-pass Markdown plan', self.source)
        self.assertIn('project_plan_sections_ran=1', self.source)


if __name__ == '__main__':
    unittest.main()
