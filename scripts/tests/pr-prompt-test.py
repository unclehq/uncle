#!/usr/bin/env python3
"""PR defaults use the existing text-input protocol and preserve other prompts."""
from pathlib import Path
import sys
import unittest
from unittest.mock import Mock

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from uncle_tui import UncleTUI


class PromptTests(unittest.TestCase):
    def ui(self, text):
        ui = UncleTUI.__new__(UncleTUI)
        ui.partial = text
        ui.prompt_kind = ''
        ui.prompt_seen = 0
        return ui

    def detect(self, ui):
        for _ in range(3):
            ui._detect_prompt()

    def test_unicode_default_edit_and_send(self):
        ui = self.ui('PR title [default: Fix café 日本語]: ')
        self.detect(ui)
        self.assertEqual(ui.prompt_kind, 'input')
        self.assertEqual(ui.prompt_buf, 'Fix café 日本語')
        ui.proc = Mock()
        ui.proc.poll.return_value = None
        ui.prompt_buf += '!'
        ui._send_raw(ui.prompt_buf)
        ui.proc.stdin.write.assert_called_once_with('Fix café 日本語!\n'.encode())

    def test_chunked_default_waits_for_terminator(self):
        ui = self.ui('PR title [default: Fix café')
        self.detect(ui)
        self.assertEqual(ui.prompt_kind, '')
        ui.partial += ' 日本語]: '
        self.detect(ui)
        self.assertEqual(ui.prompt_buf, 'Fix café 日本語')

    def test_every_chunk_boundary(self):
        prompt = 'PR title [default: Unicode café]: '
        for end in range(1, len(prompt) - 1):
            ui = self.ui(prompt[:end])
            self.detect(ui)
            self.assertEqual(ui.prompt_kind, '', prompt[:end])
            ui.partial = prompt
            self.detect(ui)
            self.assertEqual(ui.prompt_buf, 'Unicode café')

    def test_confirmation_words_in_title_remain_text(self):
        ui = self.ui('PR title [default: Fix [y/n] prompt]: ')
        self.detect(ui)
        self.assertEqual(ui.prompt_kind, 'input')
        self.assertEqual(ui.prompt_buf, 'Fix [y/n] prompt')

    def test_generic_prompts_unchanged(self):
        for text, kind in [('Work summary: ', 'input'), ('Proceed? [y/n]: ', 'confirm'),
                           ('Press ENTER after reviewing...', 'enter'),
                           ('Audit finding F-1 [s] Skip: ', 'audit')]:
            with self.subTest(text=text):
                ui = self.ui(text)
                self.detect(ui)
                self.assertEqual(ui.prompt_kind, kind)
                self.assertEqual(ui.prompt_buf, '')


if __name__ == '__main__':
    unittest.main()
