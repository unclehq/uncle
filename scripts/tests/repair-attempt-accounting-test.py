#!/usr/bin/env python3
"""A repair attempt that never made a model request is not counted, and an explicit rerun starts with a fresh repair budget.

The run that found this: the first repair was stopped by hand before its first request and the second crashed on a configuration
error before its first request. Both were counted (the count is written when an attempt starts), so with two automatic repairs
allowed the third was refused, and the build went straight to the final audit with its code defect unrepaired."""
import json
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts' / 'lib'))
SOURCE = (ROOT / 'scripts' / 'stagegate.sh').read_text()


def function(name):
    match = re.search(r'(?ms)^%s\(\) \{\n.*?^\}\n' % re.escape(name), SOURCE)
    assert match, name
    return match.group(0)


class Accounting(unittest.TestCase):
    def run_bash(self, count='2', marker=True, repair_investigate=None, repair=None, attempts='2'):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            (base / 'logs').mkdir()
            if count is not None:
                (base / 'repair-count').write_text(count + '\n')
            if marker:
                (base / 'repair-attempt-pending').write_text('')
            if repair_investigate is not None:
                (base / 'logs' / 'repair-investigate.jsonl').write_text(repair_investigate)
            if repair is not None:
                (base / 'logs' / 'repair.jsonl').write_text(repair)
            script = ('STATE_DIR="%s"; LOG_DIR="%s/logs"; WORKFLOW_AUTO_REPAIR_ATTEMPTS=%s\n%s\n%s\nrepair_uncount_unrun_attempt'
                      % (base, base, attempts, function('repair_attempt_did_work'), function('repair_uncount_unrun_attempt')))
            done = subprocess.run(['bash', '-c', script], capture_output=True, text=True, timeout=30)
            read = lambda name: (base / name).read_text().strip() if (base / name).exists() else None
            return done, read('repair-count'), (base / 'repair-attempt-pending').exists()

    TURN = '{"type": "self_hosted_turn", "turn": 1, "stage": "repair-investigate"}\n'

    def test_an_attempt_with_no_log_is_not_counted(self):
        done, count, marker = self.run_bash()
        self.assertEqual(count, '1')
        self.assertFalse(marker)
        self.assertIn('never made a model request, so it is not counted (1 of 2 automatic repairs used)', done.stdout)

    def test_an_attempt_whose_log_is_empty_is_not_counted(self):
        self.assertEqual(self.run_bash(repair_investigate='', repair='')[1], '1')

    def test_an_attempt_that_made_a_request_stays_counted(self):
        for kwargs in ({'repair_investigate': self.TURN}, {'repair': '{"type": "assistant", "message": {}}\n'},
                       {'repair_investigate': '{"type":"self_hosted_turn"}\n'}):
            done, count, marker = self.run_bash(**kwargs)
            self.assertEqual(count, '2', kwargs)
            self.assertFalse(marker, kwargs)            # accounted for either way
            self.assertNotIn('not counted', done.stdout)

    def test_without_the_marker_nothing_changes(self):
        done, count, _ = self.run_bash(marker=False)
        self.assertEqual((count, done.stdout), ('2', ''))

    def test_the_count_never_goes_below_zero_or_trusts_junk(self):
        self.assertEqual(self.run_bash(count='0')[1], '0')
        self.assertEqual(self.run_bash(count='x')[1], 'x')
        self.assertEqual(self.run_bash(count='12345')[1], '12345')
        self.assertIsNone(self.run_bash(count=None)[1])

    def test_a_leading_zero_count_is_read_as_decimal(self):
        self.assertEqual(self.run_bash(count='08')[1], '7')

    def test_the_driver_marks_the_attempt_and_accounts_for_it_before_anything_reads_the_count(self):
        write = SOURCE.index("printf '%s\\n' \"$repair_count\" > \"$STATE_DIR/repair-count\"")
        self.assertIn(': > "$STATE_DIR/repair-attempt-pending"', SOURCE[write:write + 200])
        loop = SOURCE.index('\nwhile true; do\n    preserve_requirements_source')
        self.assertGreater(loop, SOURCE.index('\nrepair_uncount_unrun_attempt\n'))
        self.assertLess(SOURCE.index('\ngreen_background_recover\nrepair_uncount_unrun_attempt'), loop)


class Rerun(unittest.TestCase):
    def test_a_rerun_starts_with_a_fresh_repair_budget_and_keeps_the_old_count(self):
        import rerun_stage
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            state = root / '.uncle' / 'workflow'
            (state / 'approvals').mkdir(parents=True)
            (state / 'state').write_text('REPAIR\n')
            (state / 'repair-count').write_text('2\n')
            (state / 'repair-attempt-pending').write_text('')
            (state / 'rerun-request.json').write_text(json.dumps({'stage': 'test-review'}))
            rerun_stage.consume(root, 'app')
            self.assertFalse((state / 'repair-count').exists())
            self.assertFalse((state / 'repair-attempt-pending').exists())
            kept = list((state / 'stage-reruns').glob('*/repair-count'))
            self.assertEqual([p.read_text().strip() for p in kept], ['2'])
            self.assertEqual((state / 'state').read_text().strip(), 'TEST_REVIEW')


if __name__ == '__main__':
    unittest.main()
