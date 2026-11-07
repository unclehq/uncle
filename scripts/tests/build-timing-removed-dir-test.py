"""The build sampler outlives the driver. If the driver removed the run's worktree, finishing must not recreate its directory."""
import os
import shutil
import sys
import tempfile
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'lib'))
import build_timing  # noqa: E402


class RemovedRunDirectory(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp()) / 'project-change-1'
        (self.root / '.uncle' / 'workflow').mkdir(parents=True)
        self.addCleanup(shutil.rmtree, self.root.parent, ignore_errors=True)
        self.saved = os.environ.get('UNCLE_TIMING_DIR')
        self.addCleanup(lambda: os.environ.pop('UNCLE_TIMING_DIR', None) if self.saved is None
                        else os.environ.__setitem__('UNCLE_TIMING_DIR', self.saved))

    def test_a_removed_project_is_not_recreated_by_the_sampler(self):
        with build_timing.BuildTiming(self.root / '.uncle' / 'workflow'):
            time.sleep(.3)
            shutil.rmtree(self.root)              # the driver removed the worktree mid-run
            build_timing.event('x', 'late', time.time(), 0.1)
            build_timing.stage('late-stage')
            time.sleep(.3)
        self.assertFalse(self.root.exists(), 'the sampler recreated the removed directory')

    def test_a_normal_run_still_writes_its_report(self):
        with build_timing.BuildTiming(self.root / '.uncle' / 'workflow'):
            time.sleep(.3)
        runs = list((self.root / '.uncle' / 'workflow' / 'performance').iterdir())
        self.assertEqual(len(runs), 1)
        self.assertTrue((runs[0] / 'report.md').exists())


if __name__ == '__main__':
    unittest.main()
