#!/usr/bin/env python3
"""Mouse selection in the build page / home page output column: press-drag-release highlights and copies text."""
import curses
import os
import sys
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'scripts' / 'lib'))
os.environ.setdefault('UNCLE_MODEL_REFRESH', '0')

import uncle_tui as tui  # noqa: E402

LINES = ['alpha bravo charlie', 'delta echo foxtrot', 'golf hotel india', 'juliet kilo lima']
PRESS, RELEASE = curses.BUTTON1_PRESSED, curses.BUTTON1_RELEASED
MOVE, WHEEL_UP = curses.REPORT_MOUSE_POSITION, curses.BUTTON4_PRESSED


def make(start=0):
    ui = tui.UncleTUI.__new__(tui.UncleTUI)
    ui.state, ui.prompt_kind, ui.chat_error = 'running', '', ''
    ui.build_scroll = 0
    ui._text_view = {'state': 'running', 'top': 2, 'left': 4, 'width': 30, 'rows': 4, 'start': start, 'lines': list(LINES)}
    ui.copied = []
    ui._copy_to_clipboard = lambda text: ui.copied.append(text)
    return ui


def drag(ui, a, b, release=True):
    """a, b are (x, y) screen cells."""
    ui._handle_mouse(a[0], a[1], PRESS)
    ui._handle_mouse(b[0], b[1], MOVE)
    if release:
        ui._handle_mouse(b[0], b[1], RELEASE)


class SelectionTest(unittest.TestCase):
    def test_drag_within_one_line_copies_that_span(self):
        ui = make()
        drag(ui, (4 + 6, 2), (4 + 10, 2))  # columns 6..10 of line 0
        self.assertEqual(ui.copied, ['bravo'])
        self.assertIn('Copied 5 characters', ui.chat_error)

    def test_drag_across_lines_copies_the_range(self):
        ui = make()
        drag(ui, (4 + 6, 2), (4 + 4, 4))  # line 0 col 6 .. line 2 col 4
        self.assertEqual(ui.copied, ['bravo charlie\ndelta echo foxtrot\ngolf'])  # trailing spaces trimmed per line

    def test_dragging_upwards_selects_the_same_text(self):
        ui = make()
        drag(ui, (4 + 4, 4), (4 + 6, 2))
        self.assertEqual(ui.copied, ['bravo charlie\ndelta echo foxtrot\ngolf'])  # trailing spaces trimmed per line

    def test_a_scrolled_view_selects_the_right_lines(self):
        ui = make(start=1)  # the first visible row is line 1
        drag(ui, (4, 2), (4 + 4, 2))
        self.assertEqual(ui.copied, ['delta'])

    def test_plain_click_copies_nothing_and_clears(self):
        ui = make()
        drag(ui, (8, 3), (8, 3))
        self.assertEqual(ui.copied, [])
        self.assertIsNone(ui._sel)

    def test_a_press_outside_the_output_column_selects_nothing(self):
        ui = make()
        drag(ui, (90, 3), (95, 3))  # the stage sidebar
        self.assertEqual(ui.copied, [])
        self.assertIsNone(ui._sel)

    def test_no_selection_while_a_prompt_is_open(self):
        ui = make()
        ui.prompt_kind = 'confirm'
        drag(ui, (8, 2), (20, 2))
        self.assertEqual(ui.copied, [])

    def test_dragging_past_the_text_clamps_to_its_edge(self):
        ui = make()
        drag(ui, (4 + 6, 2), (4 + 29, 9))  # far right and below the last row
        self.assertTrue(ui.copied[0].endswith('juliet kilo lima'))

    def test_drag_highlight_is_in_progress_until_release(self):
        ui = make()
        drag(ui, (8, 2), (14, 3), release=False)
        self.assertTrue(ui._sel['drag'])
        self.assertEqual(ui._selected_text(), 'a bravo charlie\ndelta echo')
        self.assertEqual(ui.copied, [])

    def test_any_key_clears_the_selection(self):
        ui = make()
        drag(ui, (8, 2), (14, 2))
        with mock.patch.object(tui.UncleTUI, '_control_key', return_value=True):
            ui.state = 'running'
            ui.handle_key(ord('x'))
        self.assertIsNone(ui._sel)

    def test_a_view_from_another_screen_is_ignored(self):
        ui = make()
        ui.state = 'menu'
        drag(ui, (8, 2), (14, 2))
        self.assertEqual(ui.copied, [])


class WheelTest(unittest.TestCase):
    def test_wheel_up_scrolls_back_and_a_bare_position_report_scrolls_forward(self):
        ui = make()
        ui.build_scroll = 5
        ui._handle_mouse(10, 5, WHEEL_UP)
        self.assertEqual(ui.build_scroll, 8)
        ui._handle_mouse(10, 5, MOVE)  # wheel-down on this ncurses, with no drag in progress
        self.assertEqual(ui.build_scroll, 5)

    def test_getmouse_failure_counts_as_wheel_down_unless_dragging(self):
        ui = make()
        ui.build_scroll = 5
        ui._handle_mouse(0, 0, None)
        self.assertEqual(ui.build_scroll, 2)
        ui._handle_mouse(8, 2, PRESS)
        ui._handle_mouse(0, 0, None)
        self.assertEqual(ui.build_scroll, 2)

    def test_motion_during_a_drag_never_scrolls_the_middle_of_the_view(self):
        ui = make()
        ui.build_scroll = 5
        ui._handle_mouse(8, 3, PRESS)
        ui._handle_mouse(12, 4, MOVE)
        self.assertEqual(ui.build_scroll, 5)


if __name__ == '__main__':
    unittest.main()
