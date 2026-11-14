#!/usr/bin/env python3
"""Preflight: `command -v NAME` probes NAME; unlisted tools are presence-checked, never executed."""
import os
import stat
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts' / 'lib'))
import preflight  # noqa: E402


class Toolchain(unittest.TestCase):
    def test_command_v_probes_name(self):
        self.assertEqual(preflight.prerequisites('command -v ocaml\\n'.replace('\\n', '\n')), ['ocaml'])

    def test_which_probes_name(self):
        self.assertEqual(preflight.prerequisites('which dune'), ['dune'])

    def test_unlisted_executable_is_collected(self):
        self.assertEqual(preflight.prerequisites('ocaml -version && dune build'), ['dune', 'ocaml'])

    def test_path_like_still_rejected(self):
        with self.assertRaises(ValueError):
            preflight.prerequisites('./run-it')

    def test_bare_command_rejected(self):
        with self.assertRaises(ValueError):
            preflight.prerequisites('command -v')

    def test_missing_raises(self):
        with self.assertRaises(ValueError) as cm:
            preflight.probe('no-such-tool-xyz')
        self.assertEqual(str(cm.exception), 'Missing runtime: no-such-tool-xyz')

    def test_present_not_executed(self):
        with tempfile.TemporaryDirectory() as d:
            marker = Path(d) / 'ran'
            tool = Path(d) / 'faketool'
            tool.write_text('#!/bin/sh\ntouch "%s"\n' % marker)
            tool.chmod(tool.stat().st_mode | stat.S_IXUSR)
            old = os.environ['PATH']
            os.environ['PATH'] = d + os.pathsep + old
            try:
                msg = preflight.probe('faketool')
            finally:
                os.environ['PATH'] = old
            self.assertEqual(msg, 'faketool found at ' + str(tool))
            self.assertFalse(marker.exists())


if __name__ == '__main__':
    unittest.main()
