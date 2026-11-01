#!/usr/bin/env python3
import sys
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'lib'))
from browser_setup import install


class BrowserSetup(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve()
        self.cli = self.root / 'node_modules/playwright/cli.js'
        self.cli.parent.mkdir(parents=True)
        self.cli.write_text('// fixture only; never executed')

    def test_success_uses_existing_cli_without_fetching_a_runtime(self):
        run = Mock(return_value=0)
        self.assertEqual(install(['chromium'], self.root, run), 0)
        run.assert_called_once_with(['node', str(self.cli), 'install', 'chromium'], 120)

    def test_stall_retries_exact_cli_with_isolated_runtime_and_propagates_result(self):
        run = Mock(side_effect=[124, 7])
        self.assertEqual(install(['chromium', '--with-deps'], self.root, run), 7)
        self.assertEqual(run.call_args.args[0], ['npm', 'exec', '--yes', '--package=node@22', '--',
                                               'node', str(self.cli), 'install', 'chromium', '--with-deps'])
        self.assertEqual(run.call_args.args[1], 180)

    def test_ordinary_failures_are_not_hidden_or_retried(self):
        run = Mock(return_value=1)
        self.assertEqual(install(['chromium'], self.root, run), 1)
        self.assertEqual(run.call_count, 1)


if __name__ == '__main__':
    unittest.main()
