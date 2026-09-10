#!/usr/bin/env python3
import pathlib
import subprocess
import sys
import tempfile
import unittest

HELPER = pathlib.Path(__file__).resolve().parents[1] / 'lib/fix-report-whitespace.py'


class Checks(unittest.TestCase):
    def test_repairs_reports_without_hiding_source_errors(self):
        with tempfile.TemporaryDirectory() as folder:
            root = pathlib.Path(folder)
            def git(*args):
                return subprocess.run(['git', *args], cwd=root, check=True, capture_output=True)
            git('init')
            report = root / 'CHANGE_REQUEST.md'
            source = root / 'source.py'
            report.write_bytes(b'# Request\noriginal\n')
            source.write_bytes(b'x = 1\n')
            git('add', '.')
            report.write_bytes(b'# Request\noriginal\nnew text  \n\n')
            source.write_bytes(b'x = 2  \n')
            result = subprocess.run([sys.executable, str(HELPER)], cwd=root, capture_output=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertEqual(report.read_bytes(), b'# Request\noriginal\nnew text\n')
            self.assertEqual(source.read_bytes(), b'x = 2  \n')
            self.assertIn(b'source.py', result.stdout)
            source.write_bytes(b'x = 2\n')
            result = subprocess.run([sys.executable, str(HELPER)], cwd=root, capture_output=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(report.read_bytes(), b'# Request\noriginal\nnew text\n')


if __name__ == '__main__':
    unittest.main()
