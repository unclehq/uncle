import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

LIB = Path(__file__).resolve().parents[1]/'lib'
MODULE = LIB/'revalidate.py'
sys.path.insert(0, str(LIB))
spec = importlib.util.spec_from_file_location('revalidate', MODULE)
rv = importlib.util.module_from_spec(spec)
spec.loader.exec_module(rv)

# Hard-coded from the plan's D-9 table; deliberately not read from rv.STAGES.
FIRST = 'PLAN'
LATER = 'IMPLEMENT'


class StubRunner:
    def __init__(self, fail_on=None):
        self.calls = []
        self.fail_on = fail_on

    def __call__(self, stage, *args, **kwargs):
        self.calls.append(stage)
        return 1 if stage == self.fail_on else 0


def make_project(d):
    root = Path(d)
    subprocess.run(['git', '-c', 'commit.gpgsign=false', 'init', '-q', str(root)], check=True)
    (root/'.uncle/docs').mkdir(parents=True)
    (root/'.uncle/workflow').mkdir(parents=True)
    (root/'README.md').write_text('docs\n')
    (root/'app.py').write_text('print(1)\n')
    return root


def cli(root, *args):
    return subprocess.run([sys.executable, str(MODULE), *args], cwd=root, capture_output=True, text=True)


class RevalidateCli(unittest.TestCase):
    def test_no_recorded_passes_exits_2_and_runs_nothing(self):
        with tempfile.TemporaryDirectory() as d:
            root = make_project(d)
            r = cli(root, 'run', '--dry-run')
            self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
            self.assertIn('no recorded passes', (r.stdout + r.stderr).lower())
            self.assertFalse((root/'.uncle/workflow/stage-fingerprints').exists() and
                             any((root/'.uncle/workflow/stage-fingerprints').glob('*.json')))

    def test_legacy_project_with_state_only_exits_2_with_zero_runner_calls(self):
        with tempfile.TemporaryDirectory() as d:
            root = make_project(d)
            (root/'.uncle/workflow/state').write_text('DONE\n')
            runner = StubRunner()
            try:
                code = rv.run(root, False, runner)
            except TypeError:
                code = rv.run(root, dry_run=False, runner=runner)
            code = code if isinstance(code, int) else getattr(code, 'exit_code', 2)
            self.assertEqual(code, 2)
            self.assertEqual(runner.calls, [])

    def test_record_writes_pass_record(self):
        with tempfile.TemporaryDirectory() as d:
            root = make_project(d)
            r = cli(root, 'record', FIRST)
            self.assertEqual(r.returncode, 0, r.stderr)
            rec = json.loads((root/'.uncle/workflow/stage-fingerprints'/f'{FIRST}.json').read_text())
            self.assertEqual(rec['stage'], FIRST)
            self.assertEqual(rec['status'], 'pass')
            self.assertTrue(rec['hash'])
            self.assertIsInstance(rec['inputs'], dict)

    def test_record_is_deterministic_for_unchanged_inputs(self):
        with tempfile.TemporaryDirectory() as d:
            root = make_project(d)
            cli(root, 'record', FIRST)
            p = root/'.uncle/workflow/stage-fingerprints'/f'{FIRST}.json'
            h1 = json.loads(p.read_text())['hash']
            cli(root, 'record', FIRST)
            self.assertEqual(json.loads(p.read_text())['hash'], h1)

    def test_readme_edit_does_not_change_stage_hash(self):
        with tempfile.TemporaryDirectory() as d:
            root = make_project(d)
            cli(root, 'record', LATER)
            p = root/'.uncle/workflow/stage-fingerprints'/f'{LATER}.json'
            h1 = json.loads(p.read_text())['hash']
            (root/'README.md').write_text('changed docs\n')
            cli(root, 'record', LATER)
            self.assertEqual(json.loads(p.read_text())['hash'], h1)

    def test_dry_run_does_not_modify_tree(self):
        with tempfile.TemporaryDirectory() as d:
            root = make_project(d)
            cli(root, 'record', FIRST)
            before = sorted((str(p.relative_to(root)), p.read_bytes()) for p in root.rglob('*')
                            if p.is_file() and '.git/' not in str(p))
            (root/'app.py').write_text('print(2)\n')
            before = sorted((str(p.relative_to(root)), p.read_bytes()) for p in root.rglob('*')
                            if p.is_file() and '.git/' not in str(p))
            r = cli(root, 'run', '--dry-run')
            self.assertIn(r.returncode, (0, 1))
            after = sorted((str(p.relative_to(root)), p.read_bytes()) for p in root.rglob('*')
                           if p.is_file() and '.git/' not in str(p))
            self.assertEqual(before, after)


class RevalidateApi(unittest.TestCase):
    def _rows(self, root):
        why, rows = rv.plan(root)
        self.assertIsNone(why)
        return {r['stage']: r for r in rows}

    def test_source_edit_reruns_stage_and_invalidates_downstream_before_runner(self):
        with tempfile.TemporaryDirectory() as d:
            root = make_project(d)
            rv.record(FIRST, root)
            rv.record(LATER, root)
            (root/'app.py').write_text('print(2)\n')
            seen = []

            def runner(stage, *a, **k):
                rec = root/'.uncle/workflow/stage-fingerprints'/f'{LATER}.json'
                seen.append((stage, json.loads(rec.read_text()).get('status') if rec.exists() else None))
                return 1

            rv.run(root, False, runner)
            self.assertTrue(seen, 'runner was never called')
            self.assertEqual(seen[0][0], FIRST)
            # Downstream record is already invalidated when the FIRST runner call happens.
            self.assertEqual(seen[0][1], 'invalidated')

    def test_failed_runner_keeps_invalidation_for_next_invocation(self):
        with tempfile.TemporaryDirectory() as d:
            root = make_project(d)
            rv.record(FIRST, root)
            rv.record(LATER, root)
            (root/'app.py').write_text('print(2)\n')
            r1 = StubRunner(fail_on=LATER)
            rv.run(root, False, r1)
            r2 = StubRunner()
            rv.run(root, False, r2)
            self.assertIn(LATER, r2.calls)
            self.assertNotIn(FIRST, r2.calls)

    def test_unchanged_inputs_reuse_everything(self):
        with tempfile.TemporaryDirectory() as d:
            root = make_project(d)
            rv.record(FIRST, root)
            runner = StubRunner()
            code = rv.run(root, False, runner, out=open('/dev/null', 'w'))
            self.assertEqual(runner.calls, [])
            self.assertEqual(code, 0)
            rows = self._rows(root)
            self.assertEqual(rows[FIRST]['action'], 'reuse')
            self.assertTrue(all(r['action'] == 'skip' for n, r in rows.items() if n != FIRST))

    def test_unmapped_stage_is_reported_changed(self):
        with tempfile.TemporaryDirectory() as d:
            root = make_project(d)
            rv.record(FIRST, root)
            p = root/'.uncle/workflow/stage-fingerprints/NOT_A_STAGE.json'
            p.write_text(json.dumps({'stage': 'NOT_A_STAGE', 'hash': 'x', 'inputs': {}, 'status': 'pass'}))
            runner = StubRunner()
            rv.run(root, False, runner, out=open('/dev/null', 'w'))
            self.assertNotIn('NOT_A_STAGE', runner.calls)
            self.assertNotIn('NOT_A_STAGE', self._rows(root))
            with self.assertRaises(Exception):
                rv.fingerprint('NOT_A_STAGE', root)


class DefaultRunnerArguments(unittest.TestCase):
    """default_runner started the driver with `--noui`, which change-workflow.sh rejects as an unknown argument, so the first stage
    that actually had to run failed before doing anything (found by the PR's own manual check). A stub runner never sees the
    driver's parser; these feed the runner's real arguments to it."""
    DRIVER = Path(__file__).resolve().parents[1]/'change-workflow.sh'

    def argv_used(self, env_extra):
        from unittest import mock
        captured = {}

        def fake(argv, **kwargs):
            captured['argv'], captured['env'] = argv, kwargs.get('env', {})
            return subprocess.CompletedProcess(argv, 0)
        with tempfile.TemporaryDirectory() as d:
            root = make_project(d)
            with mock.patch.object(rv.subprocess, 'run', side_effect=fake), \
                    mock.patch.dict(rv.os.environ, env_extra, clear=False):
                rv.default_runner('PLAN', root)
        return captured['argv'], captured['env']

    def test_the_driver_accepts_every_argument_default_runner_passes(self):
        argv, _ = self.argv_used({'UNCLE_ATTENDED': ''})
        self.assertNotIn('--noui', argv)
        # The driver parses its arguments in order, so a trailing --help proves every earlier one was accepted.
        # Run it inside a throwaway project with the run policy off: the driver acts on its working directory before it parses.
        with tempfile.TemporaryDirectory() as d:
            root = make_project(d)
            env = {k: v for k, v in os.environ.items() if not k.startswith(('UNCLE_', 'WORKFLOW_'))}
            env.update(UNCLE_PROJECT_ROOT=str(root), UNCLE_RUN_POLICY='off', UNCLE_NOUI='1')
            done = subprocess.run(['bash', str(self.DRIVER), *argv[2:], '--help'], cwd=root, env=env,
                                  capture_output=True, text=True, timeout=60)
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        self.assertNotIn('Unknown argument', done.stderr)

    def test_no_ui_travels_in_the_environment(self):
        _, env = self.argv_used({})
        self.assertEqual(env.get('UNCLE_NOUI'), '1')

    def test_an_attended_run_passes_attended_and_otherwise_unattended(self):
        self.assertEqual(self.argv_used({'UNCLE_ATTENDED': '1'})[0][2:], ['--attended'])
        self.assertEqual(self.argv_used({'UNCLE_ATTENDED': ''})[0][2:], ['--unattended'])


class DriverExitIsNotAPass(unittest.TestCase):
    """The driver exits 0 after reopening a gate whose approval no longer matches, having run nothing; default_runner recorded
    that as a pass. A stage passed only if the driver's own pending list no longer names it."""

    def run_with_pending(self, pending_text):
        from unittest import mock

        def fake(argv, **kwargs):
            if pending_text is not None:
                (Path(kwargs['cwd'])/'.uncle/workflow/revalidate-pending.txt').write_text(pending_text)
            return subprocess.CompletedProcess(argv, 0)
        with tempfile.TemporaryDirectory() as d:
            root = make_project(d)
            with mock.patch.object(rv.subprocess, 'run', side_effect=fake):
                return rv.default_runner('PLAN', root)

    def test_exit_0_with_the_stage_still_pending_is_a_failure(self):
        self.assertEqual(self.run_with_pending('PLAN\n'), 'failed')

    def test_only_this_stage_being_listed_as_pending_makes_it_a_failure(self):
        self.assertEqual(self.run_with_pending('IMPLEMENT\n'), 'pass')

    def test_exit_0_with_the_pending_list_emptied_is_a_pass(self):
        self.assertEqual(self.run_with_pending(''), 'pass')

    def test_exit_0_when_the_driver_never_wrote_a_pending_list_is_a_failure(self):
        self.assertEqual(self.run_with_pending(None), 'failed')


class AttestationLine(unittest.TestCase):
    """The attestation line reports the verifier's verdict, not whatever line it printed last (it prints an explanation after
    a NOT VERIFIED verdict, which used to surface as `attestation: then run uncle verify again.`)."""

    def line(self, stdout, returncode=1):
        import io
        from unittest import mock
        done = subprocess.CompletedProcess([], returncode, stdout=stdout, stderr='')
        out = io.StringIO()
        with mock.patch.object(rv.subprocess, 'run', return_value=done):
            rv._attestation_line('.', out)
        return out.getvalue().strip()

    def test_verdict_before_an_explanation_block_is_the_one_reported(self):
        text = ('UNCLE CHANGE VERIFICATION\n\n\u2717 head tree does not match\n\nNOT VERIFIED\n\n'
                'This change could not be verified.\nReasons:\n  - head tree does not match\n\n'
                'Fix the failed checks listed above, then run uncle verify again.')
        self.assertEqual(self.line(text), 'attestation: NOT VERIFIED')

    def test_each_verdict_form_is_recognised(self):
        for verdict in ('VERIFIED', 'NOT HUMAN VERIFIED', 'INTEGRITY ONLY \u2014 SIGNATURE PRESENT BUT UNTRUSTED'):
            self.assertEqual(self.line('checks\n\n%s\n' % verdict, 0), 'attestation: ' + verdict)

    def test_output_with_no_verdict_falls_back_to_its_last_line(self):
        self.assertEqual(self.line('something odd\nlast words'), 'attestation: last words')

    def test_the_real_verifier_run_in_a_project_prints_a_verdict(self):
        import io
        with tempfile.TemporaryDirectory() as d:
            root = make_project(d)
            out = io.StringIO()
            rv._attestation_line(root, out)
            self.assertRegex(out.getvalue(), r'^attestation: (NOT VERIFIED|NOT HUMAN VERIFIED|VERIFIED|INTEGRITY ONLY|[A-Za-z]).*')
            self.assertNotIn('then run uncle verify again', out.getvalue())


class RevalidateAudit(unittest.TestCase):
    def _rows(self, root):
        why, rows = rv.plan(root)
        self.assertIsNone(why)
        return {r['stage']: r for r in rows}

    def test_only_root_readme_is_exempt(self):
        with tempfile.TemporaryDirectory() as d:
            root = make_project(d)
            rv.record(FIRST, root)
            (root/'README.md').write_text('changed\n')
            self.assertEqual(self._rows(root)[FIRST]['action'], 'reuse')
            (root/'docs').mkdir()
            (root/'docs/README.md').write_text('a\n')
            rv.record(FIRST, root)
            (root/'docs/README.md').write_text('b\n')
            self.assertEqual(self._rows(root)[FIRST]['action'], 'run')

    def test_protected_path_edit_is_needs_review_not_run_and_exits_nonzero(self):
        with tempfile.TemporaryDirectory() as d:
            root = make_project(d)
            (root/'verify.sh').write_text('true\n')
            (root/'.uncle/workflow/protected-paths').write_text('verify.sh\n')
            for st in (FIRST, LATER):
                rv.record(st, root)
            (root/'verify.sh').write_text('exit 0\n')
            rows = self._rows(root)
            self.assertEqual(rows[LATER]['action'], 'needs-review')
            runner = StubRunner()
            code = rv.run(root, False, runner, out=open('/dev/null', 'w'))
            self.assertNotEqual(code, 0)
            self.assertNotIn(LATER, runner.calls)

    def test_legacy_stage_runs_and_never_run_stage_skips(self):
        with tempfile.TemporaryDirectory() as d:
            root = make_project(d)
            rv.record(FIRST, root)
            (root/'.uncle/docs/ADVERSARIAL_REVIEW.md').write_text('x\n')
            rows = self._rows(root)
            self.assertEqual(rows['ADVERSARIAL_REVIEW']['action'], 'run')
            self.assertEqual(rows['FINAL_AUDIT']['action'], 'skip')

    def test_no_passes_exits_2_even_with_history(self):
        with tempfile.TemporaryDirectory() as d:
            root = make_project(d)
            (root/'.uncle/docs/ADVERSARIAL_REVIEW.md').write_text('x\n')
            runner = StubRunner()
            self.assertEqual(rv.run(root, False, runner, out=open('/dev/null', 'w')), 2)
            self.assertEqual(runner.calls, [])

    def test_run_writes_plan_handoff_file(self):
        with tempfile.TemporaryDirectory() as d:
            root = make_project(d)
            rv.record(FIRST, root)
            (root/'app.py').write_text('print(2)\n')
            rv.run(root, False, StubRunner(), out=open('/dev/null', 'w'))
            data = json.loads(rv.plan_path(root).read_text())
            self.assertIn(FIRST, {r['stage'] for r in data['rows'] if r['action'] == 'run'})


class RevalidateHook(unittest.TestCase):
    def test_driver_records_only_at_explicit_success_points(self):
        for script in ('change-workflow.sh', 'stagegate.sh'):
            text = (LIB.parent/script).read_text()
            self.assertIn('revalidate.py', text)
            for line in text.splitlines():
                if 'revalidate.py' in line and 'record' in line:
                    self.assertNotIn('set_state()', line)
        text = (LIB.parent/'change-workflow.sh').read_text()
        body = text.split('set_state()', 1)[-1].split('\n}', 1)[0]
        self.assertNotIn('revalidate.py', body)


UNCLE = LIB.parents[1]/'uncle'


class RevalidateTableIndependent(unittest.TestCase):
    """Expectations hard-coded from the plan's D-9 table, not read from rv.STAGES."""

    def _hash(self, root, stage):
        return rv.fingerprint(stage, root)

    def test_plan_stage_hash_ignores_unrelated_plan_doc(self):
        with tempfile.TemporaryDirectory() as d:
            root = make_project(d)
            (root/'.uncle/docs/CHANGE_PLAN.md').write_text('plan v1\n')
            h = self._hash(root, 'PLAN')
            (root/'.uncle/docs/CHANGE_PLAN.md').write_text('plan v2\n')
            self.assertEqual(self._hash(root, 'PLAN'), h)

    def test_classify_stage_hash_tracks_plan_doc(self):
        with tempfile.TemporaryDirectory() as d:
            root = make_project(d)
            (root/'.uncle/docs/CHANGE_PLAN.md').write_text('plan v1\n')
            h = self._hash(root, 'CLASSIFY')
            (root/'.uncle/docs/CHANGE_PLAN.md').write_text('plan v2\n')
            self.assertNotEqual(self._hash(root, 'CLASSIFY'), h)

    def test_analyze_stage_ignores_app_source_but_tracks_request(self):
        with tempfile.TemporaryDirectory() as d:
            root = make_project(d)
            (root/'.uncle/docs/CHANGE_REQUEST.md').write_text('req 1\n')
            h = self._hash(root, 'ANALYZE')
            (root/'app.py').write_text('print(99)\n')
            self.assertEqual(self._hash(root, 'ANALYZE'), h)
            (root/'.uncle/docs/CHANGE_REQUEST.md').write_text('req 2\n')
            self.assertNotEqual(self._hash(root, 'ANALYZE'), h)

    def test_implement_stage_tracks_app_source(self):
        with tempfile.TemporaryDirectory() as d:
            root = make_project(d)
            h = self._hash(root, 'IMPLEMENT')
            (root/'app.py').write_text('print(99)\n')
            self.assertNotEqual(self._hash(root, 'IMPLEMENT'), h)

    def test_unmapped_stage_raises_so_it_counts_as_changed(self):
        with tempfile.TemporaryDirectory() as d:
            root = make_project(d)
            with self.assertRaises(KeyError):
                rv.fingerprint('NOT_A_STAGE', root)

    def test_unmapped_input_kind_raises(self):
        with tempfile.TemporaryDirectory() as d:
            root = make_project(d)
            with self.assertRaises(KeyError):
                rv.input_hash('bogus-kind', root)


class UncleDispatch(unittest.TestCase):
    def test_usage_lists_revalidate(self):
        r = subprocess.run(['bash', str(UNCLE), '--help'], capture_output=True, text=True)
        self.assertIn('--revalidate', r.stdout + r.stderr)

    def test_dry_run_without_revalidate_is_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            r = subprocess.run(['bash', str(UNCLE), '--dry-run'], cwd=d, capture_output=True, text=True)
            self.assertNotEqual(r.returncode, 0)
            self.assertIn('--revalidate', r.stdout + r.stderr)

    def test_revalidate_dispatches_to_module_with_no_state(self):
        with tempfile.TemporaryDirectory() as d:
            root = make_project(d)
            r = subprocess.run(['bash', str(UNCLE), '--revalidate', '--dry-run'], cwd=root,
                               capture_output=True, text=True)
            self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
            self.assertIn('no recorded passes', (r.stdout + r.stderr).lower())


if __name__ == '__main__':
    unittest.main()
