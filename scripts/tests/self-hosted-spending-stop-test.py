"""Spending-stop client tests: 402 parsing, field validation, marker schema, Stopped line, budget_cap, header capture."""
import json
import os
import sys
import tempfile
import unittest
from io import StringIO
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts' / 'lib'))

import self_hosted  # noqa: E402
import self_hosted_http as http  # noqa: E402
import unit_scheduler  # noqa: E402


def body(**fields):
    return json.dumps(dict({'code': 'budget_reached'}, **fields)).encode()


class ParseTests(unittest.TestCase):
    def test_full_budget_reached(self):
        stop = http.parse_spending_stop(402, body(scope='task', limit_atomic=5000000, used_atomic=5000001,
                                                  suggested_increase_atomic=2000000))
        self.assertEqual((stop.code, stop.scope, stop.limit_atomic, stop.used_atomic, stop.suggested_increase_atomic,
                          stop.balance_atomic), ('budget_reached', 'task', 5000000, 5000001, 2000000, None))

    def test_balance_exhausted(self):
        stop = http.parse_spending_stop(402, json.dumps({'code': 'balance_exhausted', 'balance_atomic': 0}))
        self.assertEqual((stop.code, stop.balance_atomic), ('balance_exhausted', 0))

    def test_missing_figures_are_none(self):
        stop = http.parse_spending_stop(402, body())
        self.assertIsNone(stop.limit_atomic)
        self.assertIsNone(stop.scope)

    def test_not_a_spending_stop(self):
        for status, raw in ((401, body()), (429, body()), (402, b'not json'), (402, b'[]'), (402, b'null'),
                            (402, json.dumps({'code': 'other'})), (402, json.dumps({'code': 'Budget_Reached'})),
                            (402, json.dumps({'error': {'code': 'budget_reached'}})), (402, json.dumps({'code': ['budget_reached']}))):
            self.assertIsNone(http.parse_spending_stop(status, raw), (status, raw))

    def test_non_integer_atomic_fields_invalidate(self):
        for value in ('5', 5.5, True, [1], {'a': 1}, 1e3):
            for field in http.SPENDING_ATOMIC_FIELDS:
                self.assertIsNone(http.parse_spending_stop(402, body(**{field: value})), (field, value))

    def test_scope_sanitised(self):
        stop = http.parse_spending_stop(402, body(scope='a\x00b\x1b[31mé\n' + 'x' * 100))
        self.assertTrue(all(0x20 <= ord(c) <= 0x7E for c in stop.scope))
        self.assertEqual(len(stop.scope), 64)
        self.assertNotIn('\x1b', stop.scope)
        self.assertIsNone(http.parse_spending_stop(402, body(scope=5)))


class RenderTests(unittest.TestCase):
    def test_usd_rounds_up(self):
        self.assertEqual(self_hosted._usd(1500001), '$1.51')
        self.assertEqual(self_hosted._usd(1500000), '$1.50')
        self.assertEqual(self_hosted._usd(1), '$0.01')
        self.assertEqual(self_hosted._usd(0), '$0.00')
        self.assertEqual(self_hosted._usd(None), 'unknown')

    def test_budget_reached_line(self):
        line = self_hosted.spending_stop_line(http.SpendingStop('budget_reached', 'task', 5000000, 5000001, 2000000))
        self.assertIn('$5.00', line)
        self.assertIn('$5.01', line)
        self.assertIn('$2.00', line)
        self.assertNotIn('None', line)

    def test_balance_line(self):
        line = self_hosted.spending_stop_line(http.SpendingStop('balance_exhausted', balance_atomic=250000))
        self.assertIn('balance', line)
        self.assertIn('$0.25', line)

    def test_missing_figures_omitted(self):
        for stop in (http.SpendingStop('budget_reached'), http.SpendingStop('balance_exhausted'),
                     http.SpendingStop('budget_reached', limit_atomic=1000000)):
            line = self_hosted.spending_stop_line(stop)
            self.assertNotIn('None', line)
            self.assertNotIn('$0', line)
            self.assertNotIn('unknown', line)
            self.assertNotIn(': .', line)
        self.assertNotIn('used', self_hosted.spending_stop_line(http.SpendingStop('budget_reached', limit_atomic=1000000)))


class MarkerTests(unittest.TestCase):
    def run_main(self, stop, marker):
        env = {'UNCLE_SPENDING_STOP_FILE': marker} if marker else {}
        with patch.dict(os.environ, env), patch.object(self_hosted, '_main', side_effect=stop), \
                patch('sys.stderr', new_callable=StringIO) as err:
            return self_hosted.main('agent', []), err.getvalue()

    def test_exit_75_and_marker(self):
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, 'w1.json')
            code, err = self.run_main(http.SpendingStop('budget_reached', 'task', 5000000, 5000001), path)
            self.assertEqual(code, 75)
            self.assertEqual(json.load(open(path)), {
                'code': 'budget_reached', 'scope': 'task', 'limit_atomic': 5000000, 'used_atomic': 5000001,
                'suggested_increase_atomic': None, 'balance_atomic': None})
            self.assertEqual(os.listdir(directory), ['w1.json'])  # no temp files left
            self.assertIn('Stopped', err)

    def test_missing_fields_are_null(self):
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, 'w.json')
            self.run_main(http.SpendingStop('balance_exhausted'), path)
            data = json.load(open(path))
            self.assertEqual(sorted(data), sorted(['code', 'scope', 'limit_atomic', 'used_atomic',
                                                   'suggested_increase_atomic', 'balance_atomic']))
            self.assertIsNone(data['balance_atomic'])

    def test_never_creates_directory(self):
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, 'missing', 'w.json')
            code, _ = self.run_main(http.SpendingStop('budget_reached'), path)
            self.assertEqual(code, 75)
            self.assertFalse(os.path.exists(os.path.dirname(path)))

    def test_no_marker_path_still_exits_75(self):
        code, _ = self.run_main(http.SpendingStop('budget_reached'), None)
        self.assertEqual(code, 75)

    def test_marker_overwrites_stale(self):
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, 'w.json')
            Path(path).write_text('stale')
            self.run_main(http.SpendingStop('budget_reached', limit_atomic=1), path)
            self.assertEqual(json.load(open(path))['limit_atomic'], 1)


class BudgetCapTests(unittest.TestCase):
    def test_boundaries(self):
        cap = unit_scheduler.budget_cap
        self.assertEqual(cap(0, 400000, 8), 1)
        self.assertEqual(cap(-5, 400000, 8), 1)
        self.assertEqual(cap(399999, 400000, 8), 1)
        self.assertEqual(cap(800000, 400000, 8), 2)
        self.assertEqual(cap(1199999, 400000, 8), 2)
        self.assertEqual(cap(10**9, 400000, 4), 4)
        self.assertEqual(cap(800000, 0, 8), 2)      # typical <= 0 uses 400000
        self.assertEqual(cap(800000, -3, 8), 2)
        self.assertEqual(cap(1000, 100, 8), 8)
        self.assertEqual(cap(None, 400000, 5), 5)    # absent: unchanged

    def test_never_above_configured(self):
        for remaining in (0, 1, 10**6, 10**12):
            self.assertLessEqual(unit_scheduler.budget_cap(remaining, 1, 3), 3)


class HeaderCaptureTests(unittest.TestCase):
    def capture(self, headers, existing=None):
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, 'budget')
            if existing is not None:
                Path(path).write_text(existing)
            with patch.dict(os.environ, {'UNCLE_BUDGET_REMAINING_FILE': path}):
                http._record_budget_header(headers)
            return Path(path).read_text() if os.path.exists(path) else None

    def test_valid_value_written(self):
        self.assertEqual(self.capture({http.BUDGET_HEADER: ' 123456 '}), '123456')

    def test_invalid_values_ignored(self):
        for value in ('-5', '1.5', 'abc', '', '1e3', '0x10'):
            self.assertIsNone(self.capture({http.BUDGET_HEADER: value}), value)

    def test_absent_header_leaves_file(self):
        self.assertEqual(self.capture({}, existing='7'), '7')

    def test_no_env_is_noop(self):
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop('UNCLE_BUDGET_REMAINING_FILE', None)
            http._record_budget_header({http.BUDGET_HEADER: '5'})  # must not raise


if __name__ == '__main__':
    unittest.main()
