#!/usr/bin/env python3
"""A comment marker in a step's Owns list is not a file the step owns: it is dropped, and the real paths stay."""
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts/lib'))
import plan_steps  # noqa: E402


class OwnsCommentMarker(unittest.TestCase):
    def test_haskell_guard_is_dropped(self):
        self.assertEqual(plan_steps.paths('`-- EOF-GUARD`, `src/Main.hs`'), ['src/Main.hs'])

    def test_other_comment_markers_are_dropped(self):
        self.assertEqual(plan_steps.paths('`// end`, `# end`, `; end`, `a/b.c`'), ['a/b.c'])

    def test_real_paths_survive(self):
        self.assertEqual(plan_steps.paths('`src/**`, `.gitignore`, `.uncle/launch.json`'),
                         ['src/**', '.gitignore', '.uncle/launch.json'])


if __name__ == '__main__':
    unittest.main()
