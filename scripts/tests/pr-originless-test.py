"""Origin-less change-request builds reach the PR handoff (Issue 47, T-1..T-12).

Unit cases exec the engine namespace like pr-signing-test.py; integration
cases use disposable Git repositories, isolated signing configuration and a
fake gh transport like close-flow-test.sh. PR_ORIGINLESS_LIB points the
suite at an alternate engine copy for defect-injection runs.
"""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import Mock

ROOT = Path(__file__).resolve().parents[2]
LIB = Path(os.environ.get('PR_ORIGINLESS_LIB') or ROOT / 'scripts/lib/change-pr.sh')
SOURCE = LIB.read_text().split("<<'PY'", 1)[1].split('\n', 1)[1].split('\nPY\n', 1)[0]
REAL_GIT = shutil.which('git')
DRIFT = 'Remote configuration changed; rerun FINAL_AUDIT.'
NO_REMOTE = 'No Git remote is configured; add a GitHub remote and rerun to resume PR handoff.'
AMBIGUOUS_BASE = 'Ambiguous base remote; name one remote origin or upstream.'

GIT_SHIM = '''#!/usr/bin/env bash
printf '%s\\n' "$*" >> "$GIT_CALLS"
if [[ "$1" == remote && "${2:-}" == get-url ]]; then
    "$REAL_GIT" "$@" | while IFS= read -r url; do
        case "$url" in
            "$BASE_BARE") echo 'https://github.com/owner/repo.git' ;;
            "$FORK_BARE") echo 'git@github.com:forker/repo.git' ;;
            *) printf '%s\\n' "$url" ;;
        esac
    done
    exit 0
fi
if [[ "${CRASH_GIT:-}" == "$1" ]]; then
    "$REAL_GIT" "$@"
    exit 70
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
    print(json.dumps({'fork': True, 'parent': {'full_name': 'owner/repo'}, 'owner': {'type': 'User'}}))
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


def isolated_env(**extra):
    env = {k: v for k, v in os.environ.items()
           if not k.startswith(('UNCLE_', 'STAGEGATE_', 'WORKFLOW_', 'GIT_', 'GPG_'))}
    env.update(GIT_CONFIG_GLOBAL='/dev/null', GIT_CONFIG_NOSYSTEM='1', **extra)
    return env


class ResolveUnitTests(unittest.TestCase):
    """T-1..T-5, T-8 (helper), T-11, T-12 against the exec'd engine namespace."""

    def setUp(self):
        self.ns = {}
        exec(SOURCE[:SOURCE.rindex('\ntry:\n    main()')], self.ns)
        self.j = dict(origin='', original_head='old', original_branch='feature', owner='a' * 32)
        self.ask = Mock(side_effect=AssertionError('ask must not be called'))
        self.identities = {'origin': 'owner/repo'}
        self.git_calls = []

        def git(*args, **kwargs):
            self.git_calls.append(args)
            if args[0] == 'remote' and len(args) == 1:
                return '\n'.join(self.identities)
            if args[0] == 'ls-remote':
                return ''
            return ''

        def gh(*args):
            if args[:2] == ('repo', 'view'):
                return json.dumps({'nameWithOwner': args[2], 'defaultBranchRef': {'name': 'main'}})
            if args[0] == 'api':
                return json.dumps({'fork': True, 'parent': {'full_name': 'owner/repo'}, 'owner': {'type': 'User'}})
            raise AssertionError('unexpected gh ' + ' '.join(args))

        self.real = {name: self.ns[name] for name in ('check_remotes', 'remote_identity')}
        self.ns.update(git=git, gh=gh, ask=self.ask, save=Mock(), check_remotes=Mock(),
                       remote_identity=lambda r: self.identities[r])

    def test_t1_sole_origin_selects_repo_and_default_branch(self):
        self.ns['resolve'](self.j)
        self.ask.assert_not_called()
        self.assertEqual((self.j['base_repo'], self.j['base_branch'], self.j['head_repo'], self.j['remote']),
                         ('owner/repo', 'main', 'owner/repo', 'origin'))
        self.assertEqual(self.j['head_branch'], 'feature')

    def test_t2_upstream_base_with_fork_origin(self):
        self.identities = {'origin': 'forker/repo', 'upstream': 'owner/repo'}
        self.ns['resolve'](self.j)
        self.ask.assert_not_called()
        self.assertEqual((self.j['base_repo'], self.j['head_repo'], self.j['remote']),
                         ('owner/repo', 'forker/repo', 'origin'))

    def test_t3_no_remote_fails_without_prompt_or_add(self):
        self.identities = {}
        with self.assertRaisesRegex(ValueError, NO_REMOTE.replace('.', r'\.')):
            self.ns['resolve'](self.j)
        self.ask.assert_not_called()
        self.assertFalse([c for c in self.git_calls if c[:2] == ('remote', 'add')])
        self.assertNotIn('base_repo', self.j)

    def test_t4_multiple_unnamed_candidates_are_ambiguous(self):
        self.identities = {'alpha': 'owner/repo', 'beta': 'other/repo'}
        with self.assertRaisesRegex(ValueError, 'Ambiguous base remote'):
            self.ns['resolve'](self.j)
        self.ask.assert_not_called()
        self.assertNotIn('base_repo', self.j)

    def test_t5_unsupported_host_and_dual_identity_reject_without_prompt(self):
        def git(*args, **kwargs):
            if args == ('remote',):
                return 'origin'
            if args[:2] == ('remote', 'get-url'):
                return self.urls[args[2] == '--push']
            return ''
        self.ns['git'] = git
        self.ns['remote_identity'] = self.real['remote_identity']
        for urls, message in [(('https://gitlab.com/o/r.git', 'https://gitlab.com/o/r.git'), 'Unsupported GitHub remote'),
                              (('https://github.com/o/r.git', 'https://github.com/x/r.git'), 'Ambiguous fetch/push remote'),
                              (('https://github.com/o/r.git', 'https://github.com/o/r.git\nhttps://github.com/o/r.git'), 'Ambiguous fetch/push remote')]:
            self.urls = urls
            with self.assertRaisesRegex(ValueError, message):
                self.ns['resolve'](self.j)
        self.ask.assert_not_called()

    def test_t7_bound_origin_keeps_issue_base(self):
        self.j['origin'] = 'owner/repo\t7\tgh\n'
        self.identities = {'origin': 'owner/repo'}
        self.ns['resolve'](self.j)
        self.ask.assert_not_called()
        self.assertEqual(self.j['base_repo'], 'owner/repo')

    def test_t8_check_remotes_rejects_any_configuration_difference(self):
        frozen = {'origin': [['https://github.com/owner/repo.git'], ['https://github.com/owner/repo.git']]}
        self.ns['remote_configuration'] = lambda: json.loads(json.dumps(frozen))
        check = self.real['check_remotes']
        check(dict(origin='', audit_remotes=frozen))
        for altered in [{'origin': [['https://github.com/owner/repo.git'], ['https://github.com/owner/repo']]},
                        {'upstream': frozen['origin']},
                        dict(frozen, upstream=frozen['origin']),
                        {}, None, 'origin', {'origin': ['https://github.com/owner/repo.git']}]:
            with self.assertRaisesRegex(ValueError, DRIFT.replace('.', r'\.')):
                check(dict(origin='', audit_remotes=altered))
        with self.assertRaisesRegex(ValueError, DRIFT.replace('.', r'\.')):
            check(dict(origin=''))
        check(dict(origin='owner/repo\t7\tgh\n'))  # issue-bound journals are unaffected

    def test_t11_legacy_originless_journal_denied_in_every_phase(self):
        self.ns.update(audit_hash=lambda: 'h', head=lambda: 'old', branch=lambda: 'feature',
                       snapshot=lambda audit=False: 'tree', override_allows=lambda j, v: True,
                       check_remotes=self.real['check_remotes'])
        self.ns['remote_configuration'] = lambda: {'origin': [['u'], ['u']]}
        base = dict(origin='', audit_hash='h', verdict_run='', reviewed_tree='tree', commit_tree='tree',
                    original_head='old', intended_head='', original_branch='feature', head_branch='feature')
        self.ns['read'] = lambda p: 'run\tREADY\th' if p.name == 'audit-verdict' else ''
        for phase in ('bound', 'prepared', 'published', 'creating', 'unknown', 'created'):
            with self.assertRaisesRegex(ValueError, DRIFT.replace('.', r'\.')):
                self.ns['validate'](dict(base, phase=phase, verdict_run='run'))
        self.ns['validate'](dict(base, phase='bound', verdict_run='run', audit_remotes={'origin': [['u'], ['u']]}))
        legacy_bound = dict(base, phase='bound', verdict_run='run', origin='owner/repo\t7\tgh\n')
        self.ns['read'] = lambda p: {'audit-verdict': 'run\tREADY\th', 'origin': 'owner/repo\t7\tgh\n'}.get(p.name, '')
        self.ns['validate'](legacy_bound)

    def test_t12_signing_configuration_never_invokes_signer(self):
        recorder = Mock()
        self.ns['subprocess'] = Mock()
        self.ns['subprocess'].run.return_value = Mock(returncode=0, stdout='true\n')
        self.ns['head'] = lambda: 'old'
        self.ns['git'] = recorder
        self.ask.side_effect = ['', 'n']
        j = dict(original_head='old', intended_head='', commit_tree='tree', title='t', origin='')
        with self.assertRaisesRegex(ValueError, 'No new commit'):
            self.ns['prepare_commit'](j)
        self.assertTrue(j['requires_signature'])
        recorder.assert_not_called()
        self.assertIn('git commit -S', self.ask.call_args_list[0].args[0])


class HandoffFixture(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.repo = self.root / 'repo'
        self.repo.mkdir()
        self.bin = self.root / 'bin'
        self.bin.mkdir()
        self.bare = self.root / 'remote.git'
        self.fork = self.root / 'fork.git'
        self.env = isolated_env(PATH=str(self.bin) + os.pathsep + os.environ['PATH'], REAL_GIT=REAL_GIT,
                                SERVER=str(self.root / 'server.json'), GH_CALLS=str(self.root / 'gh.jsonl'),
                                GIT_CALLS=str(self.root / 'git.log'), BASE_BARE=str(self.bare),
                                FORK_BARE=str(self.fork), UNCLE_LIB_DIR=str(ROOT / 'scripts/lib'))
        for name, text in (('git', GIT_SHIM), ('gh', GH_FAKE)):
            (self.bin / name).write_text(text)
            (self.bin / name).chmod(0o755)
        for bare in (self.bare, self.fork):
            subprocess.run([REAL_GIT, 'init', '--bare', '-q', str(bare)], check=True, env=self.env)
        self.git('init', '-q', '-b', 'main')
        self.git('config', 'user.name', 'Fixture')
        self.git('config', 'user.email', 'fixture@example.test')
        self.git('config', 'commit.gpgsign', 'false')
        self.git('config', 'tag.gpgsign', 'false')
        (self.repo / '.gitignore').write_text('.uncle/workflow/\n')
        (self.repo / 'source.txt').write_text('before\n')
        (self.repo / 'CHANGE_REQUEST.md').write_text('## Summary\n\nChat request\n')
        self.git('add', '.')
        self.git('commit', '--no-gpg-sign', '-qm', 'initial')
        self.original = self.git('rev-parse', 'HEAD')
        self.git('remote', 'add', 'origin', str(self.bare))
        self.git('push', '-q', 'origin', 'main')
        self.state = self.repo / '.uncle/workflow'
        self.state.mkdir(parents=True)
        (self.repo / 'source.txt').write_text('audited\n')

    def git(self, *args):
        return subprocess.check_output([REAL_GIT, '-c', 'commit.gpgsign=false', '-c', 'tag.gpgsign=false', *args],
                                       cwd=self.repo, env=self.env, stderr=subprocess.PIPE).decode().strip()

    def engine(self, action, text='', **env):
        # Signing is off in this fixture, so the engine commits itself; no
        # operator step is simulated and no prompt for one may appear.
        result = subprocess.run(['bash', '-c', '. "$1"; change_pr_engine "$2"', 'test', str(LIB), action],
                                cwd=self.repo, env=dict(self.env, **env), input=text, text=True,
                                stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        self.assertNotIn('needs your help', result.stdout)
        return result

    def ok(self, result):
        self.assertEqual(result.returncode, 0, result.stdout)

    def freeze(self):
        self.ok(self.engine('freeze'))
        (self.repo / 'FINAL_AUDIT.md').write_text('READY\n')
        sha = hashlib.sha256((self.repo / 'FINAL_AUDIT.md').read_bytes()).hexdigest()
        (self.state / 'audit-verdict').write_text('-\tREADY\t' + sha + '\n')
        self.ok(self.engine('bind'))

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

    def publish(self, text='Custom title\nSummary text\nManual steps\ny\n', **env):
        return self.engine('handoff', text, **env)

    def assert_pending_bound(self, result, message):
        self.assertNotEqual(result.returncode, 0, result.stdout)
        self.assertIn('PR pending: ' + message, result.stdout)
        self.assertNotIn('Base repository [', result.stdout)
        self.assertNotIn('GitHub remote URL', result.stdout)
        self.assertEqual(self.journal()['phase'], 'bound')
        self.assertEqual(self.creates(), [])
        self.assertEqual([l for l in self.git_log() if l.split(' ')[0] in ('push', 'commit', 'remote add', 'update-ref')
                          or l.startswith('remote add')], [])
        self.assertEqual(self.git('rev-parse', 'HEAD'), self.original)


class OriginlessHandoffTests(HandoffFixture):
    def test_t9_full_originless_handoff_and_resume(self):
        self.assertFalse((self.state / 'origin').exists())
        self.freeze()
        self.assertEqual(self.journal()['audit_remotes'],
                         {'origin': [['https://github.com/owner/repo.git'], ['https://github.com/owner/repo.git']]})
        result = self.publish()
        self.ok(result)
        self.assertNotIn('Base repository [', result.stdout)
        j = self.journal()
        self.assertEqual(j['phase'], 'created')
        self.assertEqual((j['base_repo'], j['base_branch'], j['head_repo']), ('owner/repo', 'main', 'owner/repo'))
        self.assertEqual(j['head_branch'], 'uncle/chat-request-' + j['owner'][:12])
        self.assertEqual(self.git('rev-parse', 'HEAD'), j['intended_head'])
        self.assertEqual(self.git('rev-parse', 'HEAD^{tree}'), j['commit_tree'])
        self.assertEqual(self.git('rev-parse', 'HEAD^'), self.original)
        self.assertEqual(self.git('show', 'HEAD:source.txt'), 'audited')
        pushes = [l for l in self.git_log() if l.startswith('push ')]
        self.assertEqual(pushes, ['push -- origin ' + j['intended_head'] + ':refs/heads/' + j['head_branch']])
        remote_sha = subprocess.check_output([REAL_GIT, '--git-dir', str(self.bare), 'rev-parse', j['head_branch']]).decode().strip()
        self.assertEqual(remote_sha, j['intended_head'])
        create = self.creates()
        self.assertEqual(len(create), 1)
        self.assertEqual(create[0][create[0].index('--title') + 1], 'Custom title')
        self.assertEqual(create[0][create[0].index('--base') + 1], 'main')
        self.assertEqual(create[0][create[0].index('--repo') + 1], 'owner/repo')
        body = (self.root / 'server.body').read_text()
        self.assertIn('Summary text', body)
        self.assertIn('Manual steps', body)
        self.assertNotIn('Closes', body)
        self.assertNotIn('#', body.split('<!--', 1)[0].replace('## ', ''))
        self.assertFalse([a for a in self.gh_calls() if 'issue' in a[0] or (a[0] == 'api' and 'issues' in a[1])])
        self.assertFalse((self.state / 'issue-closed').exists())
        resumed = self.engine('handoff')
        self.ok(resumed)
        self.assertIn('https://github.com/owner/repo/pull/7', resumed.stdout)
        self.assertEqual(len(self.creates()), 1)

    def test_t6_operator_fields_preserved_without_closes(self):
        self.freeze()
        self.ok(self.publish('\nWhat changed\nHow to check\ny\n'))
        create = self.creates()[0]
        self.assertEqual(create[create.index('--title') + 1], 'Chat request')
        body = (self.root / 'server.body').read_text()
        self.assertTrue(body.startswith('## Work summary\n\nWhat changed\n\n## Manual verification\n\nHow to check\n'))
        self.assertNotIn('Closes', body)

    def test_t7_bound_issue_keeps_prompts_and_closes(self):
        (self.state / 'origin').write_text('owner/repo\t7\tgh\n')
        self.freeze()
        self.assertNotIn('audit_remotes', self.journal())
        result = self.publish()
        self.ok(result)
        for prompt in ('PR title [default: Chat request]: ', 'Work summary: ', 'Manual verification steps: ',
                       'Commit and publish exactly this audited diff and create the PR? [y/n]: '):
            self.assertIn(prompt, result.stdout)
        self.assertIn('\nCloses owner/repo#7\n', (self.root / 'server.body').read_text())
        self.assertEqual(len(self.creates()), 1)

    def test_t10_invalid_destinations_pend_then_repair_needs_audit(self):
        self.git('remote', 'remove', 'origin')
        self.freeze()
        self.assertEqual(self.journal()['audit_remotes'], {})
        self.assert_pending_bound(self.publish(), NO_REMOTE)
        self.git('remote', 'add', 'origin', str(self.bare))
        self.assert_pending_bound(self.publish(), DRIFT)
        self.freeze()
        self.ok(self.publish())
        self.assertEqual(len(self.creates()), 1)

    def test_t10_ambiguous_and_unsupported_destinations(self):
        self.git('remote', 'rename', 'origin', 'alpha')
        self.git('remote', 'add', 'beta', str(self.fork))
        self.freeze()
        self.assert_pending_bound(self.publish(), AMBIGUOUS_BASE)
        self.git('remote', 'remove', 'beta')
        self.git('remote', 'rename', 'alpha', 'origin')
        self.git('remote', 'set-url', 'origin', 'https://gitlab.com/owner/repo.git')
        self.freeze()
        self.assert_pending_bound(self.publish(), 'Unsupported GitHub remote')
        self.git('remote', 'set-url', 'origin', str(self.bare))
        self.git('remote', 'set-url', '--push', 'origin', str(self.fork))
        self.freeze()
        self.assert_pending_bound(self.publish(), 'Ambiguous fetch/push remote')

    def test_t8_drift_between_freeze_and_bind(self):
        for mutate in (lambda: self.git('remote', 'add', 'upstream', str(self.bare)),
                       lambda: self.git('remote', 'rename', 'origin', 'upstream'),
                       lambda: self.git('remote', 'set-url', '--push', 'origin', str(self.bare) + '/')):
            self.setUp()
            self.ok(self.engine('freeze'))
            mutate()
            (self.repo / 'FINAL_AUDIT.md').write_text('READY\n')
            sha = hashlib.sha256((self.repo / 'FINAL_AUDIT.md').read_bytes()).hexdigest()
            (self.state / 'audit-verdict').write_text('-\tREADY\t' + sha + '\n')
            result = self.engine('bind')
            self.assertIn('PR pending: ' + DRIFT, result.stdout)
            self.assertEqual(self.journal()['phase'], 'auditing')

    def test_t8_drift_between_bind_and_handoff_with_identical_sha(self):
        self.freeze()
        self.git('remote', 'add', 'upstream', str(self.bare))  # same repository, same SHAs
        self.assert_pending_bound(self.publish(), DRIFT)
        self.git('remote', 'remove', 'upstream')
        self.git('remote', 'set-url', 'origin', str(self.bare) + '/')
        self.assert_pending_bound(self.publish(), DRIFT)

    def test_t8_drift_during_prompts(self):
        self.freeze()
        process = subprocess.Popen(['bash', '-c', '. "$1"; change_pr_engine handoff', 'test', str(LIB)],
                                   cwd=self.repo, env=self.env, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                   stderr=subprocess.STDOUT, text=True)
        output = ''
        while not output.endswith(']: '):
            ch = process.stdout.read(1)
            self.assertTrue(ch, output)
            output += ch
        self.git('remote', 'set-url', '--push', 'origin', str(self.bare) + '/')
        remainder, _ = process.communicate('\nSummary\nManual\ny\n', timeout=15)
        self.assertIn('PR pending: ' + DRIFT, remainder)
        self.assertEqual(self.journal()['phase'], 'bound')
        self.assertEqual(self.creates(), [])
        self.assertFalse([l for l in self.git_log() if l.startswith(('push ', 'commit '))])

    def test_t8_drift_between_push_and_create(self):
        self.freeze()
        crashed = self.publish(CRASH_GIT='push')
        self.assertNotEqual(crashed.returncode, 0)
        j = self.journal()
        self.assertEqual(j['phase'], 'prepared')
        self.assertEqual(len(self.creates()), 0)
        self.git('remote', 'add', 'upstream', str(self.bare))
        result = self.engine('handoff')
        self.assertIn('PR pending: ' + DRIFT, result.stdout)
        self.assertEqual(self.journal()['phase'], 'prepared')
        self.assertEqual(len(self.creates()), 0)
        self.assertEqual(len([l for l in self.git_log() if l.startswith('push ')]), 1)

    def test_t11_legacy_originless_journal_needs_fresh_audit(self):
        self.freeze()
        path = self.state / 'pr/journal.json'
        for phase in ('bound', 'prepared', 'published', 'creating', 'unknown', 'created'):
            j = self.journal()
            j.pop('audit_remotes', None)
            j['phase'] = phase
            path.write_text(json.dumps(j))
            result = self.engine('handoff')
            self.assertIn('PR pending: ' + DRIFT, result.stdout, phase)
            self.assertEqual(self.creates(), [])
        for malformed in ('[]', '"origin"', '{"origin": ["x"]}'):
            j = self.journal()
            j['audit_remotes'] = json.loads(malformed)
            j['phase'] = 'bound'
            path.write_text(json.dumps(j))
            self.assertIn('PR pending: ' + DRIFT, self.engine('handoff').stdout, malformed)
        self.assertEqual(self.engine('validate').returncode, 1)
        self.freeze()
        self.ok(self.engine('validate'))

    def test_t11_remote_sha_divergence_still_rejects(self):
        self.git('checkout', '-qb', 'feature')
        self.freeze()
        other = self.git('commit-tree', '--no-gpg-sign', self.git('rev-parse', 'HEAD^{tree}'), '-p', self.original, '-m', 'remote edit')
        self.git('push', '-q', 'origin', other + ':refs/heads/feature')
        self.assert_pending_bound(self.publish(), 'Remote head differs from audited HEAD; rerun FINAL_AUDIT.')

    def test_b9_driver_messages_without_issue_wording(self):
        self.freeze()
        (self.state / 'state').write_text('COMPLETE\n')
        env = dict(self.env, UNCLE_PROJECT_ROOT=str(self.repo), WORKFLOW_CLOSE_ISSUE='0', UNATTENDED='0')
        result = subprocess.run(['bash', str(ROOT / 'scripts/change-workflow.sh')], cwd=self.repo, env=env,
                                input='\n', text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=60)
        self.ok(result)
        self.assertIn('PR handoff disabled or unattended; no PR was created.', result.stdout)
        self.assertNotIn('issue', result.stdout.split('PR handoff disabled', 1)[1].split('\n', 1)[0])
        self.assertEqual(self.creates(), [])
        driver = (ROOT / 'scripts/change-workflow.sh').read_text()
        self.assertIn('Build complete without a commit. PR publication requires an existing base commit; no PR was created.', driver)
        self.assertIn('Build complete without a commit. PR publication requires an existing base commit; the issue remains open.', driver)

    def test_driver_complete_originless_creates_pr(self):
        self.freeze()
        (self.state / 'state').write_text('COMPLETE\n')
        env = dict(self.env, UNCLE_PROJECT_ROOT=str(self.repo), WORKFLOW_CLOSE_ISSUE='1', UNATTENDED='0')
        command = ['bash', str(ROOT / 'scripts/change-workflow.sh')]
        result = subprocess.run(command, cwd=self.repo, env=env, input='\nSummary\nManual\ny\n', text=True,
                                stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=60)
        self.ok(result)
        self.assertNotIn('Base repository [', result.stdout)
        self.assertNotIn('needs your help', result.stdout)
        self.assertIn('PR: https://github.com/owner/repo/pull/7', result.stdout)
        self.assertEqual(len(self.creates()), 1, result.stdout)
        self.assertFalse((self.state / 'issue-closed').exists())
        self.assertNotIn('Closes', (self.root / 'server.body').read_text())
        result = subprocess.run(command, cwd=self.repo, env=env, input='', text=True,
                                stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=60)
        self.ok(result)
        self.assertIn('https://github.com/owner/repo/pull/7', result.stdout)
        self.assertEqual(len(self.creates()), 1)


class EarlyBranchHandoffTests(HandoffFixture):
    """Issue 60 T-8: a journal started before the first stage reaches the same handoff."""

    def start(self):
        self.git('remote', 'set-head', 'origin', 'main')
        self.ok(self.engine('start'))
        j = self.journal()
        self.assertEqual((j['version'], j['phase'], j['early_ref']), (2, 'started', True))
        self.assertEqual(self.git('rev-parse', 'refs/heads/' + j['head_branch']), self.original)
        return j

    def test_t8_started_identity_reaches_freeze_bind_and_handoff(self):
        started = self.start()
        self.freeze()
        j = self.journal()
        self.assertEqual((j['version'], j['phase'], j['owner'], j['head_branch'], j['early_ref']),
                         (2, 'bound', started['owner'], started['head_branch'], True))
        self.assertEqual(self.git('rev-list', '--count', '--all'), '1')
        result = self.publish()
        self.ok(result)
        j = self.journal()
        self.assertEqual((j['phase'], j['head_branch']), ('created', started['head_branch']))
        self.assertEqual(self.git('branch', '--show-current'), started['head_branch'])
        self.assertEqual(self.git('rev-parse', 'HEAD'), j['intended_head'])
        self.assertEqual(self.git('rev-parse', 'HEAD^'), self.original)
        self.assertEqual(self.git('rev-parse', 'HEAD^{tree}'), j['commit_tree'])
        self.assertEqual([l for l in self.git_log() if l.startswith('push ')],
                         ['push -- origin ' + j['intended_head'] + ':refs/heads/' + started['head_branch']])
        remote_sha = subprocess.check_output([REAL_GIT, '--git-dir', str(self.bare), 'rev-parse', started['head_branch']]).decode().strip()
        self.assertEqual(remote_sha, j['intended_head'])
        # The ref was claimed once, at start; handoff advanced it instead of creating it.
        creations = [l for l in self.git_log() if l.startswith('update-ref refs/heads/' + started['head_branch'] + ' ')]
        self.assertEqual(creations, ['update-ref refs/heads/' + started['head_branch'] + ' ' + self.original + ' ' + '0' * 40])
        create = self.creates()
        self.assertEqual(len(create), 1)
        self.assertEqual(create[0][create[0].index('--head') + 1], 'owner:' + started['head_branch'])

    def test_t8_started_identity_survives_a_rerun_before_audit(self):
        started = self.start()
        self.ok(self.engine('start'))
        self.assertEqual(self.journal(), started)
        self.freeze()
        self.ok(self.engine('start'))  # a driver rerun after the audit leaves the bound journal alone
        self.assertEqual(self.journal()['phase'], 'bound')
        self.assertEqual(self.journal()['owner'], started['owner'])

    def test_t8_missing_early_ref_pends_instead_of_recreating(self):
        started = self.start()
        self.freeze()
        self.git('update-ref', '-d', 'refs/heads/' + started['head_branch'], self.original)
        result = self.publish()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('PR pending: Pre-created branch is missing; rerun FINAL_AUDIT.', result.stdout)
        self.assertEqual(self.creates(), [])
        self.assertFalse([l for l in self.git_log() if l.startswith('push ')])
        self.assertEqual(self.git('branch', '--show-current'), 'main')

    def test_t8_moved_early_ref_defers_naming_at_freeze(self):
        started = self.start()
        other = self.git('commit-tree', '--no-gpg-sign', self.git('rev-parse', 'HEAD^{tree}'), '-p', self.original, '-m', 'other')
        self.git('update-ref', 'refs/heads/' + started['head_branch'], other, self.original)
        self.freeze()
        j = self.journal()
        self.assertEqual((j['version'], j['phase']), (1, 'bound'))
        self.assertNotIn('early_ref', j)
        self.assertNotEqual(j['owner'], started['owner'])
        self.ok(self.publish())
        self.assertEqual(self.journal()['head_branch'], 'uncle/chat-request-' + j['owner'][:12])
        self.assertEqual(self.git('rev-parse', 'refs/heads/' + started['head_branch']), other)


if __name__ == '__main__':
    unittest.main()
