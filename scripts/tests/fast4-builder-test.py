#!/usr/bin/env python3
"""Progress watchdog and evidence regressions without model calls."""
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

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
