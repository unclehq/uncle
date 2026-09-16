#!/usr/bin/env python3
"""Issue 59 handoff: release envelope, in-toto Statement, blocking policy,
secret filter, PR block, gitignore boundary and the legacy (no envelopes) path.

Disposable repositories built with fixture_repo (signing off at every level),
a git shim that maps the bare remote to a GitHub URL, and a fake gh.
"""
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import unittest

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(ROOT / 'scripts/lib'))
import fixture_repo  # noqa: E402
import envelope  # noqa: E402

LIB = ROOT / 'scripts/lib/change-pr.sh'
DRIVER = ROOT / 'scripts/change-workflow.sh'
ANSWERS = '\nSummary text\nManual steps\ny\n'
SECRET = 'ghp_abcdefghijklmnopqrstuvwxyz0123456789'

GIT_SHIM = '''#!/usr/bin/env bash
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

GATES = ('BASELINE_REPORT', 'CHANGE_SPEC', 'ADVERSARIAL_REVIEW', 'CHANGE_PLAN', 'IMPLEMENTATION_REVIEW')
READY_AUDIT = '# FINAL_AUDIT.md\n\n## Findings\n\n| ID | Severity | Evidence | Required correction | Blocks |\n|---|---|---|---|---|\n| FA-1 | low | fixture | none | NO |\n\nREADY\n'
NOT_READY_AUDIT = READY_AUDIT.replace('READY\n', 'NOT READY\n').replace('| low | fixture | none | NO |', '| blocking | fixture | fix it | YES |')


class Fixture(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='attestation-statement-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.bin = self.root / 'bin'
        self.bin.mkdir()
        self.bare = self.root / 'remote.git'
        self.env = fixture_repo.isolated_env(
            PATH=str(self.bin) + os.pathsep + os.environ['PATH'], REAL_GIT=fixture_repo.REAL_GIT,
            SERVER=str(self.root / 'server.json'), GH_CALLS=str(self.root / 'gh.jsonl'),
            BASE_BARE=str(self.bare), HOME=str(self.root / 'home'), UNCLE_APPROVAL_NAME='Brian',
            UNCLE_LIB_DIR=str(ROOT / 'scripts/lib'), UNCLE_VERSION='0.1.0-test', STAGEGATE_RUN_ID='run-59')
        (self.root / 'home').mkdir()
        for name, text in (('git', GIT_SHIM), ('gh', GH_FAKE)):
            (self.bin / name).write_text(text)
            (self.bin / name).chmod(0o755)
        subprocess.run([fixture_repo.REAL_GIT, 'init', '--bare', '-q', str(self.bare)], check=True, env=self.env)
        self.repo = fixture_repo.init_repo(self.root / 'repo', env=self.env)
        (self.repo / '.gitignore').write_text((ROOT / '.gitignore').read_text())
        (self.repo / 'source.txt').write_text('before\n')
        (self.repo / 'CHANGE_REQUEST.md').write_text('## Summary\n\nAttested change\n')
        (self.repo / '.uncle').mkdir()
        (self.repo / '.uncle/allowed_signers').write_text('fixture@example.test ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIPlaceholderKeyFixtureOnly0000000000000000\n')
        self.git('add', '-A')
        self.git('add', '-f', '.uncle/allowed_signers')
        self.original = fixture_repo.commit(self.repo, 'initial', env=self.env, add_all=False)
        self.git('remote', 'add', 'origin', str(self.bare))
        self.git('push', '-q', 'origin', 'main')
        self.state = self.repo / '.uncle/workflow'
        (self.state / 'approvals').mkdir(parents=True)
        (self.state / 'origin').write_text('owner/repo\t59\tgh\n')
        (self.repo / 'source.txt').write_text('audited\n')
        for name in ('BASELINE_REPORT', 'CHANGE_SPEC', 'ADVERSARIAL_REVIEW', 'CHANGE_PLAN'):
            (self.repo / (name + '.md')).write_text('# ' + name + '\n\nfixture body\n')
        (self.repo / 'ADVERSARIAL_REVIEW.md').write_text(
            '# Review\n\n## AR-001: High finding\n\n- Severity: High\n- References: x\n- Failure: y\n- Fix: z\n- Verify: w\n\n## Overall assessment\nOne finding.\n')
        (self.repo / 'CHANGE_PLAN.md').write_text('# Plan\n\n| Finding | Disposition | Reason | Exact plan change |\n|---|---|---|---|\n| AR-001 | Accepted | r | c |\n')
        (self.repo / 'FINAL_AUDIT.md').write_text(READY_AUDIT)
        (self.repo / 'VERIFICATION_REPORT.md').write_text('# VR\n')
        (self.repo / 'IMPLEMENTATION_NOTES.md').write_text('## Acceptance delivery\n| ID | Status | Changed code | Observed targeted verification |\n|---|---|---|---|\n| AC-1 | IMPLEMENTED | source.txt | Fixture check PASS |\n')
        (self.repo / 'CHANGE_TEST_REPORT.md').write_text('# report\n')
        (self.state / 'green-check.tsv').write_text('PASS\tcmd1\nPREEXISTING\tcmd2\n')

    def git(self, *args, data=None):
        return fixture_repo.git(self.repo, *args, env=self.env, data=data)

    def engine(self, action, text='', **env):
        return subprocess.run(['bash', '-c', '. "$1"; change_pr_engine "$2"', 'test', str(LIB), action],
                              cwd=self.repo, env=dict(self.env, **env), input=text, text=True,
                              stdout=subprocess.PIPE, stderr=subprocess.STDOUT)

    def ok(self, result):
        self.assertEqual(result.returncode, 0, result.stdout)

    def artifact(self):
        result = self.engine('artifact')
        self.ok(result)
        return result.stdout.strip()

    def approve(self, name, action='APPROVE', approved_by='Brian', delegated_by='', digest=True):
        approvals = self.state / 'approvals'
        if digest:
            path = self.repo / (name + '.md')
            (approvals / (name + '.sha256')).write_text(hashlib.sha256(path.read_bytes()).hexdigest() + '\n')
        (approvals / (name + '.gate-action')).write_text(action + '\n')
        (approvals / (name + '.approved-by')).write_text(approved_by + '\n')
        (approvals / (name + '.delegated-by')).write_text(delegated_by + '\n')

    def seed_envelopes(self, artifact=None, verification='pass', audit='pass', reason=''):
        artifact = artifact or self.artifact()
        for name in ('BASELINE_REPORT', 'CHANGE_SPEC', 'ADVERSARIAL_REVIEW', 'CHANGE_PLAN'):
            self.approve(name)
        self.approve('IMPLEMENTATION_REVIEW', digest=False)
        state, root = self.state, self.repo
        envelope.write_envelope(state, 'requirements', 'pass', evidence=['BASELINE_REPORT.md', 'CHANGE_SPEC.md'],
                                root=root, approvals=['BASELINE_REPORT', 'CHANGE_SPEC'])
        envelope.write_envelope(state, 'review', 'pass', evidence=['ADVERSARIAL_REVIEW.md'], root=root,
                                findings_path='ADVERSARIAL_REVIEW.md')
        envelope.write_envelope(state, 'plan', 'pass', evidence=['CHANGE_PLAN.md'], root=root,
                                dispositions_path='CHANGE_PLAN.md', approvals=['CHANGE_PLAN', 'ADVERSARIAL_REVIEW'],
                                inputs={'review': hashlib.sha256((root / 'ADVERSARIAL_REVIEW.md').read_bytes()).hexdigest()})
        envelope.write_envelope(state, 'implementation', 'pass', artifact=artifact, root=root,
                                approvals=['IMPLEMENTATION_REVIEW'], evidence=['IMPLEMENTATION_NOTES.md'])
        envelope.write_envelope(state, 'verification', verification, reason=reason or '2 commands: 1 pass, 1 pre-existing, 0 regressed',
                                inputs={'artifact': artifact}, root=root, evidence=['.uncle/workflow/green-check.tsv'])
        envelope.write_envelope(state, 'audit', audit, reason='READY' if audit == 'pass' else 'NOT_READY',
                                inputs={'artifact': artifact}, root=root, evidence=['FINAL_AUDIT.md'])
        return artifact

    def freeze(self, verdict='READY'):
        self.ok(self.engine('freeze'))
        sha = hashlib.sha256((self.repo / 'FINAL_AUDIT.md').read_bytes()).hexdigest()
        (self.state / 'audit-verdict').write_text('run-59\t' + verdict + '\t' + sha + '\n')
        self.ok(self.engine('bind'))

    def handoff(self, text=ANSWERS, **env):
        return self.engine('handoff', text, **env)

    def journal(self):
        return json.loads((self.state / 'pr/journal.json').read_text())

    def creates(self):
        path = self.root / 'gh.jsonl'
        rows = [json.loads(line) for line in path.read_text().splitlines()] if path.exists() else []
        return [a for a in rows if a[:2] == ['pr', 'create']]

    def statement(self):
        raw = (self.repo / '.uncle/attestation.json').read_bytes()
        value = json.loads(raw)
        self.assertEqual(envelope.canonical(value), raw)
        return value


def keys_of(value, out):
    if isinstance(value, dict):
        for key, item in value.items():
            out.add(key)
            keys_of(item, out)
    elif isinstance(value, list):
        for item in value:
            keys_of(item, out)
    return out


class StatementTests(Fixture):
    def test_handoff_commits_statement_beside_audited_files(self):
        artifact = self.seed_envelopes()
        self.freeze()
        before = self.journal()
        result = self.handoff()
        self.ok(result)
        self.assertIn('Attestation: none ' + artifact[:12], result.stdout)
        self.assertIn('Envelope: release pass', result.stdout)
        j = self.journal()
        self.assertEqual(j['phase'], 'created')
        self.assertEqual(len(self.creates()), 1)
        stmt = self.statement()
        self.assertEqual(stmt['_type'], 'https://in-toto.io/Statement/v1')
        self.assertEqual(stmt['predicateType'], 'https://uncle.dev/attestation/v1')
        self.assertEqual(stmt['subject'], [{'name': 'owner/repo@' + j['head_branch'], 'digest': {'gitTree': artifact}}])
        self.assertEqual(stmt['predicate']['release']['artifact']['digest']['gitTree'], artifact)
        self.assertEqual(stmt['predicate']['schema_version'], '1')
        self.assertEqual(stmt['predicate']['authentication'], 'none')
        self.assertEqual(set(stmt['predicate']['envelopes']), set(envelope.STAGES))
        self.assertEqual(stmt['predicate']['envelopes']['release']['result'], 'pass')
        # The commit is the journal's commit tree, one parent, and carries the
        # attestation beside the audited files (AC-4, AC-23).
        self.assertEqual(self.git('rev-parse', 'HEAD^{tree}'), j['commit_tree'])
        self.assertEqual(self.git('rev-list', '--parents', '-n', '1', 'HEAD').split(), [j['intended_head'], self.original])
        names = self.git('ls-tree', '-r', '--name-only', 'HEAD').split('\n')
        self.assertIn('.uncle/attestation.json', names)
        self.assertIn('source.txt', names)
        self.assertNotIn('.uncle/attestation.sig', names)
        self.assertEqual(self.git('show', 'HEAD:.uncle/attestation.json'), (self.repo / '.uncle/attestation.json').read_text().strip())
        self.assertEqual(j['audited_tree'], before['commit_tree'])
        self.assertNotEqual(j['audited_tree'], j['commit_tree'])
        # AR-006: the tracked trust root is byte-identical in the commit tree.
        self.assertEqual(self.git('show', 'HEAD:.uncle/allowed_signers'), (self.repo / '.uncle/allowed_signers').read_text().strip())
        # The artifact digest is the head tree minus the excluded files.
        self.assertNotIn('.uncle/attestation.json', self.git('ls-tree', '-r', '--name-only', artifact).split('\n'))
        self.assertIn('source.txt', self.git('ls-tree', '-r', '--name-only', artifact).split('\n'))
        # AC-12: the PR block is rendered from the Statement.
        body = (self.root / 'server.body').read_text()
        self.assertIn('UNCLE CHANGE ATTESTATION', body)
        self.assertIn(artifact[:12], body)
        self.assertRegex(body, r'Gate: publication\s+APPROVED \(human\)')
        self.assertRegex(body, r'Gate: plan approval\s+APPROVED \(human\)')
        self.assertRegex(body, r'Verification\s+2 commands: 1 pass, 1 pre-existing, 0 regressed')
        self.assertRegex(body, r'Review result\s+READY')
        self.assertIn('Closes owner/repo#59', body)
        # AC-2: every key of every envelope and the Statement is in the vocabulary.
        keys = keys_of(stmt, set())
        for stage in envelope.STAGES:
            keys_of(json.loads((self.state / 'envelopes' / (stage + '.json')).read_bytes()), keys)
        self.assertFalse(keys & envelope.FORBIDDEN_KEYS, keys & envelope.FORBIDDEN_KEYS)
        self.assertTrue(keys <= envelope.VOCABULARY | envelope.STRUCTURE | set(envelope.STAGES), keys - envelope.VOCABULARY - envelope.STRUCTURE)
        # Resume is idempotent: the same Statement bytes and no second PR.
        again = self.handoff('')
        self.ok(again)
        self.assertEqual(len(self.creates()), 1)
        self.assertEqual(self.statement(), stmt)

    def test_commit_from_the_audited_tree_is_rejected(self):
        self.seed_envelopes()
        self.freeze()
        self.ok(self.handoff())
        j = self.journal()
        other = self.git('commit-tree', j['audited_tree'], '-p', self.original, '-m', 'wrong tree')
        (self.state / 'pr/journal.json').write_text(json.dumps(dict(j, intended_head=other), sort_keys=True) + '\n')
        result = self.engine('validate')
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('Handoff commit tree differs from audit', result.stdout)

    def test_not_ready_override_is_recorded_but_does_not_release(self):
        # AC-20 / D-17: the override reaches the handoff, which refuses before
        # any git write; release.json records the reason.
        (self.repo / 'FINAL_AUDIT.md').write_text(NOT_READY_AUDIT)
        self.seed_envelopes(audit='fail')
        self.freeze('NOT_READY')
        result = self.engine('verdict-override', 'y\n')
        self.ok(result)
        self.assertIn('Override recorded', result.stdout)
        result = self.handoff()
        self.assertEqual(result.returncode, 3, result.stdout)
        self.assertIn('PR pending: Attestation blocked: audit result fail', result.stdout)
        self.assertIn('the override is recorded but does not release', result.stdout)
        self.assertEqual(self.creates(), [])
        self.assertEqual(self.git('rev-parse', 'HEAD'), self.original)
        self.assertEqual(self.journal()['phase'], 'bound')
        self.assertFalse((self.repo / '.uncle/attestation.json').exists())
        release = envelope.read_envelope(self.state, 'release')
        self.assertEqual(release['result'], 'fail')
        self.assertIn('audit result fail', release['reason'])
        self.assertEqual(release['override']['gate'], 'verdict-override')

    def test_verification_failure_and_missing_envelope_block(self):
        self.seed_envelopes(verification='fail')
        self.freeze()
        result = self.handoff()
        self.assertEqual(result.returncode, 3, result.stdout)
        self.assertIn('verification result fail', result.stdout)
        self.assertEqual(self.git('rev-parse', 'HEAD'), self.original)
        (self.state / 'envelopes/review.json').unlink()
        result = self.handoff()
        self.assertEqual(result.returncode, 3, result.stdout)
        self.assertIn('review result unavailable; envelope missing', result.stdout)
        self.assertEqual(self.creates(), [])

    def test_artifact_drift_between_stages_blocks(self):
        self.seed_envelopes(artifact='0' * 40)
        self.freeze()
        result = self.handoff()
        self.assertEqual(result.returncode, 3, result.stdout)
        self.assertIn('artifact mismatch', result.stdout)
        self.assertEqual(envelope.read_envelope(self.state, 'release')['result'], 'fail')

    def test_skipped_diff_gate_is_a_required_unapproved_entry(self):
        self.seed_envelopes()
        self.approve('IMPLEMENTATION_REVIEW', action='SKIPPED', approved_by='', delegated_by='disabled:WORKFLOW_DIFF_GATE=0', digest=False)
        self.freeze()
        self.ok(self.handoff())
        entries = {row['gate']: row for row in self.statement()['predicate']['approvals']}
        self.assertEqual((entries['IMPLEMENTATION_REVIEW']['required'], entries['IMPLEMENTATION_REVIEW']['approved_by'],
                          entries['IMPLEMENTATION_REVIEW']['delegated_by']), (True, '', 'disabled:WORKFLOW_DIFF_GATE=0'))
        self.assertEqual((entries['publication']['required'], entries['publication']['approved_by']), (True, 'Brian'))
        self.assertEqual(entries['CHANGE_PLAN']['approved_by'], 'Brian')
        verify = subprocess.run([sys.executable, str(ROOT / 'scripts/uncle-verify.py')], cwd=self.repo, env=self.env,
                                text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        self.assertEqual(verify.returncode, 1, verify.stdout)
        self.assertIn('required gate IMPLEMENTATION_REVIEW has no human approval', verify.stdout)
        self.assertTrue(verify.stdout.rstrip().endswith('NOT VERIFIED'))

    def test_delegated_plan_approval_is_kept_verbatim_and_not_human(self):
        self.seed_envelopes()
        self.approve('CHANGE_PLAN', approved_by='', delegated_by='supervisor:standing:Brian')
        self.freeze()
        self.ok(self.handoff())
        entries = {row['gate']: row for row in self.statement()['predicate']['approvals']}
        self.assertEqual((entries['CHANGE_PLAN']['approved_by'], entries['CHANGE_PLAN']['delegated_by']), ('', 'supervisor:standing:Brian'))
        self.assertRegex((self.root / 'server.body').read_text(), r'Gate: plan approval\s+APPROVED \(supervisor:standing:Brian\)')

    def test_secrets_and_absolute_paths_never_reach_the_statement(self):
        self.seed_envelopes(reason='2 commands; token=' + SECRET)
        self.approve('CHANGE_SPEC', approved_by='ghp_' + 'x' * 36)
        envelope.write_envelope(self.state, 'requirements', 'pass', reason='log at /tmp/elsewhere/run.log',
                                evidence=['BASELINE_REPORT.md'], root=self.repo)
        self.freeze()
        self.ok(self.handoff(ANSWERS, UNCLE_APPROVAL_NAME='Brian', MY_API_TOKEN='supersecretvalue123'))
        raw = (self.repo / '.uncle/attestation.json').read_text()
        self.assertNotIn(SECRET, raw)
        self.assertNotIn('ghp_', raw)
        self.assertNotIn('/tmp/elsewhere', raw)
        self.assertNotIn('supersecretvalue123', raw)
        self.assertNotIn(str(self.root), raw)
        self.assertNotIn(os.environ.get('HOME', 'HOME-unset'), raw)
        self.assertIn('[redacted]', raw)
        stmt = json.loads(raw)
        for match in re.finditer(r'"([^"]*)"', raw):
            self.assertFalse(envelope._filters()[0].search(match.group(1)), match.group(1))
            self.assertFalse(envelope._filters()[1].search(match.group(1)), match.group(1))
        self.assertEqual(stmt['predicate']['envelopes']['verification']['reason'], '[redacted]')

    def test_without_envelopes_directory_the_legacy_path_runs(self):
        # D-18 / AC-26: fixtures that never had a driver keep today's handoff.
        self.freeze()
        result = self.handoff()
        self.ok(result)
        self.assertIn('Attestation: none (no envelopes directory; run predates attestation)', result.stdout)
        self.assertFalse((self.repo / '.uncle/attestation.json').exists())
        self.assertFalse((self.state / 'envelopes').exists())
        j = self.journal()
        self.assertEqual(j['phase'], 'created')
        self.assertNotIn('statement', j)
        self.assertEqual(self.git('rev-parse', 'HEAD^{tree}'), j['commit_tree'])
        self.assertNotIn('.uncle/attestation.json', self.git('ls-tree', '-r', '--name-only', 'HEAD'))
        self.assertEqual(j['attestation']['gate_publication'], 'APPROVED (human)')
        self.assertIn('UNCLE CHANGE ATTESTATION', (self.root / 'server.body').read_text())

    def test_manifest_without_directory_refuses(self):
        self.seed_envelopes()
        self.freeze()
        import shutil
        (self.state / 'envelopes.manifest').write_text('{".": "present"}\n')
        shutil.rmtree(self.state / 'envelopes')
        result = self.handoff()
        self.assertEqual(result.returncode, 3, result.stdout)
        self.assertIn('envelopes directory is missing', result.stdout)
        self.assertEqual(self.creates(), [])

    def test_gitignore_boundary(self):
        # AC-14, against this repository's .gitignore copied into the fixture.
        for path, expected in (('.uncle/attestation.json', 1), ('.uncle/attestation.sig', 1),
                               ('.uncle/allowed_signers', 1), ('.uncle/workflow/envelopes/x.json', 0), ('.uncle/config', 0)):
            result = subprocess.run([fixture_repo.REAL_GIT, 'check-ignore', '-q', path], cwd=self.repo, env=self.env)
            self.assertEqual(result.returncode, expected, path)

    def test_docs_have_the_required_headings(self):
        # AC-15
        integration = (ROOT / 'GITHUB_INTEGRATION.md').read_text()
        readme = (ROOT / 'scripts/README.md').read_text()
        for word in ('Envelopes', 'Signing', 'Trust root', 'Verification', 'Audit override'):
            self.assertRegex(integration, r'(?m)^#+ .*' + word, word)
        self.assertRegex(readme, r'(?m)^### uncle-verify\.py')
        self.assertRegex(readme, r'(?m)^### Envelopes and attestation')
        self.assertIn('## Attestation', integration)


class DriverTests(Fixture):
    """AC-1: the driver's own writes from FINAL_AUDIT onward, then handoff."""

    def reviewer(self, text):
        path = self.bin / 'reviewer'
        path.write_text('#!/usr/bin/env python3\nfrom pathlib import Path\nimport sys\n'
                        "Path(sys.argv[sys.argv.index('--output-last-message') + 1]).write_text(%r)\n" % text)
        path.chmod(0o755)
        return path

    def run_driver(self, text, **extra):
        env = dict(self.env, UNCLE_PROJECT_ROOT=str(self.repo), WORKFLOW_AUDIT_GATE='0', WORKFLOW_CLOSE_ISSUE='1',
                   UNATTENDED='0', WORKFLOW_REVIEWER_CMD=str(self.bin / 'reviewer'), **extra)
        return subprocess.run(['bash', str(DRIVER)], cwd=self.repo, env=env, input=text, text=True,
                              stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=120)

    def test_final_audit_writes_audit_and_release_envelopes(self):
        artifact = self.seed_envelopes()
        for stage in ('audit',):
            (self.state / 'envelopes' / (stage + '.json')).unlink()
        (self.repo / 'CHANGE_SPEC.md').write_text('## Acceptance criteria\n| ID | Criterion | Verification |\n|---|---|---|\n| AC-1 | Fixture behavior | Fixture check |\n')
        self.approve('CHANGE_SPEC')
        self.reviewer(READY_AUDIT)
        (self.state / 'state').write_text('59:FINAL_AUDIT\n')
        result = self.run_driver('\nSummary\nManual\ny\n')
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertIn('Envelope: audit unavailable', result.stdout)
        self.assertIn('Envelope: audit pass', result.stdout)
        self.assertIn('Envelope: release pass', result.stdout)
        self.assertIn('Attestation: none ' + artifact[:12], result.stdout)
        audit = envelope.read_envelope(self.state, 'audit')
        self.assertEqual((audit['result'], audit['reason'], audit['attempt']), ('pass', 'READY', 3))
        self.assertEqual(audit['inputs']['artifact']['digest']['gitTree'], artifact)
        self.assertEqual(audit['producer']['role'], 'verifier')
        for stage in envelope.STAGES:
            env = envelope.read_envelope(self.state, stage)
            self.assertIsNotNone(env, stage)
            for key in ('schema_version', 'stage', 'attempt', 'producer', 'inputs', 'result', 'evidence', 'produced_at'):
                self.assertIn(key, env, stage)
            self.assertEqual(set(env['producer']), {'role', 'runner', 'model', 'uncle_version'})
        self.assertEqual(len(self.creates()), 1, result.stdout)
        self.assertEqual((self.state / 'state').read_text().strip(), '59:COMPLETE')
        self.statement()

    def test_not_ready_audit_with_driver_override_never_publishes(self):
        self.seed_envelopes()
        (self.state / 'envelopes/audit.json').unlink()
        (self.repo / 'CHANGE_SPEC.md').write_text('## Acceptance criteria\n| ID | Criterion | Verification |\n|---|---|---|\n| AC-1 | Fixture behavior | Fixture check |\n')
        self.approve('CHANGE_SPEC')
        self.reviewer(NOT_READY_AUDIT)
        (self.state / 'state').write_text('59:FINAL_AUDIT\n')
        result = self.run_driver('y\n\nSummary\nManual\ny\n')
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertIn('Override recorded', result.stdout)
        self.assertIn('PR pending: Attestation blocked: audit result fail', result.stdout)
        self.assertEqual(envelope.read_envelope(self.state, 'audit')['result'], 'fail')
        self.assertEqual(envelope.read_envelope(self.state, 'release')['result'], 'fail')
        self.assertEqual(self.creates(), [])
        self.assertEqual(self.git('rev-parse', 'HEAD'), self.original)
        self.assertEqual((self.state / 'state').read_text().strip(), '59:COMPLETE')


if __name__ == '__main__':
    unittest.main(verbosity=0)
