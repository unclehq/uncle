"""Auto mode stops at the publication boundary (Issue 48, CHANGE_PLAN.md T-1..T-10).

Driver cases run scripts/change-workflow.sh from COMPLETE in a disposable
origin-less repository (pr-originless-test.py pattern) with a git shim that
records calls and a fake gh. Signing is isolated: fixture Git disables it,
and only T-4/T-5 sign, with a disposable SSH key kept inside the fixture.
TUI cases reuse the supervisor-chat-test.py harness (no runner is spawned).
"""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import Mock

ROOT = Path(__file__).resolve().parents[2]
LIB = ROOT / 'scripts/lib/change-pr.sh'
DRIVER = ROOT / 'scripts/change-workflow.sh'
SOURCE = LIB.read_text().split("<<'PY'", 1)[1].split('\n', 1)[1].split('\nPY\n', 1)[0]
REAL_GIT = shutil.which('git')
SKIP = 'PR handoff disabled or unattended; no PR was created.'
BOUNDARY = 'Publication boundary: unattended stages ended; a person answers from here.'
PENDING_EOF = 'No answer received; PR remains pending. Rerun to resume.'
LEDGER = '2026-09-14T00:00:00Z\tCHANGE_PLAN.md\tapproved unattended\n2026-09-14T00:00:01Z\tFINAL_AUDIT\tapproved unattended\n'

GIT_SHIM = '''#!/usr/bin/env bash
printf '%s\\n' "$*" >> "$GIT_CALLS"
if [[ "$1" == remote && "${2:-}" == get-url ]]; then
    "$REAL_GIT" "$@" | while IFS= read -r url; do
        case "$url" in
            "$BASE_BARE") echo 'https://github.com/owner/repo.git' ;;
            *) printf '%s\\n' "$url" ;;
        esac
    done
    exit 0
fi
exec "$REAL_GIT" "$@"
'''

GH_FAKE = '''#!/usr/bin/env python3
import json, os, pathlib, subprocess, sys
args = sys.argv[1:]
with open(os.environ['GH_CALLS'], 'a') as f: f.write(json.dumps(args) + '\\n')
server = pathlib.Path(os.environ['SERVER'])
if args[:2] == ['auth', 'status']: sys.exit(0)
if args[:2] == ['repo', 'view']:
    print(json.dumps({'nameWithOwner': args[2], 'defaultBranchRef': {'name': 'main'}}))
elif args[0] == 'api':
    print(json.dumps({'fork': False, 'owner': {'type': 'User'}}))
elif args[:2] == ['pr', 'list']:
    print(json.dumps(json.loads(server.read_text()) if server.exists() else []))
elif args[:2] == ['pr', 'view']:
    print(json.dumps(json.loads(server.read_text())[0]))
elif args[:2] == ['pr', 'create']:
    branch = subprocess.check_output(['git', 'branch', '--show-current']).decode().strip()
    sha = subprocess.check_output(['git', 'rev-parse', 'HEAD']).decode().strip()
    server.with_suffix('.body').write_text(pathlib.Path(args[args.index('--body-file') + 1]).read_text())
    server.write_text(json.dumps([dict(number=7, url='https://github.com/owner/repo/pull/7',
        headRefName=branch, headRefOid=sha, headRepository={'name': 'repo'},
        headRepositoryOwner={'login': 'owner'}, baseRefName='main')]))
    print('https://github.com/owner/repo/pull/7')
else:
    sys.exit(1)
'''

# A signer that records every invocation and fails: T-10 proves nothing in the
# fixture or the driver ever reaches an inherited signer.
SIGNER = '''#!/usr/bin/env bash
printf '%s\\n' "$*" >> "$SIGNER_CALLS"
exit 1
'''


def isolated_env(**extra):
    env = {k: v for k, v in os.environ.items()
           if not k.startswith(('UNCLE_', 'STAGEGATE_', 'WORKFLOW_', 'GIT_', 'GPG_', 'SSH_'))}
    env.update(GIT_CONFIG_GLOBAL='/dev/null', GIT_CONFIG_NOSYSTEM='1', **extra)
    return env


class Fixture(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='auto-boundary-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.repo = self.root / 'repo'
        self.repo.mkdir()
        self.bin = self.root / 'bin'
        self.bin.mkdir()
        self.bare = self.root / 'remote.git'
        self.env = isolated_env(PATH=str(self.bin) + os.pathsep + os.environ['PATH'], REAL_GIT=REAL_GIT,
                                SERVER=str(self.root / 'server.json'), GH_CALLS=str(self.root / 'gh.jsonl'),
                                GIT_CALLS=str(self.root / 'git.log'), BASE_BARE=str(self.bare),
                                SIGNER_CALLS=str(self.root / 'signer.log'), HOME=str(self.root / 'home'))
        (self.root / 'home').mkdir()
        for name, text in (('git', GIT_SHIM), ('gh', GH_FAKE), ('signer', SIGNER)):
            (self.bin / name).write_text(text)
            (self.bin / name).chmod(0o755)
        subprocess.run([REAL_GIT, 'init', '--bare', '-q', str(self.bare)], check=True, env=self.env)
        self.git('init', '-q', '-b', 'main')
        self.git('config', 'user.name', 'Fixture')
        self.git('config', 'user.email', 'fixture@example.test')
        self.git('config', 'commit.gpgsign', 'false')
        self.git('config', 'tag.gpgsign', 'false')
        (self.repo / '.gitignore').write_text('.uncle/workflow/\n')
        (self.repo / 'source.txt').write_text('before\n')
        (self.repo / 'CHANGE_REQUEST.md').write_text('## Summary\n\nBoundary request\n')
        self.git('add', '.')
        self.git('commit', '--no-gpg-sign', '-qm', 'initial')
        self.original = self.git('rev-parse', 'HEAD')
        self.git('remote', 'add', 'origin', str(self.bare))
        self.git('push', '-q', 'origin', 'main')
        self.state = self.repo / '.uncle/workflow'
        self.state.mkdir(parents=True)
        (self.repo / 'source.txt').write_text('audited\n')
        self.ledger = self.state / 'unattended-gates'

    def git(self, *args):
        return subprocess.check_output([REAL_GIT, '-c', 'commit.gpgsign=false', '-c', 'tag.gpgsign=false', *args],
                                       cwd=self.repo, env=self.env, stderr=subprocess.PIPE).decode().strip()

    def engine(self, action, text='', **env):
        return subprocess.run(['bash', '-c', '. "$1"; change_pr_engine "$2"', 'test', str(LIB), action],
                              cwd=self.repo, env=dict(self.env, UNCLE_LIB_DIR=str(ROOT / 'scripts/lib'), **env),
                              input=text, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)

    def ok(self, result):
        self.assertEqual(result.returncode, 0, result.stdout)

    def freeze(self, verdict='READY'):
        self.ok(self.engine('freeze'))
        (self.repo / 'FINAL_AUDIT.md').write_text('READY\n')
        sha = hashlib.sha256((self.repo / 'FINAL_AUDIT.md').read_bytes()).hexdigest()
        (self.state / 'audit-verdict').write_text('-\tREADY\t' + sha + '\n')
        self.ok(self.engine('bind'))
        if verdict != 'READY':
            (self.state / 'audit-verdict').write_text('-\t' + verdict + '\t' + sha + '\n')
        (self.state / 'state').write_text('COMPLETE\n')

    def journal(self):
        return json.loads((self.state / 'pr/journal.json').read_text())

    def gh_calls(self):
        path = self.root / 'gh.jsonl'
        return [json.loads(line) for line in path.read_text().splitlines()] if path.exists() else []

    def creates(self):
        return [a for a in self.gh_calls() if a[:2] == ['pr', 'create']]

    def git_log(self):
        path = self.root / 'git.log'
        return path.read_text().splitlines() if path.exists() else []

    def pushes(self):
        return [line for line in self.git_log() if line.startswith('push ')]

    def commits(self):
        return [line for line in self.git_log() if line.split(' ')[0] in ('commit', 'commit-tree')]

    def gate_events(self):
        path = self.root / 'status.jsonl'
        rows = [json.loads(line) for line in path.read_text().splitlines()] if path.exists() else []
        return [r for r in rows if r.get('event') == 'gate_open']

    def driver_env(self, unattended, relay, close='1'):
        env = dict(self.env, UNCLE_PROJECT_ROOT=str(self.repo), WORKFLOW_CLOSE_ISSUE=close)
        if relay:
            env['UNCLE_STATUS_FILE'] = str(self.root / 'status.jsonl')
        return env

    def complete(self, text='', unattended=True, relay=True, close='1', ledger=True):
        """One driver run from COMPLETE; stdin is a pipe that closes after `text`."""
        if ledger and not self.ledger.exists():
            self.ledger.write_text(LEDGER)
        (self.state / 'state').write_text('COMPLETE\n')
        args = ['bash', str(DRIVER)] + (['--unattended'] if unattended else [])
        return subprocess.run(args, cwd=self.repo, env=self.driver_env(unattended, relay, close), input=text,
                              text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=120)

    def complete_open_pipe(self, unattended=True, relay=False, timeout=5):
        """The driver with a pipe nobody closes: a prompt would hang here."""
        (self.state / 'state').write_text('COMPLETE\n')
        args = ['bash', str(DRIVER)] + (['--unattended'] if unattended else [])
        proc = subprocess.Popen(args, cwd=self.repo, env=self.driver_env(unattended, relay), stdin=subprocess.PIPE,
                                stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        try:
            deadline = time.time() + timeout
            while proc.poll() is None and time.time() < deadline:
                time.sleep(0.1)
            if proc.poll() is None:
                proc.kill()
                out = proc.stdout.read()
                self.fail('driver waited on an open pipe for %ss:\n%s' % (timeout, out))
            out = proc.stdout.read()
        finally:
            proc.stdin.close()
            proc.stdout.close()
        return proc.returncode, out

    def human_commit(self, output, signed=False):
        """The printed block, run as the person would in another terminal; the
        fixture never lets the engine execute it."""
        marker = 'Commit signing needs your help.' if signed else 'Commit needs your help.'
        self.assertIn(marker, output)
        command = output.split('then run:\n', 1)[1].split('\nReturn here', 1)[0]
        self.assertIn('git commit -S ' if signed else 'git commit --no-gpg-sign ', command)
        self.ok(subprocess.run(['sh', '-c', command], cwd=self.repo, env=self.env, text=True,
                               stdout=subprocess.PIPE, stderr=subprocess.STDOUT))
        return command

    def enable_signing(self):
        key = self.root / 'signing-key'
        subprocess.run(['ssh-keygen', '-q', '-t', 'ed25519', '-N', '', '-f', str(key)], check=True, env=self.env)
        allowed = self.root / 'allowed-signers'
        allowed.write_text('fixture@example.test ' + key.with_suffix('.pub').read_text())
        self.git('config', 'gpg.format', 'ssh')
        self.git('config', 'user.signingkey', str(key))
        self.git('config', 'gpg.ssh.allowedSignersFile', str(allowed))
        self.git('config', 'commit.gpgsign', 'true')

    def assert_prompted(self, output, signed=None):
        for text in ('PR title [default:', 'Work summary:', 'Manual verification steps:',
                     'Commit and publish exactly this audited diff and create the PR? [y/n]:'):
            self.assertIn(text, output)
        if signed is not None:
            self.assertIn('Commit signing needs your help.' if signed else 'Commit needs your help.', output)

    def assert_no_prompt(self, output):
        for text in ('PR title', 'Work summary', 'Manual verification', 'Create the PR anyway', 'needs your help', BOUNDARY):
            self.assertNotIn(text, output)

    def assert_created(self, count=1):
        j = self.journal()
        self.assertEqual(j['phase'], 'created')
        self.assertEqual(len(self.creates()), count)
        self.assertEqual(self.git('rev-parse', 'HEAD'), j['intended_head'])
        self.assertEqual(self.git('rev-parse', 'HEAD^{tree}'), j['commit_tree'])
        self.assertEqual(self.git('rev-parse', 'HEAD^'), self.original)
        return j


class HeadlessTests(Fixture):
    def test_t1_headless_auto_skips_without_prompt(self):
        self.freeze()
        result = self.complete('', unattended=True, relay=False)
        self.ok(result)
        self.assertIn(SKIP, result.stdout)
        self.assert_no_prompt(result.stdout)
        self.assertEqual(self.journal()['phase'], 'bound')
        self.assertEqual((self.creates(), self.pushes(), self.commits()), ([], [], []))
        self.assertEqual(self.git('rev-parse', 'HEAD'), self.original)
        self.assertFalse((self.root / 'status.jsonl').exists())

    def test_t2_attended_rerun_with_ledger_publishes(self):
        self.freeze()
        self.ok(self.complete('', unattended=True, relay=False))
        self.assertEqual(self.journal()['phase'], 'bound')
        before = self.ledger.read_bytes()
        result = self.complete('\nSummary text\nManual steps\n', unattended=False, relay=False)
        self.ok(result)
        self.assert_prompted(result.stdout)
        self.assertNotIn(SKIP, result.stdout)
        self.assertIn(PENDING_EOF, result.stdout)
        self.assertEqual(self.journal()['phase'], 'bound')
        self.assertEqual((self.creates(), self.pushes(), self.commits()), ([], [], []))
        result = self.complete('\nSummary text\nManual steps\ny\n', unattended=False, relay=False)
        self.ok(result)
        self.assertNotIn('needs your help', result.stdout)
        self.assert_created()
        self.assertEqual(len(self.pushes()), 1)
        self.assertEqual(self.ledger.read_bytes(), before)

    def test_t9_open_pipe_never_waits(self):
        self.freeze()
        code, out = self.complete_open_pipe(unattended=True, relay=False)
        self.assertEqual(code, 0, out)
        self.assertIn(SKIP, out)
        self.assert_no_prompt(out)
        self.assertEqual(self.journal()['phase'], 'bound')
        # A prepared journal whose commit the person has not made yet (signing
        # on): the dialog would wait on the pipe; the headless probe declines.
        self.enable_signing()
        result = self.complete('\nSummary text\nManual steps\ny\n', unattended=True, relay=True)
        self.ok(result)
        self.assertEqual(self.journal()['phase'], 'prepared')
        self.assertEqual(self.git('rev-parse', 'HEAD'), self.original)
        code, out = self.complete_open_pipe(unattended=True, relay=False)
        self.assertEqual(code, 0, out)
        self.assertIn(SKIP, out)
        self.assert_no_prompt(out)
        self.assertEqual(self.journal()['phase'], 'prepared')
        self.assertEqual(self.creates(), [])
        # The completed signed-resume path (close-flow-test.sh phases/markers)
        # still publishes headless once the commit exists, and only once.
        self.human_commit(result.stdout, signed=True)
        for close in ('1', '0'):
            code, out = self.complete_open_pipe(unattended=True, relay=False)
            self.assertEqual(code, 0, out)
            self.assert_no_prompt(out)
        j = self.assert_created()
        self.assertEqual(j['manual_signed_head'], j['intended_head'])
        for phase in ('prepared', 'published', 'creating', 'unknown'):
            for marker in (True, False):
                row = dict(j, phase=phase)
                if not marker:
                    row.pop('manual_signed_head')
                (self.state / 'pr/journal.json').write_text(json.dumps(row))
                result = self.complete('', unattended=True, relay=False, close='0')
                self.ok(result)
                self.assertEqual(self.journal()['phase'], 'created', result.stdout)
                self.assertEqual(len(self.creates()), 1)


class PersonChannelTests(Fixture):
    def test_t3_auto_relay_unsigned_publishes_by_human_input(self):
        self.freeze()
        self.ledger.write_text(LEDGER)
        before = self.ledger.read_bytes()
        result = self.complete('\nSummary text\nManual steps\ny\n', unattended=True, relay=True)
        self.ok(result)
        self.assertIn(BOUNDARY, result.stdout)
        self.assertNotIn(SKIP, result.stdout)
        self.assert_prompted(result.stdout)
        self.assertNotIn('needs your help', result.stdout)
        self.assertNotIn(PENDING_EOF, result.stdout)
        self.assertIn('Unattended run: 2 gate(s) passed with no human review.', result.stdout)
        self.assertLess(result.stdout.index('Unattended run:'), result.stdout.index(BOUNDARY))
        events = self.gate_events()
        self.assertEqual([e['class'] for e in events], ['sensitive'] * len(events))
        self.assertEqual({e['reason'] for e in events}, {'publication'})
        self.assertEqual(len(events), 4, events)
        j = self.assert_created()
        self.assertFalse(j['requires_signature'])
        self.assertNotIn('manual_signing', j)
        self.assertEqual([line.split(' ')[0] for line in self.commits()], ['commit'])
        self.assertEqual(j['attestation']['gate_publication'], 'APPROVED (human)')
        self.assertEqual(self.ledger.read_bytes(), before)
        self.assertEqual(before, LEDGER.encode())
        self.assertEqual(len(self.pushes()), 1)
        self.assertNotIn('Closes', (self.root / 'server.body').read_text())

    def test_t4_auto_relay_signed_resume_creates_pr(self):
        self.enable_signing()
        self.freeze()
        result = self.complete('\nSummary text\nManual steps\ny\n', unattended=True, relay=True)
        self.ok(result)
        self.assertIn(BOUNDARY, result.stdout)
        self.assert_prompted(result.stdout, signed=True)
        self.assertIn(PENDING_EOF, result.stdout)
        j = self.journal()
        self.assertEqual((j['phase'], j['manual_signing'], j['requires_signature']), ('prepared', True, True))
        self.assertEqual(self.commits(), [])
        self.assertEqual(self.git('rev-parse', 'HEAD'), self.original)
        command = self.human_commit(result.stdout, signed=True)
        self.assertNotIn('--no-gpg-sign', command)
        self.assertEqual(self.git('verify-commit', 'HEAD'), '')
        result = self.complete('', unattended=True, relay=True)
        self.ok(result)
        j = self.assert_created()
        self.assertEqual(j['manual_signed_head'], j['intended_head'])
        self.assertEqual(j['attestation']['gate_publication'], 'APPROVED (human)')
        self.assertEqual([e['reason'] for e in self.gate_events()][-1], 'signing')

    def test_t5_unsigned_commit_is_rejected(self):
        self.enable_signing()
        self.freeze()
        result = self.complete('\nSummary text\nManual steps\ny\n', unattended=True, relay=True)
        self.ok(result)
        self.assertIn('Commit signing needs your help.', result.stdout)
        j = self.journal()
        self.git('read-tree', j['commit_tree'])
        self.git('commit', '--no-gpg-sign', '-qm', 'unsigned by hand')
        result = self.complete('', unattended=True, relay=True)
        self.ok(result)
        self.assertIn('PR pending: Command failed: git verify-commit', result.stdout)
        self.assertEqual(self.journal()['phase'], 'prepared')
        self.assertEqual((self.creates(), self.pushes()), ([], []))

    def test_t6_not_ready_override_asks_the_person(self):
        self.freeze('NOT_READY')
        declined = self.complete('n\n', unattended=True, relay=True)
        self.ok(declined)
        self.assertIn(BOUNDARY, declined.stdout)
        self.assertIn('The audit verdict is NOT_READY, not READY. Create the PR anyway? [y/N]:', declined.stdout)
        self.assertIn('Publication declined; PR remains pending.', declined.stdout)
        self.assertFalse((self.state / 'pr/verdict-override').exists())
        self.assertEqual(self.journal()['phase'], 'bound')
        self.assertEqual(self.creates(), [])
        headless = self.complete('y\n', unattended=True, relay=False)
        self.ok(headless)
        self.assertIn(SKIP, headless.stdout)
        self.assert_no_prompt(headless.stdout)
        self.assertFalse((self.state / 'pr/verdict-override').exists())
        approved = self.complete('y\n\nSummary text\nManual steps\ny\n', unattended=True, relay=True)
        self.ok(approved)
        self.assertIn('Override recorded; creating the PR over a NOT_READY verdict.', approved.stdout)
        self.assert_prompted(approved.stdout)
        self.assertNotIn('needs your help', approved.stdout)
        self.assert_created()
        self.assertIn('operator override', (self.root / 'server.body').read_text())
        events = self.gate_events()
        self.assertTrue(events)
        self.assertEqual([e['class'] for e in events], ['sensitive'] * len(events))


class EngineTests(unittest.TestCase):
    """T-8 against the exec'd engine namespace: no production commit or signing."""

    def setUp(self):
        self.ns = {}
        exec(SOURCE[:SOURCE.rindex('\ntry:\n    main()')], self.ns)

    def test_t8_signing_block_is_printed_never_executed(self):
        j = dict(original_head='old', intended_head='', commit_tree='tree', title='Change', manual_signing=True,
                 requires_signature=True)
        git = Mock(return_value='')
        run = Mock(side_effect=AssertionError('no process may run'))
        ask = Mock(return_value='')
        self.ns.update(head=lambda: 'old', git=git, run=run, ask=ask, save=Mock(), validate=Mock())
        with self.assertRaisesRegex(ValueError, 'No new commit'):
            self.ns['manual_signed_commit'](j)
        block = ask.call_args_list[0].args[0]
        self.assertIn('git commit -S ', block)
        self.assertNotIn('--no-gpg-sign', block)
        self.assertEqual(ask.call_args_list[0].args[0].split('.', 1)[0], 'Commit signing needs your help')
        git.assert_not_called()
        run.assert_not_called()
        j['requires_signature'] = False
        ask.reset_mock()
        with self.assertRaisesRegex(ValueError, 'No new commit'):
            self.ns['manual_signed_commit'](j)
        self.assertIn('git commit --no-gpg-sign ', ask.call_args_list[0].args[0])
        git.assert_not_called()

    def test_t7_ask_forwards_publication_hint(self):
        opened = []

        class Helper:
            def open(self, text, signing=False, class_hint=''):
                opened.append((text, signing, class_hint))
                return 'p1'

            def read(self, answer):
                return ''
        self.ns['gate'] = lambda: Helper()
        # A closed pipe stands in for stdin so every read is an immediate EOF.
        read_end, write_end = os.pipe()
        os.close(write_end)
        self.addCleanup(os.close, read_end)
        self.ns['sys'] = Mock(stdin=Mock(isatty=lambda: False, fileno=lambda: read_end))
        with self.assertRaisesRegex(ValueError, 'No answer received'):
            self.ns['ask']('Work summary: ')
        self.assertEqual(opened, [('Work summary: ', False, 'sensitive:publication')])
        with self.assertRaisesRegex(ValueError, 'No answer received'):
            self.ns['ask']('Commit signing needs your help. block Return here and press ENTER (OK) when finished: ')
        self.assertTrue(opened[-1][1])


class GateClassTests(unittest.TestCase):
    """T-7: every handoff prompt classifies sensitive with the driver's hint."""

    PROMPTS = (
        ('PR title [default: Completed change]: ', 'input', 'publication'),
        ('Work summary: ', 'input', 'publication'),
        ('Manual verification steps: ', 'input', 'publication'),
        ('Commit and publish exactly this audited diff and create the PR? [y/n]: ', 'confirm', 'publication'),
        ('The audit verdict is NOT_READY, not READY. Create the PR anyway? [y/N]: ', 'confirm', 'publication'),
        ('No new commit found. Keep the commit dialog open? [y/n]: ', 'confirm', 'publication'),
        ('Commit needs your help. block Return here and press ENTER (OK) when finished: ', 'enter', 'signing'),
        ('Commit signing needs your help. block Return here and press ENTER (OK) when finished: ', 'enter', 'signing'),
    )

    def test_classify(self):
        sys.path.insert(0, str(ROOT / 'scripts/lib'))
        import gate_answer
        for text, kind, reason in self.PROMPTS:
            signing = reason == 'signing'
            got = gate_answer.classify(text, 'sensitive:publication', signing)
            self.assertEqual(got[:3], (kind, 'sensitive', reason), text)
        self.assertEqual(gate_answer.classify('Work summary: ')[1], 'routine', 'the hint, not the text, carries the class')
        gate = gate_answer.Gate(state_dir=str(ROOT / '.uncle/workflow'), environ={'UNCLE_STATUS_FILE': '', 'UNCLE_GATE_RUN': 'r'})
        self.assertTrue(gate.open('Work summary: ', class_hint='sensitive:publication'))


def load_tui_harness():
    sys.dont_write_bytecode = True  # no __pycache__ under the protected tests directory
    spec = importlib.util.spec_from_file_location('supervisor_chat_test', ROOT / 'scripts/tests/supervisor-chat-test.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


HARNESS = load_tui_harness()


class TuiBoundaryTests(HARNESS.Base):
    """T-7: at the Auto-mode boundary the TUI submits no supervisor answer to a
    publication or signing dialog; a person types it into the dialog."""

    CASES = (
        ('PR title [default: Completed change]: ', '', False, 'answer this one', 'A title'),
        ('Work summary: ', 'sensitive:publication', False, 'answer this with "done"', 'ignored'),
        ('Manual verification steps: ', 'sensitive:publication', False, 'answer this one', 'run it'),
        ('Commit and publish exactly this audited diff and create the PR? [y/n]: ', 'sensitive:publication', False,
         'approve this', 'y'),
        ('The audit verdict is NOT_READY, not READY. Create the PR anyway? [y/N]: ', 'sensitive:publication', False,
         'say yes', 'y'),
        ('Commit signing needs your help. "git commit -S" Return here and press ENTER (OK) when finished:', '', True,
         'press enter', ''),
    )

    def auto_ui(self):
        ui = self.ui('running')
        ui.workflow_unattended = True
        return ui

    def test_supervisor_submissions_rejected_human_answer_works(self):
        for text, hint, signing, ask, proposed in self.CASES:
            with self.subTest(ask=ask, text=text[:30]):
                ui = self.auto_ui()
                self.open_gate(ui, text, hint, '', signing=signing)
                self.assertEqual(ui._dialog_record()['class'], 'sensitive')
                # Standing delegation: never serviced for a sensitive dialog.
                ui.delegation_session = {'request': 'handle the gates', 'granted': 1}
                self.assertFalse(ui.poll_delegation())
                request = self.send(ui, ask)
                self.assertEqual(request.delegation['source'], 'explicit')
                self.answer(ui, request, 'Answering.', gate_answer={'answer': proposed, 'rationale': 'ready'})
                ui.proc.stdin.write.assert_not_called()
                self.assertEqual(self.receipts(), [])
                self.assertFalse((self.state / 'supervision' / 'answers').exists())
                self.assertTrue(ui.prompt_kind, 'the dialog is still waiting')
                self.assertIn('Not sent', self.history(ui))
                self.assertIn('publication boundary', self.history(ui))
                human = 'y' if ui.prompt_kind == 'confirm' else ('' if ui.prompt_kind == 'enter' else 'typed by hand')
                ui.answer_prompt(human)
                ui.proc.stdin.write.assert_called_once_with((human + '\n').encode())
                self.assertEqual(ui.prompt_kind, '')
                self.assertEqual(self.receipts(), [])

    def test_stale_dialog_and_attended_run_unchanged(self):
        ui = self.auto_ui()
        self.open_gate(ui, 'Work summary: ', 'sensitive:publication', '')
        request = self.send(ui, 'answer this one')
        ui.answer_prompt('typed by hand')
        self.answer(ui, request, 'Answering.', gate_answer={'answer': 'late', 'rationale': 'r'})
        ui.proc.stdin.write.assert_called_once_with(b'typed by hand\n')
        self.assertIn('dialog changed or closed', self.history(ui))
        # A routine dialog in the same Auto run keeps explicit delegation.
        ui = self.auto_ui()
        self.open_gate(ui, 'Ready to approve CHANGE_PLAN.md? [Y/N] ')
        request = self.send(ui, 'answer this one')
        self.answer(ui, request, 'Approving.', gate_answer={'answer': 'y', 'rationale': 'complete'})
        ui.proc.stdin.write.assert_called_once_with(b'y\n')


class IsolationTests(Fixture):
    """T-10: inherited signing never reaches the fixture or the driver."""

    def test_inherited_signer_is_never_invoked(self):
        inherited = self.root / 'inherited-gitconfig'
        inherited.write_text('[commit]\n\tgpgsign = true\n[tag]\n\tgpgsign = true\n[gpg]\n\tprogram = '
                             + str(self.bin / 'signer') + '\n')
        self.env['GIT_CONFIG_GLOBAL'] = str(inherited)
        self.git('commit', '--no-gpg-sign', '--allow-empty', '-qm', 'helper commit')
        self.original = self.git('rev-parse', 'HEAD')
        self.git('push', '-q', 'origin', 'main')
        self.freeze()
        self.ok(self.complete('', unattended=True, relay=False))
        result = self.complete('\nSummary text\nManual steps\ny\n', unattended=True, relay=True)
        self.ok(result)
        self.assertNotIn('needs your help', result.stdout)
        self.assert_created()
        self.assertEqual([line.split(' ')[0] for line in self.commits()], ['commit'])
        self.assertFalse((self.root / 'signer.log').exists(), 'the inherited signer was invoked')
        self.assertEqual(self.git('config', '--get', 'commit.gpgsign'), 'false')


if __name__ == '__main__':
    unittest.main()
