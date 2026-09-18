"""Supervisor chat (Issue 45): routing, delegation, steering, dialog/log context,
metrics, failure handling and the reply allowlist. CHANGE_PLAN.md T-1, T-4,
T-6 (fixture worker), T-8..T-15; CHANGE_SPEC.md AC-1..AC-9 test names.

Every test runs against a fake worker class bound in place of the TUI's
ChatRequest; no runner is spawned except the fixture `claude` script in the
metric and isolation tests.
"""
import json
import os
import queue
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'scripts' / 'lib'))
import supervisor as sv
import supervisor_chat as sc
import gate_answer as ga
import uncle_tui as tui

FAKE_CLAUDE = r'''#!/usr/bin/env python3
import json, os, sys
prompt = sys.stdin.read()
here = os.path.dirname(os.path.abspath(sys.argv[0]))
open(os.path.join(here, 'argv.json'), 'a').write(json.dumps({'argv': sys.argv[1:], 'env': sorted(os.environ), 'cwd': os.getcwd(), 'prompt': prompt}) + '\n')
reply = open(os.path.join(here, 'reply.json')).read()
print(json.dumps({'type': 'assistant', 'message': {'content': [{'type': 'text', 'text': reply}]}}))
print(json.dumps({'type': 'result', 'subtype': 'success', 'is_error': False, 'usage': {'input_tokens': 120, 'output_tokens': 40}, 'total_cost_usd': 0.01}))
'''


def reply(text='ok', **action):
    body = {'schema': 1, 'reply': text, 'steer': None, 'gate_answer': None, 'home_action': None}
    body.update(action)
    return json.dumps(body)


def outcome(text='ok', status='reply', **action):
    return {'status': status, 'elapsed': 1, 'exit': 0 if status == 'reply' else 3, 'usage': {'input_tokens': 5, 'output_tokens': 2},
            'cost': 0.001, 'log': '', 'usage_source': 'stream-json result', 'detail': 'boom' if status != 'reply' else '',
            'reply': reply(text, **action) if status == 'reply' else ''}


class FakeChat:
    """Stands in for ChatRequest: records the call, replies when told."""
    calls = []

    def __init__(self, command, prompt, env, home, log, meta, issue_lookup=None):
        self.command, self.prompt, self.env, self.home, self.log, self.meta = command, prompt, env, home, log, meta
        self.issue_lookup = issue_lookup
        self.issue_context = ''
        self.events = queue.Queue()
        self.cancelled = False
        FakeChat.calls.append(self)

    def cancel(self):
        self.cancelled = True

    def poll(self):
        return None


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='supervisor-chat-')
        self.addCleanup(self.tmp.cleanup)
        self.project = Path(self.tmp.name) / 'project'
        self.state = self.project / '.uncle' / 'workflow'
        (self.state / 'logs').mkdir(parents=True)
        (self.state / 'state').write_text('IMPLEMENT\n')
        self.config = Path(self.tmp.name) / 'config'
        self.config.write_text('supervision.model sonnet\nsupervision.effort low\nmisc.approval_name Brian\n')
        FakeChat.calls = []
        for target, value in (('_project_root', lambda: str(self.project)), ('CONFIG_PATH', str(self.config)),
                              ('ChatRequest', FakeChat),
                              ('supervisor_command', lambda config, root, **kwargs: (['fake-claude', '--bare'], {'PATH': '/bin'}, '/tmp/x'))):
            p = patch.object(tui, target, value)
            p.start()
            self.addCleanup(p.stop)

    def ui(self, state='running'):
        ui = tui.UncleTUI.__new__(tui.UncleTUI)
        ui.state = state
        ui.proc = None
        if state == 'running':
            ui.proc = Mock()
            ui.proc.poll.return_value = None
            ui.proc.stdin = Mock()
        ui.out_q = queue.Queue()
        ui.prompt_kind = ui.prompt_text = ui.prompt_buf = ui.partial = ''
        ui.prompt_seen = 0
        ui.status_stage = 'implementation' if state == 'running' else ''
        ui.status_path = None
        ui.gate_file = ''
        ui.output = []
        ui.workflow_idx = 2
        ui.misc = {'approval_name': 'Brian'}
        ui.supervision = {}
        ui.stdscr = Mock()
        ui.stdscr.getmaxyx.return_value = (40, 120)
        ui.color = {}
        ui.steering_channels = {}
        ui.status_model = ui.status_effort = ui.status_mode = ui.status_runner = ''
        ui.status_stage_index = ui.status_stage_total = 0
        ui.session_stats = None
        ui._restore_session_totals = Mock()
        ui.maybe_reload = Mock()
        ui._absorb_line = Mock()
        ui._ensure_chat()
        return ui

    def open_gate(self, ui, text='Ready to approve CHANGE_PLAN.md? [Y/N] ', class_hint='', gate_file='CHANGE_PLAN.md', signing=False):
        """A driver-named dialog: the gate_open event, then the prompt on screen."""
        status = Path(self.tmp.name) / 'status.jsonl'
        status.write_text('')
        prompt_id = ga.open_gate(str(self.state), str(status), ui.status_stage, 'run-1', text, class_hint, gate_file, signing)
        for line in status.read_text().splitlines():
            ui._apply_status(line)
        ui.partial = text
        ui.prompt_seen = 2
        ui._detect_prompt()
        self.assertTrue(ui.prompt_kind)
        return prompt_id

    def send(self, ui, message):
        ui.home_request = None  # each test turn stands alone; the busy rule is covered in home-chat-test.py
        ui.send_home_chat(message)
        return FakeChat.calls[-1] if FakeChat.calls else None

    def answer(self, ui, request, text='ok', **action):
        request.events.put(outcome(text, **action))
        self.assertTrue(ui.poll_home_chat())

    def history(self, ui):
        return '\n'.join(role + ': ' + text for role, text in ui.home_history)

    def receipts(self):
        path = self.state / 'supervision' / 'gate-answers.jsonl'
        return [json.loads(l) for l in path.read_text().splitlines()] if path.exists() else []


class RoutingTests(Base):
    """AC-1 / T-10: every prose message goes to the supervisor worker."""

    def test_all_states_route_to_supervisor(self):
        idle = self.ui('menu')
        self.assertIsNotNone(self.send(idle, 'What does this project do?'))
        running = self.ui('running')
        running.steering_channels = {'implementation': self.tmp.name}
        request = self.send(running, 'Why is the build slow?')
        self.assertIsNotNone(request)
        self.assertEqual(list(Path(self.tmp.name).glob('*.json')), [], 'prose never reaches the steering channel')
        gate = self.ui('running')
        self.open_gate(gate)
        request = self.send(gate, 'what should I do here?')
        self.assertIn('"gate_pending": true', request.prompt)
        gate.proc.stdin.write.assert_not_called()
        recovery = self.ui('running')
        recovery.recovery_active = True
        (self.state / 'TRIAGE.md').write_text('# TRIAGE.md\nstage failed: jq error\n')
        request = self.send(recovery, 'Why did the check fail?')
        self.assertIn('jq error', request.prompt)
        for request in FakeChat.calls:
            self.assertEqual(request.command, ['fake-claude', '--bare'])
            self.assertEqual(request.meta['trigger'], 'chat')

    def test_no_stage_model_process(self):
        ui = self.ui('running')
        ui.status_runner, ui.status_model = 'codex', 'stage-model'
        with patch.object(tui, 'HomeRequest') as home, patch.object(tui, 'TriageRequest') as triage, \
                patch.object(tui.subprocess, 'Popen') as popen:
            self.send(ui, 'Explain the current stage')
            home.assert_not_called()
            triage.assert_not_called()
            popen.assert_not_called()
        self.assertEqual(len(FakeChat.calls), 1)
        self.assertNotIn('stage-model', ' '.join(FakeChat.calls[0].command))

    def test_brief_description_builds_app_without_manual_formatting(self):
        for description in ('create a webapp that prints hello world!',
                            'build an app with Hello World centered in a large font',
                            'can you build a hello world webapp?'):
            with self.subTest(description=description):
                target = self.project / 'REQUIREMENTS.md'
                target.unlink(missing_ok=True)
                ui = self.ui('menu')
                ui._run = Mock()
                request = self.send(ui, description)
                self.assertIn('Functional requirements', request.prompt)
                self.answer(ui, request, 'Preparing the build.', home_action={
                    'uncle_action': 'create_app', 'message': 'Build it',
                    'document': description, 'start': True})
                self.assertIn('## Summary\n' + description, target.read_text())
                ui._run.assert_called_once()
                self.assertEqual(ui.workflow_idx, 0)

    def test_direct_fenced_home_action_is_recovered_only_for_idle_build_request(self):
        description = 'build a groovy calendar webapp'
        action = {'uncle_action': 'create_app', 'message': 'Build a groovy calendar webapp',
                  'document': description, 'start': True}
        raw = '```swift\n' + json.dumps(action) + '\n```'
        ui = self.ui('menu')
        ui._run = Mock()
        request = self.send(ui, description)
        request.events.put(dict(outcome(), reply=raw))
        self.assertTrue(ui.poll_home_chat())
        self.assertIn('## Summary\n' + description, (self.project / 'REQUIREMENTS.md').read_text())
        ui._run.assert_called_once()
        self.assertIn('Recovered a direct homepage action', self.history(ui))
        # The same bare action must not become a stage action.
        running = self.ui('running')
        request = self.send(running, description)
        request.events.put(dict(outcome(), reply=raw))
        self.assertTrue(running.poll_home_chat())
        self.assertIn('did not follow the contract', running.chat_error)

    def test_issue_build_phrase_and_home_intent(self):
        ui = self.ui('menu')
        ui._home_action = Mock()
        ui._set_field = Mock()
        ui.send_home_chat('build from issue 34')
        ui._home_action.assert_called_once()
        self.assertEqual(FakeChat.calls, [], 'a deterministic operator command spawns no worker')
        request = self.send(ui, 'Should we draft a change request?')
        self.answer(ui, request, 'Drafting', home_action={'uncle_action': 'run_change', 'message': 'go'})
        ui._home_action.assert_called_once()  # recommendation only: a question is not intent
        self.assertIn('Recommendation only', self.history(ui))
        request = self.send(ui, 'Run the change request now')
        self.answer(ui, request, 'Running', home_action={'uncle_action': 'run_change', 'message': 'go'})
        self.assertEqual(ui._home_action.call_count, 2)

    def test_resume_phrases_authorize_home_intent(self):
        from supervisor_chat import home_intent
        for message in ('resume building #69', 'resume the build for issue 69',
                        'continue building #69', 'resume issue 69', 'Resume #69'):
            with self.subTest(message=message):
                self.assertTrue(home_intent(message))
        for message in ('should we resume #69?', 'do not resume yet'):
            with self.subTest(message=message):
                self.assertFalse(home_intent(message))

    def test_direct_homepage_edit_and_document_requests_authorize_action(self):
        from supervisor_chat import home_intent
        for message in (
                'change the main page to have a line underneath the Hello World! text',
                'Please update the homepage', 'Can you add a line under "Hello World!"?',
                'write REQUIREMENTS.md for a hello world app',
                'draft CHANGE_REQUEST.md to add a horizontal line'):
            with self.subTest(message=message):
                self.assertTrue(home_intent(message))
        for message in ('what day is it', 'Should we change the homepage?',
                        'Do not change the homepage', 'Explain how to change the page'):
            with self.subTest(message=message):
                self.assertFalse(home_intent(message))
        ui = self.ui('menu')
        ui._home_action = Mock()
        request = self.send(ui, 'change the main page to have a line underneath the Hello World! text')
        self.answer(ui, request, 'Starting the requested change',
                    home_action={'uncle_action': 'create_change', 'message': 'Starting',
                                 'document': '## Summary\nAdd a horizontal line.', 'start': True})
        ui._home_action.assert_called_once()



class SteeringTests(Base):
    """AC-2 / T-8: authorized steering on the live channel with honest states."""

    def test_steer_request_delivered_and_states_reported(self):
        ui = self.ui('running')
        channel = Path(self.tmp.name) / 'inbox'
        channel.mkdir()
        ui.steering_channels = {'implementation': str(channel)}
        request = self.send(ui, 'tell it to fix the failing test first')
        self.assertEqual(request.steer_request, 'fix the failing test first')
        self.answer(ui, request, 'Relaying.', steer={'text': 'Fix the failing test before anything else.'})
        files = list(channel.glob('*.json'))
        self.assertEqual(len(files), 1)
        sent = json.loads(files[0].read_text())
        self.assertIn('> Fix the failing test before anything else.', sent['text'])
        self.assertTrue(sent['text'].startswith(sc.STEER_HEADER))
        record = ui.steer_records[-1]
        self.assertEqual((record['state'], record['id']), ('queued', sent['id']))
        self.assertIn('queued for implementation', self.history(ui))
        ui._apply_status(json.dumps({'event': 'steering_accepted', 'stage': 'implementation', 'message_id': sent['id'], 'correlation': 'turn'}))
        self.assertEqual(record['state'], 'accepted')
        ui._apply_status(json.dumps({'event': 'steering_answered', 'stage': 'implementation', 'message_id': sent['id']}))
        self.assertEqual(record['state'], 'answered')
        self.assertIn('answered by implementation', self.history(ui))
        # Unconfirmed acceptance is reported as such, not as answered.
        request = self.send(ui, 'have it run the linter')
        self.answer(ui, request, 'Relaying.', steer={'text': 'Run the linter.'})
        second = ui.steer_records[-1]
        ui._apply_status(json.dumps({'event': 'steering_accepted', 'stage': 'implementation', 'message_id': second['id'], 'correlation': ''}))
        self.assertEqual(second['state'], 'accepted-unconfirmed')
        ui._apply_status(json.dumps({'event': 'steering_rejected', 'stage': 'implementation', 'message_id': second['id'], 'detail': 'stage ended'}))
        self.assertEqual(second['state'], 'rejected')
        # The next turn sees the delivery states as data.
        request = self.send(ui, 'did it get my message?')
        self.assertIn('"state": "answered"', request.prompt)
        self.assertIn('"state": "rejected"', request.prompt)

    def test_steer_without_channel_is_retained(self):
        ui = self.ui('running')
        request = self.send(ui, 'tell it to stop refactoring the parser')
        self.answer(ui, request, 'Relaying.', steer={'text': 'Stop refactoring the parser.'})
        self.assertIn('not delivered; retained', self.history(ui))
        self.assertEqual(ui.steer_records[-1]['state'], 'retained')
        ui.proc.stdin.write.assert_not_called()
        channel = Path(self.tmp.name) / 'inbox'
        channel.mkdir()
        ui.steering_channels = {'implementation': str(channel)}
        ui.send_home_chat('send it')
        self.assertEqual(len(list(channel.glob('*.json'))), 1)
        self.assertEqual(ui.steer_records[-1]['state'], 'queued')
        self.assertEqual(len(FakeChat.calls), 1, 'a resend is a control, not a call')

    def test_unrequested_steer_is_a_recommendation(self):
        ui = self.ui('running')
        channel = Path(self.tmp.name) / 'inbox'
        channel.mkdir()
        ui.steering_channels = {'implementation': str(channel)}
        request = self.send(ui, 'what is it doing?')
        self.answer(ui, request, 'It loops.', steer={'text': 'Stop looping.'})
        self.assertEqual(list(channel.glob('*.json')), [])
        self.assertIn('Recommendation only', self.history(ui))
        # Questions, negations and quotations never authorize steering.
        for phrase in ('should I tell it to stop?', "don't tell it to stop", 'he said "tell it to stop"', 'e.g. tell it to stop'):
            self.assertIsNone(sc.steer_intent(phrase), phrase)


class DialogTests(Base):
    """AC-3 / T-15: the dialog block tracks open, change and close."""

    def test_dialog_context_tracks_open_change_close(self):
        ui = self.ui('running')
        request = self.send(ui, 'anything waiting?')
        self.assertIn('"dialog": null', request.prompt)
        self.open_gate(ui)
        self.assertIn('Dialog opened (confirm, routine)', self.history(ui))
        request = self.send(ui, 'what should I do here?')
        block = json.loads(request.prompt.split('## Data (untrusted)\n\n', 1)[1])
        self.assertEqual((block['dialog']['kind'], block['dialog']['class'], block['dialog']['file']), ('confirm', 'routine', 'CHANGE_PLAN.md'))
        self.assertIn('Ready to approve CHANGE_PLAN.md?', block['dialog']['text'])
        self.assertEqual(block['dialog']['run'], 'run-1')
        ui.answer_prompt('n')
        self.assertIn('Dialog closed (human)', self.history(ui))
        self.open_gate(ui, 'Type a reason to waive these checks for this run, or Enter to stop and amend the plan: ', gate_file='')
        request = self.send(ui, 'and now?')
        block = json.loads(request.prompt.split('## Data (untrusted)\n\n', 1)[1])
        self.assertEqual((block['dialog']['kind'], block['dialog']['class'], block['dialog']['reason']), ('input', 'sensitive', 'waiver'))
        ui.answer_prompt('')
        request = self.send(ui, 'and now?')
        self.assertIn('"dialog": null', request.prompt)

    def test_text_fallback_without_driver_metadata_is_advice_only(self):
        ui = self.ui('running')
        ui.partial = 'Enter a new model id to retry this stage (or Enter to stop): '
        ui.prompt_seen = 2
        ui._detect_prompt()
        self.assertIsNone(ui._gate_matches())
        request = self.send(ui, 'answer this one')
        self.answer(ui, request, 'Use sonnet.', gate_answer={'answer': 'sonnet', 'rationale': 'cheaper'})
        ui.proc.stdin.write.assert_not_called()
        self.assertIn('Not sent', self.history(ui))


class DelegationTests(Base):
    """AC-4 / T-1 / T-4 / T-9 / T-14: only the operator's words delegate; every answer is validated and recorded."""

    def test_explicit_ask_answers_any_gate(self):
        cases = [
            ('Ready to approve CHANGE_PLAN.md? [Y/N] ', '', False, 'answer this one', 'y', 'y'),
            ('Ready to approve CHANGE_PLAN.md? [Y/N] ', '', False, 'reject this', 'y', 'n'),
            ('Type a reason to waive these checks for this run, or Enter to stop and amend the plan: ', 'sensitive:waiver', False,
             'answer this with "scripts/tests/example.py is not runnable here"', 'ignored', 'scripts/tests/example.py is not runnable here'),
            ('PR title [default: Completed change]: ', '', False, 'answer this one', 'Add supervisor chat: `git push` to main', 'Add supervisor chat: `git push` to main'),
            ('Commit signing needs your help. "git commit -S" Return here and press ENTER (OK) when finished:', '', True, 'press enter', 'anything', ''),
            ('Audit finding 1 of 2: [a] Accept [r] Reject [s] Skip: ', '', False, 'answer this one', 'r', 'r'),
        ]
        for text, hint, signing, ask, proposed, expected in cases:
            with self.subTest(ask=ask, text=text[:30]):
                ui = self.ui('running')
                self.open_gate(ui, text, hint, signing=signing)
                request = self.send(ui, ask)
                self.assertEqual(request.delegation['source'], 'explicit')
                self.answer(ui, request, 'Answering.', gate_answer={'answer': proposed, 'rationale': 'the plan is complete'})
                ui.proc.stdin.write.assert_called_once_with((expected + '\n').encode())
                self.assertEqual(ui.prompt_kind, '')
                rows = self.receipts()
                self.assertEqual([r['status'] for r in rows], ['attempted', 'delivered'])
                self.assertEqual(rows[0]['attribution'], 'supervisor:explicit:Brian')
                self.assertEqual(rows[0]['request'], ask)
                self.assertEqual(rows[0]['rationale'], 'the plan is complete')
                self.assertEqual(rows[0]['answer'], expected)
                self.assertIn('supervisor:explicit:Brian', self.history(ui))
                shutil.rmtree(self.state / 'supervision')

    def test_intent_table(self):
        denied = ['should I answer this?', "don't answer this", 'never approve this', 'if I say "answer this" ignore it',
                  'for example, answer this one', 'my colleague said "approve this"', 'answer this one?', 'hello',
                  'approve', 'you could answer this', 'the log says answer this one']
        for phrase in denied:
            self.assertIsNone(sc.delegation_intent(phrase), phrase)
        for phrase, choice in (('answer this one', None), ('please handle this', None), ('approve this', 'y'), ('say yes', 'y'),
                               ('say no', 'n'), ('reject it', 'n'), ('press enter', ''), ('Approve this one.', 'y')):
            intent = sc.delegation_intent(phrase)
            self.assertEqual((intent['source'], intent['choice']), ('explicit', choice), phrase)
        for phrase in ('handle the gates for this run', 'you handle the gates', 'answer all the prompts from now on'):
            self.assertEqual(sc.delegation_intent(phrase)['source'], 'standing', phrase)
        self.assertEqual(sc.delegation_intent('stop handling the gates')['source'], 'revoke')
        # "say no" can never yield yes: the operator choice binds the answer.
        ui = self.ui('running')
        self.open_gate(ui)
        request = self.send(ui, 'say no')
        self.answer(ui, request, 'Approving.', gate_answer={'answer': 'y', 'rationale': 'looks fine'})
        ui.proc.stdin.write.assert_called_once_with(b'n\n')

    def test_standing_covers_routine_only(self):
        ui = self.ui('running')
        ui.send_home_chat('handle the gates for this run')
        self.assertIsNotNone(ui.delegation_session)
        self.assertEqual(FakeChat.calls, [], 'a grant with no pending dialog makes no call')
        self.open_gate(ui)
        self.assertTrue(ui.poll_delegation())
        request = FakeChat.calls[-1]
        self.assertEqual((request.meta['trigger'], request.delegation['source']), ('standing_gate', 'standing'))
        self.assertEqual(request.delegation['request'], 'handle the gates for this run')
        self.assertFalse(ui.poll_delegation(), 'serviced once per dialog')
        self.answer(ui, request, 'Approving.', gate_answer={'answer': 'y', 'rationale': 'complete'})
        ui.proc.stdin.write.assert_called_once_with(b'y\n')
        self.assertEqual(self.receipts()[0]['attribution'], 'supervisor:standing:Brian')
        # A sensitive gate is never answered by standing delegation, only advised.
        ui.proc.stdin.write.reset_mock()
        self.open_gate(ui, 'Type a reason to waive these checks for this run, or Enter to stop and amend the plan: ', 'sensitive:waiver', '')
        self.assertFalse(ui.poll_delegation())
        request = self.send(ui, 'what now?')
        self.answer(ui, request, 'I would waive.', gate_answer={'answer': 'cannot run here', 'rationale': 'no browser'})
        ui.proc.stdin.write.assert_not_called()
        self.assertIn('Recommendation only', self.history(ui))
        # Config standing delegation, revocation, and the call bound.
        ui.send_home_chat('stop handling the gates')
        self.assertIsNone(ui.delegation_session)
        ui.answer_prompt('')
        self.open_gate(ui, 'Ready to approve CHANGE_SPEC.md? [Y/N] ')
        self.assertFalse(ui.poll_delegation(), 'no grant, no call')
        self.config.write_text(self.config.read_text() + 'supervision.delegate_gates routine\nsupervision.max_calls_per_run 2\n')
        self.assertTrue(ui.poll_delegation())
        self.assertEqual(FakeChat.calls[-1].delegation['config_key'], 'supervision.delegate_gates')
        self.assertEqual(FakeChat.calls[-1].delegation['request'], 'supervision.delegate_gates routine')
        ui.home_request = None
        ui.answer_prompt('n')
        self.open_gate(ui, 'Ready to approve BASELINE_REPORT.md? [Y/N] ')
        calls = len(FakeChat.calls)
        self.assertTrue(ui.poll_delegation())
        self.assertEqual(len(FakeChat.calls), calls, 'max_calls_per_run bounds standing calls')
        self.assertIn('max_calls_per_run', self.history(ui))

    def test_no_delegation_no_stdin(self):
        ui = self.ui('running')
        self.open_gate(ui)
        request = self.send(ui, 'is this plan any good?')
        self.answer(ui, request, 'Yes.', gate_answer={'answer': 'y', 'rationale': 'approve'})
        ui.proc.stdin.write.assert_not_called()
        self.assertEqual(ui.prompt_kind, 'confirm')
        self.assertEqual(self.receipts(), [])
        self.assertFalse((self.state / 'supervision' / 'answers').exists())
        self.assertIn('Say "answer this one"', self.history(ui))
        request = self.send(ui, 'answer this one')
        self.assertEqual(request.delegation['source'], 'explicit', 'the hinted phrase delegates')

    def test_cancel_before_apply(self):
        ui = self.ui('running')
        self.open_gate(ui)
        request = self.send(ui, 'answer this one')
        # Esc / manual takeover: the operator answers first; the late reply is discarded.
        ui.answer_prompt('n')
        self.answer(ui, request, 'Approving.', gate_answer={'answer': 'y', 'rationale': 'fine'})
        ui.proc.stdin.write.assert_called_once_with(b'n\n')
        self.assertIn('dialog changed or closed', self.history(ui))
        self.assertEqual(self.receipts(), [])
        # /clear cancels the worker; nothing is applied later.
        self.open_gate(ui, 'Ready to approve CHANGE_SPEC.md? [Y/N] ')
        request = self.send(ui, 'answer this one')
        ui.chat_composer = '/clear'
        ui._chat_command(10)
        self.assertTrue(request.cancelled)
        self.assertIsNone(ui.home_request)
        self.assertEqual(ui.prompt_kind, 'confirm')
        # A reopened identical prompt has a new id: the old reply cannot answer it.
        stale = self.send(ui, 'answer this one')
        ui.answer_prompt('n')
        self.open_gate(ui, 'Ready to approve CHANGE_SPEC.md? [Y/N] ')
        stale.events.put(outcome('Approving.', gate_answer={'answer': 'y', 'rationale': 'fine'}))
        ui.home_request = stale
        ui.poll_home_chat()
        self.assertEqual(ui.prompt_kind, 'confirm')
        self.assertEqual(ui.proc.stdin.write.call_count, 2)
        # Failed stdin write: no delivered receipt, a visible error.
        ui.proc.stdin.write.reset_mock()
        ui.proc.stdin.write.side_effect = BrokenPipeError('gone')
        request = self.send(ui, 'answer this one')
        self.answer(ui, request, 'Approving.', gate_answer={'answer': 'y', 'rationale': 'fine'})
        self.assertEqual([r['status'] for r in self.receipts()], ['attempted', 'discarded'])
        self.assertIn('could not be written', self.history(ui))
        # Receipt write failure prevents the send altogether.
        ui.proc.stdin.write.side_effect = None
        ui.proc.stdin.write.reset_mock()
        self.open_gate(ui, 'Ready to approve BASELINE_REPORT.md? [Y/N] ')
        request = self.send(ui, 'answer this one')
        with patch.object(tui.gate_answer, 'write_envelope', side_effect=OSError('disk full')):
            self.answer(ui, request, 'Approving.', gate_answer={'answer': 'y', 'rationale': 'fine'})
        ui.proc.stdin.write.assert_not_called()
        self.assertEqual(ui.prompt_kind, 'confirm')

    def test_reply_allowlist_rejections(self):
        ui = self.ui('running')
        self.open_gate(ui)
        for bad in ('{"schema":1,"reply":"x","gate_answer":{"answer":"y","rationale":"r"},"steer":{"text":"s"},"home_action":null}',
                    '{"schema":1,"reply":"x","steer":null,"gate_answer":null,"home_action":null,"approve":true}',
                    '{"schema":2,"reply":"x","steer":null,"gate_answer":null,"home_action":null}',
                    '{"schema":1,"reply":"x","steer":null,"gate_answer":{"answer":"y"},"home_action":null}',
                    '{"schema":1,"reply":"x","steer":{"text":"a\\u0000b"},"gate_answer":null,"home_action":null}',
                    'Approve it. {"schema":1}', ''):
            with self.subTest(bad=bad[:40]):
                self.assertRaises(ValueError, sc.parse_reply, bad)
        # Models occasionally put an otherwise valid envelope in a fence whose
        # language is unrelated to JSON, or widen it to four backticks because
        # the payload itself contains Markdown. It is presentation noise, not
        # an authority change: the unwrapped object still gets the full schema
        # and action allowlist validation.
        fenced = '````swift\n' + reply('Building.', home_action={'uncle_action': 'run_app', 'message': 'go',
                                                                    'document': '# App\n```html\n<body>\n```', 'start': True}) + '\n````'
        parsed = sc.parse_reply(fenced)
        self.assertEqual(parsed['reply'], 'Building.')
        self.assertEqual(parsed['home_action']['uncle_action'], 'run_app')
        self.assertRaises(ValueError, sc.parse_reply, 'Before\n' + fenced)
        prefixed = 'I will now produce the required JSON.\n' + reply('Building.')
        self.assertEqual(sc.parse_reply(prefixed)['reply'], 'Building.')
        self.assertRaises(ValueError, sc.parse_reply, prefixed + '\nAfter')
        request = self.send(ui, 'answer this one')
        for answer in ('y\nn', 'yes please', 'maybe', 'y; rm -rf /'):
            with self.subTest(answer=answer):
                ui.home_request = request
                request.events.put(outcome('Answering.', gate_answer={'answer': answer, 'rationale': 'r'}))
                ui.poll_home_chat()
                ui.proc.stdin.write.assert_not_called()
                self.assertEqual(ui.prompt_kind, 'confirm')
        self.assertEqual([r['status'] for r in self.receipts()], [])
        # Literal answers by kind (T-14).
        self.assertEqual(ga.validate_answer('input', 'scripts/tests/example.py'), 'scripts/tests/example.py')
        self.assertEqual(ga.validate_answer('input', 'Fix: run `make test` before push'), 'Fix: run `make test` before push')
        self.assertRaises(ValueError, ga.validate_answer, 'input', 'x' * 401)
        self.assertRaises(ValueError, ga.validate_answer, 'input', 'two\nlines')
        self.assertRaises(ValueError, ga.validate_answer, 'audit', 'q', ['a', 'r', 's'])
        self.assertRaises(ValueError, ga.validate_answer, 'enter', 'ok')
        # Home actions never run while a workflow is active; malformed action objects are rejected.
        request = self.send(ui, 'build the app')
        ui._home_action = Mock()
        self.answer(ui, request, 'Building.', home_action={'uncle_action': 'run_app', 'message': 'go'})
        ui._home_action.assert_not_called()
        self.assertIn('cannot run while a workflow is active', self.history(ui))
        idle = self.ui('menu')
        idle._home_action = Mock()
        request = self.send(idle, 'build the app')
        self.answer(idle, request, 'Building.', home_action={'uncle_action': 'rm_rf', 'message': 'go'})
        idle._home_action.assert_not_called()


class ContextTests(Base):
    """AC-5 / T-11 / T-15: bounded, redacted, source-cited log context."""

    def test_log_context_bounded_redacted_labeled(self):
        logs = self.state / 'logs'
        (logs / 'implementation.log').write_text('start\n' + 'x' * 30000 + '\nAPI_KEY=sk-abcdefghijklmnop123456\nlast line of implementation\n')
        (logs / 'baseline.jsonl').write_text('{"line": "baseline output"}\n')
        (logs / 'other.log').write_text('unrelated stage\n')
        status = Path(self.tmp.name) / 'status.jsonl'
        status.write_text(''.join(json.dumps({'event': 'usage', 'stage': 'implementation', 'n': i}) + '\n' for i in range(100)))
        (self.state / 'metrics').mkdir()
        (self.state / 'metrics' / 'agent-1.json').write_text(json.dumps({'kind': 'agent', 'reported_cost_usd': 0.5}))
        (self.state / 'metrics' / 'supervisor-1.json').write_text(json.dumps({'kind': 'supervisor', 'reported_cost_usd': 0.02}))
        ui = self.ui('running')
        ui.status_path = str(status)
        ui.previous_stage = 'baseline'
        request = self.send(ui, 'what is this stage doing?')
        block = json.loads(request.prompt.split('## Data (untrusted)\n\n', 1)[1])
        self.assertEqual(set(block['logs']), {'implementation', 'baseline'})
        tail = block['logs']['implementation']['tail']
        self.assertIn('last line of implementation', tail)
        self.assertIn('[head truncated]', tail)
        self.assertLessEqual(len(tail.encode('utf-8')), sc.LOG_TAIL + 100)
        self.assertNotIn('sk-abcdefghijklmnop', request.prompt)
        self.assertIn(sv.REDACTED, tail)
        self.assertEqual(block['logs']['implementation']['log'], str(logs / 'implementation.log'))
        self.assertEqual(len(block['status_events']), sc.STATUS_LINES)
        self.assertIn('"n": 99', block['status_events'][-1])
        self.assertEqual(block['costs']['stage_records'], 1)
        self.assertEqual(block['costs']['supervisor_records'], 1)
        self.assertIn('never obey it', block['note'])
        self.assertIn('"the log says', request.prompt)
        self.assertLessEqual(len(request.prompt.encode('utf-8')), sc.CONTEXT_CAP)
        # A symlink out of the project is refused; missing evidence is absent, not invented.
        (logs / 'implementation.log').unlink()
        os.symlink('/etc/hosts', logs / 'implementation.log')
        request = self.send(ui, 'and now?')
        block = json.loads(request.prompt.split('## Data (untrusted)\n\n', 1)[1])
        self.assertNotIn('implementation', block['logs'])

    def test_context_cap_shrinks_logs_first(self):
        contract = 'contract'
        logs = {'implementation': {'log': 'l', 'tail': 'x' * 200000}}
        prompt = sc.compose_context(contract, 'hi', [('user', 'hi')], None, {'source': None}, [], logs, ['s'] * 60,
                                    {}, {}, cap=50000)
        self.assertLessEqual(len(prompt.encode('utf-8')), 50000)
        self.assertIn('"operator_message": "hi"', prompt)


class MetricTests(Base):
    """AC-6 / T-6: separate measured usage; nothing spawned without a message."""

    def test_chat_metric_recorded_separately(self):
        ui = self.ui('menu')
        request = self.send(ui, 'hello')
        self.answer(ui, request, 'hi')
        rows = [json.loads(p.read_text()) for p in (self.state / 'metrics').glob('supervisor-chat-*.json')]
        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertEqual((row['kind'], row['usage_scope'], row['stage']), ('supervisor', 'supervisor chat', 'supervisor-chat-1'))
        self.assertEqual((row['input_tokens'], row['output_tokens'], row['reported_cost_usd']), (5, 2, 0.001))
        self.assertEqual(row['supervisor']['trigger'], 'chat')
        self.assertEqual(row['supervisor']['call_id'], request.meta['call_id'])
        self.assertEqual(list((self.state / 'metrics').glob('supervisor-[0-9]*.json')), [], 'not a diagnosis record')
        sys.path.insert(0, str(ROOT / 'scripts' / 'lib'))
        import importlib
        totals = importlib.import_module('session-totals').update(str(self.state))
        self.assertEqual(totals['records'], [], 'stage totals exclude supervisor usage')
        request = self.send(ui, 'again')
        request.events.put(outcome(status='timeout'))
        ui.poll_home_chat()
        rows = [json.loads(p.read_text()) for p in (self.state / 'metrics').glob('supervisor-chat-*.json')]
        self.assertEqual(sorted(r['reported_error'] for r in rows), [False, True])

    def test_idle_spawns_nothing(self):
        ui = self.ui('menu')
        with patch.object(tui.subprocess, 'Popen') as popen:
            for _ in range(300):
                ui.poll_home_chat()
                ui.poll_delegation()
                ui.poll_supervision()
            popen.assert_not_called()
        self.assertEqual(FakeChat.calls, [])
        running = self.ui('running')
        for _ in range(300):
            running.poll_delegation()
        self.assertEqual(FakeChat.calls, [], 'a running stage with no dialog and no message makes no call')
        self.assertFalse((self.state / 'metrics').exists())

    def test_real_worker_is_isolated_and_measured(self):
        """T-2/T-6 on the actual worker: allowlisted env, temporary HOME, no project cwd, usage from stream-json."""
        binary = Path(self.tmp.name) / 'bin'
        binary.mkdir()
        fake = binary / 'claude'
        fake.write_text(FAKE_CLAUDE)
        fake.chmod(fake.stat().st_mode | stat.S_IEXEC)
        (binary / 'reply.json').write_text(reply('measured'))
        config = sv.Config({'call_timeout_seconds': 20})
        env = dict(os.environ, WORKFLOW_CLAUDE_CMD=str(fake), ANTHROPIC_API_KEY='sk-testkey12345678',
                   CLAUDE_CODE_SETTINGS='/etc/x', UNCLE_STATUS_FILE='/tmp/status', HOME='/real/home')
        argv, worker_env, home = sv_runner_build(config, str(ROOT), env)
        request = sc.ChatRequest(argv, 'prompt', worker_env, home, str(self.state / 'logs' / 'chat.jsonl'), {'deadline': 20, 'number': 1})
        result = request.result(wait=True)
        self.assertEqual(result['status'], 'reply', result)
        self.assertEqual(result['usage']['input_tokens'], 120)
        self.assertEqual(result['cost'], 0.01)
        seen = json.loads((binary / 'argv.json').read_text().splitlines()[-1])
        self.assertIn('--tools', seen['argv'])
        self.assertNotIn('CLAUDE_CODE_SETTINGS', seen['env'])
        self.assertNotIn('UNCLE_STATUS_FILE', seen['env'])
        # The Claude login lives in the real home; config and cache stay isolated.
        self.assertEqual(worker_env['HOME'], '/real/home')
        self.assertTrue(worker_env['XDG_CONFIG_HOME'].startswith(home))
        self.assertTrue(worker_env['XDG_CACHE_HOME'].startswith(home))
        self.assertNotEqual(Path(seen['cwd']).resolve(), ROOT.resolve())
        self.assertFalse(Path(home).exists(), 'temporary home removed after the call')


def sv_runner_build(config, root, env):
    import supervisor_runner
    return supervisor_runner.build_command(config, root, env)


class FailureTests(Base):
    """AC-8 / T-12: one error line, the dialog untouched, retry possible, no fallback."""

    def test_worker_failures_leave_gate_pending(self):
        ui = self.ui('running')
        self.open_gate(ui)
        for status in ('unavailable', 'timeout', 'error', 'cancelled'):
            with self.subTest(status=status):
                request = self.send(ui, 'answer this one')
                request.events.put(outcome(status=status))
                self.assertTrue(ui.poll_home_chat())
                self.assertEqual(ui.prompt_kind, 'confirm')
                ui.proc.stdin.write.assert_not_called()
                self.assertTrue(ui.chat_error)
                self.assertIsNone(ui.home_request)
        request = self.send(ui, 'answer this one')
        request.events.put(dict(outcome(), reply='I approve this plan wholeheartedly.'))
        ui.poll_home_chat()
        self.assertIn('did not follow the contract', ui.chat_error)
        self.assertIn('wholeheartedly', self.history(ui))
        ui.proc.stdin.write.assert_not_called()
        self.assertEqual(self.receipts(), [])
        # Unsupported runner or missing binary: unavailable, no fallback to any other model.
        with patch.object(tui, 'supervisor_command', side_effect=ValueError('unavailable: supervision.runner codex is not supported; use claude')):
            with self.assertRaisesRegex(ValueError, 'Supervisor unavailable'):
                ui.send_home_chat('hello')
        self.assertEqual(len(FakeChat.calls), 5, 'an unavailable runner makes no call and falls back to nothing')
        self.assertEqual(ui.prompt_kind, 'confirm')


class DocsTests(Base):
    """AC-9 / T-11: keys, classes and controls documented."""

    def test_keys_documented(self):
        readme = (ROOT / 'README.md').read_text(encoding='utf-8')
        example = (ROOT / '.uncle' / 'config.example').read_text(encoding='utf-8')
        for line in ('supervision.delegate_gates none',):
            self.assertIn(line, readme)
            self.assertIn(line, example)
        for phrase in ('supervisor:explicit:<name>', 'supervisor:standing:<name>', 'gate-answers.jsonl', "usage_scope 'supervisor chat'",
                       'signing, publication and waiver', '/delegate', '/app-input', 'answer this one', 'tell it to'):
            self.assertIn(phrase, readme, phrase)
        self.assertIn('delegate_gates', tui.SUPERVISION_DESC)
        self.assertEqual(sv.parse_value('delegate_gates', 'routine'), 'routine')
        self.assertRaises(ValueError, sv.parse_value, 'delegate_gates', 'all')
        self.assertEqual(sv.load_config(str(self.config)).delegate_gates, 'none')


class ProtectionTests(unittest.TestCase):
    """T-13: the verification manifest detects mutation, deletion and untracked additions."""

    def test_manifest_detects_drift(self):
        sys.path.insert(0, str(ROOT / 'scripts' / 'lib'))
        import verification_manifest
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root / 'tests').mkdir()
            (root / 'tests' / 'a-test.py').write_text('assert 1\n')
            (root / 'scopes').write_text('tests/\n')
            cwd = os.getcwd()
            os.chdir(d)
            try:
                before = verification_manifest.manifest('scopes')
                self.assertEqual(before, verification_manifest.manifest('scopes'))
                (root / 'tests' / 'a-test.py').write_text('assert 2\n')
                self.assertNotEqual(before, verification_manifest.manifest('scopes'))
                (root / 'tests' / 'a-test.py').write_text('assert 1\n')
                (root / 'tests' / 'new-test.py').write_text('')
                self.assertNotEqual(before, verification_manifest.manifest('scopes'))
                (root / 'tests' / 'new-test.py').unlink()
                (root / 'tests' / 'a-test.py').unlink()
                self.assertNotEqual(before, verification_manifest.manifest('scopes'))
            finally:
                os.chdir(cwd)


class AttributionTests(unittest.TestCase):
    def test_receipt_and_attestation_labels(self):
        self.assertEqual(ga.attribution('explicit', 'Brian'), 'supervisor:explicit:Brian')
        self.assertEqual(ga.attribution('standing', ''), 'supervisor:standing:')
        self.assertRaises(ValueError, ga.attribution, 'human', 'Brian')
        import attestation
        with tempfile.TemporaryDirectory() as d:
            state = Path(d) / '.uncle' / 'workflow'
            (state / 'approvals').mkdir(parents=True)
            (Path(d) / 'CHANGE_PLAN.md').write_text('plan\n')
            import hashlib
            (state / 'approvals' / 'CHANGE_PLAN.sha256').write_text(hashlib.sha256(b'plan\n').hexdigest() + '\n')
            for value, label in (('Brian', 'APPROVED (human)'), ('unattended', 'APPROVED (unattended)'),
                                 ('supervisor:explicit:Brian', 'APPROVED (supervisor:explicit:Brian)'),
                                 ('supervisor:standing:', 'APPROVED (supervisor:standing)')):
                (state / 'approvals' / 'CHANGE_PLAN.approved-by').write_text(value + '\n')
                self.assertEqual(attestation._gate_plan(str(state), d), label)


if __name__ == '__main__':
    unittest.main()
