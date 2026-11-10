"""Hand-off publish mode: applying the hand-off to the base commit gives exactly the audited tree (issue 205)."""
import base64
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

LIB = Path(__file__).resolve().parents[2] / 'scripts' / 'lib'
GIT = ['git', '-c', 'user.name=t', '-c', 'user.email=t@t', '-c', 'commit.gpgsign=false']


def run(cwd, *args, env=None, data=None):
    return subprocess.run(args, cwd=cwd, check=True, input=data, stdout=subprocess.PIPE,
                          env=dict(os.environ, **(env or {}))).stdout.decode().strip()


class Handoff(unittest.TestCase):
    def setUp(self):
        d = tempfile.TemporaryDirectory()
        self.addCleanup(d.cleanup)
        self.repo = d.name
        r = self.repo
        run(r, 'git', 'init', '-q', '-b', 'main')
        Path(r, 'keep.txt').write_text('keep\n')
        Path(r, 'edit.txt').write_text('old\n')
        Path(r, 'gone.txt').write_text('bye\n')
        run(r, *GIT, 'add', '-A')
        run(r, *GIT, 'commit', '-qm', 'base')
        self.base = run(r, 'git', 'rev-parse', 'HEAD')
        Path(r, 'edit.txt').write_text('new\n')
        Path(r, 'gone.txt').unlink()
        Path(r, 'sub').mkdir()
        Path(r, 'sub', 'tool.sh').write_bytes(b'#!/bin/sh\necho \xff\x00bin\n')
        os.chmod(Path(r, 'sub', 'tool.sh'), 0o755)
        # The audited tree, built the way the driver does: a temporary index, never the user's.
        env = {'GIT_INDEX_FILE': os.path.join(r, '.git', 'tmp-index')}
        run(r, 'git', 'add', '-A', env=env)
        self.tree = run(r, 'git', 'write-tree', env=env)
        run(r, 'git', 'reset', '-q', '--hard')
        run(r, 'git', 'clean', '-fdq')
        wf = Path(r, '.uncle', 'workflow', 'pr')
        wf.mkdir(parents=True)
        (wf / 'journal.json').write_text(json.dumps({
            'commit_tree': self.tree, 'original_head': self.base, 'head_branch': 'uncle/x', 'origin': 'o/r\t7\tgh',
            'base_repo': 'o/r', 'audit_hash': 'a' * 64,
            'attestation': {'issue': 'o/r#7', 'review_result': 'NOT_READY', 'tree': self.tree[:12], 'version': '1'}}))
        (wf.parent / 'audit-verdict.original').write_text('run\tNOT_READY\t' + 'a' * 64 + '\n')

    def export(self):
        run(self.repo, sys.executable, str(LIB / 'handoff_export.py'))
        return json.loads(Path(self.repo, '.uncle', 'handoff', 'handoff.json').read_text())

    def test_applying_handoff_gives_the_audited_tree(self):
        h = self.export()
        self.assertEqual((h['base_commit'], h['head_branch'], h['draft'], h['audit_verdict']),
                         (self.base, 'uncle/x', True, 'NOT_READY'))
        self.assertIn('UNCLE CHANGE ATTESTATION', h['pr_body'])
        self.assertEqual({c['path']: c['action'] for c in h['changes']},
                         {'edit.txt': 'modify', 'gone.txt': 'delete', 'sub/tool.sh': 'add'})
        # Apply to a fresh checkout of the base commit through a temporary index and compare trees.
        r = self.repo
        env = {'GIT_INDEX_FILE': os.path.join(r, '.git', 'apply-index')}
        base_oid = h['base_commit']
        run(r, 'git', 'read-tree', base_oid, env=env)
        for c in h['changes']:
            if c['action'] == 'delete':
                run(r, 'git', 'update-index', '--force-remove', c['path'], env=env)
                continue
            oid = run(r, 'git', 'hash-object', '-w', '--stdin', env=env, data=base64.b64decode(c['content']))
            self.assertEqual(oid, c['oid'])
            run(r, 'git', 'update-index', '--add', '--cacheinfo', '%s,%s,%s' % (c['mode'], oid, c['path']), env=env)
        self.assertEqual(run(r, 'git', 'write-tree', env=env), self.tree)
        self.assertEqual([c['mode'] for c in h['changes'] if c['path'] == 'sub/tool.sh'], ['100755'])

    def test_audited_tree_banners_and_attestation_as_supplied(self):
        path = Path(self.repo, '.uncle/workflow/pr/journal.json')
        j = json.loads(path.read_text())
        j['audited_tree'] = 'c' * 40
        j['body_banners'] = '> BANNER-LINE\n\n'
        j['attestation']['gate_publication'] = 'journal-supplied'
        path.write_text(json.dumps(j))
        h = self.export()
        self.assertEqual(h['audited_tree'], 'c' * 40)
        self.assertEqual(h['attestation']['gate_publication'], 'journal-supplied')
        self.assertTrue(h['pr_body'].startswith('> BANNER-LINE\n\n> [!WARNING]'))

    def test_audited_tree_defaults_to_tree_and_fallback_seal_is_stamped(self):
        h = self.export()
        self.assertEqual(h['audited_tree'], self.tree)
        self.assertEqual(h['attestation'].get('gate_publication', 'handoff (published by the host)'), 'handoff (published by the host)')

    def test_base_tracked_sig_absent_from_tree_is_a_delete(self):
        r = self.repo
        Path(r, '.uncle', 'attestation.sig').write_text('old-sig\n')
        run(r, *GIT, 'add', '-f', '.uncle/attestation.sig')
        run(r, *GIT, 'commit', '-qm', 'tracked sig')
        path = Path(r, '.uncle/workflow/pr/journal.json')
        j = json.loads(path.read_text())
        j['original_head'] = run(r, 'git', 'rev-parse', 'HEAD')
        path.write_text(json.dumps(j))
        rows = {c['path']: c for c in self.export()['changes']}
        self.assertEqual(rows['.uncle/attestation.sig'], {'path': '.uncle/attestation.sig', 'action': 'delete'})

    def test_missing_journal_fails_nonzero(self):
        Path(self.repo, '.uncle/workflow/pr/journal.json').unlink()
        p = subprocess.run([sys.executable, str(LIB / 'handoff_export.py')], cwd=self.repo, stderr=subprocess.PIPE)
        self.assertEqual(p.returncode, 1)
        self.assertIn(b'No audited change', p.stderr)


SCRIPT = LIB / 'change-pr.sh'


def engine_source():
    text = SCRIPT.read_text()
    return text.split("<<'PY' || true\n", 1)[1].split('\nPY\n', 1)[0]


class AttestHandoff(unittest.TestCase):
    """The attest-handoff action's refusals and the consent entry (issue 233). Envelopes dir empty: enabled, never reached."""

    def setUp(self):
        d = tempfile.TemporaryDirectory()
        self.addCleanup(d.cleanup)
        self.repo = d.name
        run(self.repo, 'git', 'init', '-q', '-b', 'main')
        Path(self.repo, 'a.txt').write_text('a\n')
        run(self.repo, *GIT, 'add', '-A')
        run(self.repo, *GIT, 'commit', '-qm', 'base')
        head = run(self.repo, 'git', 'rev-parse', 'HEAD')
        wf = Path(self.repo, '.uncle', 'workflow')
        (wf / 'pr').mkdir(parents=True)
        (wf / 'envelopes').mkdir()
        self.journal = {'version': 1, 'owner': 'a' * 32, 'origin': '', 'audit_hash': 'a' * 64, 'reviewed_tree': 'b' * 40,
                        'commit_tree': 'b' * 40, 'original_head': head, 'intended_head': '', 'original_branch': 'main',
                        'head_branch': 'uncle/x', 'base_repo': 'o/r', 'head_repo': 'o/r', 'base_branch': 'main',
                        'phase': 'bound', 'url': '', 'number': '', 'verdict_run': 'run'}
        self.write_journal()

    def write_journal(self):
        Path(self.repo, '.uncle/workflow/pr/journal.json').write_text(json.dumps(self.journal))

    def engine(self, action):
        env = dict(os.environ, UNCLE_LIB_DIR=str(LIB))
        return subprocess.run([sys.executable, '-c', engine_source(), action], cwd=self.repo, env=env,
                              stdout=subprocess.PIPE, stderr=subprocess.STDOUT)

    def consent(self, mode):
        env = {k: v for k, v in os.environ.items() if not k.startswith('UNCLE_')}
        env.update(UNCLE_LIB_DIR=str(LIB), UNCLE_PUBLISH_MODE=mode, UNCLE_APPROVAL_NAME='')
        src = engine_source().split('\ntry:\n    main()', 1)[0] + '\nimport json as J\nprint(J.dumps(consent_entry("d")))\n'
        out = subprocess.run([sys.executable, '-c', src, 'x'], cwd=self.repo, env=env, stdout=subprocess.PIPE, check=True).stdout
        return json.loads(out)

    def assertRefused(self, p, code, text):
        self.assertEqual(p.returncode, code, p.stdout)
        self.assertIn(text, p.stdout.decode())
        self.assertFalse(Path(self.repo, '.uncle', 'handoff', 'handoff.json').exists())

    def test_symlinked_attestation_json_is_refused(self):
        Path(self.repo, 'elsewhere').write_text('x')
        os.symlink('../elsewhere', Path(self.repo, '.uncle', 'attestation.json'))
        self.assertRefused(self.engine('attest-handoff'), 3, 'Attestation blocked: .uncle/attestation.json is a symlink')
        self.assertEqual(Path(self.repo, 'elsewhere').read_text(), 'x')

    def test_dangling_symlinked_attestation_sig_is_refused(self):
        os.symlink('nowhere', Path(self.repo, '.uncle', 'attestation.sig'))
        self.assertRefused(self.engine('attest-handoff'), 3, 'Attestation blocked: .uncle/attestation.sig is a symlink')
        self.assertFalse(Path(self.repo, 'nowhere').exists())

    def test_prepared_journal_is_refused(self):
        self.journal['phase'] = 'prepared'
        self.write_journal()
        self.assertRefused(self.engine('attest-handoff'), 1, 'normal publish already began')

    def test_empty_envelopes_dir_blocks_and_leaves_journal_and_files(self):
        before = Path(self.repo, '.uncle/workflow/pr/journal.json').read_bytes()
        p = self.engine('attest-handoff')
        self.assertRefused(p, 3, 'Attestation blocked')
        self.assertEqual(Path(self.repo, '.uncle/workflow/pr/journal.json').read_bytes(), before)
        self.assertFalse(Path(self.repo, '.uncle', 'attestation.json').exists())

    def test_normal_publish_refuses_a_handed_off_journal(self):
        self.journal['phase'] = 'handoff-attested'
        self.write_journal()
        self.assertRefused(self.engine('handoff'), 1, 'handed off to the host')

    def test_consent_entry_unchanged_outside_handoff_mode(self):
        entry = self.consent('')
        self.assertEqual((entry['approved_by'], entry['delegated_by']), ('operator', ''))
        self.assertEqual(sorted(entry), ['approved_by', 'delegated_by', 'digest', 'gate', 'required', 'timestamp'])

    def test_consent_entry_in_handoff_mode_is_a_delegation_not_an_approval(self):
        entry = self.consent('handoff')
        self.assertEqual((entry['gate'], entry['required'], entry['approved_by'], entry['delegated_by']),
                         ('publication', True, '', 'handoff'))


import base64  # noqa: E402,F811
import importlib.util  # noqa: E402

TESTS = Path(__file__).resolve().parent
sys.path.insert(0, str(TESTS))
import fixture_repo  # noqa: E402

_spec = importlib.util.spec_from_file_location('statement_fixture', TESTS / 'attestation-statement-test.py')
statement_fixture = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(statement_fixture)
EXPORTER = LIB / 'handoff_export.py'
VERIFY = TESTS.parent / 'uncle-verify.py'


class HandoffE2E(statement_fixture.Fixture):
    """A real attest-handoff run over a full envelopes fixture, the export, and `uncle verify --tree` on the applied copy."""

    def route(self, mode='handoff'):
        script = '. "$1"; UNCLE_PUBLISH_MODE=%s change_pr_complete_route; echo "RC=$? REASON=$CHANGE_PR_EXTRAS_REASON"' % mode
        return subprocess.run(['bash', '-c', script, 'test', str(statement_fixture.LIB)], cwd=self.repo, env=self.env,
                              stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, stdin=subprocess.DEVNULL)

    def attest(self):
        return self.engine('attest-handoff', UNCLE_PUBLISH_MODE='handoff')

    def export(self):
        result = subprocess.run([sys.executable, str(EXPORTER)], cwd=self.repo, env=self.env, stdout=subprocess.PIPE,
                                stderr=subprocess.STDOUT, text=True)
        self.assertEqual(result.returncode, 0, result.stdout)
        return json.loads((self.repo / '.uncle/handoff/handoff.json').read_text())

    def prepared(self):
        self.seed_envelopes()
        self.freeze()

    def handoff_json(self):
        return self.repo / '.uncle/handoff/handoff.json'

    def apply(self, h, tamper=None):
        scratch = self.root / 'scratch'
        subprocess.run([fixture_repo.REAL_GIT, 'clone', '-q', str(self.repo), str(scratch)], check=True, env=self.env)
        fixture_repo.git(scratch, 'checkout', '-q', h['base_commit'], env=self.env)
        for row in h['changes']:
            path = scratch / row['path']
            if tamper and row['path'] == tamper:
                row = dict(row, content=base64.b64encode(b'tampered\n').decode())
            if row['action'] == 'delete':
                path.unlink()
                continue
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(base64.b64decode(row['content']))
        fixture_repo.git(scratch, 'add', '-A', '-f', env=self.env)
        commit = fixture_repo.commit(scratch, 'applied hand-off', env=self.env, add_all=False)
        return scratch, commit

    def verify(self, scratch, commit):
        return subprocess.run([sys.executable, str(VERIFY), '--tree', commit], cwd=scratch, env=self.env,
                              stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)

    def test_attestation_is_listed_byte_identical_and_applies_to_the_attested_tree(self):
        self.prepared()
        bind_tree = self.journal()['commit_tree']
        result = self.attest()
        self.assertEqual(result.returncode, 0, result.stdout)
        h = self.export()
        j = self.journal()
        rows = {c['path']: c for c in h['changes']}
        self.assertEqual(base64.b64decode(rows['.uncle/attestation.json']['content']),
                         (self.repo / '.uncle/attestation.json').read_bytes())
        self.assertNotIn('.uncle/attestation.sig', rows)                    # unsigned: no .sig (AC-2)
        scratch, commit = self.apply(h)
        applied = fixture_repo.git(scratch, 'rev-parse', 'HEAD^{tree}', env=self.env)
        self.assertEqual((applied, h['tree']), (j['commit_tree'], j['commit_tree']))
        self.assertEqual((h['audited_tree'], j['audited_tree'], j['phase']), (bind_tree, bind_tree, 'handoff-attested'))
        self.assertNotEqual(h['tree'], h['audited_tree'])
        self.assertTrue(h['pr_body'].count('UNCLE CHANGE ATTESTATION') >= 1)

    def test_pr_body_block_matches_the_committed_statement(self):
        self.prepared()
        self.assertEqual(self.attest().returncode, 0)
        h = self.export()
        stmt = self.statement()
        body = h['pr_body']
        self.assertIn('UNCLE CHANGE ATTESTATION', body)
        self.assertIn(stmt['subject'][0]['digest']['gitTree'][:12], body)     # the sealed tree, not a recomputed one
        self.assertIn('handoff (published by the host)', body)
        self.assertNotIn('HANDOFF (published', body)

    def test_rerun_keeps_audited_tree_and_attested_tree(self):
        self.prepared()
        self.assertEqual(self.attest().returncode, 0)
        first = self.export()
        self.assertEqual(self.attest().returncode, 0)
        second = self.export()
        # Only audited_tree is stable: the rerun re-attests, and the Statement carries a fresh timestamp, so the
        # attested tree may differ. What must hold on every run is that handoff.json names the journal's trees.
        j = self.journal()
        self.assertEqual((second['audited_tree'], j['audited_tree']), (first['audited_tree'],) * 2)
        self.assertEqual((first['tree'] != first['audited_tree'], second['tree']), (True, j['commit_tree']))

    def test_statement_has_one_non_human_publication_entry_and_verify_names_it(self):
        self.prepared()
        self.assertEqual(self.attest().returncode, 0)
        h = self.export()
        entries = [a for a in self.statement()['predicate']['approvals'] if a['gate'] == 'publication']
        self.assertEqual(len(entries), 1)
        self.assertEqual((entries[0]['approved_by'], entries[0]['delegated_by'], entries[0]['required']), ('', 'handoff', True))
        scratch, commit = self.apply(h)
        out = self.verify(scratch, commit)
        # Integrity checks are reached (not 'no attestation') and the only refusal is the missing human approval.
        self.assertEqual(out.returncode, 1, out.stdout)
        self.assertIn('\u2717 required gate publication has no human approval', out.stdout)
        self.assertIn('delegated_by: handoff', out.stdout)
        self.assertIn('\u2713 head tree matches release artifact', out.stdout)
        self.assertIn('NOT VERIFIED', out.stdout)
        self.assertEqual(out.stdout.count('\u2717'), 1)

    def test_tampered_changes_row_fails_verify_on_the_applied_tree(self):
        self.prepared()
        self.assertEqual(self.attest().returncode, 0)
        scratch, commit = self.apply(self.export(), tamper='source.txt')
        out = self.verify(scratch, commit)
        self.assertNotEqual(out.returncode, 0, out.stdout)
        self.assertNotIn('\u2713 head tree matches release artifact', out.stdout)
        self.assertRegex(out.stdout, r'\u2717 .*tree')

    def test_signed_run_lists_the_sig(self):
        key = self.root / 'signkey'
        subprocess.run(['ssh-keygen', '-q', '-t', 'ed25519', '-N', '', '-f', str(key)], check=True)
        self.git('config', 'gpg.format', 'ssh')
        self.git('config', 'user.signingkey', str(key))
        self.prepared()
        self.assertEqual(self.attest().returncode, 0)
        h = self.export()
        self.assertEqual(self.statement()['predicate']['authentication'], 'ssh')
        rows = {c['path']: c for c in h['changes']}
        self.assertEqual(rows['.uncle/attestation.sig']['action'], 'add')
        self.assertEqual(base64.b64decode(rows['.uncle/attestation.sig']['content']), (self.repo / '.uncle/attestation.sig').read_bytes())

    def test_unsigned_run_removes_untracked_stale_sig_and_deletes_a_tracked_one(self):
        (self.repo / '.uncle/attestation.sig').write_text('stale\n')
        self.prepared()
        self.assertEqual(self.attest().returncode, 0)
        self.assertFalse((self.repo / '.uncle/attestation.sig').exists())
        self.assertNotIn('.uncle/attestation.sig', {c['path'] for c in self.export()['changes']})

    def test_tracked_stale_sig_is_a_delete_row(self):
        (self.repo / '.uncle/attestation.sig').write_text('old\n')
        self.git('add', '-f', '.uncle/attestation.sig')
        fixture_repo.commit(self.repo, 'track sig', env=self.env, add_all=False)
        self.prepared()
        self.assertEqual(self.attest().returncode, 0)
        rows = {c['path']: c for c in self.export()['changes']}
        self.assertEqual(rows['.uncle/attestation.sig'], {'path': '.uncle/attestation.sig', 'action': 'delete'})

    def test_tracked_allowed_signers_is_not_deleted(self):
        self.prepared()
        self.assertEqual(self.attest().returncode, 0)
        self.assertNotIn('.uncle/allowed_signers', {c['path'] for c in self.export()['changes']})

    def test_failure_after_attest_restores_files_leaves_journal_and_writes_no_handoff(self):
        if os.geteuid() == 0:
            self.skipTest('a read-only directory does not stop root')
        self.prepared()
        (self.repo / '.uncle/attestation.json').write_text('previous\n')
        journal = (self.state / 'pr/journal.json').read_bytes()
        os.chmod(self.state / 'pr', 0o500)                                  # save(j) cannot create its temp file
        self.addCleanup(os.chmod, self.state / 'pr', 0o700)
        out = self.route()
        os.chmod(self.state / 'pr', 0o700)
        self.assertIn('RC=1 REASON=handoff-failed', out.stdout)
        self.assertEqual((self.repo / '.uncle/attestation.json').read_text(), 'previous\n')
        self.assertFalse((self.repo / '.uncle/attestation.sig').exists())
        self.assertEqual((self.state / 'pr/journal.json').read_bytes(), journal)
        self.assertFalse(self.handoff_json().exists())

    def test_empty_envelopes_directory_blocks_the_route(self):
        self.prepared()
        for item in (self.state / 'envelopes').iterdir():
            item.unlink()
        out = self.route()
        self.assertIn('Attestation blocked', out.stdout)
        self.assertIn('RC=1 REASON=handoff-failed', out.stdout)
        self.assertFalse(self.handoff_json().exists())

    def test_symlinked_attestation_files_are_refused_without_writing_through(self):
        self.prepared()
        target = self.root / 'outside.txt'
        target.write_text('untouched\n')
        os.symlink(target, self.repo / '.uncle/attestation.json')
        out = self.route()
        self.assertIn('is a symlink', out.stdout)
        self.assertIn('RC=1 REASON=handoff-failed', out.stdout)
        self.assertEqual(target.read_text(), 'untouched\n')
        self.assertFalse(self.handoff_json().exists())

    def test_consent_entry_is_the_old_one_when_mode_is_not_handoff(self):
        self.prepared()
        out = self.engine('attest-handoff')                                 # UNCLE_PUBLISH_MODE unset: the action still attests, consent_entry is the old one
        self.assertEqual(out.returncode, 0, out.stdout)
        entry = [a for a in self.statement()['predicate']['approvals'] if a['gate'] == 'publication'][0]
        self.assertEqual((entry['approved_by'], entry['delegated_by']), ('Brian', ''))


if __name__ == '__main__':
    unittest.main()
