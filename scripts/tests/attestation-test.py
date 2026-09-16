#!/usr/bin/env python3
"""T-1..T-7: the sealed PR attestation (scripts/lib/attestation.py + engine wiring)."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts/lib'))
import attestation  # noqa: E402

ENGINE = (ROOT / 'scripts/lib/change-pr.sh').read_text().split("<<'PY'", 1)[1] \
    .split('\n', 1)[1].split('\nPY\n', 1)[0]
ENGINE = ENGINE[:ENGINE.rindex('\ntry:\n    main()')]

TREE = 'a' * 40
HEAD = 'b' * 40
AUDIT = 'c' * 64


def journal(**extra):
    j = dict(version=1, owner='0' * 32, origin='owner/repo\t38\tgh', original_head='d' * 40,
             original_branch='main', reviewed_tree=TREE, intended_head=HEAD, commit_tree=TREE,
             audit_hash=AUDIT, verdict_run='run-1', base_repo='owner/repo', head_repo='owner/repo',
             base_branch='main', head_branch='uncle/change-1', phase='bound', url='', number=None)
    j.update(extra)
    return j


class Fixture(unittest.TestCase):
    """A workflow state directory built only from driver-written files."""

    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.root = Path(self.dir.name)
        self.addCleanup(self.dir.cleanup)
        self.state = self.root / '.uncle/workflow'
        (self.state / 'approvals').mkdir(parents=True)
        (self.state / 'pr').mkdir()
        self.artifact('CHANGE_SPEC', 'spec body\n')
        self.artifact('CHANGE_PLAN', 'plan body\n')
        (self.state / 'approvals/CHANGE_PLAN.approved-by').write_text('Brian\n')
        self.write('audit-verdict', 'run-1\tREADY\t' + AUDIT + '\n')
        self.write('green-check.tsv', 'PASS\tcmd1\nFIXED\tcmd2\nPREEXISTING\tcmd3\nREGRESSION\tcmd4\n')
        self.totals([dict(kind='agent', stage='implementation', runner='/libexec/scripts/agent-claude.sh',
                          model='claude-opus-5', speculative=False, process_exit=0,
                          reported_error=False, ended_at=100),
                     dict(kind='reviewer', stage='final-audit', runner='reviewer-codex.sh',
                          model='gpt-5-codex', speculative=False, process_exit=0,
                          reported_error=False, ended_at=200)])

    def write(self, name, text):
        (self.state / name).write_text(text)

    def artifact(self, name, text):
        import hashlib
        (self.root / (name + '.md')).write_text(text)
        (self.state / 'approvals' / (name + '.sha256')).write_text(
            hashlib.sha256(text.encode()).hexdigest() + '\n')

    def totals(self, records):
        (self.state / 'session-totals.json').write_text(json.dumps(dict(records=records)))

    def seal(self, **extra):
        return attestation.seal(journal(**extra), self.state, root=self.root,
                                version='0.1.0', lib=str(ROOT / 'scripts/lib'))

    def body(self, **extra):
        return attestation.render(self.seal(**extra))

    def rows(self, body=None, **extra):
        """Rendered rows as label -> value; column padding is not the assertion."""
        body = self.body(**extra) if body is None else body
        out = {}
        for line in body.splitlines()[6:]:
            if line.startswith('```') or '  ' not in line:
                continue
            label, value = line.split('  ', 1)
            out[label.strip()] = value.strip()
        return out


class T1FullSeal(Fixture):
    def test_every_field_sealed_and_rendered(self):
        sealed = self.seal()
        sealed['gate_publication'] = 'APPROVED (human)'
        body = attestation.render(sealed)
        self.assertIn('UNCLE CHANGE ATTESTATION', body)
        self.assertEqual(self.rows(body), {
            'Issue': '#38',
            'Specification (SHA-256)': sealed['specification'],
            'Implementation agent': 'claude (claude-opus-5)',   # AC-4
            'Review agent': 'codex (gpt-5-codex)',              # AC-5
            'Review result': 'READY',
            'Verification': '4 commands: 2 pass, 1 pre-existing, 1 regressed',  # FIXED counts as pass
            'Audited tree': TREE[:12],
            'Published commit': HEAD[:12],
            'Gate: plan approval': 'APPROVED (human)',
            'Gate: publication': 'APPROVED (human)',
            'Uncle version': '0.1.0',
        })

    def test_version_falls_back_to_version_file(self):
        sealed = attestation.seal(journal(), self.state, root=self.root, version='',
                                 lib=str(ROOT / 'scripts/lib'))
        self.assertEqual(sealed['version'], (ROOT / 'VERSION').read_text().strip())

    def test_unattended_plan_gate_is_labelled(self):
        # D-8: the delegation lives in `.delegated-by`; `.approved-by` is empty.
        (self.state / 'approvals/CHANGE_PLAN.approved-by').write_text('\n')
        (self.state / 'approvals/CHANGE_PLAN.delegated-by').write_text('unattended\n')
        self.assertEqual(self.rows()['Gate: plan approval'], 'APPROVED (unattended)')
        (self.state / 'approvals/CHANGE_PLAN.delegated-by').write_text('supervisor:standing:Brian\n')
        self.assertEqual(self.rows()['Gate: plan approval'], 'APPROVED (supervisor:standing:Brian)')
        # Legacy files kept the value in `.approved-by` itself.
        (self.state / 'approvals/CHANGE_PLAN.delegated-by').unlink()
        (self.state / 'approvals/CHANGE_PLAN.approved-by').write_text('unattended\n')
        self.assertEqual(self.rows()['Gate: plan approval'], 'APPROVED (unattended)')

    def test_render_from_statement_predicate(self):
        # AC-12 / D-11: the block is rendered from the Statement, with the
        # same labels; nothing outside the whitelist appears.
        envelopes = {
            'implementation': {'producer': {'runner': 'agent-claude.sh', 'model': 'claude-opus-5'}},
            'audit': {'producer': {'runner': 'codex', 'model': 'gpt-5-codex'}, 'result': 'pass', 'reason': 'READY_WITH_NON_BLOCKING_ISSUES'},
            'verification': {'result': 'pass', 'reason': '4 commands: 2 pass, 1 pre-existing, 1 regressed'},
            'release': {'result': 'pass'},
        }
        statement = {'_type': 'https://in-toto.io/Statement/v1', 'predicateType': 'https://uncle.dev/attestation/v1',
                     'subject': [{'name': 'owner/repo@uncle/x', 'digest': {'gitTree': TREE}}],
                     'predicate': {'schema_version': '1', 'uncle_version': '0.1.0', 'run_id': 'run-1',
                                   'source': {'repository': 'owner/repo', 'issue': '38'}, 'envelopes': envelopes,
                                   'approvals': [{'gate': 'CHANGE_SPEC', 'digest': 'f' * 64, 'approved_by': 'Brian', 'delegated_by': '', 'required': True},
                                                 {'gate': 'CHANGE_PLAN', 'digest': 'e' * 64, 'approved_by': '', 'delegated_by': 'supervisor:explicit:Brian', 'required': True},
                                                 {'gate': 'publication', 'digest': TREE, 'approved_by': 'Brian', 'delegated_by': '', 'required': True}],
                                   'release': {'artifact': {'digest': {'gitTree': TREE}}}, 'authentication': 'none'}}
        sealed = attestation.from_statement(statement)
        body = attestation.render(sealed)
        self.assertEqual(self.rows(body), {
            'Issue': '#38',
            'Specification (SHA-256)': 'f' * 64,
            'Implementation agent': 'claude (claude-opus-5)',
            'Review agent': 'codex (gpt-5-codex)',
            'Review result': 'READY_WITH_NON_BLOCKING_ISSUES',
            'Verification': '4 commands: 2 pass, 1 pre-existing, 1 regressed',
            'Audited tree': TREE[:12],
            'Gate: plan approval': 'APPROVED (supervisor:explicit:Brian)',
            'Gate: publication': 'APPROVED (human)',
            'Uncle version': '0.1.0',
        })
        self.assertTrue(set(self.rows(body)) <= {label for _, label in attestation.FIELDS})
        # The engine's sealed_attestation() takes this path when a Statement exists.
        ns = dict(__name__='engine')
        os.environ['UNCLE_LIB_DIR'] = str(ROOT / 'scripts/lib')
        exec(compile(ENGINE, '<engine>', 'exec'), ns)
        ns['STATE'] = self.state
        merged = ns['sealed_attestation'](journal(statement=statement, intended_head=HEAD))
        self.assertEqual(merged['published_commit'], HEAD[:12])
        self.assertEqual(merged['gate_publication'], 'APPROVED (human)')
        # An empty predicate renders every row as unavailable, never as a crash.
        self.assertEqual(set(self.rows(attestation.render(attestation.from_statement({'predicate': {}}))).values()), {'unavailable'})

    def test_override_row_appears_only_with_a_bound_override(self):
        self.write('pr/verdict-override', '\t'.join(['run-1', 'NOT_READY', AUDIT, 'now']) + '\n')
        self.assertEqual(self.rows()['Audit override'], 'operator override over NOT_READY')


class T2MissingEvidence(Fixture):
    """AC-13/I-7: removing a source makes exactly that field unavailable."""

    def unavailable(self, label):
        # Exactly this field degrades; the publication gate is stamped at
        # consent, so it is the one other row still unavailable at seal.
        rows = self.rows()
        self.assertEqual(rows[label], 'unavailable', rows)
        degraded = {k for k, v in rows.items() if v == 'unavailable'}
        self.assertEqual(degraded, {label, 'Gate: publication'} - {None}, rows)

    def test_missing_origin(self):
        self.assertEqual(self.rows(origin='')['Issue'], 'unavailable')

    def test_non_gh_origin(self):
        self.assertEqual(self.rows(origin='owner/repo\t38\tmanual')['Issue'], 'unavailable')

    def test_missing_spec_approval(self):
        (self.state / 'approvals/CHANGE_SPEC.sha256').unlink()
        self.unavailable('Specification (SHA-256)')

    def test_spec_edited_after_approval(self):
        (self.root / 'CHANGE_SPEC.md').write_text('edited after approval\n')
        self.unavailable('Specification (SHA-256)')

    def test_missing_session_totals(self):
        (self.state / 'session-totals.json').unlink()
        rows = self.rows()
        self.assertEqual(rows['Implementation agent'], 'unavailable')
        self.assertEqual(rows['Review agent'], 'unavailable')

    def test_speculative_or_failed_agent_run_is_not_identity(self):
        self.totals([dict(kind='agent', stage='implementation', runner='claude', model='m',
                          speculative=True, process_exit=0, reported_error=False, ended_at=100),
                     dict(kind='agent', stage='implementation', runner='claude', model='m',
                          speculative=False, process_exit=1, reported_error=False, ended_at=150),
                     dict(kind='agent', stage='implementation', runner='claude', model='m',
                          speculative=False, process_exit=0, reported_error=True, ended_at=160),
                     dict(kind='reviewer', stage='final-audit', runner='codex', model='m',
                          speculative=False, process_exit=0, reported_error=False, ended_at=200)])
        self.unavailable('Implementation agent')

    def test_wrong_stage_is_not_identity(self):
        self.totals([dict(kind='reviewer', stage='manual-checklist', runner='cline', model='m',
                          speculative=False, process_exit=0, reported_error=False, ended_at=200),
                     dict(kind='agent', stage='implementation-step-2', runner='claude', model='m',
                          speculative=False, process_exit=0, reported_error=False, ended_at=100)])
        self.unavailable('Review agent')

    def test_missing_verdict(self):
        (self.state / 'audit-verdict').unlink()
        self.unavailable('Review result')

    def test_verdict_bound_to_another_audit(self):
        self.write('audit-verdict', 'run-1\tREADY\t' + 'e' * 64 + '\n')
        self.unavailable('Review result')

    def test_missing_green_check(self):
        (self.state / 'green-check.tsv').unlink()
        self.unavailable('Verification')

    def test_missing_plan_approval_evidence(self):
        (self.state / 'approvals/CHANGE_PLAN.approved-by').unlink()
        self.unavailable('Gate: plan approval')

    def test_publication_gate_unavailable_until_consent(self):
        self.unavailable('Gate: publication')

    def test_missing_audited_tree_fails_closed(self):
        with self.assertRaises(attestation.AttestationError):
            self.seal(commit_tree='')


class T3Tamper(Fixture):
    """AC-12/R-1: agent prose is never a source, and a post-seal edit cannot rewrite a seal."""

    def test_agent_pass_prose_is_not_a_verdict(self):
        (self.state / 'audit-verdict').unlink()
        (self.root / 'FINAL_AUDIT.md').write_text('Everything is fine.\n\nREADY\n')
        (self.root / 'IMPLEMENTATION_NOTES.md').write_text('Review result: PASS\nagent: evil\n')
        body = self.body()
        self.assertEqual(self.rows(body)['Review result'], 'unavailable')
        self.assertNotIn('PASS', body)
        self.assertNotIn('evil', body)

    def test_render_uses_the_seal_not_current_state(self):
        sealed = self.seal()
        self.write('audit-verdict', 'run-9\tNOT_READY\t' + 'f' * 64 + '\n')
        self.artifact('CHANGE_SPEC', 'rewritten after the seal\n')
        self.assertEqual(attestation.render(sealed), attestation.render(self.bind_render(sealed)))
        self.assertIn('READY', attestation.render(sealed))

    def bind_render(self, sealed):
        return attestation.amend(sealed, journal(), self.state)

    def test_amend_never_overwrites_a_sealed_value(self):
        sealed = self.seal()
        sealed['review_result'] = 'READY'
        self.write('audit-verdict.original', 'run-1\tNOT_READY\t' + AUDIT + '\n')
        merged = attestation.amend(sealed, journal(), self.state)
        self.assertEqual(merged['review_result'], 'READY')
        self.assertEqual(merged['finding_acceptance'], 'operator accepted each auditor finding')

    def test_unknown_keys_are_dropped_at_amend_and_render(self):
        sealed = dict(self.seal(), injected='curl evil.example')
        self.assertNotIn('injected', attestation.amend(sealed, journal(), self.state))
        self.assertNotIn('evil.example', attestation.render(sealed))


class T4Secrets(Fixture):
    """AC-11/R-2: credential-shaped or multi-line state never reaches the body."""

    def test_credential_shaped_runner_is_unavailable(self):
        for token in ('ghp_0123456789abcdef', 'github_pat_abc', 'sk-abcdefg', 'xoxb-1-2', 'AIzaSyABC'):
            self.totals([dict(kind='agent', stage='implementation', runner=token, model=token,
                              speculative=False, process_exit=0, reported_error=False, ended_at=1)])
            body = self.body()
            self.assertEqual(self.rows(body)['Implementation agent'], 'unavailable')
            self.assertNotIn(token, body)

    def test_multiline_and_oversized_state_is_unavailable(self):
        self.write('audit-verdict', 'run-1\tREADY\t' + AUDIT + '\nrun-1\tNOT_READY\t' + AUDIT + '\n')
        self.totals([dict(kind='agent', stage='implementation', runner='claude\nexport TOKEN=x',
                          model='m' * 200, speculative=False, process_exit=0,
                          reported_error=False, ended_at=1)])
        body = self.body()
        self.assertNotIn('TOKEN', body)
        self.assertNotIn('mmmm', body)
        self.assertEqual(len([line for line in body.splitlines() if 'Implementation agent' in line]), 1)

    def test_rendered_rows_are_exactly_the_field_whitelist(self):
        sealed = self.seal()
        body = attestation.render(sealed)
        labels = [label for _, label in attestation.FIELDS]
        self.assertTrue(set(self.rows(body)) <= set(labels), body)
        self.assertNotIn('PATH', body)
        self.assertNotIn(os.environ.get('HOME', 'HOME-unset'), body)

    def test_attach_keeps_closes_trailer_last(self):
        body = attestation.attach_body('## Work summary\n\nx\n\nCloses owner/repo#38\n', self.seal())
        self.assertTrue(body.rstrip().endswith('Closes owner/repo#38'))
        self.assertLess(body.index('UNCLE CHANGE ATTESTATION'), body.index('Closes'))

    def test_attach_is_idempotent(self):
        once = attestation.attach_body('## Work summary\n\nx\n', self.seal())
        self.assertEqual(once, attestation.attach_body(once, self.seal()))


class T5Engine(Fixture):
    """AC-8/AC-14/B-9: empty intended_head seals; missing tree and corrupt journal create no PR."""

    def test_bound_journal_without_intended_head_seals_the_tree(self):
        sealed = self.seal(intended_head='')
        self.assertEqual(sealed['tree'], TREE[:12])
        self.assertNotIn('published_commit', sealed)
        self.assertNotIn('Published commit', attestation.render(sealed))

    def test_engine_reports_attestation_block_recoverably(self):
        ns = dict(__name__='engine')
        os.environ['UNCLE_LIB_DIR'] = str(ROOT / 'scripts/lib')
        exec(compile(ENGINE, '<engine>', 'exec'), ns)
        with self.assertRaises(attestation.AttestationError):
            ns['seal_attestation'](journal(commit_tree=''))

    def test_corrupt_journal_creates_no_pr(self):
        repo = self.root / 'repo'
        (repo / '.uncle/workflow/pr').mkdir(parents=True)
        (repo / '.uncle/workflow/pr/journal.json').write_text('{not json')
        subprocess.run(['git', 'init', '-q', str(repo)], check=True)
        bin_dir = self.root / 'bin'
        bin_dir.mkdir()
        calls = self.root / 'gh-calls'
        (bin_dir / 'gh').write_text('#!/bin/sh\necho "$@" >> ' + str(calls) + '\nexit 0\n')
        (bin_dir / 'gh').chmod(0o755)
        script = ('. "' + str(ROOT / 'scripts/lib/change-pr.sh') + '"\n'
                  'change_pr_engine handoff\n')
        result = subprocess.run(['bash', '-c', script], cwd=repo, text=True,
                                stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                env=dict(os.environ, PATH=str(bin_dir) + ':' + os.environ['PATH'],
                                         UNCLE_LIB_DIR=str(ROOT / 'scripts/lib')))
        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertIn('Missing/corrupt PR binding', result.stdout)
        self.assertFalse(calls.exists(), result.stdout)


class T6Acceptance(Fixture):
    """AC-6/R-9: operator acceptance of findings is not the auditor's verdict."""

    def test_auditor_not_ready_survives_the_rewrite(self):
        self.write('audit-verdict.original', 'run-1\tNOT_READY\t' + AUDIT + '\n')
        self.write('audit-verdict', 'run-1\tREADY\t' + AUDIT + '\n')
        rows = self.rows()
        self.assertEqual(rows['Review result'], 'NOT_READY')
        self.assertEqual(rows['Finding acceptance'], 'operator accepted each auditor finding')

    def test_stale_original_from_another_audit_is_ignored(self):
        self.write('audit-verdict.original', 'run-0\tNOT_READY\t' + 'e' * 64 + '\n')
        rows = self.rows()
        self.assertEqual(rows['Review result'], 'READY')
        self.assertNotIn('Finding acceptance', rows)

    def test_ready_audit_records_no_acceptance_row(self):
        self.write('audit-verdict.original', 'run-1\tREADY\t' + AUDIT + '\n')
        self.assertNotIn('Finding acceptance', self.rows())


class T7LegacyJournal(Fixture):
    """AR-006/D-14: a journal prepared before attestation gains the block once, with no second PR."""

    def engine(self, j, gh_log):
        ns = dict(__name__='engine')
        os.environ['UNCLE_LIB_DIR'] = str(ROOT / 'scripts/lib')
        exec(compile(ENGINE, '<engine>', 'exec'), ns)
        written = {}

        def gh(*args):
            gh_log.append(args)
            if args[:2] == ('repo', 'view'):
                return json.dumps({'nameWithOwner': 'owner/repo',
                                   'defaultBranchRef': {'name': 'main'}})
            if args[:2] == ('pr', 'create'):
                written['body'] = Path(args[args.index('--body-file') + 1]).read_text()
                return 'https://github.com/owner/repo/pull/7'
            if args[:2] == ('pr', 'view'):
                return json.dumps({'number': 7, 'headRefOid': HEAD})
            if args[:2] == ('auth', 'status'):
                return ''
            raise AssertionError('unexpected gh call: ' + repr(args))

        # No PR exists until create returns one; then lookup must find it.
        def lookup(journal_arg):
            return {'number': 7, 'url': 'https://github.com/owner/repo/pull/7'} if written else None

        ns.update(STATE=self.state, gh=gh, git=lambda *a, **k: '', validate=lambda *a, **k: None,
                  remote_sha=lambda j: HEAD, branch=lambda: j['head_branch'], head=lambda: HEAD,
                  save=lambda j: None, lookup=lookup,
                  ask=lambda *a, **k: (_ for _ in ()).throw(AssertionError('no prompt at resume')))
        return ns, written

    def test_prepared_body_gains_the_block_before_create(self):
        calls = []
        j = journal(phase='prepared', title='t',
                    body='## Work summary\n\nx\n\nCloses owner/repo#38\n')
        ns, written = self.engine(j, calls)
        ns['handoff'](j)
        self.assertEqual(j['phase'], 'created')
        self.assertIn('UNCLE CHANGE ATTESTATION', written['body'])
        self.assertIn(TREE[:12], written['body'])
        self.assertTrue(written['body'].rstrip().endswith('Closes owner/repo#38'))
        self.assertEqual(len([c for c in calls if c[:2] == ('pr', 'create')]), 1)
        self.assertEqual(j['attestation']['tree'], TREE[:12])

    def test_already_attested_body_is_not_attached_twice(self):
        calls = []
        body = attestation.attach_body('## Work summary\n\nx\n', self.seal())
        j = journal(phase='prepared', title='t', body=body, attestation=self.seal())
        ns, written = self.engine(j, calls)
        ns['handoff'](j)
        self.assertEqual(written['body'].count('UNCLE CHANGE ATTESTATION'), 1)
        self.assertEqual(len([c for c in calls if c[:2] == ('pr', 'create')]), 1)


if __name__ == '__main__':
    unittest.main(verbosity=0)
