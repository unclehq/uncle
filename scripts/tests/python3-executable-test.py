#!/usr/bin/env python3
"""process_tree.python3_executable(): a stable stand-in for sys.executable.

sys.executable resolves symlinks to find the interpreter's real location. A
packaged install (Homebrew) relies on a stable `opt_libexec` symlink so a
long-running workflow survives a reinstall mid-run: the versioned Cellar
directory sys.executable had already resolved to and frozen gets deleted,
and any later subprocess.run([sys.executable, ...]) fails with ENOENT even
though the running process itself is fine. python3_executable() must resolve
through PATH fresh every call, without following symlinks, so it re-resolves
through the stable opt-symlink chain instead of the frozen concrete path.
"""
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'lib'))
from process_tree import python3_executable


class Python3Executable(unittest.TestCase):
    def test_prefers_path_lookup_over_sys_executable(self):
        with patch('process_tree.shutil.which', return_value='/opt/homebrew/opt/uncle/libexec/venv/bin/python3'):
            self.assertEqual(python3_executable(), '/opt/homebrew/opt/uncle/libexec/venv/bin/python3')

    def test_falls_back_to_sys_executable_when_path_lookup_fails(self):
        with patch('process_tree.shutil.which', return_value=None):
            self.assertEqual(python3_executable(), sys.executable)

    def test_does_not_resolve_a_symlink_to_its_real_target(self):
        # The actual property the bug hinges on: shutil.which returns the
        # matched PATH entry verbatim, so a symlinked "python3" on PATH is
        # returned as the symlink path, not realpath()'d through to wherever
        # it currently points -- exactly what lets this keep working after
        # the thing it points to is swapped out from under a live process.
        with tempfile.TemporaryDirectory() as tmp:
            link = Path(tmp) / 'python3'
            link.symlink_to(sys.executable)
            with patch.dict(os.environ, {'PATH': tmp + os.pathsep + os.environ.get('PATH', '')}):
                self.assertEqual(python3_executable(), str(link))


if __name__ == '__main__':
    unittest.main()
