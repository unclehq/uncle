#!/usr/bin/env python3
"""PR defaults use the existing text-input protocol and preserve other prompts."""
from pathlib import Path
import sys
import json
import subprocess
import unittest
from unittest.mock import Mock, patch

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

    def signing(self):
        command = "git add -A && git commit -S -m 'café 日本語 [y/n] Return here and press ENTER (OK) when finished: '\n"
        return command, 'Commit signing needs your help. ' + json.dumps(command) + ' Return here and press ENTER (OK) when finished: '

    def test_signing_chunks_copy_and_keys(self):
        command, prompt = self.signing()
        for end in range(1, len(prompt.rstrip())):
            ui = self.ui(prompt[:end])
            self.detect(ui)
            self.assertEqual(ui.prompt_kind, '', prompt[:end])
        ui = self.ui(prompt)
        self.detect(ui)
        self.assertEqual(ui.signing_command, command)
        self.assertEqual(ui.prompt_kind, 'enter')
        ui.state = 'running'
        ui.answer_prompt = Mock()
        ui.stop_workflow = Mock()
        with patch('uncle_tui.sys.platform', 'darwin'), patch('uncle_tui.shutil.which', return_value='/usr/bin/pbcopy'), patch('uncle_tui.subprocess.run') as run:
            ui.handle_key(ord('c'))
            run.assert_called_once_with(['/usr/bin/pbcopy'], input=command.encode('utf-8'), stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, timeout=2, check=True)
        ui.answer_prompt.assert_not_called()
        self.assertEqual(ui.prompt_kind, 'enter')
        ui.handle_key(10)
        ui.answer_prompt.assert_called_once_with('')
        ui.handle_key(27)
        ui.stop_workflow.assert_called_once()

    def test_clipboard_backends_and_failures(self):
        command, prompt = self.signing()
        for env, available, expected in [({'WAYLAND_DISPLAY': 'wayland-0'}, ['wl-copy'], ['wl-copy']), ({'DISPLAY': ':0'}, ['xclip', 'xsel'], ['xclip', '-selection', 'clipboard']), ({'DISPLAY': ':0'}, ['xsel'], ['xsel', '--clipboard', '--input']), ({}, [], None)]:
            for error in (None, OSError('failed'), subprocess.TimeoutExpired('copy', 2), subprocess.CalledProcessError(1, 'copy')):
                ui = self.ui(prompt)
                self.detect(ui)
                with patch('uncle_tui.sys.platform', 'linux'), patch.dict('os.environ', env, clear=True), patch('uncle_tui.shutil.which', side_effect=lambda name: name if name in available else None), patch('uncle_tui.subprocess.run', side_effect=error) as run:
                    ui._copy_signing_command()
                self.assertEqual(ui.prompt_kind, 'enter')
                if expected:
                    self.assertEqual(run.call_args.args[0], expected)
                else:
                    run.assert_not_called()
                self.assertIn('failed' if error or not expected else 'Copied', ui.signing_copy_status)

    def test_signing_render_bounds(self):
        command, prompt = self.signing()
        for height, width in ((24, 80), (18, 36)):
            ui = self.ui(prompt)
            self.detect(ui)
            ui.color = dict(title=0, accent=0, sel=0, cursor=0)
            ui.stdscr = Mock()
            ui._draw_modal(height, width)
            for call in ui.stdscr.addnstr.call_args_list:
                row, col, text, count = call.args[:4]
                self.assertTrue(0 <= row < height, call)
                self.assertTrue(0 <= col < width, call)
                self.assertLessEqual(col + count, width, call)
            drawn = ' '.join(call.args[2] for call in ui.stdscr.addnstr.call_args_list)
            self.assertIn('[c] Copy command', drawn)
            self.assertEqual(ui.signing_command, command)

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
                           ('Commit signing needs your help. Commit in another terminal and press ENTER (OK) when finished: ', 'enter'),
                           ('Audit finding F-1 [s] Skip: ', 'audit')]:
            with self.subTest(text=text):
                ui = self.ui(text)
                self.detect(ui)
                self.assertEqual(ui.prompt_kind, kind)
                self.assertEqual(ui.prompt_buf, '')


if __name__ == '__main__':
    unittest.main()
