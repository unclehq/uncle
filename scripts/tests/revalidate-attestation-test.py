"""Revalidating from the attestation, and re-issuing it when only documentation changed.

The fixture is a git project with a hand-made attestation whose trees and document digests are real, so every case compares the
recorded baseline with a real change, and the re-issued attestation is checked by the real verifier."""
import hashlib
import importlib.util
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

os.environ['UNCLE_REVALIDATE_SUPERVISOR'] = '0'     # a test never spends a model call

LIB = Path(__file__).resolve().parents[1] / 'lib'
ROOT = LIB.parents[1]
sys.path.insert(0, str(LIB))
import envelope as env  # noqa: E402
import revalidate_attestation as ra  # noqa: E402

spec = importlib.util.spec_from_file_location('revalidate', LIB / 'revalidate.py')
rv = importlib.util.module_from_spec(spec)
spec.loader.exec_module(rv)

DOCS = {'BASELINE_REPORT.md': 'baseline\n', 'PROJECT_PLAN.md': 'plan\n', 'ADVERSARIAL_REVIEW.md': 'review\n'}
STAGE_DOC = {'requirements': 'BASELINE_REPORT.md', 'plan': 'PROJECT_PLAN.md', 'review': 'ADVERSARIAL_REVIEW.md'}


def sha(text):
    return hashlib.sha256(text.encode()).hexdigest()


class Fixture(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.repo = Path(self.tmp.name)
        self.cwd = os.getcwd()
        self.addCleanup(os.chdir, self.cwd)
        self.git('init', '-q', '-b', 'main', '.')
        self.git('config', 'user.email', 'a@b.test')
        self.git('config', 'user.name', 'fixture')
        self.git('config', 'commit.gpgsign', 'false')
        for rel, text in {'README.md': 'hello\n', 'src/app.js': 'export const x = 1;\n', 'tests/app.test.js': 'test\n',
                          'package.json': '{}\n'}.items():
            self.write(rel, text)
        for name, text in DOCS.items():
            self.write('.uncle/docs/' + name, text)
        self.git('add', '-A')
        self.git('commit', '-q', '-m', 'built')
        os.chdir(self.repo)
        self.v = ra.verifier()
        self.attest()

    def git(self, *args):
        return subprocess.run(['git', *args], cwd=self.repo, check=True, stdout=subprocess.PIPE,
                              stderr=subprocess.PIPE).stdout.decode().strip()

    def write(self, rel, text):
        path = self.repo / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)

    def attest(self, results=None, tree=None):
        tree = tree or self.v.artifact_of(self.git('rev-parse', 'HEAD^{tree}'))
        results = results or {}
        art = {'digest': {'gitTree': tree}}
        envelopes = {}
        for stage in ra.STAGES:
            evidence = []
            if stage in STAGE_DOC:
                evidence = [{'path': '.uncle/docs/' + STAGE_DOC[stage], 'digest': {'sha256': sha(DOCS[STAGE_DOC[stage]])}}]
            item = {'result': results.get(stage, 'pass'), 'evidence': evidence, 'stage': stage}
            if results.get(stage) == 'fail':
                item['reason'] = 'NOT_READY' if stage == 'audit' else '1 command regressed'
            if stage == 'implementation':
                item['artifact'] = art
            if stage in ('verification', 'audit'):
                item['inputs'] = {'artifact': art}
            envelopes[stage] = item
        predicate = {'schema_version': '1', 'uncle_version': 'x', 'run_id': 'fixture', 'source': {'repository': '', 'issue': ''},
                     'approvals': [], 'envelopes': envelopes, 'release': {'artifact': art}, 'authentication': 'none',
                     'procedure': {'result': 'pass'}}
        body = {'_type': self.v.STATEMENT_TYPE, 'subject': [{'name': 'fixture', 'digest': {'gitTree': tree}}],
                'predicateType': self.v.PREDICATE_TYPE, 'predicate': predicate}
        (self.repo / '.uncle').mkdir(exist_ok=True)
        (self.repo / '.uncle' / 'attestation.json').write_bytes(env.canonical(body))

    def current(self):
        raw, statement = ra.load(self.repo)
        return raw, statement, ra.plan(self.repo, statement)

    def verify(self):
        done = subprocess.run([sys.executable, str(ROOT / 'scripts' / 'uncle-verify.py')], cwd=self.repo,
                              capture_output=True, text=True, timeout=120)
        return done.stdout


class Plan(Fixture):
    def test_a_readme_change_invalidates_no_stage_and_is_eligible(self):
        self.write('README.md', 'hello, edited\n')
        _, _, info = self.current()
        self.assertEqual(info['changed'], ['README.md'])
        self.assertEqual({r['action'] for r in info['rows']}, {'reuse'})
        self.assertTrue(ra.eligible(info))

    def test_a_new_file_under_docs_is_documentation(self):
        self.write('docs/guide.md', 'a new doc\n')
        _, _, info = self.current()
        self.assertEqual(info['changed'], ['docs/guide.md'])
        self.assertTrue(ra.eligible(info))

    def test_a_new_root_level_markdown_file_is_documentation(self):
        self.write('NOTES.md', 'notes\n')
        self.assertTrue(ra.eligible(self.current()[2]))

    def test_nothing_changed_is_not_stale(self):
        info = self.current()[2]
        self.assertFalse(info['stale'])
        self.assertFalse(ra.eligible(info))

    def test_a_source_change_invalidates_implementation_verification_and_audit(self):
        self.write('src/app.js', 'export const x = 2;\n')
        info = self.current()[2]
        actions = {r['stage']: r['action'] for r in info['rows']}
        self.assertEqual([actions[s] for s in ('requirements', 'plan', 'review')], ['reuse'] * 3)
        self.assertEqual([actions[s] for s in ('implementation', 'verification', 'audit')], ['run'] * 3)
        self.assertFalse(ra.eligible(info))

    def test_a_test_change_is_flagged_for_review_and_not_eligible(self):
        self.write('tests/app.test.js', 'a weaker test\n')
        info = self.current()[2]
        self.assertIn('protected verification file changed', {r['stage']: r['reason'] for r in info['rows']}['verification'])
        self.assertFalse(ra.eligible(info))

    def test_an_unknown_file_is_source_so_the_stages_rerun(self):
        self.write('data.json', '{"a": 1}\n')
        self.assertFalse(ra.eligible(self.current()[2]))

    def test_a_changed_approved_document_invalidates_the_stage_that_wrote_it(self):
        self.write('.uncle/docs/PROJECT_PLAN.md', 'plan, edited\n')
        info = self.current()[2]
        rows = {r['stage']: r for r in info['rows']}
        self.assertEqual(rows['requirements']['action'], 'reuse')
        for stage in ('plan', 'review', 'implementation', 'verification', 'audit'):
            self.assertEqual(rows[stage]['action'], 'run', stage)
            self.assertEqual(rows[stage]['cause'], 'change', stage)
        self.assertFalse(ra.eligible(info))

    def test_a_stage_that_failed_before_reruns_but_does_not_block_re_issuing(self):
        self.attest(results={'verification': 'fail', 'audit': 'fail'})
        self.write('README.md', 'edited\n')
        info = self.current()[2]
        rows = {r['stage']: r for r in info['rows']}
        self.assertEqual((rows['verification']['action'], rows['verification']['cause']), ('run', 'failed'))
        self.assertEqual((rows['audit']['action'], rows['audit']['cause']), ('run', 'failed'))
        self.assertTrue(ra.eligible(info))

    def test_a_supervisor_added_stage_blocks_re_issuing(self):
        self.write('README.md', 'edited\n')
        info = self.current()[2]
        info['rows'][1] = dict(info['rows'][1], action='run', cause='supervisor', reason='supervisor: the plan is stale')
        self.assertFalse(ra.eligible(info))

    def test_an_attested_tree_that_is_not_in_the_repository_cannot_be_compared(self):
        self.attest(tree='0123456789abcdef0123456789abcdef01234567')
        self.write('README.md', 'edited\n')
        info = self.current()[2]
        self.assertIsNone(info['changed'])
        self.assertFalse(ra.eligible(info))
        self.assertIn('nothing can be compared', {r['stage']: r['reason'] for r in info['rows']}['verification'])

    def test_no_attestation_is_refused(self):
        (self.repo / '.uncle' / 'attestation.json').unlink()
        with self.assertRaises(ValueError):
            ra.load(self.repo)


class Reissue(Fixture):
    def reissue(self, dry_run=False):
        raw, statement, info = self.current()
        return ra.reissue(self.repo, info, statement, dry_run=dry_run), raw

    def new_statement(self):
        return json.loads((self.repo / '.uncle' / 'attestation.json').read_text())

    def test_the_attestation_is_re_issued_for_the_new_tree_with_the_claim_recorded(self):
        old = self.current()[1]['predicate']['release']['artifact']['digest']['gitTree']
        self.write('README.md', 'hello, edited\n')
        (ok, message), _ = self.reissue()
        self.assertTrue(ok, message)
        statement = self.new_statement()
        predicate = statement['predicate']
        new = predicate['release']['artifact']['digest']['gitTree']
        self.assertNotEqual(new, old)
        # every tree the old attestation named now names the new one: subject, release and each stage's artifact
        self.assertEqual(statement['subject'][0]['digest']['gitTree'], new)
        self.assertEqual(predicate['envelopes']['implementation']['artifact']['digest']['gitTree'], new)
        self.assertEqual(predicate['envelopes']['verification']['inputs']['artifact']['digest']['gitTree'], new)
        self.assertEqual(predicate['envelopes']['audit']['inputs']['artifact']['digest']['gitTree'], new)
        claim = predicate['revalidation']
        self.assertEqual(claim['method'], 'documentation-only')
        self.assertEqual(claim['changed_files'], ['README.md'])
        self.assertEqual(claim['carried_forward_from']['digest']['gitTree'], old)

    def test_recorded_results_are_carried_forward_unchanged_a_failure_stays_a_failure(self):
        self.attest(results={'audit': 'fail'})
        self.write('README.md', 'edited\n')
        (ok, _), _ = self.reissue()
        self.assertTrue(ok)
        envelopes = self.new_statement()['predicate']['envelopes']
        self.assertEqual(envelopes['audit']['result'], 'fail')
        self.assertEqual(envelopes['audit']['reason'], 'NOT_READY')
        self.assertEqual(envelopes['plan']['result'], 'pass')

    def test_the_written_attestation_is_canonical_and_the_verifier_accepts_the_claim(self):
        self.write('docs/guide.md', 'a new doc\n')
        (ok, _), _ = self.reissue()
        self.assertTrue(ok)
        raw = (self.repo / '.uncle' / 'attestation.json').read_bytes()
        self.assertEqual(env.canonical(json.loads(raw)), raw)
        self.git('add', '-A')
        self.git('commit', '-q', '-m', 'doc')
        out = self.verify()
        self.assertIn('head tree matches release artifact', out)
        self.assertRegex(out, r'✓ revalidated: carried forward from .* across documentation only \(docs/guide.md\)')
        self.assertNotIn('✗ revalidation', out)

    def test_before_the_edit_is_committed_with_it_the_verifier_still_refuses_the_tree(self):
        self.write('README.md', 'edited, not committed\n')
        (ok, _), _ = self.reissue()
        self.assertTrue(ok)
        self.assertIn('head tree does not match the release artifact', self.verify())

    def test_dry_run_writes_nothing(self):
        self.write('README.md', 'edited\n')
        (ok, message), raw = self.reissue(dry_run=True)
        self.assertTrue(ok)
        self.assertIn('would re-issue', message)
        self.assertEqual((self.repo / '.uncle' / 'attestation.json').read_bytes(), raw)

    def test_a_source_change_is_never_carried_forward_and_writes_nothing(self):
        self.write('src/app.js', 'export const x = 2;\n')
        (ok, message), raw = self.reissue()
        self.assertFalse(ok)
        self.assertIn('not eligible', message)
        self.assertEqual((self.repo / '.uncle' / 'attestation.json').read_bytes(), raw)

    def test_a_signed_attestation_is_never_downgraded_to_unsigned(self):
        (self.repo / '.uncle' / 'attestation.sig').write_text('{}')
        self.write('README.md', 'edited\n')
        raw = (self.repo / '.uncle' / 'attestation.json').read_bytes()
        with mock.patch.object(env, 'select_signer', return_value=('none', '')):
            ok, message = ra.reissue(self.repo, self.current()[2], self.current()[1])
        self.assertFalse(ok)
        self.assertIn('downgraded', message)
        self.assertEqual((self.repo / '.uncle' / 'attestation.json').read_bytes(), raw)
        self.assertTrue((self.repo / '.uncle' / 'attestation.sig').exists())

    def test_a_signing_failure_on_a_signed_attestation_writes_nothing(self):
        (self.repo / '.uncle' / 'attestation.sig').write_text('{}')
        self.write('README.md', 'edited\n')
        raw = (self.repo / '.uncle' / 'attestation.json').read_bytes()
        with mock.patch.object(env, 'select_signer', return_value=('ssh', '/nonexistent')), \
                mock.patch.object(env, 'sign', return_value=(None, 'ssh-keygen failed')):
            ok, message = ra.reissue(self.repo, self.current()[2], self.current()[1])
        self.assertFalse(ok)
        self.assertIn('signing failed', message)
        self.assertEqual((self.repo / '.uncle' / 'attestation.json').read_bytes(), raw)

    def test_a_signature_is_written_when_a_signer_is_configured(self):
        self.write('README.md', 'edited\n')
        fake = {'payloadType': 'x', 'payload': 'e30=', 'signatures': [{'keyid': 'k', 'sig': 'c2ln', 'signer': 'ssh'}]}
        with mock.patch.object(env, 'select_signer', return_value=('ssh', '/key')), mock.patch.object(env, 'sign', return_value=(fake, '')):
            ok, message = ra.reissue(self.repo, self.current()[2], self.current()[1])
        self.assertTrue(ok, message)
        self.assertTrue((self.repo / '.uncle' / 'attestation.sig').is_file())
        self.assertEqual(self.new_statement()['predicate']['authentication'], 'ssh')
        self.assertIn('signed: ssh', message)


class EachLayerHoldsOnItsOwn(Fixture):
    """A source change is stopped in three places (the stage causes, eligible(), and a second check inside reissue()). Each is
    tested alone so that weakening any one of them fails a test, not just the last one standing."""

    def test_eligible_refuses_a_source_change_even_when_every_row_says_reuse(self):
        self.write('src/app.js', 'export const x = 2;\n')
        info = self.current_info()
        info['rows'] = [dict(r, action='reuse', cause='') for r in info['rows']]
        self.assertFalse(ra.eligible(info))

    def test_eligible_refuses_a_test_change_even_when_every_row_says_reuse(self):
        self.write('tests/app.test.js', 'weaker\n')
        info = self.current_info()
        info['rows'] = [dict(r, action='reuse', cause='') for r in info['rows']]
        self.assertFalse(ra.eligible(info))

    def test_reissue_refuses_on_its_own_when_the_project_outside_documentation_differs(self):
        self.write('src/app.js', 'export const x = 2;\n')
        raw, statement = ra.load(self.repo)
        info = self.current_info()
        with mock.patch.object(ra, 'eligible', return_value=True):
            ok, message = ra.reissue(self.repo, info, statement)
        self.assertFalse(ok)
        self.assertIn('outside its documentation differs', message)
        self.assertEqual((self.repo / '.uncle' / 'attestation.json').read_bytes(), raw)

    def current_info(self):
        return ra.plan(self.repo, ra.load(self.repo)[1])


class VerifierChecksTheClaim(Fixture):
    """The claim is verified from the project, not trusted: it cannot be used to carry a source change across."""

    def claim_for(self, files, rest=None):
        rest = rest or self.v.rest_of(self.v.artifact_of(self.git('rev-parse', 'HEAD^{tree}')))
        return {'predicate': {'revalidation': {'method': 'documentation-only',
                                               'carried_forward_from': {'digest': {'gitTree': 'a' * 40}},
                                               'rest': {'digest': {'gitTree': rest}}, 'changed_files': files}}}

    def tree(self):
        return self.git('rev-parse', 'HEAD^{tree}')

    def test_no_claim_means_nothing_to_check(self):
        self.assertEqual(self.v.check_9({'predicate': {}}, self.tree()), '')

    def test_a_true_claim_passes(self):
        line = self.v.check_9(self.claim_for(['README.md']), self.tree())
        self.assertIn('revalidated: carried forward', line)

    def test_a_claim_naming_a_source_file_is_refused(self):
        with self.assertRaises(self.v.Refused) as caught:
            self.v.check_9(self.claim_for(['src/app.js']), self.tree())
        self.assertIn('not documentation', caught.exception.args[0][0])

    def test_a_claim_whose_recorded_rest_no_longer_matches_is_refused(self):
        claim = self.claim_for(['README.md'])
        self.write('src/app.js', 'export const x = 999;\n')      # source edited after the claim was made
        self.git('add', '-A')
        self.git('commit', '-q', '-m', 'tamper')
        with self.assertRaises(self.v.Refused) as caught:
            self.v.check_9(claim, self.tree())
        self.assertIn('does not hold', caught.exception.args[0][0])

    def test_a_malformed_claim_is_refused(self):
        for bad in ({'method': 'documentation-only'}, {'method': 'anything', 'changed_files': ['README.md']},
                    {'method': 'documentation-only', 'changed_files': [], 'carried_forward_from': {}, 'rest': {}}):
            with self.assertRaises(self.v.Refused, msg=str(bad)):
                self.v.check_9({'predicate': {'revalidation': bad}}, self.tree())

    def test_documentation_is_decided_the_same_way_everywhere(self):
        yes = ['README.md', 'LICENSE', 'CHANGELOG', 'NOTES.md', 'docs/guide.md', 'docs/img/a.png', 'CONTRIBUTING.rst']
        no = ['src/notes.md', 'package.json', 'src/app.js', 'tests/a.test.js', 'docs/script.js', 'index.html', 'a/b/README.md']
        for path in yes:
            self.assertTrue(self.v.is_documentation(path), path)
        for path in no:
            self.assertFalse(self.v.is_documentation(path), path)


class RunFromTheAttestation(Fixture):
    """Through revalidate.run(): a project with no stage fingerprints is compared with its attestation, not refused."""

    def run_cli(self, dry_run=False):
        out = io.StringIO()
        code = rv.run(self.repo, dry_run=dry_run, out=out, supervisor=False)
        return code, out.getvalue()

    def test_a_readme_change_revalidates_and_re_issues_the_attestation(self):
        self.write('README.md', 'edited\n')
        code, out = self.run_cli()
        self.assertEqual(code, 0, out)
        self.assertIn('baseline: the attestation', out)
        self.assertIn('changed since the attestation: README.md', out)
        self.assertIn('attestation: re-issued for', out)
        self.assertIn('revalidation', (self.repo / '.uncle' / 'attestation.json').read_text())

    def test_dry_run_says_what_it_would_do_and_changes_nothing(self):
        self.write('README.md', 'edited\n')
        before = (self.repo / '.uncle' / 'attestation.json').read_bytes()
        code, out = self.run_cli(dry_run=True)
        self.assertEqual(code, 0, out)
        self.assertIn('attestation: would re-issue for', out)
        self.assertEqual((self.repo / '.uncle' / 'attestation.json').read_bytes(), before)

    def test_a_source_change_reports_the_stages_to_run_and_does_not_re_issue(self):
        self.write('src/app.js', 'export const x = 2;\n')
        before = (self.repo / '.uncle' / 'attestation.json').read_bytes()
        code, out = self.run_cli()
        self.assertEqual(code, 1, out)
        self.assertRegex(out, r'verification\s+run\s+source changed')
        self.assertIn('stage(s) must run again', out)
        self.assertEqual((self.repo / '.uncle' / 'attestation.json').read_bytes(), before)

    def test_a_project_that_failed_before_is_re_issued_but_still_exits_nonzero(self):
        self.attest(results={'audit': 'fail'})
        self.write('README.md', 'edited\n')
        code, out = self.run_cli()
        self.assertEqual(code, 1, out)
        self.assertIn('attestation: re-issued for', out)
        self.assertIn('audit', out.split('must run again:')[1])

    def test_nothing_changed_exits_zero_and_writes_nothing(self):
        before = (self.repo / '.uncle' / 'attestation.json').read_bytes()
        code, out = self.run_cli()
        self.assertEqual(code, 0, out)
        self.assertIn('no project file changed since the attestation', out)
        self.assertEqual((self.repo / '.uncle' / 'attestation.json').read_bytes(), before)

    def test_without_an_attestation_the_refusal_says_why(self):
        (self.repo / '.uncle' / 'attestation.json').unlink()
        code, out = self.run_cli()
        self.assertEqual(code, 2, out)
        self.assertIn('no attestation to compare with', out)


if __name__ == '__main__':
    unittest.main()
