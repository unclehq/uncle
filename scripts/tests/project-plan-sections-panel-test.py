#!/usr/bin/env python3
"""The project plan's parallel sections draw as one stage with a sprite per section."""
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'scripts' / 'lib'))
from uncle_tui import UncleTUI, parent_stage

SECTIONS = ('core', 'behaviors', 'invariants', 'tests', 'commands', 'closing', 'trace')


class Panel(unittest.TestCase):
    def test_every_section_rolls_up_under_project_plan(self):
        for name in SECTIONS:
            self.assertEqual(parent_stage('project-plan-section-' + name), 'project-plan')
        self.assertEqual(parent_stage('project-plan'), 'project-plan')
        self.assertEqual(parent_stage('project-plan-investigate'), 'project-plan')

    def test_preview_build_parts_roll_up_under_preview_build(self):
        for name in ('contract', 'markup', 'styles', 'script'):
            self.assertEqual(parent_stage('preview-build-part-' + name), 'preview-build')
        self.assertEqual(parent_stage('preview-build'), 'preview-build')

    def test_other_stages_keep_their_own_parents(self):
        self.assertEqual(parent_stage('implementation-step-2'), 'implementation')
        self.assertEqual(parent_stage('project-planning-extra'), 'project-planning-extra')

    def test_running_sections_draw_one_row_with_a_sprite_per_section(self):
        import time
        ui = UncleTUI.__new__(UncleTUI)
        now = time.time()
        ui.session_stats = {
            'active': {'project-plan-section-verify': now - 5, 'project-plan-section-closing': now - 5},
            'live': {}, 'tick': 0, 'stopped_at': now,
            'records': [{'stage': 'project-plan-section-core', 'started_at': now - 60, 'ended_at': now - 20,
                         'elapsed_seconds': 40, 'process_exit': 0}],
        }
        lines = ui._session_panel_lines()
        rows = [line for line in lines if 'project-plan' in line]
        self.assertEqual(len(rows), 1, lines)
        self.assertTrue(rows[0].startswith('> project-plan'), rows[0])
        self.assertNotIn('section', rows[0])
        # three sections -> three indicators: two spinning, one finished
        indicators = rows[0][len('> project-plan'):].strip()
        self.assertEqual(len(indicators.replace(' ', '')), 3, repr(indicators))

    def test_a_failed_section_is_marked_failed(self):
        import time
        ui = UncleTUI.__new__(UncleTUI)
        now = time.time()
        ui.session_stats = {'active': {}, 'live': {}, 'tick': 0, 'stopped_at': now, 'records': [
            {'stage': 'project-plan-section-core', 'started_at': now - 60, 'ended_at': now - 20, 'elapsed_seconds': 40, 'process_exit': 0},
            {'stage': 'project-plan-section-verify', 'started_at': now - 20, 'ended_at': now - 5, 'elapsed_seconds': 15, 'process_exit': 1}]}
        rows = [line for line in ui._session_panel_lines() if 'project-plan' in line]
        self.assertEqual(len(rows), 1)
        self.assertEqual(ui._panel_indicator_styles[rows[0]], ['good', 'bad'])
        self.assertEqual(ui._panel_stage_styles[rows[0]], 'bad')


if __name__ == '__main__':
    unittest.main()
