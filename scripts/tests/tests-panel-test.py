#!/usr/bin/env python3
"""The tests authors draw as one stage with an indicator per author, like the other fan-outs."""
import sys
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'scripts' / 'lib'))
from uncle_tui import UncleTUI, parent_stage

LANES = ('harness', 'unit', 'e2e', 'mutation', 'complete')


class Panel(unittest.TestCase):
    def test_every_author_rolls_up_under_tests(self):
        for name in LANES:
            self.assertEqual(parent_stage('tests-' + name), 'tests')

    def test_neighbouring_stages_keep_their_own_parents(self):
        self.assertEqual(parent_stage('implementation-step-2'), 'implementation')
        self.assertEqual(parent_stage('test-review'), 'test-review')
        self.assertEqual(parent_stage('testsly'), 'testsly')

    def test_running_authors_draw_one_row_with_an_indicator_each(self):
        ui = UncleTUI.__new__(UncleTUI)
        now = time.time()
        ui.session_stats = {
            'active': {'tests-unit': now - 5, 'tests-e2e': now - 5, 'tests-mutation': now - 5},
            'live': {}, 'tick': 0, 'stopped_at': now,
            'records': [{'stage': 'tests-harness', 'started_at': now - 60, 'ended_at': now - 20,
                         'elapsed_seconds': 40, 'process_exit': 0}],
        }
        rows = [line for line in ui._session_panel_lines() if 'tests' in line]
        self.assertEqual(len(rows), 1, rows)
        self.assertTrue(rows[0].startswith('> tests'), rows[0])
        self.assertNotIn('harness', rows[0])
        indicators = rows[0][len('> tests'):].strip()
        self.assertEqual(len(indicators.replace(' ', '')), 4, repr(indicators))   # harness done, three running

    def test_a_failed_author_is_marked_failed(self):
        ui = UncleTUI.__new__(UncleTUI)
        now = time.time()
        ui.session_stats = {'active': {}, 'live': {}, 'tick': 0, 'stopped_at': now, 'records': [
            {'stage': 'tests-harness', 'started_at': now - 60, 'ended_at': now - 40, 'elapsed_seconds': 20, 'process_exit': 0},
            {'stage': 'tests-unit', 'started_at': now - 40, 'ended_at': now - 5, 'elapsed_seconds': 35, 'process_exit': 1}]}
        rows = [line for line in ui._session_panel_lines() if 'tests' in line]
        self.assertEqual(len(rows), 1)
        self.assertEqual(ui._panel_indicator_styles[rows[0]], ['good', 'bad'])   # sorted: harness, unit
        self.assertEqual(ui._panel_stage_styles[rows[0]], 'bad')


if __name__ == '__main__':
    unittest.main()
