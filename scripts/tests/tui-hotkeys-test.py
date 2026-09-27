#!/usr/bin/env python3
"""Issue 92: Claude Code control hotkeys (AC-1..AC-9 of CHANGE_SPEC.md).

No curses screen, no real driver: keys go through UncleTUI.handle_key.
"""
import curses
from pathlib import Path
import sys
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import uncle_tui as tui
from uncle_tui import UncleTUI

ESC, CTRL_B, CTRL_L, CTRL_R = 27, 2, 12, 18


class Clock:
    def __init__(self):
        self.now = 100.0

    def __call__(self):
        return self.now


def live_proc():
    proc = Mock()
    proc.poll.return_value = None
    return proc


class HotkeyTests(unittest.TestCase):
    def ui(self, state='running', live=True, **attrs):
        ui = UncleTUI.__new__(UncleTUI)
        ui.state = state
        ui.stdscr = Mock()
        ui.stdscr.getch.return_value = -1
        ui.stdscr.getmaxyx.return_value = (40, 120)
        ui.chat = Mock(preview='', seed=None)
        ui.chat_open = True
        ui.chat_focus = 'chat'
        ui.chat_composer = ''
        ui.chat_edit = False
        ui.chat_picker = False
        ui.chat_choices = []
        ui.chat_error = ''
        ui.recovery_active = False
        ui.completion_preview = None
        ui.prompt_kind = ''
        ui.prompt_text = ''
        ui.prompt_scroll = 0
        ui.home_history = []
        ui.home_menu_open = False
        ui.proc = live_proc() if live else None
        ui.workflow_exit_reported = False
        ui.status_stage = 'implement'
        ui.misc = {}
        ui.clock = Clock()
        ui.stop_workflow = Mock(side_effect=lambda: setattr(ui, 'proc', None))
        ui._build_finished = Mock(return_value=False)
        ui.send_home_chat = Mock()
        for k, v in attrs.items():
            setattr(ui, k, v)
        return ui

    def messages(self, ui):
        return [text for _, text in ui.home_history]

    # AC-1
    def test_esc_interrupts(self):
        ui = self.ui()
        ui.handle_key(ESC)
        ui.stop_workflow.assert_called_once()
        self.assertEqual(ui.state, 'running')
        self.assertTrue(ui.proc_done)
        self.assertTrue(ui.workflow_exit_reported)
        self.assertEqual(self.messages(ui), ['Interrupted implement. /resume continues the run.'])

    def test_esc_without_live_stage_does_not_stop(self):
        ui = self.ui(live=False)
        ui.handle_key(ESC)
        ui.stop_workflow.assert_not_called()
        self.assertEqual(ui.home_history, [])

    def test_split_escape_sequence_is_not_interrupt(self):
        ui = self.ui()
        ui.stdscr.getch.return_value = ord('[')
        with patch.object(tui.curses, 'ungetch') as ungetch:
            ui.handle_key(ESC)
        ungetch.assert_called_once_with(ord('['))
        ui.stop_workflow.assert_not_called()

    # AC-2
    def test_double_esc_rewind(self):
        ui = self.ui()
        ui.chat_composer = 'fix the tests'
        ui.handle_key(10)
        self.assertEqual(ui.chat_composer, '')
        ui.handle_key(ESC)  # first Esc acts immediately
        ui.stop_workflow.assert_called_once()
        ui.clock.now += 0.3
        ui.handle_key(ESC)
        self.assertEqual(ui.chat_composer, 'fix the tests')
        self.assertEqual(self.messages(ui), ['Interrupted implement. /resume continues the run.'])

    def test_second_esc_after_window_is_fresh(self):
        ui = self.ui(input_history=[{'text': 'x', 'gate': False, 'sent': False}])
        ui.handle_key(ESC)
        ui.clock.now += 0.5
        ui.handle_key(ESC)
        self.assertEqual(ui.chat_composer, '')

    def test_rewind_nothing_and_sent_gate_answer(self):
        ui = self.ui(live=False)
        ui.handle_key(ESC)
        ui.clock.now += 0.1
        ui.handle_key(ESC)
        self.assertEqual(self.messages(ui), ['Nothing to rewind.'])
        ui = self.ui(live=False, input_history=[{'text': 'y', 'gate': True, 'sent': True}])
        ui.handle_key(ESC)
        ui.clock.now += 0.1
        ui.handle_key(ESC)
        self.assertEqual(ui.chat_composer, 'y')
        self.assertIn('already taken by the driver', self.messages(ui)[0])

    def test_pure_helpers(self):
        self.assertTrue(tui.is_double_esc(1.0, 1.4))
        self.assertFalse(tui.is_double_esc(1.0, 1.41))
        self.assertFalse(tui.is_double_esc(None, 1.0))
        self.assertEqual(tui.history_step(['a', 'b'], None, -1), 1)
        self.assertEqual(tui.history_step(['a', 'b'], 0, -1), 0)
        self.assertIsNone(tui.history_step(['a', 'b'], 1, 1))
        self.assertIsNone(tui.history_step([], None, -1))

    # AC-3
    def test_ctrl_r_toggle(self):
        ui = self.ui()
        ui.handle_key(CTRL_R)
        self.assertTrue(ui.transcript_full)
        ui.handle_key(CTRL_R)
        self.assertFalse(ui.transcript_full)

    # AC-4
    def test_ctrl_b_background(self):
        ui = self.ui()
        ui.handle_key(CTRL_B)
        self.assertEqual(ui.state, 'menu')
        self.assertTrue(ui.backgrounded)
        ui.stop_workflow.assert_not_called()
        self.assertEqual(ui._background_status(), 'build running — Ctrl-B to return')
        ui.start_workflow()  # D-12: no second build
        self.assertIn('running in the background', self.messages(ui)[-1])
        ui.handle_key(CTRL_B)
        self.assertEqual(ui.state, 'running')
        self.assertFalse(ui.backgrounded)

    def test_ctrl_b_keeps_polling_and_draining(self):
        ui = self.ui()
        ui.handle_key(CTRL_B)
        ui.proc.poll.return_value = 0
        ui.proc.returncode = 0
        ui._end_title = Mock()
        ui._dialog_closed = Mock()
        ui._poll_workflow()
        self.assertTrue(ui.workflow_exit_reported)
        self.assertEqual(ui._background_status(), 'build finished — Ctrl-B to view')
        source = Path(tui.__file__).read_text()
        self.assertIn('or getattr(self, "backgrounded", False)) and getattr(self, "proc", None)', source)

    def test_ctrl_b_without_live_build_is_noop(self):
        ui = self.ui(live=False)
        ui.handle_key(CTRL_B)
        self.assertEqual(ui.state, 'running')

    def test_quit_while_backgrounded_needs_confirmation(self):
        ui = self.ui()
        ui.handle_key(CTRL_B)
        ui._quit = Mock()
        ui.handle_key(3)
        ui._quit.assert_not_called()
        self.assertIn('Ctrl-C again', ui.chat_error)

    # AC-5
    def test_ctrl_l_redraw(self):
        for state in ('running', 'menu', 'triage', 'config'):
            ui = self.ui(state=state)
            ui.handle_key(CTRL_L)
            ui.stdscr.clearok.assert_called_once_with(True)

    # AC-6
    def test_history_recall(self):
        ui = self.ui(live=False)
        for text in ('first', 'second'):
            ui.chat_composer = text
            ui.handle_key(10)
        ui._remember_input('y', gate=True, sent=True)  # excluded from recall
        ui.handle_key(curses.KEY_UP)
        self.assertEqual(ui.chat_composer, 'second')
        ui.handle_key(curses.KEY_UP)
        self.assertEqual(ui.chat_composer, 'first')
        ui.handle_key(curses.KEY_DOWN)
        self.assertEqual(ui.chat_composer, 'second')
        ui.handle_key(curses.KEY_DOWN)
        self.assertEqual(ui.chat_composer, '')

    def test_arrow_owners_preserved(self):
        hist = [{'text': 'old', 'gate': False, 'sent': False}]
        ui = self.ui(chat_choices=['a', 'b'], chat_pick=0, input_history=hist)
        ui.handle_key(curses.KEY_DOWN)
        self.assertEqual((ui.chat_pick, ui.chat_composer), (1, ''))
        ui = self.ui(prompt_kind='confirm', prompt_text='ok?', chat_focus='gate', input_history=hist)
        ui.handle_key(curses.KEY_DOWN)
        self.assertEqual((ui.prompt_scroll, ui.chat_composer), (1, ''))
        ui = self.ui(chat_composer='typed', input_history=hist)
        ui.handle_key(curses.KEY_UP)
        self.assertEqual(ui.chat_composer, 'typed')
        ui = self.ui(state='triage', input_history=hist)
        ui._triage_key = Mock()
        ui.handle_key(curses.KEY_UP)
        ui._triage_key.assert_called_once_with(curses.KEY_UP)

    # AC-7
    def test_shift_tab_mode(self):
        ui = self.ui()
        ui.misc = {'auto_mode': 'false'}
        ui.handle_key(curses.KEY_BTAB)
        self.assertTrue(ui._next_run_unattended())
        self.assertEqual(ui.chat_focus, 'chat')
        self.assertEqual(ui.chat_error, 'Next run: UNATTENDED (Shift-Tab)')
        self.assertEqual(ui.misc, {'auto_mode': 'false'})  # never persisted
        ui.handle_key(curses.KEY_BTAB)
        self.assertFalse(ui._next_run_unattended())
        self.assertEqual(ui.chat_error, 'Next run: attended')

    def test_auto_mode_is_the_default(self):
        # Unset means auto; only an explicit false runs attended.
        for misc, expected in (({}, True), ({'auto_mode': 'true'}, True),
                               ({'auto_mode': 'false'}, False), ({'auto_mode': 'FALSE'}, False)):
            with self.subTest(misc=misc):
                ui = self.ui()
                ui.misc = dict(misc)
                self.assertEqual(ui._next_run_unattended(), expected)
        ui = self.ui(config_section='misc')
        self.assertEqual(ui._config_items()[0], 'Auto mode: on')
        ui.handle_key(curses.KEY_BTAB)
        self.assertFalse(ui._next_run_unattended())
        self.assertEqual(ui.chat_error, 'Next run: attended')

    # AC-8
    def test_hints(self):
        ui = self.ui(has_kcbt=True)
        hint = ui._control_hint(120)
        for key in ('Esc interrupt', '^R', '^B', '^L', 'Shift-Tab', '/homepage'):
            self.assertIn(key, hint)
        self.assertIn('Ctrl-P', ui._control_hint(120, False))
        ui.has_kcbt = False
        self.assertNotIn('Shift-Tab', ui._control_hint(120))
        self.assertNotIn('Shift-Tab', ui._control_hint(120, False))

    # AC-9
    def test_existing_esc_paths(self):
        ui = self.ui(chat_choices=['a'], chat_picker=True)
        ui.handle_key(ESC)
        self.assertEqual(ui.chat_choices, [])
        ui.stop_workflow.assert_not_called()
        ui = self.ui(chat_edit=True, chat_composer='draft')
        ui.handle_key(ESC)
        self.assertFalse(ui.chat_edit)
        ui.stop_workflow.assert_not_called()
        ui = self.ui(chat_composer='typed')
        ui.handle_key(ESC)
        ui.stop_workflow.assert_not_called()
        ui = self.ui(recovery_active=True)
        ui.handle_key(ESC)
        self.assertFalse(ui.recovery_active)
        ui.stop_workflow.assert_not_called()
        ui = self.ui(prompt_kind='confirm', prompt_text='ok?', chat_focus='gate')
        ui.answer_prompt = Mock()
        ui.handle_key(ESC)
        ui.answer_prompt.assert_called_once_with('n')
        ui.stop_workflow.assert_not_called()
        ui = self.ui(state='menu', live=False)
        ui._homepage_key = Mock(return_value=False)
        ui.handle_key(ESC)
        self.assertEqual(ui.chat_focus, 'menu')


if __name__ == '__main__':
    unittest.main()
