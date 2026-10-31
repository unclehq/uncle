#!/usr/bin/env python3
"""Progress watchdog and evidence regressions without model calls."""
import os
import json
import re
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts/lib'))
import writer_deadline


class WriterBounds(unittest.TestCase):
    def test_progress_extends_idle_window_but_never_absolute_ceiling(self):
        with tempfile.TemporaryDirectory() as temp, patch.dict(os.environ, {
                'UNCLE_CONFIG': str(Path(temp) / 'config'),
                'WORKFLOW_SELF_HOSTED_WRITER_NO_PROGRESS_SECONDS': '1'}, clear=True):
            start = time.monotonic()
            with self.assertRaisesRegex(ValueError, 'deadline: ceiling'):
                with writer_deadline.deadline(2):
                    while True:
                        writer_deadline.progress()
                        time.sleep(.1)
            self.assertGreaterEqual(time.monotonic() - start, 2)
            self.assertLess(time.monotonic() - start, 3)

    def test_shell_watchdog_uses_progress_file_and_stops_silent_descendants(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            script = '''
. "$ROOT/scripts/lib/model-jobs.sh"
stage_uses_self_hosted() { return 0; }
run_claude() {
    python3 -c 'import os,time; p=os.environ["UNCLE_WRITER_PROGRESS_FILE"]; [(os.utime(p,None),time.sleep(.2)) for _ in range(8)]'
}
workflow_model_writer updated-plan run_claude prompt writer
run_claude() { (sleep 8; touch leaked) & wait; }
workflow_model_writer updated-plan run_claude prompt writer
'''
            env = dict(os.environ, ROOT=str(ROOT), UNCLE_CONFIG=str(root / 'config'),
                       WORKFLOW_SELF_HOSTED_WRITER_SECONDS='6', WORKFLOW_SELF_HOSTED_WRITER_NO_PROGRESS_SECONDS='1')
            result = subprocess.run(['bash', '-ec', script], cwd=root, env=env,
                                    capture_output=True, text=True, timeout=6)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn('deadline: no-progress', result.stderr)
            self.assertNotIn('deadline: ceiling', result.stderr)
            self.assertFalse((root / 'leaked').exists())

    def test_inner_deadline_is_not_hidden_by_runner_recovery(self):
        with tempfile.TemporaryDirectory() as temp:
            script = '''
. "$ROOT/scripts/lib/model-jobs.sh"
stage_uses_self_hosted() { return 0; }
run_claude() {
    python3 -c 'import sys,time;sys.path.insert(0,sys.argv[1]);from writer_deadline import deadline
try:
 with deadline(.2):time.sleep(1)
except ValueError:pass' "$ROOT/scripts/lib"
}
workflow_model_writer updated-plan run_claude prompt updated-plan-worker-edits-1
'''
            result = subprocess.run(['bash', '-c', script], cwd=temp, env=dict(os.environ,
                ROOT=str(ROOT), UNCLE_CONFIG=str(Path(temp) / 'config')), capture_output=True, text=True, timeout=4)
            self.assertEqual(result.returncode, 124, result.stderr)
            self.assertIn('deadline: ceiling', result.stderr)

    def test_archived_packets_are_outside_live_resolution_globs(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            packet = root / 'resolutions-G1.json'
            packet.write_text('old')
            subprocess.run(['bash', '-ec', '. "$ROOT/scripts/lib/model-jobs.sh"; workflow_archive_attempt resolutions-G1.json'],
                cwd=root, env=dict(os.environ, ROOT=str(ROOT)), check=True)
            packet.write_text('new')
            self.assertEqual(list(root.glob('resolutions-*.json')), [packet])
            self.assertEqual((root / 'attempts/resolutions-G1-r1.json').read_text(), 'old')

    def test_archive_keeps_packets_and_directory_inputs_across_rounds(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / 'edits').mkdir()
            (root / 'edits/packet.json').write_text('first')
            script = '''
. "$ROOT/scripts/lib/model-jobs.sh"
workflow_archive_attempt edits
printf second > edits/packet.json
workflow_archive_attempt edits
printf third > edits/packet.json
'''
            subprocess.run(['bash', '-ec', script], cwd=root, env=dict(os.environ, ROOT=str(ROOT)), check=True)
            self.assertEqual((root / 'edits-r1/packet.json').read_text(), 'first')
            self.assertEqual((root / 'edits-r2/packet.json').read_text(), 'second')
            self.assertEqual((root / 'edits/packet.json').read_text(), 'third')

    def test_cancelled_speculation_cannot_keep_writing_attempt_logs(self):
        source = (ROOT / 'scripts/stagegate.sh').read_text()
        cancel = re.search(r'^cancel_speculation\(\) \{\n.*?^}', source, re.M | re.S)[0]
        with tempfile.TemporaryDirectory() as temp:
            script = cancel + '''
run_stage() { (sleep .7; echo leaked > "$STATE_DIR/leaked") & wait; }
run_stage &
spec_pid=$!; spec_stage=UPDATED_PLAN
sleep .1
cancel_speculation
sleep 1
'''
            subprocess.run(['bash', '-c', script], cwd=temp, env=dict(os.environ,
                ROOT=str(ROOT), STATE_DIR=temp), capture_output=True, text=True, check=True, timeout=5)
            self.assertFalse((Path(temp) / 'leaked').exists())

    def test_stage_archive_retains_advisor_resolver_and_prior_rounds(self):
        for stage in ('updated-plan', 'updated-change-plan'):
            with self.subTest(stage=stage), tempfile.TemporaryDirectory() as temp:
                root = Path(temp)
                names = ['updated-plan-worker-review.log', 'updated-plan-worker-resolve-G1.jsonl', 'UPDATED_PLAN.log']
                for name in names:
                    (root / name).write_text('first')
                script = '''
    . "$ROOT/scripts/lib/model-jobs.sh"
    workflow_archive_stage "$ARCHIVE_STAGE"
    printf second > "$LOG_DIR/updated-plan-worker-review.log"
    workflow_archive_stage "$ARCHIVE_STAGE"
    '''
                subprocess.run(['bash', '-ec', script], cwd=root, env=dict(os.environ,
                    ROOT=str(ROOT), LOG_DIR=str(root), ARCHIVE_STAGE=stage), check=True)
                self.assertEqual((root / 'updated-plan-worker-review-r1.log').read_text(), 'first')
                self.assertEqual((root / 'updated-plan-worker-review-r2.log').read_text(), 'second')
                self.assertEqual((root / 'updated-plan-worker-resolve-G1-r1.jsonl').read_text(), 'first')
                self.assertFalse(list(root.glob('*-r1-r*')))

    def test_triage_includes_last_delta_when_runner_exits_between_polls(self):
        import triage_chat
        with tempfile.TemporaryDirectory() as temp:
            def launch(*args, **kwargs):
                output = kwargs['stdout']
                def say(text):
                    output.write((json.dumps({'type': 'assistant', 'message': {
                        'content': [{'type': 'text', 'text': text}]}}) + '\n').encode())
                    output.flush()
                say('part one')
                child = Mock()
                child.wait.side_effect = lambda **kw: (say('part two and done'), 0)[1]
                return child
            with patch.object(triage_chat.subprocess, 'Popen', side_effect=launch), \
                    patch.object(triage_chat, 'kill_tree'):
                request = triage_chat.TriageRequest(['stub'], 'prompt', {}, temp, str(Path(temp) / 'log.jsonl'))
                request.thread.join(timeout=3)
                self.assertFalse(request.thread.is_alive())
                events = list(request.events.queue)
            self.assertEqual([value for kind, value in events if kind == 'delta'],
                             ['part one', 'part two and done'])
            self.assertEqual(events[-1], ('reply', 'part two and done'))

    def test_writer_jobs_respects_smaller_provider_pool_and_hosted_defaults(self):
        with tempfile.TemporaryDirectory() as temp:
            script = '''
. "$ROOT/scripts/lib/model-jobs.sh"
workflow_model_capacity() { echo 4; }
stage_uses_self_hosted() { return 0; }
workflow_writer_jobs updated-plan
workflow_model_capacity() { echo 0; }
workflow_writer_jobs updated-plan
stage_uses_self_hosted() { return 1; }
workflow_writer_jobs updated-plan
'''
            result = subprocess.run(['bash', '-ec', script], cwd=temp, env=dict(os.environ,
                ROOT=str(ROOT), UNCLE_CONFIG=str(Path(temp) / 'config'), WORKFLOW_SELF_HOSTED_WRITER_JOBS='12'),
                capture_output=True, text=True, check=True)
            self.assertEqual(result.stdout, '4\n12\n0\n')


if __name__ == '__main__':
    unittest.main()
