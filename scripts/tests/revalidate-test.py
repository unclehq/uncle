"""`uncle revalidate` (issue #243): which stages of a finished build still hold, from its attestation.

The fixture is a small git project with a hand-made attestation whose tree and document digests are real, so every case
compares the recorded baseline with a real change. The README case is the acceptance test: a documentation edit must not
re-run any stage."""
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
REVALIDATE = ROOT / 'scripts' / 'lib' / 'revalidate.py'
sys.path.insert(0, str(ROOT / 'scripts' / 'lib'))
import revalidate

DOCS = {
    'BASELINE_REPORT.md': 'baseline\n', 'PROJECT_PLAN.md': 'plan\n', 'ADVERSARIAL_REVIEW.md': 'review\n',
    'FINAL_AUDIT.md': 'audit\n',
}
STAGE_DOC = {'requirements': 'BASELINE_REPORT.md', 'plan': 'PROJECT_PLAN.md', 'review': 'ADVERSARIAL_REVIEW.md',
             'audit': 'FINAL_AUDIT.md'}


def sha(text):
    return hashlib.sha256(text.encode()).hexdigest()


class Revalidate(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.repo = Path(self.tmp.name)
        self.git('init', '-q', '.')
        self.git('config', 'user.email', 'a@b.test')
        self.git('config', 'user.name', 'fixture')
        self.git('config', 'commit.gpgsign', 'false')
        for rel, text in {'README.md': 'hello\n', 'src/app.js': 'export const x = 1;\n',
                          'tests/app.test.js': 'test\n', 'package.json': '{}\n'}.items():
            self.write(rel, text)
        for name, text in DOCS.items():
            self.write('.uncle/docs/' + name, text)
        self.git('add', '-A')
        self.git('commit', '-q', '-m', 'built')
        self.attest()

    def git(self, *args):
        return subprocess.run(['git', *args], cwd=self.repo, check=True, stdout=subprocess.PIPE,
                              stderr=subprocess.PIPE).stdout.decode().strip()

    def write(self, rel, text):
        path = self.repo / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)

    def attest(self, results=None, tree=None):
        """Record what a passing run would have: the filtered tree of HEAD and each stage's approved documents."""
        previous = os.getcwd()
        os.chdir(self.repo)
        try:
            baseline = tree or revalidate.load_verifier().artifact_of(self.git('rev-parse', 'HEAD^{tree}'))
        finally:
            os.chdir(previous)
        results = results or {}
        envelopes = {}
        for stage in revalidate.STAGES:
            evidence = []
            if stage in STAGE_DOC:
                name = STAGE_DOC[stage]
                evidence = [{'path': '.uncle/docs/' + name, 'digest': {'sha256': sha(DOCS[name])}}]
            envelopes[stage] = {'result': results.get(stage, 'pass'), 'evidence': evidence,
                                'reason': 'NOT_READY' if results.get(stage) == 'fail' else None}
        predicate = {'schema_version': 1, 'run_id': 'fixture', 'envelopes': envelopes,
                     'release': {'artifact': {'digest': {'gitTree': baseline}}}}
        self.write('.uncle/attestation.json', json.dumps({'predicate': predicate}))

    def run_cli(self, *args):
        result = subprocess.run([sys.executable, str(REVALIDATE), *args], cwd=self.repo, stdout=subprocess.PIPE,
                                stderr=subprocess.STDOUT, text=True)
        return result.returncode, result.stdout

    def status(self, out):
        """stage label -> 'reused' or 're-run', read from the printed report."""
        rows = {}
        for line in out.splitlines():
            if line[:1] in ('✓', '✗'):
                for stage in revalidate.STAGES:
                    if line[2:].startswith(revalidate.LABEL[stage]):
                        rows[stage] = 'reused' if line[0] == '✓' else 're-run'
        return rows

    def assertReused(self, out, *stages):
        rows = self.status(out)
        for stage in stages:
            self.assertEqual(rows.get(stage), 'reused', '%s should be reused:\n%s' % (stage, out))

    def assertRerun(self, out, *stages):
        rows = self.status(out)
        for stage in stages:
            self.assertEqual(rows.get(stage), 're-run', '%s should re-run:\n%s' % (stage, out))

    # --- the acceptance case ---------------------------------------------------------------------------------------

    def test_readme_change_reuses_every_stage_without_a_full_run(self):
        self.write('README.md', 'hello, with a new paragraph\n')
        code, out = self.run_cli()
        self.assertEqual(code, 0, out)
        self.assertReused(out, *revalidate.STAGES)
        self.assertEqual(sum(1 for status in self.status(out).values() if status == 're-run'), 0)
        self.assertIn('README.md', out)
        self.assertIn('documentation that no stage reads as an input', out)
        self.assertIn('6 stage(s) reused, none re-run.', out)

    def test_readme_change_still_reports_the_attestation_as_stale(self):
        self.write('README.md', 'changed\n')
        _, out = self.run_cli()
        self.assertIn('attestation is stale', out)
        self.assertIn('does not by itself re-run any stage', out)

    def test_other_documentation_is_reused_too(self):
        self.write('docs/guide.md', 'guide\n')
        self.write('CHANGELOG.md', 'log\n')
        self.write('docs/diagram.svg', '<svg/>\n')
        code, out = self.run_cli()
        self.assertEqual(code, 0, out)
        self.assertReused(out, *revalidate.STAGES)

    # --- unchanged and changed ------------------------------------------------------------------------------------

    def test_nothing_changed_reuses_everything(self):
        code, out = self.run_cli()
        self.assertEqual(code, 0, out)
        self.assertReused(out, *revalidate.STAGES)
        self.assertIn('no project file changed since the attestation', out)
        self.assertNotIn('attestation is stale', out)

    def test_source_change_reruns_verification_and_audit_but_not_the_plan_stages(self):
        self.write('src/app.js', 'export const x = 2;\n')
        code, out = self.run_cli()
        self.assertEqual(code, 1, out)
        self.assertReused(out, 'requirements', 'plan', 'review')
        self.assertRerun(out, 'implementation', 'verification', 'audit')
        self.assertIn('changed outside a run: src/app.js', out)

    def test_a_test_file_change_is_reported_as_a_protected_verification_change(self):
        self.write('tests/app.test.js', 'weaker test\n')
        code, out = self.run_cli()
        self.assertEqual(code, 1, out)
        self.assertRerun(out, 'verification', 'audit')
        self.assertIn('protected verification file changed, needs review: tests/app.test.js', out)

    def test_a_file_listed_in_the_protected_paths_is_a_test_even_with_an_ordinary_name(self):
        self.write('.uncle/workflow/verification.paths', 'checks/oracle.txt\n')
        self.write('checks/oracle.txt', 'a\n')
        self.git('add', '-A')
        self.git('commit', '-q', '-m', 'oracle')
        self.attest()
        self.write('checks/oracle.txt', 'b\n')
        code, out = self.run_cli()
        self.assertEqual(code, 1, out)
        self.assertIn('protected verification file changed, needs review: checks/oracle.txt', out)

    def test_an_unknown_file_counts_as_source_not_documentation(self):
        self.write('data.json', '{"a": 1}\n')
        code, out = self.run_cli()
        self.assertEqual(code, 1, out)
        self.assertRerun(out, 'verification', 'audit')

    def test_a_changed_plan_reruns_the_plan_and_everything_after_it(self):
        self.write('.uncle/docs/PROJECT_PLAN.md', 'plan, edited\n')
        code, out = self.run_cli()
        self.assertEqual(code, 1, out)
        self.assertReused(out, 'requirements')
        self.assertRerun(out, 'plan', 'review', 'implementation', 'verification', 'audit')
        self.assertIn('follows plan, which must be re-run', out)

    # --- never reuse what did not pass ----------------------------------------------------------------------------

    def test_a_stage_that_did_not_pass_last_time_is_never_reused(self):
        self.attest(results={'audit': 'fail'})
        code, out = self.run_cli()
        self.assertEqual(code, 1, out)
        self.assertRerun(out, 'audit')
        self.assertReused(out, 'requirements', 'plan', 'review', 'implementation', 'verification')
        self.assertIn('did not pass last time (NOT_READY)', out)

    def test_a_failed_verification_also_reruns_the_audit_after_it(self):
        self.attest(results={'verification': 'fail'})
        _, out = self.run_cli()
        self.assertRerun(out, 'verification', 'audit')

    # --- cannot compare: re-run, never guess ----------------------------------------------------------------------

    def test_an_attested_tree_that_is_not_in_the_repository_reruns_what_it_cannot_compare(self):
        self.attest(tree='0123456789abcdef0123456789abcdef01234567')
        code, out = self.run_cli()
        self.assertEqual(code, 1, out)
        self.assertRerun(out, 'verification', 'audit')
        self.assertIn('nothing can be compared', out)

    def test_no_attestation_is_a_clear_refusal(self):
        (self.repo / '.uncle' / 'attestation.json').unlink()
        code, out = self.run_cli()
        self.assertEqual(code, 2, out)
        self.assertIn('No recorded passing run', out)

    def test_an_attestation_without_stage_results_is_refused(self):
        self.write('.uncle/attestation.json', json.dumps({'predicate': {'envelopes': {}}}))
        code, out = self.run_cli()
        self.assertEqual(code, 2, out)
        self.assertIn('Cannot revalidate', out)

    # --- it only reads -------------------------------------------------------------------------------------------

    def test_it_writes_nothing_to_the_project(self):
        self.write('README.md', 'changed\n')
        before = {p: p.read_bytes() for p in self.repo.rglob('*') if p.is_file() and '.git' not in p.parts}
        status_before = self.git('status', '--porcelain')
        self.run_cli()
        after = {p: p.read_bytes() for p in self.repo.rglob('*') if p.is_file() and '.git' not in p.parts}
        self.assertEqual(before, after)
        self.assertEqual(self.git('status', '--porcelain'), status_before)
        self.assertEqual(self.git('stash', 'list'), '')

    def test_dry_run_is_accepted_and_changes_nothing(self):
        code, out = self.run_cli('--dry-run')
        self.assertEqual(code, 0, out)

    # --- through the real launcher ---------------------------------------------------------------------------------

    def launcher(self, *args):
        env = dict(os.environ, UNCLE_SKIP_UPGRADE='1')
        env.pop('UNCLE_PROJECT_ROOT', None)
        result = subprocess.run([str(ROOT / 'uncle'), *args], cwd=self.repo, env=env, stdin=subprocess.DEVNULL,
                                stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, timeout=60)
        return result.returncode, result.stdout

    def test_uncle_revalidate_is_wired_into_the_launcher(self):
        self.write('README.md', 'launcher\n')
        code, out = self.launcher('--revalidate')
        self.assertEqual(code, 0, out)
        self.assertIn('UNCLE REVALIDATION', out)
        self.assertReused(out, *revalidate.STAGES)

    def test_the_launcher_passes_the_exit_code_through(self):
        self.write('src/app.js', 'export const x = 3;\n')
        code, out = self.launcher('--revalidate')
        self.assertEqual(code, 1, out)
        self.assertRerun(out, 'verification', 'audit')

    def test_help_lists_the_command(self):
        code, out = self.launcher('--help')
        self.assertEqual(code, 0, out)
        self.assertIn('uncle --revalidate', out)

    # --- classification, in isolation ----------------------------------------------------------------------------

    def test_classification(self):
        cases = {'README.md': 'docs', 'docs/guide.md': 'docs', 'LICENSE': 'docs', 'CHANGELOG': 'docs',
                 'docs/img/a.png': 'docs', 'src/App.jsx': 'source', 'package.json': 'source', 'requirements.txt': 'source',
                 'src/style.css': 'source', 'tests/a.js': 'tests', 'src/a.test.js': 'tests', 'e2e/flow.js': 'tests',
                 'playwright.config.js': 'tests', 'test_x.py': 'tests', 'index.html': 'source', 'vite.config.js': 'source'}
        for path, want in cases.items():
            self.assertEqual(revalidate.classify(path, set()), want, path)
        self.assertEqual(revalidate.classify('weird/name.dat', {'weird/name.dat'}), 'tests')


if __name__ == '__main__':
    unittest.main()
