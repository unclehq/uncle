#!/usr/bin/env python3
"""A finished new-application build is attested, and `uncle verify` with no
argument verifies the attestation on the main branch, not the checkout."""
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
LIB = ROOT / 'scripts/lib'
VERIFY = ROOT / 'scripts/uncle-verify.py'


def run(*cmd, cwd, env=None):
    return subprocess.run(cmd, cwd=cwd, env=env, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)


class BuildAttestationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.repo = Path(self.tmp.name)
        (self.repo / '.empty-gitconfig').write_text('')
        (self.repo / '.home').mkdir()
        empty = str(self.repo / '.empty-gitconfig')
        self.env = dict(os.environ, STATE_DIR='.uncle/workflow', UNCLE_LIB_DIR=str(LIB),
                        GIT_CONFIG_GLOBAL=empty, GIT_CONFIG_SYSTEM=empty, HOME=str(self.repo / '.home'),
                        GIT_AUTHOR_NAME='t', GIT_AUTHOR_EMAIL='t@t',
                        GIT_COMMITTER_NAME='t', GIT_COMMITTER_EMAIL='t@t')
        self.env.pop('GPG_AGENT_INFO', None)
        self.env.pop('GNUPGHOME', None)
        self.git('init', '-q', '-b', 'main')
        self.git('config', 'commit.gpgsign', 'false')
        self.git('config', 'tag.gpgsign', 'false')
        (self.repo / '.gitignore').write_text('.uncle/*\n!.uncle/docs/\n!.uncle/attestation.json\n'
                                              '!.uncle/attestation.sig\n!.uncle/allowed_signers\n')
        (self.repo / 'app.txt').write_text('hi\n')
        (self.repo / '.uncle/docs').mkdir(parents=True)
        (self.repo / '.uncle/workflow/approvals').mkdir(parents=True)
        self.git('add', '-A')
        self.git('-c', 'commit.gpgsign=false', '-c', 'tag.gpgsign=false', 'commit', '--no-gpg-sign', '-qm', 'init')

    def tearDown(self):
        self.tmp.cleanup()

    def git(self, *args):
        result = run('git', *args, cwd=self.repo, env=self.env)
        self.assertEqual(result.returncode, 0, result.stdout)
        return result.stdout.strip()

    def finish(self, green='PASS\tcmd\n', verdict='READY', extra=(), drop=()):
        docs = self.repo / '.uncle/docs'
        for name in ('REQUIREMENTS_INTERPRETATION', 'ADVERSARIAL_REVIEW', 'UPDATED_PROJECT_PLAN',
                     'IMPLEMENTATION_NOTES', 'FINAL_AUDIT'):
            if name not in drop:
                (docs / (name + '.md')).write_text('# ' + name + '\n')
        (self.repo / '.uncle/workflow/green-check.tsv').write_text(green)
        approvals = self.repo / '.uncle/workflow/approvals'
        (approvals / 'UPDATED_PROJECT_PLAN.sha256').write_text('abc\n')
        (approvals / 'UPDATED_PROJECT_PLAN.gate-action').write_text('APPROVE\n')
        artifact = run('bash', '-c', '. "%s/change-pr.sh"; change_pr_engine artifact' % LIB,
                       cwd=self.repo, env=self.env).stdout.strip()
        return run(sys.executable, str(LIB / 'build_attestation.py'), '--state', '.uncle/workflow',
                   '--artifact', artifact, '--verdict', verdict, *extra, cwd=self.repo, env=self.env)

    def test_verify_reads_main_even_when_another_branch_is_checked_out(self):
        self.assertEqual(self.finish().returncode, 0)
        self.assertTrue((self.repo / '.uncle/attestation.json').exists())
        self.git('add', '-A')
        self.git('-c', 'commit.gpgsign=false', '-c', 'tag.gpgsign=false', 'commit', '--no-gpg-sign', '-qm', 'build')
        self.git('checkout', '-q', '-b', 'feature')
        (self.repo / '.uncle/attestation.json').unlink()
        verify = run(sys.executable, str(VERIFY), cwd=self.repo, env=self.env)
        self.assertIn('verifying the attestation on refs/heads/main', verify.stdout)
        self.assertIn('head tree matches release artifact', verify.stdout)
        self.assertIn(verify.returncode, (0, 3), verify.stdout)

    def predicate(self):
        import json
        return json.loads((self.repo / '.uncle/attestation.json').read_text())['predicate']

    def test_a_not_ready_build_is_attested_as_procedure_followed_with_the_verdict_recorded(self):
        result = self.finish(verdict='NOT_READY')
        self.assertEqual(result.returncode, 0, result.stdout)
        predicate = self.predicate()
        self.assertEqual(predicate['procedure']['result'], 'pass')
        self.assertEqual(predicate['outcomes']['verdict'], 'NOT_READY')
        self.assertEqual(predicate['outcomes']['audit'], 'fail')
        self.assertEqual(predicate['envelopes']['release']['result'], 'pass')

    def test_a_regressed_green_check_is_a_recorded_outcome_not_a_procedure_failure(self):
        result = self.finish(green='REGRESSION\tcmd\n')
        self.assertEqual(result.returncode, 0, result.stdout)
        predicate = self.predicate()
        self.assertEqual(predicate['procedure']['result'], 'pass')
        self.assertEqual(predicate['outcomes']['verification'], 'fail')

    def test_a_stage_that_did_not_run_breaks_the_procedure_and_is_recorded_as_such(self):
        result = self.finish(drop=('FINAL_AUDIT',))
        self.assertEqual(result.returncode, 0, result.stdout)
        predicate = self.predicate()
        self.assertEqual(predicate['procedure']['result'], 'fail')
        self.assertIn('audit did not run', predicate['procedure']['reason'])
        self.assertEqual(predicate['envelopes']['release']['result'], 'fail')

    def test_a_verifier_prints_the_verdict_and_exits_zero_for_a_not_ready_build_that_followed_procedure(self):
        self.assertEqual(self.finish(verdict='NOT_READY').returncode, 0)
        verify = run(sys.executable, str(VERIFY), cwd=self.repo, env=self.env)
        self.assertIn('build verdict recorded: NOT_READY', verify.stdout)
        self.assertIn('procedure followed', verify.stdout)
        self.assertNotIn('✗', verify.stdout.replace('✗ no required human gate', '').replace('✗ required gate', ''), verify.stdout)

    def test_a_verifier_refuses_a_build_whose_procedure_was_not_followed(self):
        self.assertEqual(self.finish(drop=('FINAL_AUDIT',)).returncode, 0)
        verify = run(sys.executable, str(VERIFY), cwd=self.repo, env=self.env)
        self.assertIn('✗ audit did not run', verify.stdout)
        self.assertNotEqual(verify.returncode, 0)

    def test_a_gate_with_a_recorded_delegation_counts_but_one_with_nothing_recorded_does_not(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location('envelope', LIB / 'envelope.py')
        mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
        ran = {s: {'result': 'pass', 'artifact': {'digest': {'gitTree': 'T'}}, 'inputs': {'artifact': {'digest': {'gitTree': 'T'}}}}
               for s in mod.PROCEDURE_STAGES}
        delegated = [{'gate': 'PROJECT_PLAN', 'required': True, 'approved_by': '', 'delegated_by': 'unattended'}]
        nothing = [{'gate': 'PROJECT_PLAN', 'required': True, 'approved_by': '', 'delegated_by': ''}]
        self.assertEqual(mod.procedure_reason(ran, delegated, 'T'), '')
        self.assertIn('no recorded approval or delegation', mod.procedure_reason(ran, nothing, 'T'))

    def test_every_build_refreshes_the_attestation(self):
        self.assertEqual(self.finish().returncode, 0)
        first = (self.repo / '.uncle/attestation.json').read_text()
        self.assertEqual(self.finish(verdict='NOT_READY').returncode, 0)
        self.assertNotEqual(first, (self.repo / '.uncle/attestation.json').read_text())
        self.assertEqual(self.predicate()['outcomes']['verdict'], 'NOT_READY')

    def test_an_overridden_build_discloses_the_override_as_an_outcome(self):
        result = self.finish(green='REGRESSION\tcmd\n', verdict='NOT_READY', extra=('--overridden', '1'))
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertTrue(self.predicate()['outcomes']['override'])
        self.assertEqual(self.predicate()['outcomes']['verdict'], 'NOT_READY')

if __name__ == '__main__':
    unittest.main()
