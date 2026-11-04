#!/usr/bin/env python3
"""Bug report (/report): module behavior with a fake gh, and the TUI confirmation gate.

Covers AC-1..AC-8 from the change spec. The fake `gh` is a shell script on PATH;
nothing here contacts GitHub.
"""
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'scripts' / 'lib'))
import bug_report  # noqa: E402

FAKE_GH = r'''#!/bin/sh
echo "$@" >> "$FAKE_GH_LOG"
if [ "$1" = "auth" ]; then
  [ "$FAKE_GH_AUTH" = "fail" ] && { echo "not logged in" >&2; exit 1; }
  exit 0
fi
if [ "$1" = "issue" ]; then
  case "$FAKE_GH_CREATE" in
    nourl) echo "created something"; exit 0 ;;
    fail) echo "boom" >&2; exit 1 ;;
    *) echo "Creating issue..."; echo "https://github.com/unclehq/uncle/issues/999"; exit 0 ;;
  esac
fi
exit 0
'''


class Sandbox:
    def __init__(self, test):
        self.tmp = tempfile.TemporaryDirectory()
        test.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve() / 'proj'
        self.state = self.root / '.uncle' / 'workflow'
        self.state.mkdir(parents=True)
        self.bin = Path(self.tmp.name) / 'bin'
        self.bin.mkdir()
        gh = self.bin / 'gh'
        gh.write_text(FAKE_GH)
        gh.chmod(0o755)
        self.log = Path(self.tmp.name) / 'gh.log'
        self.env = {'PATH': str(self.bin) + os.pathsep + os.environ.get('PATH', ''),
                    'FAKE_GH_LOG': str(self.log)}
        p = patch.dict(os.environ, self.env)
        p.start()
        test.addCleanup(p.stop)

    def gh_calls(self):
        return self.log.read_text().splitlines() if self.log.exists() else []

    def drafts(self):
        return sorted(self.state.glob('bug-report-*.md'))


class ModuleTests(unittest.TestCase):
    def setUp(self):
        self.sb = Sandbox(self)
        self.report = {'title': 'Tool bug in stage plan', 'body': '# Report\n\nstage: plan\n', 'fields': {}}

    def test_eligible_only_for_tool_bug(self):
        self.assertTrue(bug_report.eligible('tool bug'))
        for other in ('', None, 'test failure', 'environment', 'requirements gap'):
            self.assertFalse(bug_report.eligible(other), other)

    def test_scrub_paths_and_tokens(self):
        home = str(Path.home())
        roots = [str(self.sb.root), '/opt/uncle-install', home]
        text = ('%s/a.py /opt/uncle-install/x %s/.ssh ghp_abcDEF123 github_pat_AB_12 sk-abc_DEF-1 '
                'Bearer abc.def AKIAABCDEFGHIJKLMNOP https://user:pw@host/x see .uncle/workflow/y'
                % (self.sb.root, home))
        out = bug_report.scrub(text, roots)
        for leaked in (str(self.sb.root), '/opt/uncle-install', home + '/', 'ghp_abc', 'github_pat_AB',
                       'sk-abc', 'abc.def', 'AKIAABCDEFGHIJKLMNOP', 'user:pw'):
            self.assertNotIn(leaked, out)
        self.assertIn('<project>', out)
        self.assertIn('<uncle>', out)
        self.assertIn('~', out)
        self.assertIn('[REDACTED]', out)
        self.assertIn('.uncle/workflow/y', out)

    def test_residual_check_flags_leftovers(self):
        roots = [str(self.sb.root)]
        self.assertTrue(bug_report.residual_check('see /Users/someone/secret/file', roots))
        self.assertTrue(bug_report.residual_check('token ghp_abcdef123456', roots))
        self.assertFalse(bug_report.residual_check('see .uncle/workflow/log and <project>/x', roots))

    def test_missing_sources_render_unavailable(self):
        report = bug_report.build_report(str(self.sb.state), str(self.sb.root), str(ROOT))
        self.assertIn('unavailable', report['title'] + report['body'])
        self.assertNotIn(str(self.sb.root), report['body'])

    def test_bad_stage_argument_is_unavailable(self):
        report = bug_report.build_report(str(self.sb.state), str(self.sb.root), str(ROOT), stage='x; rm -rf /')
        self.assertNotIn('rm -rf', report['title'] + report['body'])

    def test_save_draft_lowest_unused_never_overwrites(self):
        p1 = Path(bug_report.save_draft(str(self.sb.state), self.report))
        p2 = Path(bug_report.save_draft(str(self.sb.state), self.report))
        self.assertEqual(p1.name, 'bug-report-1.md')
        self.assertEqual(p2.name, 'bug-report-2.md')
        p1.unlink()
        self.assertEqual(Path(bug_report.save_draft(str(self.sb.state), self.report)).name, 'bug-report-1.md')
        self.assertEqual(p2.read_text(), self.report['body'])

    def test_save_draft_does_not_follow_symlink(self):
        victim = Path(self.sb.tmp.name) / 'victim.txt'
        victim.write_text('keep')
        (self.sb.state / 'bug-report-1.md').symlink_to(victim)
        path = Path(bug_report.save_draft(str(self.sb.state), self.report))
        self.assertEqual(victim.read_text(), 'keep')
        self.assertNotEqual(path.name, 'bug-report-1.md')

    def _publish(self, **env):
        draft = bug_report.save_draft(str(self.sb.state), self.report)
        with patch.dict(os.environ, env):
            result = bug_report.publish(draft, 'T', confirm=True)
        return draft, result

    def test_publish_reports_url_after_extra_output_and_creates_once(self):
        draft, result = self._publish()
        self.assertIn('https://github.com/unclehq/uncle/issues/999', str(result))
        creates = [c for c in self.sb.gh_calls() if c.startswith('issue create')]
        self.assertEqual(len(creates), 1)
        self.assertIn('--repo unclehq/uncle', creates[0])
        self.assertTrue(Path(draft).exists())

    def test_publish_no_url_is_failure_without_retry(self):
        draft, result = self._publish(FAKE_GH_CREATE='nourl')
        self.assertNotIn('https://github.com/unclehq/uncle/issues/999', str(result))
        self.assertIn('may already exist', str(result).lower())
        self.assertEqual(len([c for c in self.sb.gh_calls() if c.startswith('issue create')]), 1)
        self.assertTrue(Path(draft).exists())

    def test_publish_unauthenticated_keeps_draft_and_gives_command(self):
        draft, result = self._publish(FAKE_GH_AUTH='fail')
        self.assertEqual([c for c in self.sb.gh_calls() if c.startswith('issue create')], [])
        self.assertIn('gh auth login', str(result))
        self.assertIn('gh issue create --repo unclehq/uncle', str(result))
        self.assertTrue(Path(draft).exists())

    def test_publish_create_timeout_keeps_draft_no_retry(self):
        calls = []

        def runner(argv, **kw):
            calls.append(list(argv))
            if 'auth' in argv:
                return subprocess.CompletedProcess(argv, 0, '', '')
            raise subprocess.TimeoutExpired(argv, 30)
        draft = bug_report.save_draft(str(self.sb.state), self.report)
        result = bug_report.publish(draft, 'T', confirm=True, runner=runner)
        self.assertIn('may already exist', str(result).lower())
        self.assertEqual(len([c for c in calls if 'create' in c]), 1)
        self.assertTrue(Path(draft).exists())

    def test_publish_auth_timeout_is_failure(self):
        def runner(argv, **kw):
            raise subprocess.TimeoutExpired(argv, 30)
        draft = bug_report.save_draft(str(self.sb.state), self.report)
        result = bug_report.publish(draft, 'T', confirm=True, runner=runner)
        self.assertNotIn('issues/999', str(result))
        self.assertTrue(Path(draft).exists())

    def test_publish_sends_saved_bytes(self):
        draft = bug_report.save_draft(str(self.sb.state), self.report)
        seen = []

        def runner(argv, **kw):
            if 'create' in argv:
                seen.append(argv)
            return subprocess.CompletedProcess(argv, 0, 'https://github.com/unclehq/uncle/issues/5\n', '')
        bug_report.publish(draft, 'T', confirm=True, runner=runner)
        self.assertEqual(len(seen), 1)
        self.assertIn('--body-file', seen[0])
        self.assertIsInstance(seen[0], list)


class TuiTests(unittest.TestCase):
    """Drive /report through the real TUI methods; no curses."""

    def make(self, classification='tool bug', recovery=True):
        import uncle_tui
        self.sb = Sandbox(self)
        ui = uncle_tui.UncleTUI.__new__(uncle_tui.UncleTUI)
        ui.state = 'triage'
        ui.home_history = []
        ui._triage_init()
        ui.triage_classification = classification
        ui.recovery_active = recovery
        ui.triage_composer = ''
        self.chat = patch.object(uncle_tui.UncleTUI, '_triage_turn')
        self.chat_mock = self.chat.start()
        self.addCleanup(self.chat.stop)
        pr = patch.object(uncle_tui, '_project_root', return_value=str(self.sb.root))
        pr.start()
        self.addCleanup(pr.stop)
        return ui

    def arm(self, ui):
        ui._triage_command('/report')
        self.assertTrue(getattr(ui, 'report_pending', None), 'report_pending should be armed')
        self.assertEqual(len(self.sb.drafts()), 1)
        self.assertEqual(self.sb.gh_calls(), [])

    def creates(self):
        return [c for c in self.sb.gh_calls() if c.startswith('issue create')]

    def test_report_refused_when_ineligible_or_unclassified(self):
        for cls, rec in (('test failure', True), ('', True), ('tool bug', False)):
            ui = self.make(cls, rec)
            ui._triage_command('/report')
            self.assertFalse(getattr(ui, 'report_pending', None), (cls, rec))
            self.assertEqual(self.sb.drafts(), [])
            self.assertEqual(self.sb.gh_calls(), [])

    def test_yes_variants_publish_saved_draft_and_never_reach_chat(self):
        for answer in ('yes', 'YES', '  yes  ', 'Yes\n'):
            ui = self.make()
            self.arm(ui)
            ui._triage_command(answer.strip()) if answer.strip() else None
            self.assertEqual(len(self.creates()), 1, repr(answer))
            self.assertFalse(getattr(ui, 'report_pending', None))
            self.chat_mock.assert_not_called()
            self.assertEqual(len(self.sb.drafts()), 1)

    def test_other_input_cancels_without_gh_or_chat_forwarding(self):
        for answer in ('y', 'no', 'maybe yes', '/resume', '/do 1', '/triage', 'why did this fail?'):
            ui = self.make()
            self.arm(ui)
            with patch.object(type(ui), '_resume_build', return_value='', create=True), \
                    patch.object(type(ui), '_triage_do', create=True):
                ui._triage_command(answer)
            self.assertFalse(getattr(ui, 'report_pending', None), answer)
            self.assertEqual(self.creates(), [], answer)
            self.chat_mock.assert_not_called()
            self.assertEqual(len(self.sb.drafts()), 1, answer)

    def test_only_one_input_is_intercepted(self):
        ui = self.make()
        self.arm(ui)
        ui._triage_command('no')
        ui._triage_command('a follow-up question')
        self.chat_mock.assert_called_once()

    def test_empty_input_cancels_pending(self):
        ui = self.make()
        self.arm(ui)
        # The composer path strips and may drop empty text before _triage_command; use the key path.
        ui.triage_composer = ''
        ui._triage_key(10)
        self.assertFalse(getattr(ui, 'report_pending', None))
        self.assertEqual(self.creates(), [])
        self.chat_mock.assert_not_called()

    def test_repeat_report_replaces_pending_with_new_draft(self):
        ui = self.make()
        self.arm(ui)
        ui._triage_command('/report')
        self.assertTrue(getattr(ui, 'report_pending', None))
        self.assertEqual(len(self.sb.drafts()), 2)
        self.assertEqual(self.sb.gh_calls(), [])

    def test_clear_cancels_pending_then_runs(self):
        ui = self.make()
        self.arm(ui)
        with patch.object(type(ui), '_clear_build', return_value='cleared', create=True) as clear:
            ui._triage_command('/clear')
        self.assertFalse(getattr(ui, 'report_pending', None))
        clear.assert_called_once()
        self.assertEqual(self.creates(), [])
        self.chat_mock.assert_not_called()

    def test_declined_draft_kept(self):
        ui = self.make()
        self.arm(ui)
        ui._triage_command('no')
        self.assertEqual(len(self.sb.drafts()), 1)


if __name__ == '__main__':
    unittest.main()
