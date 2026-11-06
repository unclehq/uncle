import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'scripts' / 'lib'))

from uncle_tui import format_failure_line


class FailureLine(unittest.TestCase):
    def test_exit_zero_has_no_line(self):
        self.assertIsNone(format_failure_line(0, 'anything'))

    def test_nonzero_with_last_line(self):
        self.assertEqual(format_failure_line(1, 'boom happened'),
                         'Driver exited with status 1: boom happened')

    def test_nonzero_no_output(self):
        for empty in ('', None, '   '):
            self.assertEqual(format_failure_line(2, empty),
                             'Driver exited with status 2: (no output)')

    def test_signal_statuses_show_line(self):
        for code in (130, 143):
            self.assertEqual(format_failure_line(code, 'stopped'),
                             'Driver exited with status %d: stopped' % code)

    def test_escapes_removed(self):
        line = format_failure_line(1, '\x1b[31mred\x1b[0m text\x07')
        self.assertEqual(line, 'Driver exited with status 1: red text')

    def test_redaction(self):
        line = format_failure_line(1, 'Authorization: Bearer abc123secret')
        self.assertNotIn('abc123secret', line)
        self.assertIn('[REDACTED]', line)


if __name__ == '__main__':
    unittest.main()
