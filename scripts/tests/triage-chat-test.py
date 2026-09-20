"""TUI triage: auto-open, on-request keys, parsing, consent, guard, resume.

Covers AC-5 (parse side), AC-6..9, AC-10 (TUI path), AC-17, AC-18, AC-20 and
the adversarial rows AR-003, AR-011, AR-012, AR-013, AR-014. The driver is a
shell script; the master is a Python script launched through the real
TriageRequest and guard, so what is asserted is what a real turn does.
"""
import json
import os
import queue
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'scripts' / 'lib'))
import uncle_tui as tui
import triage_chat

# The fake master: reads the prompt on stdin, acts on FAKE_MASTER_ACTION with
# the sandbox as cwd, and replies with stream-json. Its classification is read
# off the bundle in the prompt, never canned (AR-013).
FAKE_MASTER = r'''
import json, os, sys, pathlib
prompt = sys.stdin.read()
pathlib.Path(os.environ['FAKE_MASTER_LOG']).open('a').write(prompt + '\n=====\n')
action = os.environ.get('FAKE_MASTER_ACTION', '')
live = os.environ.get('FAKE_MASTER_LIVE', '')
install = os.environ.get('FAKE_MASTER_INSTALL', '')
def say(text):
    print(json.dumps({'type': 'assistant', 'message': {'content': [{'type': 'text', 'text': text}]}}))
ask = prompt.rsplit('\n---\n', 1)[-1]
if action == 'edit-plan-empty-reply' and ask.strip().startswith('Execute Proposal'):
    # A real runner (kimi-code) has reported success and spent real output
    # tokens making the requested edit, yet returned no reply text at all --
    # no assistant message with any text, an empty final "result". Skipping
    # the shared "thinking" narration below is the point: extract_reply()
    # takes the last non-empty assistant text, so any text at all here would
    # defeat this fixture.
    pathlib.Path('CHANGE_PLAN.md').write_text('# plan edited by triage\n')
    print(json.dumps({'type': 'result', 'subtype': 'success', 'is_error': False, 'result': ''}))
    raise SystemExit(0)
say('thinking')
if ask.strip().startswith('Execute Proposal'):
    if action == 'edit-plan':
        pathlib.Path('CHANGE_PLAN.md').write_text('# plan edited by triage\n')
    elif action == 'draft-issue':
        pathlib.Path('.uncle/workflow').mkdir(parents=True, exist_ok=True)
        pathlib.Path('.uncle/workflow/triage-issue-1.md').write_text('# jq crash\n\n## Observed\nx\n')
    elif action == 'forbidden':
        pathlib.Path('.uncle/workflow/approvals').mkdir(parents=True, exist_ok=True)
        pathlib.Path('.uncle/workflow/approvals/CHANGE_PLAN.sha256').write_text('forged\n')
        pathlib.Path('ADVERSARIAL_REVIEW.md').write_text('tampered\n')
        pathlib.Path(live, 'ADVERSARIAL_REVIEW.md').write_text('tampered\n')
        pathlib.Path(live, '.uncle/workflow/waivers').mkdir(parents=True, exist_ok=True)
        pathlib.Path(live, '.uncle/workflow/waivers/AC-1').write_text('id: AC-1\n')
        pathlib.Path(live, '.uncle/workflow/state').write_text('COMPLETE\n')
        pathlib.Path(install, 'scripts/lib/thing.sh').write_text('patched\n')
    say('Done. Changed the files the proposal named. /do 2')
    raise SystemExit(0)
if action == 'diagnosis-write':
    pathlib.Path('src').mkdir(exist_ok=True)
    pathlib.Path('src/x').write_text('changed during diagnosis\n')
if action == 'bad-reply':
    say('I looked at it. Run /do 1 to fix it.')
    raise SystemExit(0)
if action == 'canned':
    say('Classification: code defect\nProposal 1: edit the code')
    raise SystemExit(0)
if action == 'crash':
    print(json.dumps({'type': 'result', 'is_error': 'true', 'error_detail': 'model exploded'}))
    raise SystemExit(1)
bundle = prompt.split('# TRIAGE.md', 1)[1] if '# TRIAGE.md' in prompt else ''
rules = [('jq: error', 'tool bug', 'Draft an issue against uncle for the jq parse failure'),
         ('wrong parent', 'tool bug', 'Draft an issue for the signing loop'),
         ('Connection refused', 'needs owner decision', 'Start the self-hosted endpoint, then resume'),
         ('EMPTY ROW', 'requirement gap', 'Fill the empty requirement rows in REQUIREMENTS.md'),
         ('contains whitespace', 'requirement gap', 'Rename the id in PREFLIGHT_REPORT.md'),
         ('has spaces', 'code defect', 'Fix the id in the test file'),
         ('Repair limit', 'needs owner decision', 'Raise the repair limit at the driver prompt on resume'),
         ('injected defects', 'code defect', 'Strengthen the assertion in tests/'),
         ('BLOCKED', 'needs owner decision', 'Provide the live endpoint or waive AC-4 on resume'),
         ('got 500', 'code defect', 'Fix the /health handler')]
for marker, klass, proposal in rules:
    if marker in bundle:
        say('The bundle shows: ' + marker + '\nClassification: ' + klass + '\nProposal 1: ' + proposal
            + '\nProposal 2: Edit CHANGE_PLAN.md to record the decision\nOffer: resume')
        break
else:
    say('The bundle carries no evidence I recognise, so I will not classify it.')
print(json.dumps({'type': 'result', 'subtype': 'success', 'is_error': False, 'result': 'ignored'}))
'''

GATE_DRIVER = '''#!/usr/bin/env bash
mkdir -p .uncle/workflow/approvals
printf 'Current state: WAIT_PLAN_APPROVAL\\n'
printf 'Ready to approve CHANGE_PLAN.md? [Y/N] '
IFS= read -r answer
printf '%s\\n' "$answer" > "$GATE_ANSWER"
exit 0
'''


def wait_for(predicate, timeout=20):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if predicate():
            return True
        time.sleep(0.05)
    return False


class FixtureSigningTests(unittest.TestCase):
    def test_fixture_does_not_use_inherited_signer(self):
        # Any accidental signing fails without touching a user's key or agent.
        fixture = TriageTests()
        with tempfile.TemporaryDirectory() as directory:
            signer = Path(directory) / 'must-not-sign'
            marker = Path(directory) / 'signer-called'
            signer.write_text('#!/bin/sh\ntouch "' + str(marker) + '"\nexit 1\n')
            signer.chmod(0o755)
            with patch.dict(os.environ, {
                'GIT_CONFIG_COUNT': '2',
                'GIT_CONFIG_KEY_0': 'commit.gpgsign', 'GIT_CONFIG_VALUE_0': 'true',
                'GIT_CONFIG_KEY_1': 'gpg.program', 'GIT_CONFIG_VALUE_1': str(signer),
            }):
                try:
                    fixture.setUp()
                    self.assertFalse(marker.exists())
                finally:
                    fixture.doCleanups()


class TriageTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='triage-chat-')
        self.addCleanup(self.tmp.cleanup)
        base = Path(self.tmp.name).resolve()
        self.project = base / 'project'
        (self.project / '.uncle' / 'workflow' / 'logs').mkdir(parents=True)
        (self.project / 'src').mkdir()
        (self.project / 'src' / 'x').write_text('live\n')
        (self.project / 'CHANGE_PLAN.md').write_text('| AC-1 | plan row |\n')
        (self.project / 'ADVERSARIAL_REVIEW.md').write_text('review\n')
        subprocess.run(['git', 'init', '-q', '.'], cwd=self.project, check=True)
        subprocess.run(['git', 'config', 'commit.gpgsign', 'false'], cwd=self.project, check=True)
        subprocess.run(['git', 'config', 'tag.gpgsign', 'false'], cwd=self.project, check=True)
        (self.project / '.gitignore').write_text('.uncle/workflow/\n')
        subprocess.run(['git', 'add', '-A'], cwd=self.project, check=True)
        subprocess.run(['git', '-c', 'commit.gpgsign=false', '-c', 'tag.gpgsign=false', '-c', 'user.email=t@t', '-c', 'user.name=t', 'commit', '--no-gpg-sign', '-qm', 'init'],
                       cwd=self.project, check=True)
        # A fake install: the guard, bundle lib, and prompt the TUI needs, so
        # the installed-tree check has a tree the fake master can try to edit.
        self.install = base / 'install'
        for rel in ('scripts/lib/triage_guard.py', 'scripts/lib/triage.sh', 'scripts/lib/state.sh',
                    'scripts/lib/sha256.sh', 'scripts/lib/terminal-title.sh', 'prompts/triage.md'):
            (self.install / rel).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(ROOT / rel, self.install / rel)
        (self.install / 'scripts' / 'lib' / 'thing.sh').write_text('installed\n')
        self.master = base / 'fake_master.py'
        self.master.write_text(FAKE_MASTER)
        self.master_log = base / 'master.log'
        self.answer_file = base / 'answer'
        self.env = patch.dict(os.environ, {
            'FAKE_MASTER_LOG': str(self.master_log), 'FAKE_MASTER_LIVE': str(self.project),
            'FAKE_MASTER_INSTALL': str(self.install), 'GATE_ANSWER': str(self.answer_file),
            'UNCLE_CONFIG': str(base / 'config')})
        self.env.start()
        self.addCleanup(self.env.stop)
        os.environ.pop('FAKE_MASTER_ACTION', None)
        for target, value in (('_project_root', lambda: str(self.project)), ('ROOT', str(self.install)),
                              ('runner_command', lambda runner, side: sys.executable)):
            p = patch.object(tui, target, value)
            p.start()
            self.addCleanup(p.stop)
        # runner_command returns one executable; the master script is the
        # first "flag", which python treats as the script to run.
        p = patch.object(tui, 'triage_runner_flags', lambda effort, model, tools: [str(self.master)])
        p.start()
        self.addCleanup(p.stop)

    def ui(self, state='chat'):
        ui = tui.UncleTUI.__new__(tui.UncleTUI)
        ui.state = state
        ui.proc = None
        ui.out_q = queue.Queue()
        ui.prompt_kind = ''
        ui.prompt_text = ''
        ui.prompt_buf = ''
        ui.prompt_seen = 0
        ui.status_stage = ''
        ui.gate_file = ''
        ui.workflow_idx = 0
        ui.misc = {}
        ui.stdscr = Mock()
        ui.stdscr.getmaxyx.return_value = (40, 120)
        ui.color = {}
        ui.stage_runner = lambda stage: 'claude'
        ui.stage_model = lambda stage: ''
        ui.stage_effort = lambda stage: 'medium'
        ui.stage_env = lambda: {}
        ui._restore_session_totals = Mock()
        ui.maybe_reload = Mock()
        ui._ensure_chat()
        return ui

    def finish_turn(self, ui):
        self.assertTrue(wait_for(lambda: ui.poll_triage()), 'the triage turn did not finish: ' + ui.triage_error)
        return ui

    def prompts(self):
        return self.master_log.read_text().split('=====\n') if self.master_log.exists() else []

    def run_driver(self, ui, script, wait_exit=True):
        path = Path(self.tmp.name) / 'driver.sh'
        path.write_text(script)
        ui.cmd_for = lambda: ['bash', str(path)]
        ui.state = 'running'
        ui.start_workflow()
        if wait_exit:
            self.assertTrue(wait_for(lambda: ui.proc.poll() is not None))
            for _ in range(5):
                ui.drain_output()
        return ui

    # --- AC-6 / AC-17 / AR-012: when the master starts on its own ---------------

    def test_failure_exit_opens_triage_once_with_bundle(self):
        hook = 'bash "%s" --write --state-dir .uncle/workflow > /dev/null' % (self.install / 'scripts/lib/triage.sh')
        ui = self.run_driver(self.ui(), '#!/usr/bin/env bash\nprintf \'{"x":"jq: error (at <stdin>:3)"}\\n\' > .uncle/workflow/logs/adversarial-review.jsonl\n' + hook + '\nexit 3\n')
        self.assertTrue(ui.recovery_active)
        self.assertNotEqual(ui.state, 'triage')
        self.assertIsNotNone(ui.triage_request)
        self.finish_turn(ui)
        self.assertEqual(len(self.prompts()) - 1, 1)
        self.assertIn('# TRIAGE.md', self.prompts()[0])
        self.assertIn('jq: error (at <stdin>:3)', self.prompts()[0])
        self.assertEqual(ui.triage_classification, 'tool bug')
        self.assertEqual([n for n, _ in ui.triage_proposals], [1, 2])
        self.assertEqual(ui.state, 'running')
        self.assertEqual(ui.chat_focus, 'chat')
        self.assertTrue(any('Recovery:' in line and 'Proposal 1:' in line for line in ui.chat_display()))
        self.assertEqual(ui.chat_model()[0], 'triage')
        self.assertTrue((self.project / '.uncle/workflow/logs/triage-1.jsonl').exists())
        ui._poll_workflow()
        self.assertEqual(ui.triage_turn, 1)

    def test_clean_exit_never_launches_master(self):
        ui = self.run_driver(self.ui(), '#!/usr/bin/env bash\nprintf "Workflow complete.\\n"\nexit 0\n')
        self.assertNotEqual(ui.state, 'triage')
        self.assertFalse(self.master_log.exists())
        self.assertFalse((self.project / '.uncle/workflow/TRIAGE.md').exists())
        self.assertEqual(list((self.project / '.uncle/workflow/logs').glob('triage-*')), [])

    def test_cancel_and_human_stop_do_not_open_triage(self):
        for script in ('#!/usr/bin/env bash\nexit 130\n',
                       '#!/usr/bin/env bash\nprintf human > .uncle/workflow/stop-reason\nprintf x > .uncle/workflow/TRIAGE.md\nexit 1\n'):
            ui = self.run_driver(self.ui(), script)
            self.assertNotEqual(ui.state, 'triage', script)
            self.assertFalse(self.master_log.exists(), script)

    def test_stale_bundle_does_not_open_triage(self):
        (self.project / '.uncle/workflow/TRIAGE.md').write_text('old\n')
        old = time.time() - 100
        os.utime(self.project / '.uncle/workflow/TRIAGE.md', (old, old))
        ui = self.run_driver(self.ui(), '#!/usr/bin/env bash\nexit 1\n')
        self.assertNotEqual(ui.state, 'triage')
        self.assertFalse(self.master_log.exists())

    # --- AC-7 / AR-003 / AR-014: on request at a gate ---------------------------

    def gate_ui(self):
        ui = self.run_driver(self.ui(), GATE_DRIVER, wait_exit=False)
        self.assertTrue(wait_for(lambda: (ui.drain_output(), ui.prompt_kind == 'confirm')[1]))
        self.addCleanup(lambda: ui.proc.poll() is None and ui.stop_workflow())
        return ui

    def test_t_key_opens_triage_and_leaves_the_gate_intact(self):
        ui = self.gate_ui()
        text = ui.prompt_text
        ui.handle_key(ord('t'))
        self.assertTrue(ui.recovery_active)
        self.assertNotEqual(ui.state, 'triage')
        self.finish_turn(ui)
        self.assertIn('Current state: WAIT_PLAN_APPROVAL', self.prompts()[0])
        ui.handle_key(27)
        self.assertEqual(ui.state, 'running')
        self.assertEqual((ui.prompt_kind, ui.prompt_text), ('confirm', text))
        self.assertIsNone(ui.proc.poll())
        self.assertEqual(list((self.project / '.uncle/workflow/approvals').iterdir()), [])
        self.assertFalse(self.answer_file.exists())
        ui.handle_key(ord('y'))
        self.assertTrue(wait_for(lambda: self.answer_file.exists()))
        self.assertEqual(self.answer_file.read_text(), 'y\n')

    def test_t_at_enter_and_audit_prompts_and_slash_triage_at_input(self):
        for kind in ('enter', 'audit'):
            ui = self.ui('running')
            ui.proc = Mock()
            ui.proc.poll.return_value = None
            ui.prompt_kind = kind
            ui.prompt_text = 'Press ENTER' if kind == 'enter' else 'Audit finding 1 [s] Skip'
            ui.chat_focus = 'gate'
            with patch.object(ui, 'open_triage') as opened:
                ui.handle_key(ord('t'))
                opened.assert_called_once()
            ui.proc.stdin.write.assert_not_called()
        ui = self.ui('running')
        ui.proc = Mock()
        ui.proc.poll.return_value = None
        ui.prompt_kind = 'input'
        ui.prompt_text = 'Enter a new total: '
        ui.chat_focus = 'chat'
        with patch.object(ui, 'open_triage') as opened:
            for char in '/triage':
                ui.handle_key(ord(char))
            ui.handle_key(10)
            opened.assert_called_once()
        self.assertEqual(ui.prompt_kind, 'input')
        ui.proc.stdin.write.assert_not_called()

    def test_gate_answer_is_refused_while_a_turn_runs(self):
        ui = self.gate_ui()
        ui._triage_init()
        ui.triage_request = Mock()
        ui.triage_request.events = queue.Queue()
        ui.answer_prompt('y')
        ui._send_raw('y')
        self.assertEqual(ui.prompt_kind, 'confirm')
        time.sleep(0.3)
        self.assertFalse(self.answer_file.exists())
        self.assertIn('triage turn is running', ui.chat_error)
        ui.triage_request = None
        ui.answer_prompt('n')
        self.assertTrue(wait_for(lambda: self.answer_file.exists()))

    # --- AC-8 / AC-9 / AR-013: parsing and consent -----------------------------

    def test_bad_reply_is_verbatim_and_nothing_selectable(self):
        os.environ['FAKE_MASTER_ACTION'] = 'bad-reply'
        ui = self.ui()
        ui.open_triage()
        self.finish_turn(ui)
        self.assertIn(('master', 'I looked at it. Run /do 1 to fix it.'), ui.triage_history)
        self.assertTrue(any(role == 'system' and 'nothing is selectable' in text for role, text in ui.triage_history))
        self.assertEqual(ui.triage_proposals, [])
        ui.handle_key(ord('1'))
        self.assertEqual(ui.chat_composer, '1')  # not a selection: nothing is on offer
        ui.chat_composer = ''
        ui._triage_command('/do 1')
        self.assertIn('No proposal 1 is selectable', ui.triage_error)
        self.assertIsNone(ui.triage_request)
        self.assertEqual(len(self.prompts()) - 1, 1)

    def test_master_reply_cannot_select_and_do_names_one_proposal(self):
        (self.project / '.uncle/workflow/logs/final-audit.jsonl').write_text('commit signed with wrong parent\n')
        ui = self.ui()
        ui.open_triage()
        self.finish_turn(ui)
        self.assertEqual(len(self.prompts()) - 1, 1)  # the reply's own "/do" text started nothing
        for _ in range(3):
            self.assertFalse(ui.poll_triage())
        ui.handle_key(ord('/'))
        for char in 'do 2':
            ui.handle_key(ord(char))
        ui.handle_key(10)
        self.assertIsNotNone(ui.triage_request)
        self.finish_turn(ui)
        execute = self.prompts()[1]
        self.assertIn('Execute Proposal 2 only: Edit CHANGE_PLAN.md to record the decision', execute)
        self.assertNotIn('Execute Proposal 1', execute)
        self.assertEqual(len(self.prompts()) - 1, 2)  # the execute reply's "/do 2" started nothing either
        self.assertTrue(ui.triage_offer_resume)

    def test_ten_fixtures_classify_from_bundle_and_canned_master_fails(self):
        fixtures = [('adversarial-review', 'jq: error (at <stdin>:12)', {'code defect', 'tool bug'}),
                    ('final-audit', 'signed with wrong parent', {'code defect', 'tool bug'}),
                    ('baseline', 'Connection refused (http://127.0.0.1:11434/v1)', {'code defect', 'needs owner decision'}),
                    ('requirements', "row 'Goal' is empty (EMPTY ROW)", {'requirement gap'}),
                    ('preflight', "id 'AC 3' contains whitespace", {'requirement gap', 'code defect'}),
                    ('test-review', "row id 'MC 7' has spaces", {'requirement gap', 'code defect'}),
                    ('repair', 'Repair limit (3) reached', {'needs owner decision'}),
                    ('test-review', '0 of 3 injected defects detected', {'code defect', 'needs owner decision'}),
                    ('implementation', '| AC-4 | BLOCKED | none |', {'needs owner decision', 'requirement gap'}),
                    ('execute-checklist', 'expected 200, got 500 from /health', {'code defect', 'requirement gap', 'needs owner decision', 'tool bug'})]
        canned_ok = 0
        for stage, evidence, allowed in fixtures:
            for old in (self.project / '.uncle/workflow/logs').glob('*.jsonl'):
                old.unlink()
            (self.project / '.uncle/workflow/logs' / (stage + '.jsonl')).write_text(evidence + '\n')
            ui = self.ui()
            ui.open_triage()
            self.finish_turn(ui)
            self.assertIn(ui.triage_classification, allowed, evidence)
            self.assertTrue(1 <= len(ui.triage_proposals) <= 3, evidence)
            self.assertIn(evidence, self.prompts()[-2], evidence)
            self.master_log.unlink()
            with patch.dict(os.environ, FAKE_MASTER_ACTION='canned'):
                ui = self.ui()
                ui.open_triage()
                self.finish_turn(ui)
            canned_ok += ui.triage_classification in allowed
            self.master_log.unlink()
        self.assertLess(canned_ok, len(fixtures), 'a one-class-for-all master must fail some fixture')

    # --- AC-10 / AC-11 / AC-18 / AC-20: the guard on the TUI path ----------------

    def test_forbidden_writes_reverted_and_resume_refused(self):
        os.environ['FAKE_MASTER_ACTION'] = 'forbidden'
        (self.project / '.uncle/workflow/approvals').mkdir()
        (self.project / '.uncle/workflow/approvals/CHANGE_PLAN.sha256').write_text('approved\n')
        (self.project / '.uncle/workflow/state').write_text('IMPLEMENT\n')
        (self.project / '.uncle/workflow/logs/adversarial-review.jsonl').write_text('jq: error\n')
        ui = self.ui()
        ui.open_triage()
        self.finish_turn(ui)
        ui._triage_command('/do 1')
        self.finish_turn(ui)
        self.assertEqual((self.project / '.uncle/workflow/approvals/CHANGE_PLAN.sha256').read_text(), 'forged\n')
        self.assertEqual((self.project / 'ADVERSARIAL_REVIEW.md').read_text(), 'tampered\n')
        self.assertTrue((self.project / '.uncle/workflow/waivers/AC-1').exists())
        self.assertEqual((self.project / '.uncle/workflow/state').read_text(), 'COMPLETE\n')
        self.assertEqual((self.install / 'scripts/lib/thing.sh').read_text(), 'installed\n')
        rows = [line.split('\t') for line in (self.project / '.uncle/workflow/triage-actions.tsv').read_text().splitlines()[1:]]
        refused = {row[4] for row in rows if row[3] == 'REFUSED'}
        for path in (str((self.install / 'scripts/lib/thing.sh').resolve()),):
            self.assertIn(path, refused)
        self.assertTrue(ui.triage_tainted)
        with patch.object(ui, 'start_workflow') as start:
            ui._triage_command('/resume')
            start.assert_not_called()
        self.assertIn('Resume refused', ui.triage_error)
        self.assertIn('Reinstall uncle', ui.triage_error)

    def test_diagnosis_write_reverted(self):
        os.environ['FAKE_MASTER_ACTION'] = 'diagnosis-write'
        ui = self.ui()
        ui.open_triage()
        self.finish_turn(ui)
        self.assertEqual((self.project / 'src/x').read_text(), 'live\n')
        tsv = (self.project / '.uncle/workflow/triage-actions.tsv').read_text()
        self.assertIn('\tREFUSED\tsrc/x\t', tsv)
        self.assertFalse(ui.triage_tainted)

    def test_tool_bug_draft_lands_under_workflow_only(self):
        os.environ['FAKE_MASTER_ACTION'] = 'draft-issue'
        (self.project / '.uncle/workflow/logs/adversarial-review.jsonl').write_text('jq: error\n')
        before = {p: p.read_bytes() for p in self.install.rglob('*') if p.is_file()}
        ui = self.ui()
        ui.open_triage()
        self.finish_turn(ui)
        self.assertEqual(ui.triage_classification, 'tool bug')
        for char in '/do 1':
            ui.handle_key(ord(char))
        ui.handle_key(10)
        self.finish_turn(ui)
        draft = self.project / '.uncle/workflow/triage-issue-1.md'
        self.assertTrue(draft.exists(), ui.triage_history)
        self.assertIn('# jq crash', draft.read_text())
        self.assertEqual(before, {p: p.read_bytes() for p in self.install.rglob('*') if p.is_file()})
        self.assertIn('\tAPPLIED\t.uncle/workflow/triage-issue-1.md\t',
                      (self.project / '.uncle/workflow/triage-actions.tsv').read_text())

    def test_accepted_plan_edit_is_applied_and_resume_relaunches(self):
        os.environ['FAKE_MASTER_ACTION'] = 'edit-plan'
        (self.project / 'IMPLEMENTATION_NOTES.md').write_text('# notes\n')
        (self.project / '.uncle/workflow/logs/execute-checklist.jsonl').write_text('expected 200, got 500 from /health\n')
        ui = self.ui()
        ui.open_triage()
        self.finish_turn(ui)
        ui._triage_command('/do 2')
        self.finish_turn(ui)
        self.assertEqual((self.project / 'CHANGE_PLAN.md').read_text(), '# plan edited by triage\n')
        tsv = (self.project / '.uncle/workflow/triage-actions.tsv').read_text()
        self.assertIn('\tAPPLIED\tCHANGE_PLAN.md\t', tsv)
        self.assertIn('Deviation (triage): `CHANGE_PLAN.md`', (self.project / 'IMPLEMENTATION_NOTES.md').read_text())
        self.assertFalse((self.project / '.uncle/workflow/triage/sandbox').exists())
        with patch.object(ui, 'start_workflow') as start:
            start.side_effect = lambda: setattr(ui, 'state', 'running')
            for char in '/resume':
                ui.handle_key(ord(char))
            ui.handle_key(10)
            start.assert_called_once()
        self.assertEqual(ui.state, 'running')

    def test_execute_turn_with_no_reply_text_still_reports_what_it_applied(self):
        # A real stuck run: kimi-code made the requested edit -- the guard's
        # own diff proves it -- but returned no reply text at all. Left
        # silent, that reads as if nothing happened, and a repeated /do N
        # then fails with the generic "no proposal is selectable", with no
        # hint the edit already landed and /resume is next.
        os.environ['FAKE_MASTER_ACTION'] = 'edit-plan-empty-reply'
        (self.project / 'IMPLEMENTATION_NOTES.md').write_text('# notes\n')
        (self.project / '.uncle/workflow/logs/execute-checklist.jsonl').write_text('expected 200, got 500 from /health\n')
        ui = self.ui()
        ui.open_triage()
        self.finish_turn(ui)
        ui._triage_command('/do 2')
        self.finish_turn(ui)
        self.assertEqual((self.project / 'CHANGE_PLAN.md').read_text(), '# plan edited by triage\n')
        self.assertTrue(ui.triage_offer_resume)
        self.assertTrue(any('Applied: CHANGE_PLAN.md' in text for _, text in ui.triage_history))
        self.assertTrue(any('no reply text' in text for _, text in ui.triage_history))
        # No proposals survive an execute turn; the next /do must explain
        # that the prior one already finished, not just say "not selectable".
        with self.assertRaises(ValueError) as ctx:
            ui._triage_do(1)
        self.assertIn('already ran to completion', str(ctx.exception))
        self.assertIn('/resume', str(ctx.exception))

    def test_resume_refused_while_turn_runs_or_driver_alive(self):
        ui = self.ui()
        ui._triage_init()
        ui.triage_request = Mock()
        ui.triage_request.events = queue.Queue()
        ui.state = 'triage'
        with patch.object(ui, 'start_workflow') as start:
            ui._triage_command('/resume')
            start.assert_not_called()
        self.assertIn('still running', ui.triage_error)
        ui.triage_request = None
        ui.proc = Mock()
        ui.proc.poll.return_value = None
        with patch.object(ui, 'start_workflow') as start:
            ui._triage_command('/resume')
            start.assert_not_called()
        self.assertIn('answer its prompt', ui.triage_error)

    def test_runner_error_discards_proposals_and_still_guards(self):
        os.environ['FAKE_MASTER_ACTION'] = 'crash'
        ui = self.ui()
        ui.open_triage()
        self.finish_turn(ui)
        self.assertEqual(ui.triage_proposals, [])
        self.assertIn('model exploded', ui.triage_error)
        self.assertFalse((self.project / '.uncle/workflow/triage/sandbox').exists())

    def test_no_runner_shows_configure_message(self):
        ui = self.ui()
        ui.stage_runner = lambda stage: ''
        ui.open_triage()
        self.assertTrue(ui.recovery_active)
        self.assertNotEqual(ui.state, 'triage')
        self.assertEqual(ui.triage_error, 'Choose a runner in Configure first')
        self.assertIsNone(ui.triage_request)
        ui.handle_key(27)
        self.assertEqual(ui.state, 'chat')

    # --- AR-011: the reply is the assistant stream, per adapter ----------------

    def test_extract_reply_per_adapter_shape(self):
        text = lambda t: json.dumps({'type': 'assistant', 'message': {'content': [{'type': 'text', 'text': t}]}})
        claude = [json.dumps({'type': 'system', 'subtype': 'init'}), text('first'),
                  json.dumps({'type': 'assistant', 'message': {'content': [{'type': 'tool_use', 'name': 'Read'}]}}),
                  text('Classification: tool bug\nProposal 1: x'),
                  json.dumps({'type': 'result', 'subtype': 'success', 'is_error': False, 'result': 'not this'})]
        codex = ['thread.started noise', text('Classification: code defect\nProposal 1: y'),
                 json.dumps({'type': 'result', 'model': '', 'subtype': 'success', 'is_error': 'false', 'num_turns': 1})]
        kimi = [text('Classification: requirement gap\nProposal 1: z'), json.dumps({'type': 'result', 'is_error': 'true', 'error_detail': 'quota'})]
        self.assertEqual(triage_chat.extract_reply(claude), ('Classification: tool bug\nProposal 1: x', ''))
        self.assertEqual(triage_chat.extract_reply(codex), ('Classification: code defect\nProposal 1: y', ''))
        self.assertEqual(triage_chat.extract_reply(kimi), ('Classification: requirement gap\nProposal 1: z', 'quota'))
        self.assertIsNone(triage_chat.parse_reply('Classification: code defect\nProposal 2: skipped'))
        self.assertIsNone(triage_chat.parse_reply('Classification: something else\nProposal 1: x'))
        parsed = triage_chat.parse_reply('why\nClassification: Needs Owner Decision\nProposal 1: a\nProposal 2: b\nProposal 3: c\nOffer: resume')
        self.assertEqual(parsed['classification'], 'needs owner decision')
        self.assertEqual(len(parsed['proposals']), 3)
        self.assertTrue(parsed['offer_resume'])

    def test_config_offers_recovery_separately(self):
        self.assertIn(('triage', tui.AGENT), tui.STAGES)
        self.assertIn('triage', tui.CONFIG_STAGES)  # Keep persisted settings compatible.
        ui = self.ui()
        ui.config_section = 'stages'
        self.assertNotIn('triage', tui.BUILD_CONFIG_STAGES)
        self.assertFalse(any(row.startswith('triage ') for row in ui._config_items()))
        ui.config_section = 'recovery'
        ui.config_sel = 0
        self.assertEqual(ui._config_row(), 'triage')
        self.assertIn('Recovery model', ui._config_items()[0])

    def test_do_no_edit_proposal_skips_the_master(self):
        ui = self.ui()
        ui._triage_init()
        ui.recovery_active = True
        ui.triage_proposals = [(1, 'Resume as is; no files edited.')]
        ui._triage_do(1)
        self.assertIsNone(ui.triage_request)
        self.assertEqual(self.prompts(), [])
        self.assertTrue(ui.triage_offer_resume)
        self.assertTrue(any('/do 1' in text for _, text in ui.triage_history))
        self.assertTrue(any('No files changed.' in text for _, text in ui.triage_history))

    def test_do_edit_proposal_still_uses_the_master(self):
        ui = self.ui()
        ui._triage_init()
        ui.triage_proposals = [(2, 'Edit CHANGE_PLAN.md to record the fix.')]
        ui._triage_do(2)
        self.assertIsNotNone(ui.triage_request)
        self.finish_turn(ui)
        self.assertTrue(ui.triage_offer_resume)
        self.assertTrue(any('/do 2' in text for _, text in ui.triage_history))

    def test_master_reply_streams_before_completion(self):
        stub = Path(self.tmp.name) / 'streamer.py'
        stub.write_text(
            'import json,time,sys\n'
            'def say(t):\n'
            '    print(json.dumps({"type":"assistant","message":{"content":[{"type":"text","text":t}]}}))\n'
            '    sys.stdout.flush()\n'
            'say("part one")\n'
            'time.sleep(1)\n'
            'say("part two and done")\n')
        log = Path(self.tmp.name) / 'stream.jsonl'
        request = triage_chat.TriageRequest([sys.executable, str(stub)], 'prompt', dict(os.environ),
                                            str(self.project), str(log))
        events = []
        deadline = time.time() + 15
        empties = 0
        while time.time() < deadline and empties < 10:
            try:
                events.append(request.events.get(timeout=0.2))
                empties = 0
            except queue.Empty:
                empties += 1
            if events and events[-1][0] == 'reply':
                break
        kinds = [kind for kind, _ in events]
        self.assertIn('delta', kinds)
        self.assertEqual(kinds[-1], 'reply')
        self.assertLess(kinds.index('delta'), kinds.index('reply'))
        deltas = [value for kind, value in events if kind == 'delta']
        self.assertEqual(deltas[0], 'part one')
        self.assertEqual(deltas[-1], 'part two and done')

    def test_poll_triage_streams_and_clears(self):
        ui = self.ui()
        ui._triage_init()
        ui.triage_request = Mock()
        ui.triage_request.events = queue.Queue()
        ui.triage_pending = None
        ui.triage_request.events.put(('delta', 'forming'))
        self.assertTrue(ui.poll_triage())
        self.assertEqual(ui.triage_stream, 'forming')
        ui.triage_request.events.put(('delta', 'forming more'))
        self.assertTrue(ui.poll_triage())
        self.assertEqual(ui.triage_stream, 'forming more')
        ui.triage_request.events.put(('reply', 'final text'))
        ui.triage_pending = {'mode': 'diagnosis', 'digest': ''}
        ui._triage_guard = Mock(return_value={'applied': [], 'refused': [], 'failed': [],
                                              'no_edit': False, 'tainted': False, 'messages': []})
        self.assertTrue(ui.poll_triage())
        self.assertEqual(ui.triage_stream, '')
        self.assertIn(('master', 'final text'), ui.triage_history)


if __name__ == '__main__':
    unittest.main()
