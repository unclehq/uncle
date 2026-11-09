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
        self.env = dict(os.environ, STATE_DIR='.uncle/workflow', UNCLE_LIB_DIR=str(LIB),
                        GIT_CONFIG_GLOBAL='/dev/null', GIT_AUTHOR_NAME='t', GIT_AUTHOR_EMAIL='t@t',
                        GIT_COMMITTER_NAME='t', GIT_COMMITTER_EMAIL='t@t')
        self.git('init', '-q', '-b', 'main')
        (self.repo / '.gitignore').write_text('.uncle/*\n!.uncle/docs/\n!.uncle/attestation.json\n'
                                              '!.uncle/attestation.sig\n!.uncle/allowed_signers\n')
        (self.repo / 'app.txt').write_text('hi\n')
        (self.repo / '.uncle/docs').mkdir(parents=True)
        (self.repo / '.uncle/workflow/approvals').mkdir(parents=True)
        self.git('add', '-A')
        self.git('commit', '-qm', 'init')

    def tearDown(self):
        self.tmp.cleanup()

    def git(self, *args):
        result = run('git', *args, cwd=self.repo, env=self.env)
        self.assertEqual(result.returncode, 0, result.stdout)
        return result.stdout.strip()

    def finish(self, green='PASS\tcmd\n', verdict='READY'):
        docs = self.repo / '.uncle/docs'
        for name in ('REQUIREMENTS_INTERPRETATION', 'ADVERSARIAL_REVIEW', 'UPDATED_PROJECT_PLAN',
                     'IMPLEMENTATION_NOTES', 'FINAL_AUDIT'):
            (docs / (name + '.md')).write_text('# ' + name + '\n')
        (self.repo / '.uncle/workflow/green-check.tsv').write_text(green)
        approvals = self.repo / '.uncle/workflow/approvals'
        (approvals / 'UPDATED_PROJECT_PLAN.sha256').write_text('abc\n')
        (approvals / 'UPDATED_PROJECT_PLAN.gate-action').write_text('APPROVE\n')
        artifact = run('bash', '-c', '. "%s/change-pr.sh"; change_pr_engine artifact' % LIB,
                       cwd=self.repo, env=self.env).stdout.strip()
        return run(sys.executable, str(LIB / 'build_attestation.py'), '--state', '.uncle/workflow',
                   '--artifact', artifact, '--verdict', verdict, cwd=self.repo, env=self.env)

    def test_verify_reads_main_even_when_another_branch_is_checked_out(self):
        self.assertEqual(self.finish().returncode, 0)
        self.assertTrue((self.repo / '.uncle/attestation.json').exists())
        self.git('add', '-A')
        self.git('commit', '-qm', 'build')
        self.git('checkout', '-q', '-b', 'feature')
        (self.repo / '.uncle/attestation.json').unlink()
        verify = run(sys.executable, str(VERIFY), cwd=self.repo, env=self.env)
        self.assertIn('verifying the attestation on refs/heads/main', verify.stdout)
        self.assertIn('head tree matches release artifact', verify.stdout)
        self.assertIn(verify.returncode, (0, 3), verify.stdout)

    def test_regressed_verification_writes_no_attestation(self):
        result = self.finish(green='REGRESSION\tcmd\n')
        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertIn('verification result fail', result.stdout)
        self.assertFalse((self.repo / '.uncle/attestation.json').exists())

    def test_not_ready_audit_writes_no_attestation(self):
        result = self.finish(verdict='NOT_READY')
        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertFalse((self.repo / '.uncle/attestation.json').exists())


if __name__ == '__main__':
    unittest.main()
