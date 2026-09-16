"""TUI homepage worktree rows and the worktree issue mode (Issue 64, AC-6, T-5).

No git is run: `worktree_runs.runs` is patched. The signer environment is
installed anyway so any stray fixture git call would be recorded.
"""
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import fixture_repo  # noqa: E402
import uncle_tui  # noqa: E402
from uncle_tui import UncleTUI, ISSUE_MODES  # noqa: E402

ROWS = [
    {'issue': '64', 'state': 'IMPLEMENT', 'locked': True, 'path': '/p/uncle-issue-64'},
    {'issue': '7', 'state': 'COMPLETE', 'locked': False, 'path': '/p/uncle-issue-7'},
]


class HomepageRowsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.env, self.signer_log = fixture_repo.fake_signer(self.temp.name)
        self.saved = dict(os.environ)
        os.environ.clear()
        os.environ.update(self.env)
        self.addCleanup(self.restore)

    def restore(self):
        os.environ.clear()
        os.environ.update(self.saved)

    def ui(self):
        ui = UncleTUI.__new__(UncleTUI)
        ui.stdscr = Mock()
        ui.color = {}
        ui.state = 'home'
        ui.sel = 0
        ui.chat_focus = 'menu'
        ui.chat = Mock(preview='')
        ui.home_replace_proposal = None
        ui.menu_items = Mock(return_value=['New application', 'From GitHub issue'])
        ui.chat_entries = Mock(return_value=[])
        ui._draw_chat_composer = Mock()
        return ui

    def drawn(self, ui):
        return [call.args[2] for call in ui.stdscr.addnstr.call_args_list]

    def test_rows_render_issue_state_lock_and_path(self):
        ui = self.ui()
        with patch.object(uncle_tui.worktree_runs, 'runs', return_value=ROWS) as runs:
            ui._draw_homepage(24, 100)
        runs.assert_called_once()
        texts = self.drawn(ui)
        first = [t for t in texts if '#64' in t]
        second = [t for t in texts if '#7' in t]
        self.assertEqual(len(first), 1, texts)
        self.assertEqual(len(second), 1, texts)
        for needle in ('IMPLEMENT', 'locked', '/p/uncle-issue-64'):
            self.assertIn(needle, first[0])
        for needle in ('COMPLETE', 'idle', '/p/uncle-issue-7'):
            self.assertIn(needle, second[0])
        rows_y = [call.args[0] for call in ui.stdscr.addnstr.call_args_list if '#' in call.args[2]]
        self.assertEqual(rows_y, [1, 2])
        self.assertFalse(self.signer_log.exists())

    def test_no_rows_draws_nothing(self):
        ui = self.ui()
        with patch.object(uncle_tui.worktree_runs, 'runs', return_value=[]):
            ui._draw_homepage(24, 100)
        self.assertFalse([t for t in self.drawn(ui) if '#' in t])

    def test_listing_failure_draws_nothing(self):
        ui = self.ui()
        with patch.object(uncle_tui.worktree_runs, 'runs', side_effect=uncle_tui.worktree_runs.WorktreeListError('x')):
            ui._draw_homepage(24, 100)
        self.assertFalse([t for t in self.drawn(ui) if '#' in t])

    def test_narrow_width_keeps_the_path_tail(self):
        ui = self.ui()
        with patch.object(uncle_tui.worktree_runs, 'runs', return_value=ROWS):
            ui._draw_homepage(24, 40)
        rows = [t for t in self.drawn(ui) if t.startswith('#')]
        self.assertEqual(len(rows), 2)
        for text, row in zip(rows, ROWS):
            self.assertLessEqual(len(text), 40)
            self.assertTrue(text.endswith(row['path']), text)
        # Narrower than the line: the path loses its head, keeps its tail.
        ui = self.ui()
        with patch.object(uncle_tui.worktree_runs, 'runs', return_value=ROWS):
            ui._draw_homepage(24, 30)
        rows = [t for t in self.drawn(ui) if t.startswith('#')]
        self.assertEqual(len(rows), 2)
        for text, row in zip(rows, ROWS):
            self.assertLessEqual(len(text), 29)
            self.assertTrue(text.endswith(row['path'][-6:]), text)
            self.assertIn(' …', text)

    def test_rows_are_cached_for_five_seconds(self):
        ui = self.ui()
        with patch.object(uncle_tui.worktree_runs, 'runs', return_value=ROWS) as runs:
            ui._draw_homepage(24, 100)
            ui._draw_homepage(24, 100)
        self.assertEqual(runs.call_count, 1)

    def test_issue_modes(self):
        self.assertEqual(ISSUE_MODES[:3], [('auto', ''), ('change request', '--change'), ('new application', '--new')])
        self.assertEqual(ISSUE_MODES[3], ('change request in worktree', '--worktree'))
        ui = UncleTUI.__new__(UncleTUI)
        ui.workflow_idx = 1
        ui.issue = '64'
        ui.issue_mode = ISSUE_MODES[3][1]
        ui.misc = {}
        self.assertEqual(ui.cmd_for()[-2:], ['64', '--worktree'])
        self.assertFalse(self.signer_log.exists())


if __name__ == '__main__':
    unittest.main()
