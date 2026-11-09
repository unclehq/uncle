"""Warn-once marker for --max-budget-usd (issue 212): per-build, best-effort, never silent.

The marker lives at .uncle/workflow/max-budget-unpriced-warned relative to the working directory.
The warning helper in scripts/lib/budget.py takes the warning text and prints it to stderr unless
the marker shows it was already printed.
"""
import io
import os
import shutil
import sys
import tempfile
import unittest
from contextlib import redirect_stderr
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts' / 'lib'))
import budget

MARKER = Path('.uncle/workflow/max-budget-unpriced-warned')
MSG = 'UNPRICED-MODEL-WARNING'
NAMES = ('warn_once', 'warn_unpriced_once', 'warn_once_per_build', 'warn_unpriced')


def warn_fn():
    for name in NAMES:
        fn = getattr(budget, name, None)
        if callable(fn):
            return fn
    raise AssertionError('budget.py exposes none of %s' % (NAMES,))


class Marker(unittest.TestCase):
    def setUp(self):
        self.prev = os.getcwd()
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp, True)
        os.chdir(self.tmp)
        self.addCleanup(os.chdir, self.prev)

    def warn(self):
        err = io.StringIO()
        with redirect_stderr(err):
            warn_fn()(MSG)
        return err.getvalue().count(MSG)

    def test_two_sequential_invocations_warn_once(self):
        self.assertEqual(self.warn(), 1)
        self.assertEqual(self.warn(), 0)

    def test_marker_created_when_workflow_dir_absent(self):
        self.assertFalse(Path('.uncle').exists())
        self.assertEqual(self.warn(), 1)
        self.assertTrue(MARKER.is_file() and not MARKER.is_symlink())

    @unittest.skipIf(os.name == 'nt' or (hasattr(os, 'geteuid') and os.geteuid() == 0), 'permissions not enforced')
    def test_unwritable_workflow_dir_still_warns(self):
        Path('.uncle/workflow').mkdir(parents=True)
        os.chmod('.uncle/workflow', 0o500)
        self.addCleanup(os.chmod, '.uncle/workflow', 0o700)
        self.assertEqual(self.warn(), 1)
        self.assertEqual(self.warn(), 1)

    def test_symlinked_marker_warns_and_target_untouched(self):
        Path('.uncle/workflow').mkdir(parents=True)
        target = Path('target.txt')
        target.write_text('keep')
        os.symlink(target.resolve(), MARKER)
        self.assertEqual(self.warn(), 1)
        self.assertEqual(target.read_text(), 'keep')
        self.assertTrue(MARKER.is_symlink())

    def test_non_regular_marker_warns(self):
        MARKER.mkdir(parents=True)
        self.assertEqual(self.warn(), 1)
        self.assertTrue(MARKER.is_dir())

    def test_workflow_dir_is_a_file_still_warns(self):
        Path('.uncle').mkdir()
        Path('.uncle/workflow').write_text('not a directory')
        self.assertEqual(self.warn(), 1)

    def test_removing_workflow_state_rearms_warning(self):
        self.assertEqual(self.warn(), 1)
        self.assertEqual(self.warn(), 0)
        shutil.rmtree('.uncle/workflow')
        self.assertEqual(self.warn(), 1)


class Cost(unittest.TestCase):
    def test_reported_cost_wins(self):
        self.assertEqual(budget.turn_cost({'cost': 0.2, 'input_tokens': 10 ** 9}, 'm'), 0.2)

    def test_unknown_cost_is_none(self):
        self.assertIsNone(budget.turn_cost({}, 'no-such-model'))

    def test_stop_rule_ac2(self):
        led = budget.Ledger()
        cap, requests = 0.50, 0
        while True:
            try:
                led.check(cap)
            except budget.BudgetExceeded as error:
                msg = str(error)
                break
            requests += 1
            led.add(0.20)
        self.assertEqual(requests, 2)
        self.assertTrue('budget' in msg and '0.40' in msg and '0.50' in msg)

    def test_no_cap_never_stops(self):
        led = budget.Ledger()
        led.add(99)
        led.check(None)


class Parse(unittest.TestCase):
    def setUp(self):
        sys.modules.pop('self_hosted', None)
        import self_hosted
        self.sh = self_hosted

    def test_parse(self):
        self.assertEqual(self.sh.parse_budget(['--max-budget-usd', '0.5']), 0.5)
        self.assertIsNone(self.sh.parse_budget(['-p']))

    def test_refused(self):
        for bad in ('abc', '-1', '0', 'nan', 'inf', ''):
            with self.assertRaises(ValueError):
                self.sh.parse_budget(['--max-budget-usd', bad])

    def test_other_option_still_refused(self):
        with self.assertRaises(ValueError):
            self.sh.parse_arguments('agent', ['--bogus-flag'])


if __name__ == '__main__':
    unittest.main()
