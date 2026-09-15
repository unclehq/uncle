#!/usr/bin/env python3
"""Chat reference and seed safety regressions, without native credentials."""
import os
import queue
import subprocess
import time
from pathlib import Path
import sys
import tempfile
import textwrap
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
        self.ui.open_chat()
        self.ui.send_home_chat = self.ui.chat.send

    def type(self, text):
        for char in text:
            self.ui.handle_key(ord(char))

    def test_homepage_shows_chat_without_open_action(self):
        del self.ui.chat
        self.ui.chat_open = False
        self.ui.state = 'menu'
        self.ui.sel = 0
        self.ui.color = dict(title=0, sel=0, accent=0)
        self.ui._draw_status = Mock()
        for h, w in ((30, 120), (24, 80), (12, 40)):
            screen = Mock()
            screen.getmaxyx.return_value = (h, w)
            self.ui.stdscr = screen
            self.ui.draw()
            lines = [call.args[2] for call in screen.addnstr.call_args_list]
            self.assertTrue(any('Describe' in line for line in lines))
            self.assertTrue(any('What can' in line for line in lines))
            self.assertTrue(any('Ctrl-P' in line for line in lines))
            for index, item in enumerate(self.ui.menu_items(), 1):
                self.assertTrue(any(item in call.args[2]
                                    for call in screen.addnstr.call_args_list))
            self.ui._draw_status.assert_not_called()
            for call in screen.addnstr.call_args_list:
                y, x, text, width = call.args[:4]
                self.assertTrue(0 <= y < h and 0 <= x < w)
                self.assertLessEqual(x + width, w)
            self.assertEqual(self.ui.state, 'menu')
        self.assertTrue(self.ui.chat_open)

    def test_slash_commands_in_chat_and_running_panel(self):
        for state in ('chat', 'running'):
            self.ui.state = state
            self.ui.chat_focus = 'chat'
            self.ui.chat_composer = '/'
            screen = Mock()
            screen.getmaxyx.return_value = (24, 80)
            self.ui.stdscr = screen
            self.ui._draw_file_picker(15, 0, 78)
            rows = [call.args[2] for call in screen.addnstr.call_args_list]
            self.assertTrue(any('Commands' in row for row in rows))
            self.assertTrue(any('/configure' in row for row in rows))
            self.ui.chat_composer = '/file'
            self.ui.handle_key(10)
            self.assertTrue(self.ui.chat_picker)
            self.assertEqual(self.ui.state, state)
            self.ui.handle_key(27)
            self.ui.chat_composer = '/settings'
            self.ui.handle_key(10)
            self.assertEqual(self.ui.state, 'config')
        self.ui.state = 'running'
        self.ui._run = Mock()
        self.ui.chat_composer = '/issue 123'
        self.ui.handle_key(10)
        self.ui._run.assert_not_called()
        self.assertIn('already active', self.ui.chat_error)
        self.ui.state = 'chat'
        self.ui.chat_composer = '/issue 123'
        self.ui.handle_key(10)
        self.ui._run.assert_called_once_with()
        self.ui.state = 'chat'
        self.ui.chat_composer = '/sett'
        self.ui.handle_key(10)
        self.assertEqual(self.ui.state, 'config')
        self.ui.state = 'chat'
        self.ui.chat_composer = '/quit'
        self.ui.handle_key(10)
        self.assertEqual(self.ui.state, 'quit')
        self.assertFalse(self.ui.chat.messages)

    def test_requested_slash_commands(self):
        for command in ('/configure', '/settings'):
            self.ui.state = 'menu'
            self.ui.chat_composer = command
            self.ui.handle_key(10)
            self.assertEqual(self.ui.state, 'config')
        self.ui.state = 'menu'
        self.ui.chat_composer = '/file'
        self.ui.handle_key(10)
        self.assertTrue(self.ui.chat_picker)
        self.ui.handle_key(27)
        self.ui._run = Mock()
        for command, index, filename in (('/requirements', 0, 'REQUIREMENTS.md'),
                                         ('/change', 2, 'CHANGE_REQUEST.md')):
            self.ui.state = 'menu'
            self.ui.chat_composer = command
            self.ui.handle_key(10)
            self.assertEqual(self.ui.state, 'notice')
            self.assertIn(filename, self.ui.notice_lines[0])
            self.ui._run.assert_not_called()
            (self.root / filename).write_text('Build input')
            self.ui.state = 'menu'
            self.ui.chat_composer = command
            self.ui.handle_key(10)
            self.assertEqual(self.ui.workflow_idx, index)
            self.ui._run.assert_called_once_with()
            self.ui._run.reset_mock()
        for argument in ('123', '#456'):
            self.ui.state = 'menu'
            self.ui.chat_composer = '/issue ' + argument
            self.ui.handle_key(10)
            self.assertEqual(self.ui.issue, argument.lstrip('#'))
            self.assertEqual(self.ui.issue_mode, '')
            self.assertEqual(self.ui.workflow_idx, 1)
            self.ui._run.assert_called_once_with()
            self.ui._run.reset_mock()
        for command in ('/issue nope', '/issue 0', '/issue 1 extra', '/requirements extra'):
            self.ui.state = 'menu'
            self.ui.chat_composer = command
            self.ui.handle_key(10)
            self.ui._run.assert_not_called()
            self.assertEqual(self.ui.chat_composer, command)
            self.assertTrue(self.ui.chat_error)
        self.ui.chat_composer = '/quit'
        self.ui.handle_key(10)
        self.assertEqual(self.ui.state, 'quit')

    def test_response_preserves_homepage_menu_position(self):
        self.ui.state = 'menu'
        for h, w in ((40, 140), (30, 120), (24, 80), (12, 40)):
            screen = Mock()
            screen.getmaxyx.return_value = (h, w)
            self.ui.stdscr = screen
            positions = []
            for history in ([], [('user', 'Hello'), ('assistant', 'A response ' * 100)]):
                self.ui.home_history = history
                screen.reset_mock()
                self.ui.draw()
                positions.append([(call.args[0], call.args[1])
                                  for call in screen.addnstr.call_args_list
                                  if call.args[2].lstrip('› ') in self.ui.menu_items()])
            self.assertEqual(positions[0], positions[1])
            self.assertEqual(len(positions[0]), len(self.ui.menu_items()))

    def test_homepage_command_menu_and_slash_commands(self):
        self.ui.state = 'menu'
        self.ui.sel = 0
        self.ui.handle_key(16)
        self.assertTrue(self.ui.home_menu_open)
        self.ui.handle_key(tui.curses.KEY_DOWN)
        self.assertEqual(self.ui.sel, 1)
        self.ui.handle_key(27)
        self.assertFalse(self.ui.home_menu_open)
        self.assertEqual(self.ui.chat_focus, 'chat')
        self.type('/configure')
        self.ui.handle_key(10)
        self.assertEqual(self.ui.state, 'config')
        self.ui.state = 'menu'
        (self.root / 'notes.txt').write_text('notes')
        self.type('/files')
        self.ui.handle_key(10)
        self.assertTrue(self.ui.chat_picker)
        self.assertIn('notes.txt', self.ui.chat_choices)

    def test_running_chat_is_bottom_left_full_width(self):
        self.ui.state = 'running'
        self.ui.color = dict(title=0, sel=0, accent=0)
        self.ui._draw_running = Mock()
        self.ui._draw_session_stats = Mock()
        self.ui._draw_chat_panel = Mock()
        for h, w in ((40, 160), (30, 120), (24, 80), (12, 40)):
            for stage in ('requirements', 'implementation', 'final-audit'):
                self.ui.status_stage = stage
                self.ui.chat_open = False
                self.ui.stdscr = Mock()
                self.ui.stdscr.getmaxyx.return_value = (h, w)
                self.ui.draw()
                panel = min(34, w // 3) if w >= 60 else 0
                chat_height = min(6, max(0, h - 3))
                self.ui._draw_chat_panel.assert_called_with(
                    h - chat_height, h, 0, w - panel)
                self.ui._draw_running.assert_called_with(
                    h - chat_height, w - panel)
                self.assertTrue(self.ui.chat_open)

    def test_running_preserves_dialog_and_statistics_renderer(self):
        self.ui.state = 'running'
        self.ui.color = dict(title=0, sel=0, accent=0)
        self.ui.stdscr = Mock()
        self.ui.stdscr.getmaxyx.return_value = (30, 120)
        self.ui._draw_running = Mock()
        self.ui._draw_session_stats = Mock()
        self.ui.draw()
        self.ui._draw_running.assert_called_once_with(24, 86)
        self.ui._draw_session_stats.assert_called_once_with(30, 120, 34)

    def test_homepage_focus_and_configuration_preserve_draft(self):
        self.ui.state = 'menu'
        self.ui.chat_focus = 'menu'
        self.ui.sel = 0
        self.ui.handle_key(9)
        self.type('Build a homepage')
        self.assertEqual(self.ui.chat_composer, 'Build a homepage')
        self.ui.handle_key(9)
        self.ui.sel = len(tui.WORKFLOWS)
        self.ui.handle_key(10)
        self.assertEqual(self.ui.state, 'config')
        self.ui.state = 'menu'
        self.assertEqual(self.ui.chat_composer, 'Build a homepage')
        self.ui.handle_key(10)
        self.assertEqual(self.ui.chat.messages, ['Build a homepage'])

    def test_menu_and_text_isolation(self):
        self.assertEqual(self.ui.menu_items()[:5],
                         [w[0] for w in tui.WORKFLOWS] + ['Configure', 'Quit'])
        self.assertEqual(self.ui.state, 'chat')
        self.type('Design a task list')
        self.ui.handle_key(10)
        self.assertEqual(self.ui.chat.messages, ['Design a task list'])
        self.ui.answer_prompt.assert_not_called()

    def test_implement_issue_selects_auto_and_lands_on_build_page(self):
        del self.ui.send_home_chat  # Exercise the real homepage send path.
        self.ui.misc = {}
        self.ui.stage_runners = {}
        self.ui.stage_efforts = {}
        self.ui.stage_models = {}
        self.ui.stage_networks = {}
        self.ui.stage_billings = {}
        self.ui.stage_base_urls = {}
        self.ui.stage_api_keys = {}
        self.ui.maybe_reload = Mock(return_value=False)
        self.ui.start_workflow = Mock()
        self.ui.state = 'menu'
        self.ui.chat_focus = 'chat'
        config = patch.object(tui, 'CONFIG_PATH', str(self.root / 'config'))
        config.start()
        self.addCleanup(config.stop)
        self.type('implement issue https://github.com/unclehq/uncle/issues/44')
        self.ui.handle_key(10)
        self.assertEqual(self.ui.misc['auto_mode'], 'true')
        self.assertIn('misc.auto_mode true', (self.root / 'config').read_text())
        self.assertEqual(self.ui.workflow_idx, 1)
        self.assertEqual(self.ui.issue, 'https://github.com/unclehq/uncle/issues/44')
        self.assertEqual(self.ui.issue_mode, '')
        self.assertEqual(self.ui.state, 'running')
        self.ui.start_workflow.assert_called_once()
        cmd = self.ui.cmd_for()
        self.assertIn('https://github.com/unclehq/uncle/issues/44', cmd)
        self.assertIn('--unattended', cmd)

    def test_picker_shows_and_enters_all_directories(self):
        for name in ('.git', '.ssh', '.uncle', 'visible'):
            (self.root / name / 'nested').mkdir(parents=True)
        (self.root / 'linked').symlink_to(self.root / 'visible', target_is_directory=True)
        for index in range(205):
            (self.root / ('dir%03d' % index)).mkdir()
        choices = self.ui.chat.refs.browse('')
        for name in ('.git/', '.ssh/', '.uncle/', 'visible/', 'linked/', 'dir204/'):
            self.assertIn(name, choices)
        self.assertEqual(self.ui.chat.refs.browse('.ssh/'), ['.ssh/nested/'])
        self.assertEqual(self.ui.chat.refs.browse('linked/'), ['linked/nested/'])

    def test_home_and_absolute_paths_are_explicit_chat_attachments(self):
        outside = self.root / 'home'
        outside.mkdir()
        (outside / 'notes.txt').write_text('selected context')
        (outside / '.env').write_text('secret')
        with patch('chat.Path.home', return_value=outside):
            for prefix in ('~', '~/', str(outside) + '/'):
                self.ui.chat_composer = ''
                self.ui.chat_picker = False
                self.type('@' + prefix)
                expected = ('~/' if prefix.startswith('~') else prefix) + 'notes.txt'
                self.assertIn(expected, self.ui.chat_choices)
                self.assertFalse(any(name.endswith('.env') for name in self.ui.chat_choices))
                self.ui.chat_pick = self.ui.chat_choices.index(expected)
                self.ui.handle_key(9)
                self.assertEqual(self.ui.chat_composer, '@' + expected + ' ')
                self.assertIn('selected context', self.ui.chat.refs.expand(self.ui.chat_composer))

    def test_parent_directory_completion_and_attachment(self):
        project = self.root / 'parent' / 'project'
        project.mkdir(parents=True)
        (project.parent / 'near.txt').write_text('parent context')
        (self.root / 'far.txt').write_text('grandparent context')
        (self.root / '.env').write_text('secret')
        self.ui.chat.refs.root = project
        for prefix, filename, contents in (('../', 'near.txt', 'parent context'),
                                            ('../../', 'far.txt', 'grandparent context')):
            self.ui.chat_composer = ''
            self.ui.chat_picker = False
            self.type('@' + prefix)
            self.assertIn(prefix + filename, self.ui.chat_choices)
            self.assertNotIn(prefix + '.env', self.ui.chat_choices)
            self.type(filename[:3])
            self.ui.handle_key(9)
            self.assertEqual(self.ui.chat_composer, '@' + prefix + filename + ' ')
            self.assertIn(contents, self.ui.chat.refs.expand(self.ui.chat_composer))
            self.assertEqual(self.ui.chat_focus, 'chat')

    def test_tab_completes_directories_and_files_without_changing_focus(self):
        folder = self.root / 'pack aging'
        folder.mkdir()
        (folder / 'README.md').write_text('context')
        for state in ('menu', 'chat', 'running'):
            self.ui.state = state
            self.ui.chat_composer = ''
            self.ui.chat_picker = False
            self.ui.chat_focus = 'chat'
            self.type('foo @pack')
            self.assertEqual(self.ui.chat_choices, ['pack aging/'])
            self.ui.handle_key(9)
            self.assertEqual(self.ui.chat_composer, 'foo @"pack aging/')
            self.assertEqual(self.ui.chat_choices, ['pack aging/README.md'])
            self.type('READ')
            self.ui.handle_key(9)
            self.assertEqual(self.ui.chat_composer, 'foo @"pack aging/README.md" ')
            self.assertFalse(self.ui.chat_picker)
            self.assertEqual(self.ui.chat_focus, 'chat')
            self.assertFalse(self.ui.chat.messages)

    def test_at_picker_visible_filters_scrolls_and_closes(self):
        for i in range(12):
            (self.root / ('file%02d.txt' % i)).write_text('context')
        self.type('@')
        self.assertTrue(self.ui.chat_picker)
        self.assertEqual(len(self.ui.chat_choices), 12)
        screen = Mock()
        screen.getmaxyx.return_value = (24, 80)
        self.ui.stdscr = screen
        for _ in range(10):
            self.ui.handle_key(tui.curses.KEY_DOWN)
        self.ui._draw_file_picker(15, 2, 70)
        rows = [call.args[2] for call in screen.addnstr.call_args_list]
        self.assertTrue(any('Files' in row for row in rows))
        self.assertTrue(any('› file10.txt' in row for row in rows))
        self.type('file11')
        self.assertEqual(self.ui.chat_choices, ['file11.txt'])
        self.ui.handle_key(10)
        self.assertEqual(self.ui.chat_composer, '@file11.txt ')
        self.assertFalse(self.ui.chat.messages)
        self.assertFalse(self.ui.chat_picker)
        self.type('@absent')
        self.ui.handle_key(10)
        self.assertIn('No matching files', self.ui.chat_error)
        self.ui.handle_key(27)
        self.assertFalse(self.ui.chat_picker)

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
        self.ui.handle_key(27)  # Dismiss the empty file picker.
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

    def test_new_build_dialog_takes_focus_and_preserves_chat_draft(self):
        self.ui.state = 'running'
        for prompt in ('Approve brief? [y/n]', 'Press ENTER to continue:',
                       'Retry, waive, or stop:', 'PR title [default: Example]:'):
            with self.subTest(prompt=prompt):
                self.ui.chat_focus = 'chat'
                self.ui.chat_composer = 'Unsent direction'
                self.ui.prompt_kind = ''
                self.ui.partial = prompt
                self.ui.prompt_seen = 2
                self.ui._detect_prompt()
                self.assertEqual(self.ui.chat_focus, 'gate')
                self.assertEqual(self.ui.chat_composer, 'Unsent direction')
                self.ui.chat_focus = 'chat'
                self.ui._detect_prompt()
                self.assertEqual(self.ui.chat_focus, 'chat')

    def test_closing_build_dialog_returns_focus_to_chat(self):
        self.ui.state = 'running'
        self.ui.chat_composer = 'Draft direction'
        self.ui.partial = 'Approve? '
        self.ui.output = []
        for exited in (False, True):
            self.ui.proc = Mock()
            self.ui.proc.poll.return_value = 0 if exited else None
            self.ui.prompt_kind = 'confirm'
            self.ui.chat_focus = 'gate'
            tui.UncleTUI.answer_prompt(self.ui, 'y')
            self.assertEqual(self.ui.prompt_kind, '')
            self.assertEqual(self.ui.chat_focus, 'chat')
            self.assertEqual(self.ui.chat_composer, 'Draft direction')
        self.ui.prompt_kind = 'support'
        self.ui.chat_focus = 'gate'
        self.ui.handle_key(10)
        self.assertEqual(self.ui.chat_focus, 'chat')
        self.ui.prompt_kind = 'input'
        self.ui.chat_focus = 'gate'
        self.ui.handle_key(27)
        self.assertEqual(self.ui.chat_focus, 'chat')

    def test_native_fragments_are_not_repeated_in_build_output(self):
        import json
        self.ui.state = 'running'
        self.ui.output = []
        self.ui.home_history = [('assistant (baseline)', 'I will run the baseline checks.')]
        for text in ('I', ' will', ' run', ' the baseline checks.'):
            self.ui._absorb_line(json.dumps({'type': 'assistant', 'uncle_chat_output': True,
                                            'message': {'content': [{'type': 'text', 'text': text}]}}))
        self.assertEqual(self.ui.output, [])
        self.assertEqual(self.ui._build_messages(),
                         ['Assistant (baseline): I will run the baseline checks.'])

    def test_composer_text_starts_after_prompt_without_padding(self):
        renderer_state(self.ui)
        self.ui.state = 'running'
        self.ui.chat_focus = 'chat'
        self.ui.chat_composer = ' ' * 70 + '\twhat day is it'
        self.ui.stdscr = Mock()
        self.ui.stdscr.getmaxyx.return_value = (40, 160)
        self.ui._draw_chat_composer(25, 39, 160, 25, 76)
        calls = self.ui.stdscr.addnstr.call_args_list
        entry = next(call for call in calls if call.args[2].startswith('› '))
        self.assertEqual(entry.args[1], 25)
        self.assertEqual(entry.args[2], '› what day is it')
        cursor = next(call for call in calls if call.args[0] == 27 and call.args[2] == ' ')
        self.assertEqual(cursor.args[1], 27 + len('what day is it'))

    def test_chat_approve_answers_pending_gate_once(self):
        import io
        ui = self.ui
        del ui.answer_prompt  # Exercise the real driver-stdin approval handler.
        ui.state = 'running'
        ui.proc = Mock()
        ui.proc.poll.return_value = None
        ui.proc.stdin = io.BytesIO()
        ui.prompt_kind = 'confirm'
        ui.prompt_text = 'Ready to approve BASELINE_REPORT.md? [Y/N]'
        ui.partial = ui.prompt_text
        ui._absorb_line = Mock()
        ui.chat_composer = '/approve'
        self.assertIn('/approve', ui._slash_choices())
        self.assertTrue(ui._chat_command(10))
        self.assertEqual(ui.proc.stdin.getvalue(), b'y\n')
        self.assertEqual(ui.prompt_kind, '')
        self.assertEqual(ui.chat_focus, 'chat')
        self.assertEqual(ui.chat_composer, '')
        ui.chat_composer = '/approve'
        ui._chat_command(10)
        self.assertEqual(ui.proc.stdin.getvalue(), b'y\n')
        self.assertIn('No stage approval', ui.chat_error)

    def test_chat_approve_rejects_nonapproval_prompts_and_stopped_runs(self):
        ui = self.ui
        ui.answer_prompt = Mock()
        for state, kind, prompt, exit_code, command in [
                ('running', '', '', None, '/approve'),
                ('running', 'input', 'Issue number:', None, '/approve'),
                ('running', 'confirm', 'Retry implementation? [Y/N]', None, '/approve'),
                ('menu', 'confirm', 'Ready to approve plan? [Y/N]', None, '/approve'),
                ('running', 'confirm', 'Ready to approve plan? [Y/N]', 0, '/approve'),
                ('running', 'confirm', 'Ready to approve plan? [Y/N]', None, '/approve all')]:
            with self.subTest(state=state, kind=kind, prompt=prompt, command=command):
                ui.state, ui.prompt_kind, ui.prompt_text = state, kind, prompt
                ui.proc = Mock()
                ui.proc.poll.return_value = exit_code
                ui.chat_composer = command
                ui._chat_command(10)
                ui.answer_prompt.assert_not_called()
                self.assertEqual(ui.chat_composer, command)
                self.assertTrue(ui.chat_error)

    def test_response_uses_full_width_before_sidebar(self):
        renderer_state(self.ui)
        self.ui.state = 'running'
        self.ui.output = []
        self.ui.prompt_kind = ''
        self.ui.home_history = [('assistant', 'x' * 240)]
        self.ui.stdscr = Mock()
        self.ui.stdscr.getmaxyx.return_value = (40, 160)
        self.ui._draw_running(29, 126)
        calls = self.ui.stdscr.addnstr.call_args_list
        self.assertEqual(len(calls[0].args[2]), 126)
        self.assertEqual(calls[0].args[1], 0)
        self.assertTrue(all(call.args[3] == 126 for call in calls))

    def test_exited_workflow_is_reported_once_and_escape_returns_home(self):
        self.ui.state = 'running'
        self.ui.proc = Mock()
        self.ui.proc.poll.return_value = 1
        self.ui.proc.returncode = 1
        self.ui._end_title = Mock()
        self.ui.home_history = []
        self.ui._poll_workflow()
        self.ui._poll_workflow()
        self.assertEqual(len(self.ui.home_history), 1)
        self.assertIn('exit code 1', self.ui.chat_error)
        self.assertFalse(self.ui.steering_channels)
        self.ui.handle_key(27)
        self.assertEqual(self.ui.state, 'menu')

    def test_issue_input_rejects_transcript_before_launch(self):
        self.ui.state = 'issue'
        self.ui.input_buf = 'Assistant (baseline): I will inspect the repository'
        self.ui._confirm_text()
        self.assertEqual(self.ui.state, 'issue')
        self.assertIn('issue number', self.ui.notice)
        for value in ('123', '#123', 'https://github.com/unclehq/uncle/issues/123'):
            self.ui.state = 'issue'
            self.ui.input_buf = value
            self.ui._confirm_text()
            self.assertEqual(self.ui.state, 'issue_mode')
        self.ui.workflow_idx = 1
        self.ui.issue = 'Assistant (baseline): invalid input'
        self.ui.start_workflow = Mock()
        self.ui._run()
        self.ui.start_workflow.assert_not_called()
        with self.assertRaises(ValueError):
            self.ui.cmd_for()

    def test_stopped_workflow_ignores_late_chat_and_ready_events(self):
        import json
        self.ui.workflow_exit_reported = True
        self.ui.home_history = [('system', 'Workflow stopped')]
        self.ui.steering_channels = {}
        self.ui._apply_status(json.dumps({'event': 'chat_output', 'stage': 'baseline', 'text': 'Still writing'}))
        self.ui._apply_status(json.dumps({'event': 'steering_ready', 'stage': 'baseline', 'channel': '/stale'}))
        self.assertEqual(self.ui.home_history, [('system', 'Workflow stopped')])
        self.assertEqual(self.ui.steering_channels, {})

    def test_build_and_chat_share_message_order(self):
        self.ui.output = ['Build started']
        self.ui.home_history = []
        self.assertEqual(self.ui._build_messages(), ['Build started'])
        self.ui.home_history.append(('assistant', 'Working on your change'))
        self.assertEqual(self.ui._build_messages()[-1], 'Assistant: Working on your change')
        self.ui.output.append('Verification passed')
        self.assertEqual(self.ui._build_messages()[-2:],
                         ['Assistant: Working on your change', 'Verification passed'])
        self.assertEqual(len(self.ui._build_messages()), 3)

    def test_loaded_layouts_keep_composer_response_and_gate(self):
        renderer_state(self.ui)
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
            self.assertTrue(any('› ' in line for line in lines))
            self.assertTrue(any('Approve brief?' in line for line in lines))
            self.assertTrue(any('Tab' in line for line in lines))
            for call in screen.addnstr.call_args_list:
                y, x, text, width = call.args[:4]
                self.assertTrue(0 <= y < h and 0 <= x < w)
                self.assertLessEqual(x + width, w)


def styled_ui(state, history, output=(), partial='', preview=''):
    """A renderer with a distinguishable palette; both draw paths share it."""
    ui = tui.UncleTUI.__new__(tui.UncleTUI)
    ui.state = state
    ui.sel = 0
    ui.chat_focus = 'chat'
    ui.home_menu_open = False
    ui.prompt_kind = ''
    ui.partial = partial
    ui.color = dict(title=1, sel=2, accent=4, emphasis=8 | tui.curses.A_BOLD)
    ui.home_history = list(history)
    ui.output = list(output)
    ui.chat = Mock()
    ui.chat.preview = preview
    ui._draw_chat_composer = Mock()
    ui.stdscr = Mock()
    ui.stdscr.getmaxyx.return_value = (40, 120)
    return ui


def drawn(ui):
    return [(c.args[0], c.args[1], c.args[2], c.args[3], c.args[4] if len(c.args) > 4 else 0)
            for c in ui.stdscr.addnstr.call_args_list
            if c.args[2] and c.args[2] not in tui.LOGO and (ui.state != 'menu' or c.args[0] > 0)]


# Literal oracles captured from the pre-change renderer (issue 52, AC-4).
HOME_MULTI = [(4, 22, 'User: Question one', 76), (5, 22, 'second line', 76),
              (6, 22, 'Supervisor: ' + 'x' * 64, 76), (7, 22, 'x' * 36, 76), (8, 22, 'System: Note', 76)]
HOME_CAP = ([(4, 22, 'u' * 7, 76), (5, 22, 'Supervisor: ' + 'v' * 64, 76)]
            + [(y, 22, 'v' * 76, 76) for y in range(6, 24)] + [(24, 22, 'v' * 68, 76)])
RUN = [(0, 0, 'Supervisor: fake', 60), (1, 0, 'build line', 60), (2, 0, 'User: Ask', 60),
       (3, 0, 'Supervisor:' + ' Reply' * 8, 60), (4, 0, ' '.join(['Reply'] * 10), 60),
       (5, 0, 'Reply Reply', 60), (6, 0, 'System: sys', 60), (7, 0, 'partial out', 60)]


class ChatStylingTests(unittest.TestCase):
    """Issue 52: user rows bold, supervisor rows emphasised, text unchanged."""
    BOLD = tui.curses.A_BOLD

    def attrs(self, rows):
        return [row[4] for row in rows]

    def test_fix_request_executes_without_numbered_proposal(self):
        from unittest.mock import Mock
        ui = styled_ui('menu', [])
        ui._ensure_chat = Mock()
        ui._triage_turn = Mock()
        ui.send_home_chat('fix the malformed audit table')
        ui._triage_turn.assert_called_once_with('execute', proposal=(1, 'fix the malformed audit table'), followup='fix the malformed audit table')

    def test_build_scroll_keys_leave_composer_intact(self):
        ui = styled_ui('running', [])
        ui.prompt_kind = ''
        ui.build_page_rows = 8
        ui.chat_buf = 'draft'
        ui.handle_key(tui.curses.KEY_PPAGE)
        self.assertEqual(ui.build_scroll, 8)
        self.assertEqual(ui.chat_buf, 'draft')
        ui.handle_key(tui.curses.KEY_NPAGE)
        self.assertEqual(ui.build_scroll, 0)
        ui.handle_key(tui.curses.KEY_PPAGE)
        ui.handle_key(tui.curses.KEY_END)
        self.assertEqual(ui.build_scroll, 0)

    def test_pending_replacement_visible_after_long_preview(self):
        ui = styled_ui('menu', [('system', 'Proposal')])
        ui.chat.preview = '## Interfaces\n' + ('Long brief content\n' * 100)
        ui.home_replace_proposal = {'uncle_action': 'create_app'}
        ui._draw_homepage(40, 120)
        text = '\n'.join(row[2] for row in drawn(ui))
        self.assertIn('Replace REQUIREMENTS.md?', text)
        self.assertIn('approve replacement', text)
        self.assertIn('decline replacement', text)
        for row in drawn(ui):
            if 'Replace REQUIREMENTS' in row[2] or 'approve replacement' in row[2]:
                self.assertTrue(row[4] & tui.curses.A_BOLD)

    def test_t1_home_roles_and_t5_home_literals(self):
        ui = styled_ui('menu', [('user', 'Question one\nsecond line'), ('supervisor', 'x' * 100), ('system', 'Note')])
        ui._draw_homepage(40, 120)
        rows = drawn(ui)
        self.assertEqual([row[:4] for row in rows], HOME_MULTI)
        self.assertEqual(self.attrs(rows), [4 | self.BOLD, 4 | self.BOLD, ui.color['emphasis'], ui.color['emphasis'], 4])

    def test_t4_t5_home_tail_cap_keeps_roles(self):
        ui = styled_ui('menu', [('user', 'u' * 2000), ('supervisor', 'v' * 1500)])
        ui._draw_homepage(40, 120)
        rows = drawn(ui)
        self.assertEqual([row[:4] for row in rows], HOME_CAP)
        self.assertEqual(self.attrs(rows), [4 | self.BOLD] + [ui.color['emphasis']] * 20)

    def test_t1_home_preview_rows_keep_accent(self):
        ui = styled_ui('menu', [('user', 'Hi')], preview='Preview body')
        ui._draw_homepage(40, 120)
        rows = drawn(ui)
        self.assertEqual([row[2] for row in rows], ['User: Hi', 'Preview:', 'Preview body'])
        self.assertEqual(self.attrs(rows), [4 | self.BOLD, 4, 4])
        self.assertEqual(ui.home_history, [('user', 'Hi')])

    def test_t2_t5_running_roles_and_literals(self):
        ui = styled_ui('running', [('user', 'Ask'), ('supervisor', 'Reply ' * 20), ('system', 'sys')],
                       output=['Supervisor: fake', 'build line'], partial='partial out')
        ui._draw_running(10, 60)
        rows = drawn(ui)
        self.assertEqual([row[:4] for row in rows], RUN)
        emphasis = ui.color['emphasis']
        self.assertEqual(self.attrs(rows), [0, 0, self.BOLD, emphasis, emphasis, emphasis, 0, 0])

    def test_t3_palette_colour_and_monochrome(self):
        pairs = {}
        with patch.object(tui.curses, 'has_colors', return_value=True), \
             patch.object(tui.curses, 'start_color'), patch.object(tui.curses, 'use_default_colors'), \
             patch.object(tui.curses, 'init_pair', side_effect=lambda n, fg, bg: pairs.__setitem__(n, (fg, bg))), \
             patch.object(tui.curses, 'color_pair', side_effect=lambda n: n << 8):
            ui = tui.UncleTUI.__new__(tui.UncleTUI)
            ui._setup_colors()
        emphasis = ui.color['emphasis']
        pair = (emphasis & ~self.BOLD) >> 8
        self.assertEqual(pairs[pair], (tui.curses.COLOR_YELLOW, -1))
        self.assertEqual(emphasis, pair << 8 | self.BOLD)
        self.assertNotEqual(emphasis, self.BOLD)
        self.assertNotEqual(emphasis, ui.color['accent'])
        self.assertEqual(ui.chat_attr('user', ui.color['accent']), ui.color['accent'] | self.BOLD)
        self.assertEqual(ui.chat_attr('supervisor', ui.color['accent']), emphasis)
        self.assertEqual(ui.chat_attr('system', ui.color['accent']), ui.color['accent'])
        for failing in ({'has_colors': Mock(return_value=False)},
                        {'has_colors': Mock(return_value=True), 'start_color': Mock(side_effect=Exception('no'))}):
            with patch.multiple(tui.curses, **failing):
                ui = tui.UncleTUI.__new__(tui.UncleTUI)
                ui._setup_colors()
            self.assertEqual(ui.color['emphasis'], tui.curses.A_REVERSE)
            self.assertNotEqual(ui.color['emphasis'], self.BOLD)
            self.assertNotEqual(ui.chat_attr('supervisor', 0), ui.chat_attr('user', 0))
        ui.color = {}
        self.assertEqual(ui.chat_attr('supervisor', 0), tui.curses.A_REVERSE)
        self.assertEqual(ui.chat_attr('user', 0), self.BOLD)

    def test_t6_stream_mutation_keeps_chat_attrs(self):
        ui = styled_ui('running', [('user', 'Question'), ('supervisor', 'Draft')], output=['b0'])
        ui._build_messages()
        ui.home_history[-1] = ('supervisor', 'Draft ' + 'grown ' * 5)
        ui.output = ['b%d' % i for i in range(1, 4100)]
        ui.output.append('User: fake')
        ui.home_history.append(('user', 'Follow-up'))
        ui.home_history.append(('system', 'note'))
        ui.partial = 'partial chunk'
        ui._draw_running(20, 30)
        rows = drawn(ui)
        emphasis = ui.color['emphasis']
        expect = {'User: Follow-up': self.BOLD, 'System: note': 0, 'partial chunk': 0, 'User: fake': 0}
        expect.update((line, emphasis) for line in textwrap.wrap('Supervisor: Draft ' + 'grown ' * 5, 30))
        self.assertEqual(len(rows), 19)
        for _, _, text, _, attr in rows:
            self.assertEqual(attr, expect.get(text, 0), text)
        self.assertEqual(sum(1 for row in rows if row[4] == emphasis), 2)
        self.assertEqual(ui._build_messages()[0], 'b104')
        self.assertEqual(ui._build_messages()[-4:], ['User: fake', 'Supervisor: Draft ' + 'grown ' * 5,
                                                     'User: Follow-up', 'System: note'])
        # Whole-stream replacement after the earliest chat rows were evicted.
        ui.home_history[:] = [('user', 'Reset')]
        ui._draw_running(20, 30)
        rows = drawn(ui)
        self.assertEqual(rows[-2][2:], ('User: Reset', 30, self.BOLD))
        self.assertEqual(rows[-1][2:], ('partial chunk', 30, 0))

    def test_t7_string_only_build_messages(self):
        ui = styled_ui('running', [])
        ui._build_messages = Mock(return_value=['User: mocked', 'Supervisor: mocked'])
        ui._draw_running(10, 60)
        rows = drawn(ui)
        self.assertEqual([row[2] for row in rows], ['User: mocked', 'Supervisor: mocked'])
        self.assertEqual(self.attrs(rows), [0, 0])
        del ui.color
        ui.home_history = [('user', 'Q'), ('supervisor', 'A')]
        ui._build_messages = tui.UncleTUI._build_messages.__get__(ui)
        ui.stdscr = Mock()
        ui.stdscr.getmaxyx.return_value = (40, 120)
        ui._draw_running(10, 60)
        self.assertEqual(self.attrs(drawn(ui)), [self.BOLD, tui.curses.A_REVERSE])


def renderer_state(ui):
    ui.partial = ''
    ui.gate_file = ''
    ui.color = dict(title=0, sel=0, accent=0, good=0, bad=0, cursor=0)
    for name in ('status_runner', 'status_model', 'status_mode', 'status_stage',
                 'status_effort', 'direct_issue'):
        setattr(ui, name, '')
    ui.status_stage_index = ui.status_stage_total = 0
    ui.workflow_idx = 0


def terminal_case(screen):
    ui = tui.UncleTUI.__new__(tui.UncleTUI)
    renderer_state(ui)
    ui.proc = None
    ui.open_chat()
    ui.send_home_chat = ui.chat.send
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
        assert any('response stays visible' in row for row in ui._build_messages()), rows
        assert any('› ' in row for row in rows), rows
        assert any('Approve brief?' in row for row in rows), rows
        assert any('Tab' in row for row in rows), rows
        assert '·' in rows[h - 2], rows
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
