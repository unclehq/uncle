"""Timing must survive concurrency and failure without changing build behavior."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'lib'))
from build_timing import BuildTiming, descendants, event, render, stage
from process_tree import start_check, finish_check


class TimingTests(unittest.TestCase):
    def test_driver_supervision_initializes_timing_for_child_and_preserves_exit(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location('timed_driver',
            Path(__file__).resolve().parents[1] / 'lib/plan-executability.py')
        driver = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(driver)
        with tempfile.TemporaryDirectory() as directory, patch.object(driver, 'STATE', Path(directory)), \
                patch.dict(os.environ, WORKFLOW_METRICS='1'):
            def supervised(callback, command, state, root):
                target = Path(os.environ['UNCLE_TIMING_DIR'])
                self.assertTrue((target / 'run.json').exists())
                code = "import os; from build_timing import event; event('test', 'child', 0, .1, 0)"
                env = dict(os.environ, PYTHONPATH=str(Path(driver.__file__).parent))
                subprocess.run([sys.executable, '-c', code], env=env, check=True)
                return 7
            with patch('supervisor.supervised_lock_run', side_effect=supervised):
                self.assertEqual(driver.lock_run(['fake-driver']), 7)
            runs = list((Path(directory) / 'performance').glob('*/run.json'))
            self.assertEqual(len(runs), 1)
            self.assertEqual(json.loads(runs[0].read_text())['process_exit'], 7)
            events = [json.loads(p.read_text()) for p in (runs[0].parent / 'events').glob('*.json')]
            self.assertTrue(any(e.get('name') == 'child' for e in events))

    def test_real_process_and_stage_failure_preserve_status(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, WORKFLOW_PROFILE_INTERVAL='.1'):
            with BuildTiming(Path(directory)) as timing:
                stage('BASELINE')
                child = start_check([sys.executable, '-c', 'import time; time.sleep(.25); raise SystemExit(7)'])
                self.assertEqual(child.wait(), 7)
                finish_check(child)
                finish_check(child)  # completion may be observed twice
                stage('WAIT_APPROVAL')
                timing.status = 7
            records = [json.loads(p.read_text()) for p in (timing.directory / 'events').glob('*.json')]
            processes = [r for r in records if r['kind'] == 'process']
            self.assertEqual(len(processes), 1)
            self.assertEqual(processes[0]['process_exit'], 7)
            self.assertGreater(processes[0]['elapsed_seconds'], .2)
            self.assertNotIn('raise SystemExit', json.dumps(records))
            report = (timing.directory / 'report.md').read_text()
            self.assertIn('BASELINE', report)
            self.assertIn('WAIT_APPROVAL', report)
            self.assertEqual(json.loads((timing.directory / 'run.json').read_text())['process_exit'], 7)
            self.assertTrue(json.loads((timing.directory / 'timeline.json').read_text())['traceEvents'])

    def test_disabled_and_unwritable_recording_do_not_change_result(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with patch.dict(os.environ, WORKFLOW_METRICS='0'):
                with BuildTiming(root) as timing:
                    event('process', 'ignored', time.time(), 1)
                self.assertFalse(timing.enabled)
                self.assertFalse((root / 'performance').exists())
            blocked = root / 'file'; blocked.write_text('blocked')
            with BuildTiming(blocked) as timing:
                self.assertFalse(timing.enabled)
            with patch.dict(os.environ, UNCLE_TIMING_DIR=str(blocked)):
                event('process', 'ignored', time.time(), 1)
                stage('BASELINE')

    def test_resumes_have_separate_runs_and_exception_is_preserved(self):
        with tempfile.TemporaryDirectory() as directory, patch('build_timing.snapshot', return_value=[]):
            with self.assertRaisesRegex(RuntimeError, 'original failure'):
                with BuildTiming(Path(directory)) as first:
                    stage('IMPLEMENT')
                    raise RuntimeError('original failure')
            with BuildTiming(Path(directory)) as second:
                stage('IMPLEMENT')
            self.assertNotEqual(first.directory, second.directory)
            self.assertEqual(json.loads((first.directory / 'run.json').read_text())['status'], 'interrupted')

    def test_renderer_failure_does_not_replace_workflow_outcome(self):
        with tempfile.TemporaryDirectory() as directory, patch('build_timing.snapshot', return_value=[]), \
                patch('build_timing.render', side_effect=RuntimeError('report failed')):
            with BuildTiming(Path(directory)) as timing:
                timing.status = 7
            self.assertEqual(timing.status, 7)
            with self.assertRaisesRegex(ValueError, 'workflow failure'):
                with BuildTiming(Path(directory)):
                    raise ValueError('workflow failure')

    def test_descendants_include_nested_tools_and_exclude_other_builds(self):
        rows = [(2, 1, 'bash', 0), (3, 2, 'python', 0), (4, 3, 'git', 0), (5, 99, 'other', 0)]
        self.assertEqual([r[0] for r in descendants(rows, 1)], [2, 3, 4])

    def test_sampling_failure_does_not_stop_build(self):
        with tempfile.TemporaryDirectory() as directory, patch('build_timing.snapshot', side_effect=OSError('unavailable')):
            with BuildTiming(Path(directory)) as timing:
                time.sleep(.02)
                timing.status = 0
            metadata = json.loads((timing.directory / 'run.json').read_text())
            self.assertEqual(metadata['process_exit'], 0)
            self.assertGreater(metadata['sampling_errors'], 0)

    def test_concurrent_records_and_run_scoped_metrics(self):
        from concurrent.futures import ThreadPoolExecutor
        with tempfile.TemporaryDirectory() as directory, patch('build_timing.snapshot', return_value=[]):
            root = Path(directory)
            with BuildTiming(root) as timing:
                with ThreadPoolExecutor(4) as pool:
                    list(pool.map(lambda i: event('process', f'tool-{i}', time.time(), .1), range(20)))
                metrics = root / 'metrics'; metrics.mkdir()
                (metrics / 'current.json').write_text(json.dumps(dict(kind='approval', stage='current-approval',
                    run_id=timing.directory.name, elapsed_seconds=2, ended_at=time.time())))
                (metrics / 'old.json').write_text(json.dumps(dict(kind='approval', stage='old-approval',
                    run_id='different-run', elapsed_seconds=100, ended_at=time.time())))
            report = (timing.directory / 'report.md').read_text()
            self.assertIn('current-approval', report)
            self.assertNotIn('old-approval', report)
            self.assertEqual(len(list((timing.directory / 'events').glob('*.json'))), 20)

    def test_report_keeps_overlapping_process_time_separate(self):
        with tempfile.TemporaryDirectory() as directory, patch('build_timing.snapshot', return_value=[]):
            with BuildTiming(Path(directory)) as timing:
                event('process', 'first', time.time(), 5)
                event('process', 'second', time.time(), 5)
            metadata = json.loads((timing.directory / 'run.json').read_text())
            self.assertLess(metadata['elapsed_seconds'], 5)
            self.assertIn('do not add categories', (timing.directory / 'report.md').read_text())


if __name__ == '__main__':
    unittest.main()
