import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / 'scripts/lib')]
import parallel_checks
import uncle_tui


class Status(unittest.TestCase):
    def test_executor_reports_stop_on_success_and_failure(self):
        for failure in (False, True):
            with tempfile.TemporaryDirectory() as directory:
                path = Path(directory) / 'status.jsonl'
                with patch.dict(os.environ, UNCLE_STATUS_FILE=str(path)), patch.object(
                        parallel_checks, '_run_checks', side_effect=ValueError('failed') if failure else None,
                        return_value=0):
                    if failure:
                        with self.assertRaises(ValueError):
                            parallel_checks.run(None)
                    else:
                        self.assertEqual(parallel_checks.run(None), 0)
                events = [json.loads(line) for line in path.read_text().splitlines()]
                self.assertEqual([e['state'] for e in events], ['Running', 'Stopped'])

    def test_ui_handles_overlap_exit_and_late_events(self):
        ui = uncle_tui.UncleTUI.__new__(uncle_tui.UncleTUI)
        ui.proc = Mock()
        ui.proc.poll.return_value = None
        self.assertEqual(ui.test_execution_status(), '')
        def event(identity, state):
            ui._apply_status(json.dumps(dict(event='test_execution', id=identity, state=state)))
        event('1', 'Running')
        event('2', 'Running')
        event('1', 'Stopped')
        self.assertEqual(ui.test_execution_status(), 'Running')
        event('2', 'Stopped')
        self.assertEqual(ui.test_execution_status(), '')
        event('3', 'Running')
        ui.proc.poll.return_value = 1
        self.assertEqual(ui.test_execution_status(), '')
        ui.workflow_exit_reported = True
        ui.proc.poll.return_value = None
        event('4', 'Running')
        self.assertEqual(ui.test_execution_status(), '')
        self.assertNotIn('4', ui.active_test_runs)


if __name__ == '__main__':
    unittest.main()
