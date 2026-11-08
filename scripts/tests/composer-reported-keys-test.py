#!/usr/bin/env python3
"""The composer types the characters a terminal reports as modifyOtherKeys / CSI-u sequences, and never prints the raw sequence."""
import curses
import sys
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'scripts' / 'lib'))
from uncle_tui import UncleTUI


class FakeScreen:
    def __init__(self, text):
        self.keys = [ord(c) for c in text]
    def timeout(self, _ms):
        pass
    def getch(self):
        return self.keys.pop(0) if self.keys else -1


def composer():
    ui = UncleTUI.__new__(UncleTUI)
    ui.chat_composer = ''
    ui.typed = []
    ui.metas = []
    ui._plain_composing = lambda: True
    ui._chat_key = lambda k: ui.typed.append(k) or True
    ui._chat_meta = lambda k: ui.metas.append(k)
    ui._composer_cursor = lambda: len(ui.chat_composer)
    def set_composer(text, cursor):
        ui.chat_composer = text
    ui._set_composer = set_composer
    ui._composer_newline = lambda: ui.typed.append('NEWLINE')
    return ui


def read(ui, body):
    """What _read_csi returns for the bytes after ESC [, plus what it pushed back for the key loop."""
    pushed = []
    with mock.patch.object(curses, 'ungetch', lambda ch: pushed.append(ch)):
        result = ui._read_csi(FakeScreen(body))
    return result, pushed


class ReportedKeys(unittest.TestCase):
    def test_shift_i_is_typed_not_printed(self):
        for body in ('27;2;73~', '73;2u'):
            ui = composer()
            result, pushed = read(ui, body)
            self.assertEqual((result, ui.typed, pushed), (73, [73], []), body)

    def test_every_capital_and_shifted_symbol_is_typed(self):
        ui = composer()
        for code in list(range(65, 91)) + [ord(c) for c in '!@#$%^&*()_+{}|:"<>?~']:
            read(ui, '27;2;%d~' % code)
        self.assertEqual(len(ui.typed), 26 + len('!@#$%^&*()_+{}|:"<>?~'))
        self.assertEqual(ui.typed[8], ord('I'))

    def test_shifted_non_ascii_is_inserted_as_text(self):
        ui = composer()
        result, _ = read(ui, '27;2;201~')      # shift+e-acute
        self.assertEqual((result, ui.chat_composer, ui.typed), (201, 'É', []))

    def test_other_well_formed_reports_are_consumed_and_never_shown(self):
        for body in ('27;6;88~', '27;4;33~', '27;2;9~', '88;6u', '27;7;49~'):
            ui = composer()
            result, pushed = read(ui, body)
            self.assertIsNotNone(result, body)
            self.assertEqual((ui.typed, ui.chat_composer, pushed), ([], '', []), body)

    def test_existing_shortcuts_are_unchanged(self):
        ui = composer()
        self.assertEqual(read(ui, '27;5;97~')[0], 1)                 # Ctrl+A -> its control byte
        self.assertEqual(ui.typed, [1])
        ui = composer()
        self.assertEqual(read(ui, '27;3;98~')[0], 98)                # Alt+b
        self.assertEqual(ui.metas, [98])
        ui = composer()
        self.assertEqual(read(ui, '13;2u')[0], 13)                   # Shift+Enter inserts a newline
        self.assertEqual(ui.typed, ['NEWLINE'])

    def test_a_sequence_that_is_not_a_key_report_is_still_pushed_back(self):
        ui = composer()
        result, pushed = read(ui, 'I')                               # a terminal focus-in report, say
        self.assertIsNone(result)
        self.assertTrue(pushed)


if __name__ == '__main__':
    unittest.main()
