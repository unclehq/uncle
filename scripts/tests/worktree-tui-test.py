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

    def test_homepage_lists_no_worktree_runs(self):
        """The homepage is the menu and the prompt, and nothing else.

        Every run in every worktree used to be listed above both. With an issue
        run taking its own worktree by default that block only grows, and it
        pushed the two things the screen is for down the page.
        `scripts/lib/worktree_runs.py` still prints the list on demand.
        """
        ui = self.ui()
        with patch.object(uncle_tui.worktree_runs, 'runs', return_value=ROWS) as runs:
            ui._draw_homepage(24, 100)
        runs.assert_not_called()
        for text in self.drawn(ui):
            self.assertNotIn('/p/uncle-issue-', text)
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
