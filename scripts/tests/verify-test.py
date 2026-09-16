#!/usr/bin/env python3
"""scripts/uncle-verify.py: one test per check 1-8, refusal before check 1,
trust-root and tool-absence verdicts, the launcher's working directory, and
the stdlib-only import list (AC-7, AC-8, AC-10, AC-11, AC-13, AC-19, AC-21,
AC-22, AC-24).

The fixture commits a Statement built by scripts/lib/envelope.py into a
disposable repository whose HEAD also carries .uncle/attestation.json,
.uncle/allowed_signers and CHANGE_PLAN.md, so check 8 only passes when the
verifier applies ARTIFACT_EXCLUDES (AR-001). Signatures use a disposable
ed25519 key made by ssh-keygen; nothing touches the user's keys.
"""
import base64
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
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

VERIFY = ROOT / 'scripts/uncle-verify.py'
ARTIFACT_FILES = {'source.txt': 'audited\n', 'lib/mod.py': 'x = 1\n'}
DOCS = {'BASELINE_REPORT': '# baseline\n', 'CHANGE_SPEC': '# spec\n', 'ADVERSARIAL_REVIEW': '# review\n', 'CHANGE_PLAN': '# plan\n'}


def approval(gate, digest='', approved_by='Brian', delegated_by='', required=True):
    return {'gate': gate, 'required': required, 'approved_by': approved_by, 'delegated_by': delegated_by,
            'digest': digest, 'timestamp': '2026-09-15T00:00:00Z'}


class Fixture(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='verify-')
        self.addCleanup(self.temp.cleanup)
        self.tmp = Path(self.temp.name)
        # A PATH with only git and python3: the verifier must not need more.
        self.bin = self.tmp / 'bin'
        self.bin.mkdir()
        for tool in ('git', 'python3'):
            os.symlink(shutil.which(tool), self.bin / tool)
        self.env = fixture_repo.isolated_env(PATH=str(self.bin), HOME=str(self.tmp / 'home'))
        # Signature checks need ssh-keygen as well; nothing else is added.
        self.ssh_env = dict(self.env, PATH=str(self.bin) + os.pathsep + os.path.dirname(shutil.which('ssh-keygen')))
        (self.tmp / 'home').mkdir()
        self.repo = fixture_repo.init_repo(self.tmp / 'repo', env=self.env)
        for name, text in ARTIFACT_FILES.items():
            (self.repo / name).parent.mkdir(parents=True, exist_ok=True)
            (self.repo / name).write_text(text)
        self.key = self.tmp / 'signing-key'
        subprocess.run(['ssh-keygen', '-q', '-t', 'ed25519', '-N', '', '-C', 'fixture@example.test', '-f', str(self.key)], check=True)
        (self.repo / '.uncle').mkdir()
        (self.repo / '.uncle/allowed_signers').write_text('fixture@example.test ' + self.key.with_suffix('.pub').read_text())
        for name, text in DOCS.items():
            (self.repo / (name + '.md')).write_text(text)
        fixture_repo.commit(self.repo, 'artifact', env=self.env)
        self.artifact = self.artifact_tree()
        self.statement = self.build_statement()

    def git(self, *args, data=None):
        return fixture_repo.git(self.repo, *args, env=self.env, data=data)

    def artifact_tree(self):
        # The artifact per D-4: the working files minus ARTIFACT_EXCLUDES.
        index = self.tmp / 'index'
        env = dict(self.env, GIT_INDEX_FILE=str(index))
        subprocess.run([fixture_repo.REAL_GIT, 'read-tree', '--empty'], cwd=self.repo, env=env, check=True)
        entries = ''
        for name in sorted(ARTIFACT_FILES):
            oid = self.git('hash-object', '-w', name)
            entries += '100644 %s\t%s\n' % (oid, name)
        subprocess.run([fixture_repo.REAL_GIT, 'update-index', '--index-info'], cwd=self.repo, env=env, input=entries, text=True, check=True)
        return subprocess.check_output([fixture_repo.REAL_GIT, 'write-tree'], cwd=self.repo, env=env).decode().strip()

    def digest(self, name):
        return hashlib.sha256((self.repo / (name + '.md')).read_bytes()).hexdigest()

    def build_statement(self, artifact=None, **override):
        artifact = artifact or self.artifact
        base = dict(schema_version='1', attempt=1, produced_at='2026-09-15T00:00:00Z',
                    producer={'role': 'verifier', 'runner': 'codex', 'model': 'm', 'uncle_version': '0.1.0'}, inputs={})
        envelopes = {
            'requirements': dict(base, stage='requirements', result='pass',
                                 evidence=[{'path': 'BASELINE_REPORT.md', 'digest': {'sha256': self.digest('BASELINE_REPORT')}},
                                           {'path': 'CHANGE_SPEC.md', 'digest': {'sha256': self.digest('CHANGE_SPEC')}}]),
            'review': dict(base, stage='review', result='pass',
                           findings=[{'id': 'AR-001', 'severity': 'blocking', 'evidence': {'sha256': self.digest('ADVERSARIAL_REVIEW')}},
                                     {'id': 'AR-002', 'severity': 'advisory', 'evidence': {'sha256': self.digest('ADVERSARIAL_REVIEW')}}],
                           evidence=[{'path': 'ADVERSARIAL_REVIEW.md', 'digest': {'sha256': self.digest('ADVERSARIAL_REVIEW')}}]),
            'plan': dict(base, stage='plan', result='pass', dispositions=[{'finding': 'AR-001', 'action': 'Accepted'}],
                         evidence=[{'path': 'CHANGE_PLAN.md', 'digest': {'sha256': self.digest('CHANGE_PLAN')}}]),
            'implementation': dict(base, stage='implementation', result='pass', artifact={'digest': {'gitTree': artifact}}, evidence=[]),
            'verification': dict(base, stage='verification', result='pass', inputs={'artifact': {'digest': {'gitTree': artifact}}}, evidence=[]),
            'audit': dict(base, stage='audit', result='pass', reason='READY', inputs={'artifact': {'digest': {'gitTree': artifact}}}, evidence=[]),
            'release': dict(base, stage='release', result='pass', artifact={'digest': {'gitTree': artifact}}, evidence=[]),
        }
        approvals = [approval(name, self.digest(name)) for name in DOCS] + [
            approval('IMPLEMENTATION_REVIEW'), approval('FINAL_AUDIT_OVERRIDE', required=False, approved_by=''), approval('publication', artifact)]
        stmt = envelope.statement('owner/repo@uncle/x', artifact, envelopes, approvals,
                                  {'repository': 'owner/repo', 'issue': '59'}, override.pop('authentication', 'none'), '0.1.0', 'run-1')
        for key, value in override.items():
            stmt['predicate'][key] = value
        return stmt

    def commit_statement(self, stmt, sig=None, extra=None):
        payload = envelope.canonical(stmt)
        (self.repo / '.uncle/attestation.json').write_bytes(payload)
        sig_path = self.repo / '.uncle/attestation.sig'
        if sig is not None:
            sig_path.write_bytes(sig)
        elif sig_path.exists():
            sig_path.unlink()
        for name, text in (extra or {}).items():
            (self.repo / name).write_text(text)
        self.git('add', '-A')
        self.git('add', '-f', '.uncle/attestation.json', '.uncle/allowed_signers')
        if sig is not None:
            self.git('add', '-f', '.uncle/attestation.sig')
        return fixture_repo.commit(self.repo, 'attested', env=self.env, add_all=False)

    def signed(self, stmt, key=None):
        payload = envelope.canonical(stmt)
        block, error = envelope.sign(payload, 'ssh', str(key or self.key))
        self.assertIsNotNone(block, error)
        return envelope.canonical(block)

    def verify(self, *args, env=None, cwd=None):
        return subprocess.run([str(self.bin / 'python3'), str(VERIFY), *args], cwd=cwd or self.repo, env=env or self.env,
                              text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)

    def assert_not_verified(self, result, *needles):
        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertTrue(result.stdout.rstrip().endswith('NOT VERIFIED'), result.stdout)
        for needle in needles:
            self.assertIn(needle, result.stdout)


class VerifyTests(Fixture):
    def test_verified_with_signature_and_trust_root(self):
        self.commit_statement(self.build_statement(authentication='ssh'), self.signed(self.build_statement(authentication='ssh')))
        result = self.verify(env=self.ssh_env)
        self.assertEqual(result.returncode, 0, result.stdout)
        lines = result.stdout.splitlines()
        self.assertEqual(lines[0], 'UNCLE CHANGE VERIFICATION')
        self.assertTrue(lines[-1] == 'VERIFIED', result.stdout)
        self.assertIn('✓ signature valid (ssh: fixture@example.test, .uncle/allowed_signers)', result.stdout)
        self.assertIn('✓ head tree matches release artifact', result.stdout)
        self.assertEqual(sum(1 for line in lines if line.startswith('✓')), 13, result.stdout)
        # The head tree carries files the artifact excludes (AR-001).
        names = self.git('ls-tree', '-r', '--name-only', 'HEAD').split('\n')
        for name in ('.uncle/attestation.json', '.uncle/allowed_signers', 'CHANGE_PLAN.md'):
            self.assertIn(name, names)

    def test_unsigned_is_integrity_only(self):
        self.commit_statement(self.statement)
        result = self.verify()
        self.assertEqual(result.returncode, 3, result.stdout)
        self.assertTrue(result.stdout.rstrip().endswith('INTEGRITY ONLY — NOT AUTHENTICATED'), result.stdout)
        self.assertNotIn('\nVERIFIED', result.stdout)

    def test_signature_without_trust_root_is_untrusted(self):
        stmt = self.build_statement(authentication='ssh')
        self.commit_statement(stmt, self.signed(stmt))
        (self.repo / '.uncle/allowed_signers').unlink()
        result = self.verify(env=self.ssh_env)
        self.assertEqual(result.returncode, 3, result.stdout)
        self.assertIn('no trust root at .uncle/allowed_signers', result.stdout)
        self.assertTrue(result.stdout.rstrip().endswith('INTEGRITY ONLY — SIGNATURE PRESENT BUT UNTRUSTED'), result.stdout)
        # AC-8: an explicit trust root path restores VERIFIED.
        allowed = self.tmp / 'signers'
        allowed.write_text('fixture@example.test ' + self.key.with_suffix('.pub').read_text())
        result = self.verify('--allowed-signers', str(allowed), env=self.ssh_env)
        self.assertEqual(result.returncode, 0, result.stdout)

    def test_invalid_signature_is_not_verified(self):
        stmt = self.build_statement(authentication='ssh')
        other = self.tmp / 'other-key'
        subprocess.run(['ssh-keygen', '-q', '-t', 'ed25519', '-N', '', '-f', str(other)], check=True)
        self.commit_statement(stmt, self.signed(stmt, other))
        self.assert_not_verified(self.verify(env=self.ssh_env), 'signature invalid against .uncle/allowed_signers')

    def test_check_1_tampered_bytes(self):
        payload = envelope.canonical(self.statement)
        self.commit_statement(self.statement)
        (self.repo / '.uncle/attestation.json').write_bytes(payload.replace(b'"result":"pass"', b'"result": "pass"', 1))
        self.assert_not_verified(self.verify(), 'attestation bytes are not canonical', 're-serialized', 'on disk')

    def test_check_2_dsse_payload_mismatch(self):
        stmt = self.build_statement(authentication='ssh')
        block = json.loads(self.signed(stmt))
        block['payload'] = base64.b64encode(envelope.canonical(self.build_statement(authentication='ssh', run_id='other'))).decode()
        self.commit_statement(stmt, envelope.canonical(block))
        self.assert_not_verified(self.verify(), 'DSSE payload differs from the attestation bytes')

    def test_check_3_approved_document_mismatch(self):
        self.commit_statement(self.statement, extra={'CHANGE_PLAN.md': '# edited after approval\n'})
        self.assert_not_verified(self.verify(), 'approved CHANGE_PLAN digest mismatch (committed copy)', 'approved:', 'present:')

    def test_check_3_embedded_copy_when_document_not_committed(self):
        # The document is gone from the tree; only the envelope's digest remains.
        (self.repo / 'CHANGE_SPEC.md').unlink()
        self.commit_statement(self.statement)
        self.assertNotIn('CHANGE_SPEC.md', self.git('ls-tree', '-r', '--name-only', 'HEAD'))
        result = self.verify()
        self.assertEqual(result.returncode, 3, result.stdout)
        self.assertIn('✓ approved change spec', result.stdout)
        stmt = json.loads(json.dumps(self.statement))
        stmt['predicate']['envelopes']['requirements']['evidence'][1]['digest']['sha256'] = 'f' * 64
        self.commit_statement(stmt)
        self.assert_not_verified(self.verify(), 'approved CHANGE_SPEC digest mismatch (embedded copy)')

    def test_check_4_artifact_mismatch(self):
        stmt = self.build_statement()
        stmt['predicate']['envelopes']['verification']['inputs']['artifact']['digest']['gitTree'] = 'a' * 40
        self.commit_statement(stmt)
        self.assert_not_verified(self.verify(), 'artifact mismatch', 'verification input', 'a' * 40, 'release artifact')

    def test_check_5_stage_result_not_pass(self):
        for stage in ('review', 'verification', 'audit'):
            stmt = self.build_statement()
            stmt['predicate']['envelopes'][stage]['result'] = 'unavailable'
            stmt['predicate']['envelopes'][stage]['reason'] = 'reviewer did not complete'
            self.commit_statement(stmt)
            self.assert_not_verified(self.verify(), stage + ' result is unavailable, not pass; reviewer did not complete')

    def test_check_6_blocking_finding_without_disposition(self):
        stmt = self.build_statement()
        stmt['predicate']['envelopes']['plan']['dispositions'] = []
        self.commit_statement(stmt)
        self.assert_not_verified(self.verify(), 'blocking finding without a disposition: AR-001')

    def test_check_7_delegated_only_gate_fails_for_each_required_gate(self):
        for gate in ('BASELINE_REPORT', 'CHANGE_SPEC', 'ADVERSARIAL_REVIEW', 'CHANGE_PLAN', 'IMPLEMENTATION_REVIEW', 'publication'):
            for approved_by, delegated_by in (('', 'supervisor:standing:Brian'), ('', 'unattended'), ('', 'disabled:WORKFLOW_DIFF_GATE=0'), ('', '')):
                stmt = self.build_statement()
                for row in stmt['predicate']['approvals']:
                    if row['gate'] == gate:
                        row['approved_by'], row['delegated_by'] = approved_by, delegated_by
                self.commit_statement(stmt)
                self.assert_not_verified(self.verify(), 'required gate %s has no human approval' % gate,
                                         'delegated_by: ' + (delegated_by or 'empty'))
        # A non-required override gate answered by nobody does not fail.
        self.commit_statement(self.statement)
        self.assertEqual(self.verify().returncode, 3)

    def test_check_8_head_tree_differs(self):
        self.commit_statement(self.statement, extra={'source.txt': 'changed after release\n'})
        self.assert_not_verified(self.verify(), 'head tree does not match the release artifact', 'head tree (filtered):', 'release artifact:')
        # --tree names the attested commit explicitly (AC-8).
        good = self.commit_statement(self.statement, extra={'source.txt': ARTIFACT_FILES['source.txt']})
        self.commit_statement(self.statement, extra={'source.txt': 'later\n'})
        self.assertEqual(self.verify('--tree', good).returncode, 3, self.verify('--tree', good).stdout)

    def test_check_8_subject_differs_from_release(self):
        stmt = self.build_statement()
        stmt['subject'][0]['digest']['gitTree'] = 'b' * 40
        self.commit_statement(stmt)
        self.assert_not_verified(self.verify(), 'subject digest:')

    def test_refuses_unknown_schema_and_predicate_before_check_1(self):
        for key, value in (('schema_version', '2'), ('predicateType', 'https://example.test/other')):
            stmt = self.build_statement()
            if key == 'schema_version':
                stmt['predicate'][key] = value
            else:
                stmt[key] = value
            self.commit_statement(stmt)
            result = self.verify()
            self.assertEqual(result.returncode, 1, result.stdout)
            self.assertIn('refused', result.stdout)
            self.assertNotIn('✓', result.stdout)
            self.assertTrue(result.stdout.rstrip().endswith('NOT VERIFIED'))

    def test_explicit_attestation_path(self):
        self.commit_statement(self.statement)
        copy = self.tmp / 'att.json'
        copy.write_bytes((self.repo / '.uncle/attestation.json').read_bytes())
        self.assertEqual(self.verify('--attestation', str(copy)).returncode, 3)
        result = self.verify('--attestation', str(self.tmp / 'missing.json'))
        self.assertEqual(result.returncode, 1)
        self.assertIn('no attestation at', result.stdout)

    def test_missing_ssh_keygen_is_a_message_not_a_traceback(self):
        stmt = self.build_statement(authentication='ssh')
        self.commit_statement(stmt, self.signed(stmt))
        result = self.verify()  # PATH holds only git and python3
        self.assertEqual(result.returncode, 3, result.stdout)
        self.assertIn('ssh-keygen is not installed', result.stdout)
        self.assertNotIn('Traceback', result.stdout)
        self.assertTrue(result.stdout.rstrip().endswith('INTEGRITY ONLY — SIGNATURE PRESENT BUT UNTRUSTED'))
        env = dict(self.env, PATH=str(self.bin) + os.pathsep + os.path.dirname(shutil.which('ssh-keygen')))
        self.assertEqual(self.verify(env=env).returncode, 0)

    def test_missing_cosign_and_gh_are_messages(self):
        stmt = self.build_statement(authentication='sigstore')
        block = {'payloadType': envelope.PAYLOAD_TYPE, 'payload': base64.b64encode(envelope.canonical(stmt)).decode(),
                 'signatures': [{'keyid': 'sigstore', 'sig': base64.b64encode(b'{}').decode(), 'signer': 'sigstore'}]}
        self.commit_statement(stmt, envelope.canonical(block))
        result = self.verify('--certificate-identity', 'me@example.test', '--certificate-oidc-issuer', 'https://issuer.example')
        self.assertEqual(result.returncode, 3, result.stdout)
        self.assertIn('cosign is not installed', result.stdout)
        self.assertNotIn('Traceback', result.stdout)
        result = self.verify()
        self.assertIn('no --certificate-identity/--certificate-oidc-issuer given', result.stdout)
        result = self.verify('https://github.com/owner/repo/pull/7')
        self.assertEqual(result.returncode, 2, result.stdout)
        self.assertIn('gh is not installed', result.stdout)
        self.assertNotIn('Traceback', result.stdout)

    def test_pr_argument_uses_gh_head(self):
        head = self.commit_statement(self.statement)
        gh = self.bin / 'gh'
        gh.write_text('#!/bin/sh\necho "$@" >> "$GH_LOG"\nprintf \'{"headRefOid":"%s"}\\n\' "$PR_HEAD"\n')
        gh.chmod(0o755)
        env = dict(self.env, PATH=str(self.bin) + os.pathsep + '/bin', GH_LOG=str(self.tmp / 'gh.log'), PR_HEAD=head)
        self.commit_statement(self.statement, extra={'source.txt': 'later\n'})
        result = self.verify('https://github.com/owner/repo/pull/7', env=env)
        self.assertEqual(result.returncode, 3, result.stdout)
        self.assertIn('pr view https://github.com/owner/repo/pull/7 --json headRefOid', (self.tmp / 'gh.log').read_text())
        self.assertEqual(self.verify('7', env=env).returncode, 3)

    def test_launcher_runs_in_the_callers_checkout(self):
        # AC-22 / AR-005: `uncle verify` from another directory reads that
        # directory's attestation and HEAD, not the install checkout's.
        self.commit_statement(self.statement)
        env = dict(self.env, PATH=str(self.bin) + os.pathsep + os.environ['PATH'])
        result = subprocess.run(['bash', str(ROOT / 'uncle'), 'verify'], cwd=self.repo, env=env, text=True,
                                stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        self.assertEqual(result.returncode, 3, result.stdout)
        self.assertIn('✓ head tree matches release artifact', result.stdout)
        elsewhere = self.tmp / 'elsewhere'
        fixture_repo.init_repo(elsewhere, env=self.env)
        fixture_repo.commit(elsewhere, 'empty', env=self.env)
        result = subprocess.run(['bash', str(ROOT / 'uncle'), 'verify'], cwd=elsewhere, env=env, text=True,
                                stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertIn('no attestation at .uncle/attestation.json', result.stdout)

    def test_stdlib_only_and_exclusion_list_identical(self):
        text = VERIFY.read_text()
        modules = set()
        for match in re.finditer(r'(?m)^(?:import (\w+)|from (\w+) import)', text):
            modules.add(match.group(1) or match.group(2))
        self.assertTrue(modules <= set(sys.stdlib_module_names), modules - set(sys.stdlib_module_names))
        self.assertNotIn('scripts/lib', text.replace('scripts/lib/envelope.py', ''))
        block = lambda path: re.search(r'ARTIFACT_EXCLUDES = \((.*?)^\)', path.read_text(), re.S | re.M).group(1)
        self.assertEqual(block(VERIFY), block(ROOT / 'scripts/lib/envelope.py'))
        ns = {}
        exec(compile('ARTIFACT_EXCLUDES = (' + block(VERIFY) + ')', '<v>', 'exec'), ns)
        self.assertEqual(ns['ARTIFACT_EXCLUDES'], envelope.ARTIFACT_EXCLUDES)


if __name__ == '__main__':
    unittest.main(verbosity=0)
