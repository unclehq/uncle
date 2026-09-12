#!/usr/bin/env python3
"""Chat reference and seed safety regressions, without native credentials."""
import os
import queue
import subprocess
import time
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lib"))
from chat import Conversation, References, Seed, sanitize
from unittest.mock import Mock, patch
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import uncle_tui as tui


class ChatSafetyTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.refs = References(self.root)

    def test_picker_and_suggestions_share_policy(self):
        (self.root / "a file.txt").write_text("Useful context")
        (self.root / ".env.local").write_text("SECRET=canary")
        (self.root / "key.pem").write_text("private")
        (self.root / "link").symlink_to("a file.txt")
        (self.root / "binary").write_bytes(b"a\0b")
        self.assertEqual(self.refs.suggestions(""), ["a file.txt"])
        self.assertEqual(self.refs.reference("a file.txt"), '@"a file.txt"')
        self.assertEqual(self.refs.expand('@"a file.txt"'), '\n[file a file.txt]\nUseful context\n')

    def test_provider_credentials_excluded_from_picker_and_payload(self):
        for name in ('self-hosted-keys.json', '.uncle-self-hosted-keys.json'):
            (self.root / name).write_text('{"baseline": "PROVIDER_CANARY"}')
            with self.subTest(name=name):
                self.assertNotIn(name, self.refs.suggestions(''))
                with self.assertRaisesRegex(ValueError, 'Excluded'):
                    self.refs.expand('@' + name)

    def test_rejects_escape_and_symlink_race(self):
        for name in ("../outside", "/etc/passwd", ".env", "missing"):
            with self.assertRaises(ValueError):
                self.refs.read(name)
        file = self.root / "ok"
        file.write_text("safe")
        self.assertEqual(self.refs.suggestions("ok"), ["ok"])
        file.unlink()
        file.symlink_to("/etc/passwd")
        with self.assertRaises(ValueError):
            self.refs.expand("@ok")

    def test_redacts_secret_assignments_and_private_keys(self):
        raw = 'api_key = "CANARY"\nAuthorization: Bearer CANARY2\n-----BEGIN PRIVATE KEY-----\nCANARY3\n-----END PRIVATE KEY-----'
        self.assertNotIn("CANARY", sanitize(raw))

    def test_redacted_transcript_also_obeys_limit(self):
        conversation = Conversation(self.root)
        with patch('chat.TRANSCRIPT_LIMIT', 10):
            with self.assertRaisesRegex(ValueError, 'limit'):
                conversation.send('api_key=x')
        self.assertEqual(conversation.messages, [])

    def test_reference_limit(self):
        (self.root / "large").write_text("x" * (256 * 1024 + 1))
        with self.assertRaisesRegex(ValueError, "limit"):
            self.refs.expand("@large")

    def test_seed_retry_preserves_identity_and_content(self):
        seed = Seed(self.root, "change")
        seed.commit("## Summary\nAdd chat\n")
        first = (self.root / "CHANGE_REQUEST.md").stat()
        seed.verify()
        self.assertEqual(first.st_ino, (self.root / "CHANGE_REQUEST.md").stat().st_ino)
        (self.root / "CHANGE_REQUEST.md").write_text("changed")
        with self.assertRaises(ValueError):
            seed.verify()

    def test_seed_collisions_and_empty_summary(self):
        with self.assertRaises(ValueError):
            Seed(self.root, "app").commit("## Summary\n\n## Goals\nSomething")
        target = self.root / "REQUIREMENTS.md"
        target.symlink_to("absent")
        with self.assertRaises((ValueError, FileExistsError)):
            Seed(self.root, "app").commit("## Summary\nBuild chat\n")
        self.assertTrue(target.is_symlink())

    def test_seed_retry_rejects_replacement_and_symlink(self):
        for replacement in ("file", "symlink"):
            with self.subTest(replacement=replacement):
                target = self.root / "CHANGE_REQUEST.md"
                target.unlink(missing_ok=True)
                seed = Seed(self.root, "change")
                content = "## Summary\nChat\n"
                seed.commit(content)
                target.rename(self.root / "old")
                if replacement == "file":
                    target.write_text(content)
                else:
                    target.symlink_to("old")
                with self.assertRaises(ValueError):
                    seed.verify()
                (self.root / "old").unlink()



APP_BRIEF = """## Summary
Build a task list.
## Problem
Tasks are lost between sessions.
## Scope
Create and complete local tasks.
## Non-goals
Sharing tasks.
## Functional requirements
Users can create tasks and mark them complete.
## User-visible behavior
Completed tasks display a check mark.
## Domain rules and invariants
Each task has a unique ID.
## Data and state
Tasks persist locally between sessions.
## Interfaces
A terminal menu lists tasks.
## Constraints
Use Python and the standard library.
## Failure behavior
Report corrupt task data without overwriting it.
## Verification
Test task creation and completion in a temporary directory.
## Definition of done
Tasks survive a restart and completion is visible.
## Open questions
None.
"""


CHANGE_BRIEF = """## Change Type
Feature
## Summary
Add task completion.
## Motivation
Users need to track completed work.
## Observed Current Behavior
Tasks remain on the active list.
## Desired Behavior
Users can mark tasks complete.
## Reproduction
Not applicable.
## Constraints
Preserve stored tasks.
## Known Relevant Files
The task list module.
## Out of Scope
Sharing tasks.
## Success Criteria
Completing a task survives restart.
"""


class ChatInteractionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        root = patch.object(tui, '_project_root', return_value=str(self.root))
        root.start()
        self.addCleanup(root.stop)
        self.ui = tui.UncleTUI.__new__(tui.UncleTUI)
        self.ui.state = 'menu'
        self.ui.sel = len(tui.WORKFLOWS) + 2
        self.ui.proc = None
        self.ui.output = []
        self.ui.prompt_kind = ''
        self.ui.prompt_text = ''
        self.ui.prompt_buf = ''
        self.ui.answer_prompt = Mock()
        self.ui._confirm()

    def type(self, text):
        for char in text:
            self.ui.handle_key(ord(char))

    def test_menu_and_text_isolation(self):
        self.assertEqual(self.ui.menu_items()[:5],
                         [w[0] for w in tui.WORKFLOWS] + ['Configure', 'Quit'])
        self.assertEqual(self.ui.state, 'chat')
        self.type('Design a task list')
        self.ui.handle_key(10)
        self.assertEqual(self.ui.chat.messages, ['Design a task list'])
        self.ui.answer_prompt.assert_not_called()

    def test_suggestions_and_picker_insert_quoted_reference(self):
        (self.root / 'a file.txt').write_text('context')
        (self.root / '.env').write_text('TOKEN=canary')
        self.type('@a')
        self.assertEqual(self.ui.chat_choices, ['a file.txt'])
        self.ui.handle_key(10)
        self.assertEqual(self.ui.chat_composer, '@"a file.txt" ')
        self.ui.chat_composer = ''
        self.ui.handle_key(16)
        self.assertEqual(self.ui.chat_choices, ['a file.txt'])
        self.ui.handle_key(10)
        self.assertEqual(self.ui.chat_composer, '@"a file.txt" ')
        self.ui.handle_key(10)
        self.assertNotIn('context', self.ui.chat.messages[0])
        self.assertIn('context', self.ui.chat.payload())

    def test_gate_focus_is_explicit(self):
        self.ui.state = 'running'
        self.ui.prompt_kind = 'confirm'
        self.type('y')
        self.ui.handle_key(10)
        self.ui.answer_prompt.assert_not_called()
        self.ui.handle_key(9)
        self.ui.handle_key(ord('y'))
        self.ui.answer_prompt.assert_called_once_with('y')

    def test_incomplete_preview_cannot_create_seed(self):
        self.ui.maybe_reload = Mock()
        self.ui.chat.preview = '## Summary\nBuild a task list\n'
        self.ui.chat.kind = 'app'
        self.ui.start_workflow = Mock()
        self.ui.start_chat_workflow()
        self.assertFalse((self.root / 'REQUIREMENTS.md').exists())
        self.ui.start_workflow.assert_not_called()
        self.assertIn('Problem', self.ui.chat_error)

    def test_app_and_change_preview_start_existing_drivers(self):
        self.ui.maybe_reload = Mock()
        self.ui.start_workflow = Mock()
        for kind, preview, filename, index in (
                ('app', APP_BRIEF, 'REQUIREMENTS.md', 0),
                ('change', CHANGE_BRIEF, 'CHANGE_REQUEST.md', 2)):
            self.ui.chat = Conversation(self.root)
            self.ui.chat.kind = kind
            self.ui.state = 'chat'
            self.ui.handle_key(tui.curses.KEY_F4)
            self.type(preview)
            self.ui.handle_key(tui.curses.KEY_F5)
            self.assertEqual((self.root / filename).read_text(), preview)
            self.assertEqual(self.ui.workflow_idx, index)
            self.assertEqual(self.ui.state, 'running')
        self.assertEqual(self.ui.start_workflow.call_count, 2)

    def test_retry_refuses_replacement_or_symlink_before_launch(self):
        self.ui.maybe_reload = Mock()
        self.ui.start_workflow = Mock(side_effect=OSError('launch failed'))
        for kind in ('replacement', 'symlink'):
            with tempfile.TemporaryDirectory(dir=self.root) as directory:
                self.ui.chat = Conversation(directory)
                self.ui.chat.kind = 'app'
                self.ui.chat.preview = APP_BRIEF
                self.ui.state = 'chat'
                self.ui.start_chat_workflow()
                target = Path(directory) / 'REQUIREMENTS.md'
                target.rename(Path(directory) / 'old')
                if kind == 'replacement':
                    target.write_text(APP_BRIEF)
                else:
                    target.symlink_to('old')
                count = self.ui.start_workflow.call_count
                self.ui.start_chat_workflow()
                self.assertEqual(self.ui.start_workflow.call_count, count)
                self.assertIn('refused', self.ui.chat_error)

    def test_git_subdirectory_defaults_to_change(self):
        (self.root / '.git').mkdir()
        child = self.root / 'child'
        child.mkdir()
        self.assertEqual(Conversation(child).kind, 'change')

    def test_launch_retry_and_duplicate_start(self):
        self.ui.chat.preview = APP_BRIEF
        self.ui.chat.kind = 'app'
        self.ui.maybe_reload = Mock()
        self.ui.start_workflow = Mock(side_effect=[OSError('launch failed'), None])
        self.ui.start_chat_workflow()
        target = self.root / 'REQUIREMENTS.md'
        identity = target.stat().st_ino
        self.assertEqual(self.ui.state, 'chat')
        self.ui.start_chat_workflow()
        self.assertEqual(target.stat().st_ino, identity)
        self.assertEqual(self.ui.state, 'running')
        self.ui.start_chat_workflow()
        self.assertEqual(self.ui.start_workflow.call_count, 2)

    def test_launch_retry_refuses_seed_mutation(self):
        self.ui.chat.preview = APP_BRIEF
        self.ui.chat.kind = 'app'
        self.ui.maybe_reload = Mock()
        self.ui.start_workflow = Mock(side_effect=OSError('launch failed'))
        self.ui.start_chat_workflow()
        (self.root / 'REQUIREMENTS.md').write_text('changed')
        self.ui.start_chat_workflow()
        self.assertEqual(self.ui.start_workflow.call_count, 1)
        self.assertIn('changed', self.ui.chat_error)

    def test_real_driver_stdin_after_popen_retry(self):
        self.ui.chat.kind = 'app'
        self.ui.chat.preview = APP_BRIEF
        self.ui.out_q = queue.Queue()
        self.ui.stage_env = Mock(return_value={})
        self.ui._restore_session_totals = Mock()
        self.ui._begin_title = Mock()
        self.ui._end_title = Mock()
        self.ui.maybe_reload = Mock()
        self.ui.cmd_for = Mock(return_value=[sys.executable, '-u', '-c',
            "from pathlib import Path; import sys; "
            "assert Path('REQUIREMENTS.md').read_text().startswith('## Summary'); "
            "print('stage output\\n' * 10000, flush=True); "
            "print('ANSWER=' + sys.stdin.readline().strip(), flush=True)"])
        launch = subprocess.Popen
        attempts = []

        def popen(*args, **kwargs):
            attempts.append((self.root / 'REQUIREMENTS.md').stat().st_ino)
            if len(attempts) == 1:
                raise OSError('first launch failed')
            return launch(*args, **kwargs)

        with patch.object(tui.subprocess, 'Popen', side_effect=popen):
            self.ui.start_chat_workflow()
            self.assertIsNone(self.ui.status_path)
            self.ui.start_chat_workflow()
        self.assertEqual(attempts[0], attempts[1])
        process = self.ui.proc
        try:
            self.type('chat must not reach the driver')
            self.ui.handle_key(10)
            self.assertIsNone(process.poll())
            self.ui.prompt_kind = 'confirm'
            self.ui.answer_prompt = tui.UncleTUI.answer_prompt.__get__(self.ui)
            self.ui.handle_key(9)
            self.ui.handle_key(ord('y'))
            self.assertEqual(process.wait(timeout=10), 0)
            chunks = []
            while True:
                chunk = self.ui.out_q.get(timeout=5)
                if chunk is None:
                    break
                chunks.append(chunk)
            output = ''.join(chunks)
            self.assertIn('ANSWER=y', output)
            self.assertNotIn('chat must not', output)
        finally:
            if process.poll() is None:
                process.kill()
                process.wait()
            process.stdin.close()
            process.stdout.close()
            Path(self.ui.status_path).unlink(missing_ok=True)

    def test_empty_invalid_and_failed_derivation_retain_draft(self):
        self.ui.handle_key(10)
        self.assertIn('message', self.ui.chat_error)
        self.type('@missing')
        self.ui.handle_key(10)
        self.assertEqual(self.ui.chat_composer, '@missing')
        self.assertFalse(self.ui.chat.messages)
        self.ui.chat_composer = 'Build a task list'
        self.ui.handle_key(10)
        self.ui.handle_key(tui.curses.KEY_F3)
        self.assertIn('isolation', self.ui.chat_error)
        self.assertEqual(self.ui.chat.messages, ['Build a task list'])
        self.assertFalse(list(self.root.iterdir()))

    def test_picker_rechecks_file_after_selection(self):
        file = self.root / 'context'
        file.write_text('safe')
        self.ui.handle_key(16)
        file.unlink()
        file.symlink_to('/etc/passwd')
        self.ui.handle_key(10)
        self.assertEqual(self.ui.chat_composer, '')
        self.assertIn('unsafe', self.ui.chat_error)

    @unittest.skipUnless(os.name == 'posix', 'PTY rendering requires POSIX')
    def test_real_curses_resize_under_load(self):
        import pty
        import select
        master, slave = pty.openpty()
        process = subprocess.Popen([sys.executable, '-B', __file__, '--terminal-case'],
                                   stdin=slave, stdout=slave, stderr=slave,
                                   env=dict(os.environ, TERM='xterm-256color',
                                            UNCLE_PROJECT_ROOT=str(self.root)))
        os.close(slave)
        output = bytearray()
        deadline = time.monotonic() + 10
        try:
            while time.monotonic() < deadline:
                ready, _, _ = select.select([master], [], [], 0.1)
                if ready:
                    try:
                        chunk = os.read(master, 65536)
                    except OSError:
                        break
                    if not chunk:
                        break
                    output.extend(chunk)
                elif process.poll() is not None:
                    break
            self.assertEqual(process.wait(timeout=1), 0, output.decode(errors='replace'))
            self.assertIn(b'TERMINAL PASS', output)
        finally:
            if process.poll() is None:
                process.kill()
                process.wait()
            os.close(master)

    def test_loaded_layouts_keep_composer_response_and_gate(self):
        self.ui.state = 'running'
        self.ui.output = ['stage output %d' % i for i in range(10000)]
        self.ui.prompt_kind = 'confirm'
        self.ui.prompt_text = 'Approve brief?'
        self.type('Keep the task list accessible')
        self.ui.handle_key(10)
        for h, w in ((30, 120), (24, 80), (12, 40)):
            screen = Mock()
            screen.getmaxyx.return_value = (h, w)
            self.ui.stdscr = screen
            self.ui.draw()
            lines = [call.args[2] for call in screen.addnstr.call_args_list]
            self.assertTrue(any('Keep the task list' in line for line in lines))
            self.assertTrue(any('Message>' in line for line in lines))
            self.assertTrue(any('Approve brief?' in line for line in lines))
            self.assertTrue(any('Tab' in line for line in lines))
            for call in screen.addnstr.call_args_list:
                y, x, text, width = call.args[:4]
                self.assertTrue(0 <= y < h and 0 <= x < w)
                self.assertLessEqual(x + width, w)


def terminal_case(screen):
    ui = tui.UncleTUI.__new__(tui.UncleTUI)
    ui.proc = None
    ui.open_chat()
    ui.stdscr = screen
    ui.state = 'running'
    ui.prompt_kind = 'confirm'
    ui.prompt_text = 'Approve brief?'
    ui.prompt_buf = ''
    answers = []
    ui.answer_prompt = answers.append
    ui.chat.send('response stays visible')
    for h, w in ((30, 120), (24, 80), (12, 40)):
        tui.curses.resizeterm(h, w)
        for frame in range(5):
            ui.output = ['stage output %d' % i for i in range(10000 + frame)]
            ui.draw()
        rows = [screen.instr(y, 0, w - 1).decode() for y in range(h)]
        assert any('response stays visible' in row for row in rows), rows
        assert 'Message>' in rows[h - 3], rows
        assert 'Approve brief?' in rows[h - 2], rows
        assert 'Tab chat/gate' in rows[h - 1], rows
        before = len(answers)
        tui.curses.ungetch(ord('x'))
        ui.handle_key(screen.getch())
        assert len(answers) == before
        ui.handle_key(9)
        tui.curses.ungetch(ord('y'))
        ui.handle_key(screen.getch())
        assert answers[-1] == 'y'
        ui.handle_key(9)
    ui.handle_key(3)
    assert ui.state == 'quit'


if __name__ == "__main__":
    if '--terminal-case' in sys.argv:
        tui.curses.wrapper(terminal_case)
        print('TERMINAL PASS')
    else:
        unittest.main()
