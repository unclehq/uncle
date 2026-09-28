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


# ── Issue 97: Chat history persistence & Ctrl-R incremental search (AC-1..AC-15) ──

class ChatHistoryTests(unittest.TestCase):
    """AC-1 through AC-15 of CHANGE_SPEC.md."""

    def ui(self, state='menu', history=None, **attrs):
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
        ui.home_history = []
        ui.home_menu_open = False
        ui.chat_error = ''
        ui.input_history = [{'text': t, 'gate': False, 'sent': False} for t in (history if history is not None else ['hello', 'world', 'foo bar'])]
        ui.history_index = None
        ui._search_active = False
        ui._search_text = ''
        ui._search_results = []
        ui._search_index = -1
        ui._search_draft = ''
        ui.chat_ref_start = 0
        ui._history_path = '/tmp/_uncle_test_history.json'
        for k, v in attrs.items():
            setattr(ui, k, v)
        return ui

    # AC-1: Ctrl-R opens incremental search overlay
    def test_search_opens(self):
        ui = self.ui()
        r = ui._chat_search(18)  # Ctrl-R
        self.assertTrue(r)
        self.assertTrue(ui._search_active)
        self.assertEqual(ui._search_text, '')
        self.assertEqual(ui._search_results, [])
        self.assertEqual(ui._search_index, -1)

    # AC-1: Ctrl-R with empty history is a no-op (overlap with AC-13)
    def test_search_empty_history_is_noop(self):
        ui = self.ui(history=[])
        r = ui._chat_search(18)
        self.assertTrue(r)
        self.assertFalse(ui._search_active)
        self.assertEqual(ui.chat_error, 'No history to search')

    # AC-2: typing narrows results
    def test_search_filters(self):
        ui = self.ui(history=['hello', 'world', 'foo bar'])
        ui._chat_search(18)  # Ctrl-R to open
        for ch in 'wo':
            ui._chat_search(ord(ch))
        self.assertEqual(ui._search_text, 'wo')
        self.assertGreaterEqual(len(ui._search_results), 1)
        self.assertIn(ui.chat_composer, ('world', 'wo'))  # whichever matches

    # AC-3: repeat Ctrl-R cycles older
    def test_search_cycle(self):
        ui = self.ui(history=['alpha', 'beta', 'gamma'])
        ui._chat_search(18)  # open
        ui._chat_search(ord('a'))  # 'a' matches all 3
        self.assertGreaterEqual(len(ui._search_results), 3)
        ui._chat_search(18)  # cycle forward
        i = ui._search_index
        self.assertIn(i, range(len(ui._search_results)))

    # AC-3: multiple matches, cycling
    def test_search_cycle_multi(self):
        ui = self.ui(history=['ab', 'ac', 'ad'])
        ui._chat_search(18)
        ui._chat_search(ord('a'))
        n = len(ui._search_results)
        self.assertGreaterEqual(n, 3)
        first = ui.chat_composer
        ui._chat_search(18)  # cycle
        second = ui.chat_composer
        self.assertNotEqual(first, second)

    # AC-4: Enter accepts result into composer
    def test_search_accept(self):
        ui = self.ui(history=['keep this'])
        ui._chat_search(18)
        ui._chat_search(ord('k'))
        self.assertEqual(ui.chat_composer, 'keep this')
        r = ui._chat_search(10)  # Enter
        self.assertTrue(r)
        self.assertFalse(ui._search_active)
        self.assertEqual(ui.chat_composer, 'keep this')

    # AC-4b: Esc restores pre-search draft
    def test_search_cancel(self):
        ui = self.ui(history=['something'])
        ui.chat_composer = 'my draft'
        ui._chat_search(18)  # Ctrl-R opens, saves draft
        ui._chat_search(ord('s'))  # overwrites composer
        self.assertNotEqual(ui.chat_composer, 'my draft')
        r = ui._chat_search(27)  # Esc cancels
        self.assertTrue(r)
        self.assertFalse(ui._search_active)
        self.assertEqual(ui.chat_composer, 'my draft')

    # AC-5: dedup — remove-then-reappend
    def test_dedup(self):
        ui = self.ui(history=['a', 'b', 'c'])
        ui._remember_input('b')
        self.assertEqual([e['text'] for e in ui.input_history], ['a', 'c', 'b'])

    # AC-6: persistence round-trip
    def test_persistence_round_trip(self):
        import json, os
        path = '/tmp/_uncle_test_rt.json'
        if os.path.exists(path):
            os.remove(path)
        ui = self.ui(_history_path=path, input_history=[])
        ui._remember_input('first')
        ui._remember_input('second')
        self.assertTrue(os.path.exists(path))
        with open(path) as f:
            data = json.load(f)
        self.assertEqual(data['entries'], ['first', 'second'])
        # simulate restart
        ui2 = self.ui(_history_path=path, input_history=[])
        ui2._load_chat_history()
        self.assertEqual([e['text'] for e in ui2.input_history], ['first', 'second'])
        os.remove(path)

    # AC-7: cap at 300
    def test_cap(self):
        ui = self.ui(history=[], input_history=[])
        for i in range(305):
            ui._remember_input(str(i))
        self.assertLessEqual(len(ui.input_history), 300)
        self.assertEqual(ui.input_history[0]['text'], '5')  # 5..304 = 300 entries

    def test_cap_persisted(self):
        ui = self.ui(history=[], input_history=[])
        for i in range(305):
            ui._remember_input(str(i))
        self.assertLessEqual(len(ui.input_history), 300)

    # AC-8: Up/Down menu/picker priority (existing behavior) — just verify no regression
    def test_arrow_with_picker_preserved(self):
        ui = self.ui(chat_picker=True, chat_choices=['a', 'b'], chat_pick=0)
        ui.handle_key(curses.KEY_DOWN)
        self.assertEqual(ui.chat_pick, 1)
        self.assertEqual(ui.chat_composer, '')
        self.assertFalse(hasattr(ui, '_search_active') and ui._search_active)

    # AC-9: Ctrl-R while running toggles transcript (unchanged)
    def test_ctrl_r_running_toggles_transcript(self):
        ui = self.ui(state='running')
        ui.handle_key(CTRL_R)
        self.assertTrue(getattr(ui, 'transcript_full', False))
        ui.handle_key(CTRL_R)
        self.assertFalse(getattr(ui, 'transcript_full', False))

    # AC-10: gate excluded from recall, search, and file
    def test_gate_excluded_from_recall(self):
        ui = self.ui(history=['a', 'b'])
        ui.input_history.append({'text': 'gate-answer', 'gate': True, 'sent': True})
        ui._recall_input(-1)
        self.assertNotEqual(ui.chat_composer, 'gate-answer')

    def test_gate_excluded_from_search(self):
        ui = self.ui(history=['visible'])
        ui.input_history.append({'text': 'gate-answer', 'gate': True, 'sent': True})
        ui._chat_search(18)  # open
        ui._chat_search(ord('g'))
        self.assertEqual(ui.chat_composer, '')
        self.assertEqual(ui.chat_error, 'No matches')

    def test_gate_not_persisted(self):
        ui = self.ui(history=[], input_history=[])
        ui._remember_input('normal')
        ui._remember_input('hidden', gate=True)
        texts = [e['text'] for e in ui.input_history if not e['gate']]
        self.assertIn('normal', texts)
        self.assertNotIn('hidden', ui.input_history)

    # AC-11: malformed or missing file => empty history, no crash
    def test_missing_file(self):
        ui = self.ui(_history_path='/tmp/_nonexistent_history.json', input_history=[])
        ui._load_chat_history()
        self.assertEqual(ui.input_history, [])

    def test_malformed_file(self):
        import os
        path = '/tmp/_uncle_bad.json'
        with open(path, 'w') as f:
            f.write('not json')
        ui = self.ui(_history_path=path, input_history=[])
        ui._load_chat_history()
        self.assertEqual(ui.input_history, [])
        os.remove(path)

    # AC-13: Ctrl-R with empty history is a no-op
    def test_empty_history_noop(self):
        ui = self.ui(history=[])
        r = ui._chat_search(18)
        self.assertTrue(r)
        self.assertFalse(ui._search_active)
        self.assertEqual(ui.chat_error, 'No history to search')

    # AC-14: partially-written file treated as malformed
    def test_partial_write(self):
        import os
        path = '/tmp/_uncle_partial.json'
        with open(path, 'w') as f:
            f.write('{"entries": ["ok", ' )  # truncated
        ui = self.ui(_history_path=path, input_history=[])
        ui._load_chat_history()
        self.assertEqual(ui.input_history, [])
        os.remove(path)

    # AC-15: Ctrl-R with menu/picker open is a no-op
    def test_ctrl_r_with_picker(self):
        ui = self.ui(chat_picker=True)
        r = ui._chat_search(18)
        self.assertFalse(r)
        self.assertFalse(ui._search_active)

    def test_ctrl_r_with_edit(self):
        ui = self.ui(chat_edit=True)
        r = ui._chat_search(18)
        self.assertFalse(r)
        self.assertFalse(ui._search_active)


if __name__ == '__main__':
    unittest.main()
