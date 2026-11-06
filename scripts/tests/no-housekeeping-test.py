#!/usr/bin/env python3
"""AC-3: the retired feature name appears only in an explicit allowlist of files."""
import os
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..'))
WORD = 'housekeeping'
ALLOWED = {
    'docs/UNATTENDED_DEFAULT_MIGRATION.md',
    'scripts/tests/no-housekeeping-test.py',
    'scripts/tests/launcher-removed-flag-test.sh',
    'scripts/tests/tui-home-agent-test.py',
    'scripts/tests/critical-suites.txt',   # lists the suite named after this one
}
SKIP_FILES = {'FINAL_AUDIT.md'}
SKIP_DIRS = {'.git', '.uncle', 'node_modules', '__pycache__', '.pytest_cache', '.venv'}


def tracked_files():
    for dirpath, dirnames, filenames in os.walk(ROOT):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        for name in filenames:
            full = os.path.join(dirpath, name)
            if os.path.islink(full) or (dirpath == ROOT and name in SKIP_FILES):
                continue
            yield os.path.relpath(full, ROOT).replace(os.sep, '/'), full


class NoHousekeeping(unittest.TestCase):
    def test_only_allowlisted_files_mention_it(self):
        offenders = []
        for rel, full in tracked_files():
            if rel in ALLOWED:
                continue
            if WORD in rel.lower():
                offenders.append(rel + ' (path)')
                continue
            try:
                with open(full, 'rb') as f:
                    data = f.read()
            except OSError:
                continue
            if WORD.encode() in data.lower():
                offenders.append(rel)
        self.assertEqual(offenders, [])

    def test_allowlisted_files_exist_or_are_known(self):
        for rel in ALLOWED:
            self.assertTrue(rel.startswith(('docs/', 'scripts/tests/')), rel)


if __name__ == '__main__':
    unittest.main()
