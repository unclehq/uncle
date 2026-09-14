import io
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'lib'))
from process_tree import start_check, wait_check, finish_check, check_timeout


class Checks(unittest.TestCase):
    def test_timeout_kills_owned_child_and_records_failure(self):
        with tempfile.TemporaryFile() as output:
            child = start_check([sys.executable, '-c', 'import time; time.sleep(60)'], stdout=output)
            try:
                self.assertEqual(wait_check(child, .2, output), 124)
                self.assertIsNotNone(child.poll())
                output.seek(0)
                self.assertIn(b'TIMEOUT', output.read())
            finally:
                finish_check(child)

    def test_success_keeps_original_status(self):
        with tempfile.TemporaryFile() as output:
            child = start_check([sys.executable, '-c', 'raise SystemExit(7)'], stdout=output)
            try:
                self.assertEqual(wait_check(child, 10, output), 7)
            finally:
                finish_check(child)

    def test_unbounded_limits_rejected(self):
        for value in ('0', '-1', 'nan', 'inf'):
            with patch.dict(os.environ, WORKFLOW_CHECK_TIMEOUT_SECONDS=value):
                with self.assertRaises(ValueError):
                    check_timeout()


if __name__ == '__main__':
    unittest.main()
