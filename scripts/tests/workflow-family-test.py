from pathlib import Path
import sys
import tempfile
import unittest
import os
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'lib'))
from workflow_family import prepare

class FamilyTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);self.state=self.root/'.uncle/workflow';self.state.mkdir(parents=True)
        (self.state/'driver.lock').write_text('owned')
        (self.state/'driver.guard').write_bytes(b'1')
        self.inode=(self.state/'driver.lock').stat().st_ino
    def test_change_state_is_archived_before_app_start(self):
        (self.state/'state').write_text('34:ANALYZE\n')
        (self.state/'approvals').mkdir();(self.state/'approvals/plan').write_text('old approval')
        archive=prepare(self.root,'app')
        self.assertEqual((archive/'state').read_text(),'34:ANALYZE\n')
        self.assertTrue((archive/'approvals/plan').exists())
        self.assertFalse((self.state/'state').exists())
        self.assertFalse((self.state/'approvals').exists())
        self.assertEqual((self.state/'driver.lock').stat().st_ino,self.inode)
        self.assertEqual((self.state/'driver.lock').read_text(),'owned')
        self.assertEqual((self.state/'driver.guard').read_bytes(),b'1')
    def test_fresh_run_keeps_active_profiler_and_archives_old_runs(self):
        active = self.state / 'performance' / 'new'
        old = self.state / 'performance' / 'old'
        for path in (active, old):
            path.mkdir(parents=True)
            (path / 'run.json').write_text('{}')
        (active / 'events').mkdir()
        (active / 'events' / 'start.json').write_text('{}')
        with patch.dict(os.environ, UNCLE_TIMING_DIR=str(active)):
            archive = prepare(self.root, 'app', fresh=True)
        self.assertTrue((active / 'run.json').exists())
        self.assertTrue((active / 'events/start.json').exists())
        self.assertTrue((archive / 'performance/old/run.json').exists())
        self.assertFalse((archive / 'performance/new').exists())
        self.assertFalse(old.exists())

    def test_resume_preserves_state_and_approvals(self):
        prepare(self.root,'app');(self.state/'state').write_text('IMPLEMENT\n')
        self.assertIsNone(prepare(self.root,'app'))
        self.assertEqual((self.state/'state').read_text(),'IMPLEMENT\n')
    def test_new_same_family_archives_prior_run(self):
        prepare(self.root,'app');(self.state/'state').write_text('COMPLETE\n')
        self.assertIsNotNone(prepare(self.root,'app',fresh=True))
        self.assertFalse((self.state/'state').exists())
    def test_explicit_family_switch_handles_shared_state(self):
        prepare(self.root,'change');(self.state/'state').write_text('34:IMPLEMENT\n')
        self.assertIsNotNone(prepare(self.root,'app'))

if __name__=='__main__':unittest.main()
