from pathlib import Path
import sys
import collections
import tempfile
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
import os
os.environ.setdefault('UNCLE_HOME_AGENT', '0')
import uncle_tui as tui


class SanitizePaste(unittest.TestCase):
    def test_crlf_and_cr_become_lf(self):
        self.assertEqual(tui.sanitize_paste('a\r\nb\rc\nd'), 'a\nb\nc\nd')

    def test_drops_escape_and_c0_keeps_lf_tab(self):
        self.assertEqual(tui.sanitize_paste('a\x1b[31mb\x00\x07\x08c\td\ne'), 'a[31mbc\td\ne')

    def test_drops_del_and_c1_including_8bit_csi(self):
        self.assertEqual(tui.sanitize_paste('a\x7fb\x80c\x9bd\x9fe'), 'abcde')

    def test_drops_bidi_controls(self):
        text = ''.join(chr(c) for c in list(range(0x202A, 0x202F)) + list(range(0x2066, 0x206A)))
        self.assertEqual(tui.sanitize_paste('x' + text + 'y'), 'xy')

    def test_keeps_ordinary_unicode(self):
        self.assertEqual(tui.sanitize_paste('héllo ✓ 日本'), 'héllo ✓ 日本')

    def test_empty_and_large_input(self):
        self.assertEqual(tui.sanitize_paste(''), '')
        big = 'ab\r\n' * 50000
        self.assertEqual(tui.sanitize_paste(big), 'ab\n' * 50000)


class ClassifyEscape(unittest.TestCase):
    def test_paste_start(self):
        self.assertEqual(tui.classify_escape(b'[200~'), 'paste')

    def test_shift_enter_csi_u_and_modify_other_keys(self):
        self.assertEqual(tui.classify_escape(b'[13;2u'), 'newline')
        self.assertEqual(tui.classify_escape(b'[27;2;13~'), 'newline')

    def test_esc_enter(self):
        self.assertEqual(tui.classify_escape(b'\r'), 'newline')
        self.assertEqual(tui.classify_escape(b'\n'), 'newline')

    def test_other_modifiers_and_unknown_are_none(self):
        for seq in (b'[13;3u', b'[A', b'[201~', b'x', b''):
            self.assertIsNone(tui.classify_escape(seq), seq)


class FakeScreen:
    def __init__(self, data=b''):
        self.q = collections.deque(data)
        self.pushed = []
    def timeout(self, ms):
        pass
    def getch(self):
        if self.pushed:
            return self.pushed.pop()
        return self.q.popleft() if self.q else -1


class Keys(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        ctx = patch.object(tui, '_project_root', return_value=tmp.name)
        ctx.start()
        self.addCleanup(ctx.stop)
        ui = tui.UncleTUI.__new__(tui.UncleTUI)
        ui._ensure_chat()
        ui.state, ui.proc = 'menu', None
        ui.chat_open, ui.chat_focus = True, 'chat'
        ui.send_home_chat = Mock()
        ui._run = Mock()
        self.ui = ui
        def ungetch(ch):
            self.screen.pushed.append(ch)
        p = patch.object(tui.curses, 'ungetch', ungetch)
        p.start()
        self.addCleanup(p.stop)

    def feed(self, first, rest=b'', text='', cursor=None):
        self.screen = FakeScreen(rest)
        self.ui.stdscr = self.screen
        self.ui._set_composer(text, len(text) if cursor is None else cursor)
        self.ui.handle_key(first)
        while self.screen.pushed or self.screen.q:
            self.ui.handle_key(self.screen.pushed.pop() if self.screen.pushed else self.screen.q.pop(0))

    def test_AC1_enter_submits_and_empty_does_not(self):
        self.feed(10, text='hi')
        self.ui.send_home_chat.assert_called_once_with('hi')
        self.assertEqual(self.ui.chat_composer, '')
        self.ui.send_home_chat.reset_mock()
        self.feed(10, text='')
        self.assertEqual([c for c in self.ui.send_home_chat.call_args_list if c.args[0].strip()], [])

    def test_AC2_ctrl_enter_forms_insert_newline_at_cursor(self):
        for seq in (b'[13;2u', b'[27;2;13~'):
            with self.subTest(seq=seq):
                self.ui.send_home_chat.reset_mock()
                self.feed(27, seq, text='abcd', cursor=2)
                self.assertEqual(self.ui.chat_composer, 'ab\ncd')
                self.assertEqual(self.ui._composer_cursor(), 3)
                self.ui.send_home_chat.assert_not_called()

    def test_ctrl_enter_submits(self):
        for seq in (b'[13;5u', b'[27;5;13~'):
            with self.subTest(seq=seq):
                self.ui.send_home_chat.reset_mock()
                self.feed(27, seq, text='hi')
                self.ui.send_home_chat.assert_called_once_with('hi')

    def test_AC2_esc_enter_inserts_newline(self):
        self.feed(27, b'\r', text='ab', cursor=1)
        self.assertEqual(self.ui.chat_composer, 'a\nb')
        self.ui.send_home_chat.assert_not_called()

    def test_shift_enter_forms_insert_newline(self):
        for seq in (b'[13;2u', b'[27;2;13~'):
            with self.subTest(seq=seq):
                self.ui.send_home_chat.reset_mock()
                self.feed(27, seq, text='hi')
                self.assertEqual(self.ui.chat_composer, 'hi\n')
                self.ui.send_home_chat.assert_not_called()

    def test_AC2_other_modifier_enter_submits(self):
        self.feed(27, b'[13;3u', text='hi')
        self.ui.send_home_chat.assert_called_once_with('hi')

    def test_AC3_bracketed_paste_inserts_without_submit(self):
        self.feed(27, b'[200~one\r\ntwo\x1b[31m\rthree\x1b[201~', text='AB', cursor=1)
        self.assertEqual(self.ui.chat_composer, 'Aone\ntwo[31m\nthreeB')
        self.ui.send_home_chat.assert_not_called()

    def test_AC3_paste_respects_limit(self):
        self.feed(27, b'[200~' + b'x' * (tui.COMPOSER_LIMIT + 50) + b'\x1b[201~', text='')
        self.assertLessEqual(len(self.ui.chat_composer.encode()), tui.COMPOSER_LIMIT)
        self.assertGreater(len(self.ui.chat_composer), 0)

    def test_AC3_unterminated_paste_does_not_hang(self):
        self.feed(27, b'[200~partial', text='')
        self.assertEqual(self.ui.chat_composer, 'partial')
        self.ui.send_home_chat.assert_not_called()

    def test_AC3_enter_burst_is_newline_but_lone_enter_submits(self):
        self.feed(10, b'ab', text='x')
        self.ui.send_home_chat.assert_not_called()
        self.assertTrue(self.ui.chat_composer.startswith('x\n'))
        self.feed(10, b'', text='y')
        self.ui.send_home_chat.assert_called_once_with('y')

    def test_AC4_esc_other_key_pushed_back(self):
        self.feed(27, b'x', text='')
        self.assertNotIn('\n', self.ui.chat_composer)
        self.ui.send_home_chat.assert_not_called()

    def test_AC5_terminal_modes_enable_and_always_disable(self):
        out = []
        m = tui.TerminalModes(writer=out.append, enabled=lambda: True)
        self.assertTrue(m.enable())
        m.disable(); m.disable()
        self.assertEqual(out, [tui.TERMINAL_MODES_ENABLE, tui.TERMINAL_MODES_DISABLE])
        self.assertIn('?2004h', tui.TERMINAL_MODES_ENABLE)
        self.assertIn('?2004l', tui.TERMINAL_MODES_DISABLE)
        out.clear()
        tui.TerminalModes(writer=out.append, enabled=lambda: False).disable()
        self.assertEqual(out, [])


if __name__ == '__main__':
    unittest.main()
