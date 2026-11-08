#!/usr/bin/env python3
"""Home-page layout: status pinned to the last row, no gap below the composer; build page and chat panel unchanged.

Baseline build-page/chat-panel offsets below are hard-coded literals taken from the unmodified code
(BASELINE_REPORT B-3: build status = composer_row + extra + 2). They are never derived from the code under test.
"""
import curses
import importlib.util
import sys
import types
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
spec = importlib.util.spec_from_file_location('uncle_tui_under_test', ROOT / 'uncle_tui.py')
tui = importlib.util.module_from_spec(spec)
spec.loader.exec_module(tui)

GREETING = 'What can uncle do for you?'
W = 80
FULL_H = 60  # tall enough to be non-compact for any realistic LOGO
LONG = ('a' * 70 + ' ') * 3  # wraps to 3 composer rows (extra == 2) at width 76


class FakeScreen:
    def __init__(self, h, w):
        self.h, self.w = h, w
        self.draws = []
        self.reverse = []  # (y, x) of every cell drawn with A_REVERSE: the app-drawn cursor
        self.moves = []

    def getmaxyx(self):
        return self.h, self.w

    def addnstr(self, y, x, text, n, attr=0):
        self.draws.append((y, x, text[:n]))
        if attr & curses.A_REVERSE:
            self.reverse.append((y, x))

    def move(self, y, x):
        self.moves.append((y, x))

    def __getattr__(self, name):
        return lambda *a, **k: None


def make(h, w=W, state='menu', composer='', history=0):
    t = object.__new__(tui.UncleTUI)
    t.stdscr = FakeScreen(h, w)
    t.state = state
    t.color = {}
    t.chat = types.SimpleNamespace(preview='')
    t.chat_composer = composer
    t.chat_error = ''
    t.chat_choices = []
    t.chat_pick = 0
    t.chat_focus = 'chat'
    t.home_scroll = 0
    t.menu_items = lambda: []
    t.chat_entries = lambda: [('user', 'msg %d' % i) for i in range(history)]
    t.chat_attr = lambda role, default=0: 0
    t._background_status = lambda: ''
    t._next_run_unattended = lambda: False
    t.test_execution_status = lambda: ''
    t._draw_file_picker = lambda *a, **k: None
    t._paint_selection = lambda: None
    t._composer_cursor = lambda: len(t.chat_composer)
    return t


def home(h, composer='', history=0, w=W):
    t = make(h, w, 'menu', composer, history)
    t._draw_homepage(h, w)
    return t, t.stdscr.draws


def rows_of(draws, pred):
    return sorted({y for y, _, text in draws if pred(text)})


def rule_rows(draws):
    return rows_of(draws, lambda s: s.startswith('─'))


WIDTHS = (20, 40, 80, 120)


def wrap_width(w):
    # Composer text width: screen width minus 4 margin columns minus the 2-column prompt (min 8).
    return max(8, (w - 4) - 2)


def composer_text(w, rows):
    """Unbroken text that wraps to exactly `rows` rows, the last one 3 columns short of full."""
    return '' if rows == 0 else 'a' * ((rows - 1) * wrap_width(w) + wrap_width(w) - 3)


def status_draws(draws, h):
    return [d for d in draws if d[0] == h - 1]


class HomeLayout(unittest.TestCase):
    def check_pinned(self, h, composer=''):
        _, draws = home(h, composer)
        extra = 2 if composer else 0
        e = min(extra, max(0, h - 4))
        crow = h - 3 - e
        self.assertTrue(status_draws(draws, h), 'nothing drawn on the last row h-1=%d' % (h - 1))
        for _, _, text in status_draws(draws, h):
            self.assertFalse(text.startswith('─'), 'rule drawn on status row')
        self.assertIn(h - 2, rule_rows(draws))
        for y, _, _ in draws:
            self.assertTrue(0 <= y < h, 'draw outside the screen at row %d' % y)
        return draws, crow, e

    def test_AC1_status_on_last_row_at_24_and_50(self):
        for h in (24, 50):
            draws, _, _ = self.check_pinned(h)
            self.assertTrue(any('Chat ready' in t for _, _, t in status_draws(draws, h)))

    def test_AC2_no_gap_between_bottom_rule_and_status(self):
        for h in (24, 50, FULL_H):
            for composer in ('', LONG):
                draws, crow, e = self.check_pinned(h, composer)
                self.assertEqual(rule_rows(draws)[-1], h - 2)
                self.assertIn(crow + 1 + e, rule_rows(draws))
                self.assertEqual(crow + 1 + e, h - 2)
                self.assertEqual(crow + e + 2, h - 1)
                self.assertTrue(any(y == crow and t.startswith('›') for y, _, t in draws))

    def test_AC1_AC2_AC5_matrix_widths_heights_composer_rows(self):
        # Plan widths {20,40,80,120} x composer rows 0..9 (cap is 6 rows) x heights that include the
        # priority-overflow range (h - 3 < rows), with expected rows written out independently.
        for w in WIDTHS:
            ww = wrap_width(w)
            for h in (4, 5, 6, 8, 12, 24, 50, FULL_H):
                for rows in (0, 1, 2, 3, 4, 5, 6, 7, 9):
                    shown = max(1, min(rows, 6, h - 3))
                    e = shown - 1
                    crow = h - 3 - e
                    tag = 'w=%d h=%d rows=%d' % (w, h, rows)
                    t, draws = home(h, composer_text(w, rows), w=w)
                    # Narrow widths clip the status text (existing behavior); only require text on the last row there.
                    self.assertTrue(any(('Chat ready' in tx) if w >= 80 else tx.strip()
                                        for _, _, tx in status_draws(draws, h)), tag + ' status')
                    self.assertIn(h - 2, rule_rows(draws), tag)
                    self.assertEqual(rule_rows(draws)[-1], h - 2, tag)
                    self.assertTrue(all(0 <= y < h for y, _, _ in draws), tag + ' off-screen draw')
                    self.assertIn(crow, rows_of(draws, lambda s: s.startswith('›')), tag + ' prompt')
                    if rows:
                        self.assertEqual(rows_of(draws, lambda s: s.lstrip('› ').startswith('a')),
                                         list(range(crow, crow + shown)), tag + ' composer rows')
                    # The app-drawn cursor sits on the last visible composer row, at the end of the text.
                    col = 2 + 2 + (ww - 3 if rows else 0)
                    self.assertEqual(t.stdscr.reverse, [(crow + e, col)], tag + ' cursor')

    def test_AC2_non_compact_block_offsets(self):
        h = FULL_H
        self.assertGreaterEqual(h, len(tui.LOGO) + 12, 'FULL_H must be non-compact')
        for composer, e in (('', 0), (LONG, 2)):
            _, draws = home(h, composer)
            crow = h - 3 - e
            # Baseline non-compact build layout (BuildAndPanelUnchanged): greeting is 4 rows above the composer.
            self.assertEqual(rows_of(draws, lambda s: s == GREETING), [crow - 4])
            self.assertIn(crow - 1, rule_rows(draws))
            self.assertEqual(sorted(set(rule_rows(draws)) & {crow - 1, h - 2}), [crow - 1, h - 2])

    def test_no_two_blocks_share_a_row(self):
        def kind(y, t, h):
            if t == GREETING:
                return 'greeting'
            if t in tui.LOGO:
                return 'logo'
            if t.startswith('─'):
                return 'rule'
            if t.startswith('›') or t.lstrip().startswith('a') or len(t) == 1:
                return 'composer'  # prompt, wrapped text, or the one-cell cursor
            if 'Chat ready' in t or 'mode(' in t:
                return 'status'
            if 'commands' in t or 'cmds' in t or 'Ctrl-P' in t:
                return 'hint'
            return 'other:' + t
        for h in (24, 50, FULL_H):
            _, draws = home(h, LONG, history=0)
            by_row = {}
            for y, _, t in draws:
                by_row.setdefault(y, set()).add(kind(y, t, h))
            for y, kinds in by_row.items():
                self.assertEqual(len(kinds), 1, 'h=%d row %d shared by %s' % (h, y, sorted(kinds)))
                self.assertFalse(any(k.startswith('other') for k in kinds), sorted(kinds))
            self.assertEqual(by_row[h - 1], {'status'})

    def test_AC5_tiny_heights_pin_bottom_derived_rows(self):
        for h in (4, 5, 6, 7, 8, 10, 12):
            for composer in ('', LONG):
                draws, crow, e = self.check_pinned(h, composer)
                self.assertTrue(any(y == crow and t.startswith('›') for y, _, t in draws), 'h=%d composer row' % h)
                self.assertEqual(h - 2, crow + 1 + e)
                # nothing drawn into the composer/rule/status rows except those blocks
                self.assertEqual([t for y, _, t in draws if y == h - 2 and not t.startswith('─')], [])

    def test_AC5_h3_and_h2_do_not_raise_and_keep_status_last(self):
        for h in (2, 3):
            _, draws = home(h)
            self.assertTrue(status_draws(draws, h))
            self.assertIn(h - 2, rule_rows(draws))

    def test_AC5_history_newest_shown_and_text_view_top(self):
        h = FULL_H
        t, draws = home(h, '', history=200)
        crow = h - 3
        greeting = crow - 5
        hist = sorted((y, tx) for y, _, tx in draws if tx.startswith('msg '))
        self.assertTrue(hist)
        self.assertIn('msg 199', [tx for _, tx in hist])
        self.assertNotIn('msg 0', [tx for _, tx in hist])
        self.assertLess(hist[-1][0], greeting)
        self.assertEqual([y for y, _ in hist], list(range(hist[0][0], hist[0][0] + len(hist))))
        self.assertEqual(t._text_view['top'], hist[0][0])
        self.assertEqual(t._text_view['rows'], len(hist))
        self.assertEqual(hist[-1][1], 'msg 199')

    def test_AC5_empty_history_text_view_top_is_greeting_row(self):
        h = FULL_H
        t, draws = home(h)
        greeting = rows_of(draws, lambda s: s == GREETING)
        self.assertEqual(len(greeting), 1)
        self.assertIsNotNone(t._text_view)
        self.assertEqual(t._text_view['top'], greeting[0] - 1)  # block start; greeting sits one row below it
        self.assertEqual(t._text_view['rows'], 0)

    def test_AC5_body_rows_zero_draws_no_history(self):
        h = 6
        t, draws = home(h, '', history=50)
        self.assertEqual([d for d in draws if d[2].startswith('msg ')], [])
        view = t._text_view
        self.assertIsNotNone(view)
        self.assertEqual(view['rows'], 0)
        self.assertEqual(view['lines'], [])
        self.assertTrue(status_draws(draws, h))

    def test_AC5_cursor_on_last_visible_composer_row(self):
        h = FULL_H
        t, _ = home(h, LONG)
        crow = h - 3 - 2
        # LONG wraps to 3 rows (asserted via the rule position), cursor is the single reverse-video cell.
        self.assertEqual(len(t.stdscr.reverse), 1)
        self.assertEqual(t.stdscr.reverse[0][0], crow + 2)
        self.assertNotEqual(t.stdscr.reverse[0][0], crow)

    def test_AC5_control_characters_are_sanitized(self):
        h = FULL_H
        _, draws = home(h, 'ab\x1b[31mcd\tef\x07gh\nij')
        texts = [tx for _, _, tx in draws]
        self.assertTrue(any('ab' in tx for tx in texts))
        for tx in texts:
            self.assertNotIn('\x1b', tx)
            self.assertNotIn('\x07', tx)
            self.assertNotIn('\t', tx)
        self.assertTrue(status_draws(draws, h))


class FeedbackVisible(unittest.TestCase):
    def feedback_texts(self, t, h):
        return [tx for y, _, tx in t.stdscr.draws if y not in range(0, h - 2) or True]

    def test_AC3_each_condition_visible_on_home(self):
        h = 30
        for setup, marker in ((lambda t: setattr(t, 'chat_error', 'boom happened'), 'boom happened'),
                              (lambda t: (setattr(t, 'chat_choices', ['x.py']), setattr(t, 'chat_pick', 0)), 'File: x.py'),
                              (lambda t: setattr(t, 'chat_composer', '/'), '/configure')):
            t = make(h)
            setup(t)
            t._draw_homepage(h, W)
            texts = [tx for _, _, tx in t.stdscr.draws]
            self.assertTrue(any(marker in tx for tx in texts), marker)
            for y, _, tx in t.stdscr.draws:
                self.assertTrue(0 <= y < h)
            self.assertTrue(status_draws(t.stdscr.draws, h))

    def test_AC3_chat_error_wins_over_choices_and_slash(self):
        h = 30
        t = make(h)
        t.chat_error = 'boom happened'
        t.chat_choices = ['x.py']
        t.chat_composer = '/'
        t._draw_homepage(h, W)
        texts = [tx for _, _, tx in t.stdscr.draws]
        self.assertTrue(any('boom happened' in tx for tx in texts))
        self.assertFalse(any(tx.startswith('File: ') for tx in texts))
        self.assertFalse(any('/configure /settings' in tx for tx in texts))

    def test_AC3_choices_win_over_slash(self):
        h = 30
        t = make(h)
        t.chat_choices = ['x.py']
        t.chat_composer = '/'
        t._draw_homepage(h, W)
        texts = [tx for _, _, tx in t.stdscr.draws]
        self.assertTrue(any(tx.startswith('File: x.py') for tx in texts))
        self.assertFalse(any('/configure /settings' in tx for tx in texts))

    def test_AC3_feedback_precedence_clip_and_no_free_row(self):
        h = 30
        t = make(h)
        t.chat_error = 'E' * 300
        t._draw_homepage(h, W)
        errs = [tx for _, _, tx in t.stdscr.draws if tx.startswith('EEE')]
        self.assertTrue(errs)
        self.assertTrue(all(len(tx) <= W - 4 for tx in errs))
        # smallest screens: no exception, status still last
        for hh in (2, 3, 4, 5, 6):
            t = make(hh)
            t.chat_error = 'boom'
            t._draw_homepage(hh, W)
            self.assertTrue(status_draws(t.stdscr.draws, hh))


class FeedbackRows(unittest.TestCase):
    """D-1: with status on the last row, feedback takes the row two above the composer (crow-2)."""

    def draw(self, h, **state):
        t = make(h)
        for k, v in state.items():
            setattr(t, k, v)
        t._draw_homepage(h, W)
        return t.stdscr.draws

    def test_AC3_compact_feedback_replaces_hint_at_crow_minus_2(self):
        h = 24  # compact: h < len(LOGO) + 12
        self.assertLess(h, len(tui.LOGO) + 12)
        crow = h - 3
        base = self.draw(h)
        self.assertEqual(len([d for d in base if d[0] == crow - 2 and '/ commands' in d[2]]), 1, 'hint at crow-2 when idle')
        for state, marker in (({'chat_error': 'boom happened'}, 'boom happened'),
                              ({'chat_choices': ['x.py']}, 'File: x.py'),
                              ({'chat_composer': '/'}, '/configure /settings')):
            d = self.draw(h, **state)
            self.assertEqual([x[2][:len(marker)] for x in d if x[0] == crow - 2], [marker], marker)
            self.assertFalse([x for x in d if '/ commands' in x[2]], 'hint must be suppressed: ' + marker)
        # clearing the condition brings the hint back on the same row
        self.assertEqual(len([d for d in self.draw(h) if d[0] == crow - 2 and '/ commands' in d[2]]), 1)

    def test_AC3_non_compact_feedback_at_crow_minus_2_hint_stays(self):
        h = FULL_H
        crow = h - 3
        d = self.draw(h, chat_error='boom happened')
        self.assertEqual([x[2] for x in d if x[0] == crow - 2], ['boom happened'])
        self.assertEqual(len([x for x in d if x[0] == crow - 3 and '/ commands' in x[2]]), 1, 'hint kept at crow-3')
        self.assertEqual(rule_rows(d), [crow - 1, h - 2])

    def test_AC3_no_free_row_feedback_never_lands_on_pinned_rows(self):
        for h in (4, 5, 6):
            d = self.draw(h, chat_error='boom happened')
            for y, _, tx in d:
                if tx.startswith('boom'):
                    self.assertNotIn(y, (h - 1, h - 2, h - 3), 'h=%d feedback on pinned row %d' % (h, y))
            self.assertTrue(status_draws(d, h))
            self.assertIn('Chat ready', status_draws(d, h)[0][2])


class BuildAndPanelUnchanged(unittest.TestCase):
    """Literal baseline offsets from the unmodified code (BASELINE_REPORT B-3)."""

    def build(self, row, h, compact, composer=''):
        t = make(h, W, 'running', composer)
        t._draw_chat_composer(row, h, W, 2, W - 4, compact)
        return t.stdscr.draws

    def test_AC4_build_non_compact_offsets(self):
        # row=10: greeting 12, hint 13, top rule 15, composer 16, bottom rule 17, status 18
        d = self.build(10, 40, False)
        self.assertEqual(rows_of(d, lambda s: s == GREETING), [12])
        self.assertEqual(rule_rows(d), [15, 17])
        self.assertIn(16, rows_of(d, lambda s: s.startswith('›')))
        self.assertEqual(rows_of(d, lambda s: 'Chat ready' in s), [18])

    def test_AC4_build_non_compact_wrapped_composer(self):
        # extra=2: composer 16..18, bottom rule 19, status 20
        d = self.build(10, 40, False, LONG)
        self.assertEqual(rule_rows(d), [15, 19])
        self.assertEqual(rows_of(d, lambda s: 'Chat ready' in s), [20])

    def test_AC4_build_compact_offsets(self):
        # row=10, compact build: row-1=9, top rule 11, composer 12, bottom rule 13, status 14
        d = self.build(10, 40, True)
        self.assertEqual(rule_rows(d), [11, 13])
        self.assertEqual(rows_of(d, lambda s: 'Chat ready' in s), [14])

    def test_AC4_chat_panel_default_not_anchored(self):
        # non-build, compact default, plenty of room: composer = row+3, bottom rule +4, status +5 (compact offset 2)
        t = make(40, W, 'menu')
        t._draw_chat_composer(10, 40, W, 2, W - 4)
        d = t.stdscr.draws
        self.assertEqual(rule_rows(d), [12, 14])
        self.assertEqual(rows_of(d, lambda s: 'Chat ready' in s), [15])
        # ...and in particular not pinned to the last row (h-1 = 39) as the home page is.
        self.assertNotIn(39, rows_of(d, lambda s: 'Chat ready' in s))

    def test_AC4_non_compact_non_build_keeps_blank_row(self):
        # non-compact, non-build, default anchor_bottom=False: status is composer+3 (blank row retained)
        t = make(40, W, 'menu')
        t._draw_chat_composer(10, 40, W, 2, W - 4, False)
        d = t.stdscr.draws
        self.assertEqual(rows_of(d, lambda s: 'Chat ready' in s), [19])


if __name__ == '__main__':
    unittest.main()
