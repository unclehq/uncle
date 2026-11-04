#!/usr/bin/env python3
"""Tests for scripts/lib/housekeeping_input.py (H-1 input limits)."""
import os
import subprocess
import sys
import tempfile
import unittest

LIB = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'lib', 'housekeeping_input.py')
CAP = 1048576


def run(private, stdin=b'', text=None):
    cmd = [sys.executable, LIB, private]
    if text is not None:
        cmd += ['--text', text]
    return subprocess.run(cmd, input=stdin, capture_output=True)


class HousekeepingInput(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = self.tmp.name

    def tearDown(self):
        self.tmp.cleanup()

    def assertRejected(self, result, fragment):
        self.assertEqual(result.returncode, 1)
        self.assertIn(fragment, result.stderr.decode())
        self.assertEqual(os.listdir(self.dir), [])

    def test_stdin_accepted_and_normalised(self):
        r = run(self.dir, b'a\r\nb\rc\n')
        self.assertEqual(r.returncode, 0)
        path = r.stdout.decode().strip()
        self.assertEqual(os.path.dirname(path), self.dir)
        with open(path, 'rb') as f:
            self.assertEqual(f.read(), b'a\nb\nc\n')
        self.assertEqual(os.stat(path).st_mode & 0o777, 0o600)

    def test_argument_text_accepted(self):
        r = run(self.dir, text='close stale branches')
        self.assertEqual(r.returncode, 0)
        with open(r.stdout.decode().strip(), 'rb') as f:
            self.assertEqual(f.read(), b'close stale branches')

    def test_no_change_request_check(self):
        open(os.path.join(self.dir, 'CHANGE_REQUEST.md'), 'w').close()
        self.assertEqual(run(self.dir, b'tidy up').returncode, 0)

    def test_empty_rejected(self):
        self.assertRejected(run(self.dir, b''), 'cannot be empty')
        self.assertRejected(run(self.dir, b' \n\t\r\n'), 'cannot be empty')
        self.assertRejected(run(self.dir, text='   '), 'cannot be empty')

    def test_control_characters_rejected(self):
        self.assertRejected(run(self.dir, b'a\x00b'), 'control characters')
        self.assertRejected(run(self.dir, b'a\x1bb'), 'control characters')
        self.assertRejected(run(self.dir, 'a\u0085b'.encode()), 'control characters')

    def test_tab_and_newline_allowed(self):
        self.assertEqual(run(self.dir, b'a\tb\nc').returncode, 0)

    def test_invalid_utf8_rejected(self):
        self.assertRejected(run(self.dir, b'\xff\xfe'), 'not valid UTF-8')

    def test_size_cap(self):
        self.assertEqual(run(self.dir, b'x' * CAP).returncode, 0)
        for name in os.listdir(self.dir):
            os.unlink(os.path.join(self.dir, name))
        self.assertRejected(run(self.dir, b'x' * (CAP + 1)), 'exceeds')


if __name__ == '__main__':
    unittest.main()
