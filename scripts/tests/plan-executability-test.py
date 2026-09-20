#!/usr/bin/env python3
import copy
import importlib.util
import json
import os
from pathlib import Path
import sys
import signal
import subprocess
import time
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('executability', ROOT / 'scripts/lib/plan-executability.py')
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


def assessment(m):
    plan = m['plan']
    requirements = sorted(mod.ids_in('CHANGE_SPEC.md' if plan == 'CHANGE_PLAN.md' else 'REQUIREMENTS_INTERPRETATION.md', 'AC'))
    evidence = str(Path(os.environ.get('WORKFLOW_AGENT_CMD', 'probe.txt')).resolve())
    status = os.environ.get('FAKE_CAP_STATUS', 'SUPPORTED')
    if 'isolated-context revision' in Path(plan).read_text():
        status = 'SUPPORTED'
    restriction_ids = sorted(mod.ids_in(plan, 'R'))
    finding_ids = sorted(mod.ids_in('ADVERSARIAL_REVIEW.md', 'AR'))
    if finding_ids and not restriction_ids:
        restriction_ids = ['R-1']
    restrictions = [dict(id=r, source_kind='DESIGN', source_location=plan, requirement_ids=requirements,
                         property='mediated access', mechanism='isolated context' if status == 'SUPPORTED' else 'blanket denial',
                         rationale='stub probe establishes capability', capability_ids=['CAP-1']) for r in restriction_ids]
    decisions = []
    if os.environ.get('FAKE_DECISION') and not (mod.STATE / 'authority-answer.json').exists():
        decisions = [dict(id='D-1', question='May the external retention limit change?',
                          alternatives=['retain limit', 'authorize change'], tradeoff='retention versus feature scope')]
    steps = [dict(id='S-1', paths=['app/main.sh', 'app/added.sh'], requirement_ids=requirements,
                  depends_on=[], capability_ids=['CAP-1'], decision_ids=['D-1'] if decisions else [])]
    if os.environ.get('FAKE_INDEPENDENT'):
        steps.append(dict(id='S-2', paths=['app/helper.sh'], requirement_ids=requirements,
                          depends_on=[], capability_ids=['CAP-1'], decision_ids=[]))
    prerequisites = []
    if os.environ.get('FAKE_LIVE'):
        prerequisites = [dict(id='P-1', phase='LIVE_VERIFICATION', status='UNVERIFIED', check_ids=['LIVE-1'],
                              commands=['bash app/live-test.sh'], evidence_paths=[os.environ['FAKE_LIVE']])]
    return dict(version=1, input_digest=m['digest'], requirement_ids=requirements,
                restrictions=restrictions,
                capabilities=[dict(id='CAP-1', binding=m['digest'], required_phase='CODING', status=status,
                                   evidence=[dict(path=evidence, sha256=mod.file_hash(evidence))],
                                   command='inspect stub runner', observed_result=status, dependent_ids=['S-1'])],
                findings=[dict(id=f, property='mediated access', disposition='alternative', evidence=evidence,
                               restriction=restriction_ids[0]) for f in finding_ids],
                prerequisites=prerequisites, steps=steps, decisions=decisions,
                verdict='DECISION' if decisions else ('READY' if status == 'SUPPORTED' else 'REVISE'))


def fixture(root, mode):
    os.chdir(root)
    plan = 'UPDATED_PROJECT_PLAN.md' if os.environ.get('FAKE_WORKFLOW') == 'stagegate' else 'CHANGE_PLAN.md'
    target = mod.ASSESS / 'manifest.json'
    if mode == 'seed' and (target.exists() or os.environ.get('FAKE_ASSESS_NO_APPROVAL')):
        return
    m = mod.manifest(root, plan)
    mod.atomic(target, m)
    mod.atomic(mod.ASSESS / 'assessment.json', assessment(m))
    if mode == 'seed':
        saved = sys.argv
        sys.argv = [saved[0], 'render']
        try:
            mod.main()
        finally:
            sys.argv = saved
        (mod.STATE / 'approvals/PLAN_EXECUTABILITY.sha256').write_text(mod.file_hash(mod.ASSESS / 'assessment.md') + '\n')


class ContractTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.old = Path.cwd()
        os.chdir(self.tmp.name)
        Path('CHANGE_PLAN.md').write_text('R-1')
        Path('CHANGE_SPEC.md').write_text('AC-1')
        Path('ADVERSARIAL_REVIEW.md').write_text('AR-001')
        Path('probe.txt').write_text('isolated context supported by stub')
        self.m = mod.manifest(ROOT, 'CHANGE_PLAN.md')
        self.a = assessment(self.m)
        self.addCleanup(self.tmp.cleanup)
        self.addCleanup(os.chdir, self.old)

    def collect_assessment(self, mode, verdict='READY'):
        response = copy.deepcopy(self.a)
        response['verdict'] = verdict
        if verdict == 'REVISE':
            response['capabilities'][0]['status'] = 'UNSUPPORTED'
        mod.atomic(mod.ASSESS / 'manifest.json', self.m)
        mod.atomic('valid-response.json', response)
        (mod.ASSESS / 'assessment.json').write_text('Old conversational response')
        (mod.ASSESS / 'validated.json').write_text('stale validation')
        (mod.ASSESS / 'assessment.md').write_text('stale rendered assessment')
        (mod.ASSESS / 'prompt.md').write_text((ROOT/'prompts/plan-executability.md').read_text())
        script = r"""
set -euo pipefail
ROOT="$1"
PLAN_ASSESS_DIR=.uncle/workflow/plan-executability
source "$ROOT/scripts/lib/plan-recovery.sh"
calls=0
plan_review() {
    calls=$((calls+1))
    printf '%s' "$calls" > calls
    if [[ "$TEST_MODE" == transport ]]; then return 7; fi
    if [[ "$TEST_MODE" == valid || ( "$TEST_MODE" == retry && "$calls" == 2 ) ]]; then
        cp valid-response.json "$2"
    else
        printf 'Yes—three coding blockers remain.' > "$2"
    fi
}
plan_collect_assessment
"""
        return subprocess.run(['bash', '-c', script, 'test', str(ROOT)],
                              env=dict(os.environ, TEST_MODE=mode),
                              capture_output=True, text=True, timeout=15)

    def test_conversational_assessment_retried_without_weakening_verdict(self):
        result = self.collect_assessment('retry', 'REVISE')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(Path('calls').read_text(), '2')
        self.assertEqual(mod.read(mod.ASSESS/'assessment.json')['verdict'], 'REVISE')
        rejected = list(mod.ASSESS.glob('output-attempt.*/rejected-response.txt'))
        self.assertEqual(len(rejected), 1)
        self.assertIn('three coding blockers', rejected[0].read_text())
        self.assertFalse((mod.ASSESS/'validated.json').exists())
        self.assertFalse((mod.ASSESS/'assessment.md').exists())
        self.assertEqual(Path('CHANGE_PLAN.md').read_text(), 'R-1')

    def test_repeated_invalid_assessment_stops_after_two_attempts(self):
        result = self.collect_assessment('invalid')
        self.assertEqual(result.returncode, 1)
        self.assertEqual(Path('calls').read_text(), '2')
        self.assertIn('after one retry', result.stderr)
        self.assertEqual(len(list(mod.ASSESS.glob('output-attempt.*/rejected-response.txt'))), 2)
        self.assertFalse((mod.ASSESS/'validated.json').exists())

    def test_valid_assessment_does_not_retry(self):
        result = self.collect_assessment('valid')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(Path('calls').read_text(), '1')

    def test_transport_failure_is_not_retried_as_bad_json(self):
        result = self.collect_assessment('transport')
        self.assertEqual(result.returncode, 1)
        self.assertEqual(Path('calls').read_text(), '1')

    def test_nonobject_assessment_has_clear_error(self):
        mod.atomic(mod.ASSESS/'manifest.json', self.m)
        for response in ('[]', '', 'Yes, three blockers remain.'):
            (mod.ASSESS/'assessment.json').write_text(response)
            result = subprocess.run([sys.executable, str(ROOT/'scripts/lib/plan-executability.py'),
                                     'validate'], capture_output=True, text=True)
            self.assertEqual(result.returncode, 12)
            self.assertIn('assessment.json', result.stderr)
            self.assertNotIn('Traceback', result.stderr)

    def test_supported(self):
        self.assertEqual(mod.validate(self.a, self.m)['eligible_steps'], ['S-1'])

    def test_rejections(self):
        mutations = [lambda a: a.update(input_digest='stale'),
                     lambda a: a.update(requirement_ids=[]), lambda a: a.update(findings=[]),
                     lambda a: a['restrictions'][0].update(source_kind='MANDATORY'),
                     lambda a: a['restrictions'][0].update(rationale=''),
                     lambda a: a['restrictions'][0].update(capability_ids=[]),
                     lambda a: a['capabilities'][0].update(status='UNSUPPORTED'),
                     lambda a: a['capabilities'][0].update(binding='another runner'),
                     lambda a: a['steps'][0].update(depends_on=['S-1']),
                     lambda a: a['steps'][0].update(depends_on=['absent']),
                     lambda a: a['steps'][0].update(paths=['../escape']),
                     lambda a: a['findings'][0].update(property='unrestricted access')]
        for index, mutate in enumerate(mutations):
            with self.subTest(index=index):
                a = copy.deepcopy(self.a); mutate(a)
                with self.assertRaises(ValueError):
                    mod.validate(a, self.m)

    def test_stale_evidence(self):
        Path('probe.txt').write_text('changed')
        with self.assertRaisesRegex(ValueError, 'stale evidence'):
            mod.validate(self.a, self.m)

    def test_decision_transitive_subset(self):
        self.a['verdict'] = 'DECISION'
        self.a['decisions'] = [dict(id='D-1', question='Change scope?', alternatives=['yes', 'no'], tradeoff='scope')]
        self.a['steps'][0]['decision_ids'] = ['D-1']
        for sid, deps in [('S-2', ['S-1']), ('S-3', [])]:
            step = copy.deepcopy(self.a['steps'][0]); step.update(id=sid, depends_on=deps, decision_ids=[])
            self.a['steps'].append(step)
        self.assertEqual(mod.validate(self.a, self.m)['eligible_steps'], ['S-3'])

    def test_live_does_not_block_coding(self):
        self.a['capabilities'][0].update(required_phase='LIVE_VERIFICATION', status='UNVERIFIED')
        self.assertEqual(mod.validate(self.a, self.m)['verdict'], 'READY')

    def test_malformed_blocker(self):
        Path('IMPLEMENTATION_NOTES.md').write_text('```plan-blockers\n{}\n```')
        with self.assertRaises(ValueError):
            mod.blockers('IMPLEMENTATION_NOTES.md')

    def test_journal_corruption(self):
        mod.atomic(mod.JOURNAL, {'version': 2})
        with self.assertRaises(ValueError):
            mod.journal()

    def prepare_runtime(self):
        mod.atomic(mod.ASSESS / 'manifest.json', self.m)
        mod.atomic(mod.ASSESS / 'assessment.json', self.a)
        subprocess.run(['git', 'init', '-q'], check=True)
        Path('.gitignore').write_text('.uncle/\n')

    def test_launch_intent_blocks_replay(self):
        self.prepare_runtime()
        self.assertEqual(mod.runtime('dispatch'), 0)
        self.assertEqual(mod.runtime('dispatch'), 25)
        self.assertEqual(mod.runtime('retry'), 0)
        self.assertEqual(mod.runtime('dispatch'), 0)
        Path('IMPLEMENTATION_NOTES.md').write_text('delivered')
        self.assertEqual(mod.runtime('classify'), 0)
        self.assertEqual(mod.runtime('dispatch'), 22)

    def test_live_failure_waits_for_changed_evidence(self):
        self.a['prerequisites'] = [dict(id='P-1', phase='LIVE_VERIFICATION', status='UNVERIFIED',
            check_ids=['LIVE-1'], commands=['true'], evidence_paths=['auth'])]
        self.prepare_runtime()
        Path('IMPLEMENTATION_NOTES.md').write_text('```plan-blockers\n' + json.dumps([
            dict(id='B-1', **{'class': 'LIVE_VERIFICATION'}, requirement_ids=['AC-1'],
                 restriction_ids=[], evidence='missing auth', independent_work='delivered')]) + '\n```')
        self.assertEqual(mod.runtime('classify'), 20)
        self.assertEqual(mod.runtime('dispatch'), 20)
        Path('auth').write_text('ready')
        self.assertEqual(mod.runtime('dispatch'), 21)
        with self.assertRaisesRegex(ValueError, 'interrupted verification'):
            mod.runtime('dispatch')
        self.assertEqual(mod.runtime('classify'), 20)
        self.assertEqual(mod.runtime('dispatch'), 20)

    def test_verification_source_mutation_rejected(self):
        self.prepare_runtime()
        Path('app.py').write_text('original')
        mod.runtime('snapshot')
        j = mod.journal(); j['phase'] = 'VERIFYING'; mod.atomic(mod.JOURNAL, j)
        Path('app.py').write_text('changed')
        with self.assertRaisesRegex(ValueError, 'verification-only source mutation'):
            mod.runtime('source-check')
        self.assertEqual(Path('app.py').read_text(), 'changed')

    def test_design_bound_survives_cosmetic_plan_changes(self):
        self.prepare_runtime()
        saved = sys.argv
        self.addCleanup(setattr, sys, 'argv', saved)
        sys.argv = ['tool', 'recover']
        self.assertEqual(mod.main(), 0)
        Path('CHANGE_PLAN.md').write_text('R-1 cosmetic edit')
        self.m = mod.manifest(ROOT, 'CHANGE_PLAN.md')
        mod.atomic(mod.ASSESS / 'manifest.json', self.m)
        with self.assertRaisesRegex(ValueError, 'same failed mechanism'):
            mod.main()
        self.a['restrictions'][0]['mechanism'] = 'different mechanism'
        mod.atomic(mod.ASSESS / 'assessment.json', self.a)
        self.assertEqual(mod.main(), 0)
        self.a['restrictions'][0]['mechanism'] = 'third mechanism'
        mod.atomic(mod.ASSESS / 'assessment.json', self.a)
        with self.assertRaisesRegex(ValueError, 'two design revisions exhausted'):
            mod.main()

    def test_preflight_rejects_misplaced_live_blocker(self):
        self.a['prerequisites'] = [dict(id='P-1', phase='LIVE_VERIFICATION', status='UNVERIFIED',
            check_ids=['LIVE-1'], commands=['true'], evidence_paths=['auth'])]
        self.prepare_runtime()
        Path('PREFLIGHT_REPORT.md').write_text('## Acceptance gate\n| P-1 | YES | BLOCKED-SETUP | auth |\n')
        with self.assertRaisesRegex(ValueError, 'belongs in Findings'):
            mod.runtime('preflight-check')
        Path('PREFLIGHT_REPORT.md').write_text('## Findings\nP-1 live auth unavailable\n## Acceptance gate\n| CODING | YES | PASS | mocks |\n')
        self.assertEqual(mod.runtime('preflight-check'), 0)

    def test_stagegate_live_success_needs_complete_delivery(self):
        Path('UPDATED_PROJECT_PLAN.md').write_text('R-1')
        Path('REQUIREMENTS_INTERPRETATION.md').write_text('## Acceptance criteria\n| ID | Criterion | Verification |\n|---|---|---|\n| AC-1 | live works | live check |\n')
        self.m = mod.manifest(ROOT, 'UPDATED_PROJECT_PLAN.md')
        self.a = assessment(self.m)
        self.prepare_runtime()
        j = mod.journal(); j['phase'] = 'VERIFYING'; mod.atomic(mod.JOURNAL, j)
        Path('IMPLEMENTATION_NOTES.md').write_text('## Acceptance delivery\n| ID | Status | Changed code | Observed targeted verification |\n|---|---|---|---|\n| AC-1 | INCOMPLETE | helper.py | missing live evidence |\n')
        self.assertEqual(mod.runtime('classify'), 20)
        self.assertEqual(mod.journal()['phase'], 'WAIT_LIVE')

    def test_incomplete_delivery_can_retry_after_resume(self):
        Path('UPDATED_PROJECT_PLAN.md').write_text('R-1')
        Path('REQUIREMENTS_INTERPRETATION.md').write_text('## Acceptance criteria\n| ID | Criterion | Verification |\n|---|---|---|\n| AC-1 | coding | test |\n')
        self.m = mod.manifest(ROOT, 'UPDATED_PROJECT_PLAN.md')
        self.a = assessment(self.m)
        self.prepare_runtime()
        self.assertEqual(mod.runtime('dispatch'), 0)
        Path('IMPLEMENTATION_NOTES.md').write_text('## Acceptance delivery\n| ID | Status | Changed code | Observed targeted verification |\n|---|---|---|---|\n| AC-1 | INCOMPLETE | helper.py | missing test |\n')
        self.assertEqual(mod.runtime('classify'), 24)
        self.assertEqual(mod.runtime('dispatch'), 22)
        self.assertEqual(mod.runtime('classify'), 24)
        self.assertEqual(mod.runtime('retry'), 0)
        self.assertEqual(mod.runtime('dispatch'), 0)

    @unittest.skipIf(os.name == 'nt', 'POSIX orphan process groups; Windows has Job Object tests')
    def test_lock_exclusion_and_orphan_group(self):
        tool = ROOT / 'scripts/lib/plan-executability.py'
        command = [sys.executable, str(tool), 'lock-run', sys.executable, '-c',
                   'import pathlib,time; pathlib.Path("started").write_text("yes"); time.sleep(20)']
        owner = subprocess.Popen(command, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
        self.addCleanup(lambda: owner.poll() is not None or owner.kill())
        for _ in range(150):
            if Path('started').exists() or owner.poll() is not None:
                break
            time.sleep(.02)
        self.assertTrue(Path('started').exists(), owner.stderr.read().decode() if owner.poll() is not None else 'startup timeout')
        record = mod.read(mod.STATE / 'driver.lock')
        competitor = subprocess.run(command, capture_output=True)
        self.assertEqual(competitor.returncode, 12)
        self.assertIn(b'another workflow', competitor.stderr)
        owner.kill(); owner.wait()
        try:
            competitor = subprocess.run(command, capture_output=True)
            self.assertEqual(competitor.returncode, 12)
            self.assertIn(b'process group still alive', competitor.stderr)
        finally:
            os.killpg(record['pgid'], signal.SIGKILL)
            owner.stderr.close()



class DeliverySummaryTests(unittest.TestCase):
    """A real stuck build: stagegate.sh's own prompts never ask an agent to
    write '## Acceptance delivery' (only prompts/change/implement-change.md
    does, for the AC-numbered CHANGE_SPEC.md convention), so a greenfield
    plan's IMPLEMENTATION_NOTES.md never has that section. Manufacturing an
    always-empty delivery-summary.tsv anyway looked, to a reviewer, like
    delivery tracking that should have updated and never did."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.old = Path.cwd()
        os.chdir(self.tmp.name)
        mod.STATE.mkdir(parents=True)
        self.addCleanup(self.tmp.cleanup)
        self.addCleanup(os.chdir, self.old)

    def test_no_acceptance_delivery_section_writes_no_file(self):
        Path('IMPLEMENTATION_NOTES.md').write_text(
            '# Notes\n\n| AT-1 | live works | live check |\n')
        self.assertEqual(mod.delivery_summary({}), 0)
        self.assertFalse((mod.STATE / 'delivery-summary.tsv').exists())

    def test_missing_notes_file_writes_no_file(self):
        self.assertEqual(mod.delivery_summary({}), 0)
        self.assertFalse((mod.STATE / 'delivery-summary.tsv').exists())

    def test_a_real_acceptance_delivery_section_still_writes_rows(self):
        Path('IMPLEMENTATION_NOTES.md').write_text(
            '## Acceptance delivery\n| ID | Status | Changed code | Observed targeted verification |\n'
            '|---|---|---|---|\n| AC-1 | IMPLEMENTED | app/main.sh | test passed |\n')
        self.assertEqual(mod.delivery_summary({}), 0)
        self.assertIn('AC-1', (mod.STATE / 'delivery-summary.tsv').read_text())

    def test_a_prior_stale_summary_is_removed_once_the_section_disappears(self):
        # Once a run enters IMPLEMENT and the section is not (yet) written,
        # a leftover summary from an earlier state must not be read as
        # current delivery evidence.
        (mod.STATE / 'delivery-summary.tsv').write_text('ID\tStatus\tEvidence\nAC-1\tIMPLEMENTED\tstale\n')
        Path('IMPLEMENTATION_NOTES.md').write_text('# Notes\n')
        self.assertEqual(mod.delivery_summary({}), 0)
        self.assertFalse((mod.STATE / 'delivery-summary.tsv').exists())


if __name__ == '__main__':
    if len(sys.argv) > 1 and sys.argv[1] in ('--fixture', '--review'):
        fixture(sys.argv[2], 'seed' if sys.argv[1] == '--fixture' else 'review')
    else:
        unittest.main()
