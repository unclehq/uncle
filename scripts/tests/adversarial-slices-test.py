#!/usr/bin/env python3
"""Hermetic review panels: unchanged public artifacts, bounded private slices."""
import collections
import importlib.util
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
LENSES = ('requirements', 'regression', 'security', 'testability')
KIND = 'adversarial-review-worker-packet'
sys.path.insert(0, str(ROOT / 'scripts/lib'))
import http_agent
import self_hosted

STUB = r'''
import fcntl, json, os, pathlib, re, sys, time
prompt, output, name = sys.argv[1:4]
root = pathlib.Path(os.environ['STATE_DIR'])
match = re.fullmatch(r'adversarial-review-worker-(requirements|regression|security|testability)(?:-slice-(\d+))?(-retry)?', name)
assert match, name
lens, number, retry = match.groups()
number = int(number or 0)
with (root / 'calls').open('a') as stream:
    fcntl.flock(stream, fcntl.LOCK_EX)
    stream.write(json.dumps({'name': name, 'prompt': pathlib.Path(prompt).read_text(),
                             'marker': os.environ.get('UNCLE_ADVERSARIAL_SLICE'),
                             'output': output}) + '\n')
mode = os.environ['FIXTURE_MODE']
if mode == 'fanout':
    deadline = time.monotonic() + 12
    while len((root / 'calls').read_text().splitlines()) < 12 and time.monotonic() < deadline:
        time.sleep(.02)
    assert len((root / 'calls').read_text().splitlines()) == 12, 'slices did not run concurrently'
target = lens == 'regression' and number == 2
if mode in ('retry', 'failed', 'overlap') and target:
    if retry:
        (root / 'retried').touch()
    if not retry or mode == 'failed':
        pathlib.Path(output).write_text('invalid packet')
        sys.exit(1)
if mode == 'overlap' and lens == 'testability' and number == 1:
    deadline = time.monotonic() + 12
    while not (root / 'retried').exists() and time.monotonic() < deadline:
        time.sleep(.02)
    assert (root / 'retried').exists(), 'retry waited for unrelated slice'
    assert not (root / 'documents/ADVERSARIAL_REVIEW.json').exists(), 'partial publication'
if mode == 'reverse':
    time.sleep((4 - min(number, 4)) * .04)
def finding(n):
    return {'id': 'AR-%03d' % n, 'summary': lens + ' issue ' + str(n),
            'evidence': 'REQ-' + str(n), 'severity': 'High' if n == 1 else 'Medium'}
items = [] if mode == 'empty' else [finding(1), finding(2)]
if number:
    items = [] if mode == 'empty' else [finding(2 if number == 3 else 1)]
    for item in items:
        item['id'] = 'AR-001'  # Independent slices naturally reuse local IDs.
pathlib.Path(output).write_text(json.dumps({'schema': 'uncle.artifact/v1',
    'kind': 'adversarial-review-worker-packet', 'findings': items}))
'''

HARNESS = r'''
set -euo pipefail
. "$FIXTURE_FUNCTIONS"
ensure_project_plan_json() { return 0; }
stage_uses_self_hosted() { [[ "$FIXTURE_RUNNER" == self-hosted ]]; }
uncle_stage_runner() { printf '%s\n' "$FIXTURE_RUNNER"; }
run_codex_review() { python3 "$FIXTURE_STUB" "$@"; }
run_codex() { python3 "$FIXTURE_STUB" "$@"; }
python3() {
    if [[ "${2:-}" == "$ROOT/scripts/lib/plan_model.py" && "${3:-}" == view ]]; then
        printf '{"sections":[{"id":"VIEW-ROW-1","text":"Canonical plan view"}]}' > "$5"
    else
        command python3 "$@"
    fi
}
run_adversarial_review_panel
'''


class PanelTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name)
        self.number = 0
        (self.path / 'stub.py').write_text(STUB)

    def run_panel(self, runner='self-hosted', driver='stagegate', config='', env=None, mode='normal'):
        self.number += 1
        project = self.path / str(self.number)
        state = project / '.uncle/workflow'
        docs = state / 'documents'
        docs.mkdir(parents=True)
        (project / '.uncle/docs').mkdir()
        (state / 'logs').mkdir()
        for name, kind in (('PROJECT_PLAN', 'project-plan'), ('CHANGE_PLAN', 'change-plan')):
            (docs / (name + '.json')).write_text(json.dumps({'schema': 'uncle.artifact/v1', 'kind': kind,
                'sections': [{'id': 'S-%02d' % i, 'title': 'Section %d' % i,
                              'content': 'Observable behavior REQ-%d.' % i} for i in range(1, 9)]}))
        for name in ('REQUIREMENTS_INTERPRETATION', 'CHANGE_SPEC'):
            (docs / (name + '.json')).write_text(json.dumps({'schema': 'uncle.artifact/v1',
                'kind': name.lower().replace('_', '-'), 'requirements': ['REQ-1', 'REQ-2']}))
        config_path = project / '.uncle/config'
        config_path.write_text(config)
        source = (ROOT / 'scripts' / (driver + '.sh')).read_text()
        functions = re.findall(r'^run_adversarial_review_[\w]+\(\) \{\n.*?^\}', source, re.M | re.S)
        self.assertTrue(functions)
        function_path = project / 'functions.sh'
        function_path.write_text('\n'.join(functions) + '\n')
        clean_env = {k: v for k, v in os.environ.items() if not k.startswith(('WORKFLOW_', 'UNCLE_', 'FIXTURE_'))}
        clean_env.update(ROOT=str(ROOT), PROJECT_ROOT=str(project), STATE_DIR=str(state),
                         LOG_DIR=str(state / 'logs'), UNCLE_CONFIG=str(config_path),
                         FIXTURE_FUNCTIONS=str(function_path), FIXTURE_STUB=str(self.path / 'stub.py'),
                         FIXTURE_RUNNER=runner, FIXTURE_MODE=mode, CODEX_EFFORT_REVIEW='high')
        clean_env.update(env or {})
        result = subprocess.run(['bash', '-c', HARNESS], cwd=project, env=clean_env,
                                text=True, capture_output=True, timeout=40)
        calls = [json.loads(line) for line in (state / 'calls').read_text().splitlines()] if (state / 'calls').exists() else []
        return result, state, calls

    def assert_ok(self, result, state):
        logs = '\n'.join(p.read_text() for p in (state / 'logs').glob('*.log'))
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr + logs)

    def assert_document(self, state):
        rows = []
        for index, lens in enumerate(LENSES):
            for n in (1, 2):
                identifier = 'AR-%03d' % (index * 2 + n)
                rows += [f'## {identifier}: {lens} issue {n}', '',
                         '- Severity: ' + ('HIGH' if n == 1 else 'MEDIUM'),
                         f'- References: REQ-{n}', f'- Failure: {lens} issue {n}',
                         '- Fix: Address in the plan.', '- Verify: Re-run the check.', '']
        rows += ['## Overall assessment', '', 'Review findings require disposition.', '']
        self.assertEqual((state.parent / 'docs/ADVERSARIAL_REVIEW.md').read_text(), '\n'.join(rows))

    def test_claude_codex_default_packets_and_document_unchanged(self):
        for driver in ('stagegate', 'change-workflow'):
            for runner in ('claude', 'codex'):
                with self.subTest(driver=driver, runner=runner):
                    result, state, calls = self.run_panel(runner, driver)
                    self.assert_ok(result, state)
                    self.assertEqual(sorted(c['name'] for c in calls),
                                     sorted('adversarial-review-worker-' + lens for lens in LENSES))
                    self.assertTrue(all(c['marker'] is None for c in calls))
                    self.assert_document(state)

    def test_small_default_fans_out_both_drivers(self):
        for driver in ('stagegate', 'change-workflow'):
            with self.subTest(driver=driver):
                result, state, calls = self.run_panel(driver=driver)
                self.assert_ok(result, state)
                self.assertEqual(len(calls), 16)
                self.assertTrue(all('-slice-' in c['name'] and c['marker'] == '1' for c in calls))
                self.assert_document(state)

    def test_slice_requests_are_concurrent(self):
        for driver in ('stagegate', 'change-workflow'):
            with self.subTest(driver=driver):
                result, state, calls = self.run_panel(driver=driver, config='adversarial-review.slices 3\n', mode='fanout')
                self.assert_ok(result, state)
                self.assertEqual(len(calls), 12)
                self.assert_document(state)

    def test_three_slices_merge_to_identical_public_artifacts(self):
        for driver in ('stagegate', 'change-workflow'):
            with self.subTest(driver=driver):
                before, original, _ = self.run_panel('claude', driver)
                result, state, calls = self.run_panel(driver=driver, config='adversarial-review.slices 3\n')
                self.assert_ok(before, original)
                self.assert_ok(result, state)
                self.assertEqual(len(calls), 12)
                self.assert_document(state)
                for artifact in ('ADVERSARIAL_REVIEW.json', 'ADVERSARIAL_REVIEW_WORKERS.json'):
                    self.assertEqual((state / 'documents' / artifact).read_bytes(),
                                     (original / 'documents' / artifact).read_bytes())
                for lens in LENSES:
                    packet = json.loads((state / 'adversarial-review-panel' / (lens + '.json')).read_text())
                    self.assertEqual(packet['kind'], KIND)
                    self.assertEqual(len(packet['findings']), 2)

    def test_off_and_large_keep_legacy_calls(self):
        for config in ('adversarial-review.slices off\n', 'adversarial-review.slices 1\n',
                       'adversarial-review.granularity large\n'):
            with self.subTest(config=config):
                result, state, calls = self.run_panel(config=config)
                self.assert_ok(result, state)
                self.assertEqual(len(calls), 4)
                self.assertTrue(all('-slice-' not in c['name'] for c in calls))
                self.assert_document(state)

    def test_slice_env_overrides_config(self):
        for env in ({'WORKFLOW_ADVERSARIAL_REVIEW_SLICES': '3'},
                    {'WORKFLOW_SELF_HOSTED_SLICES_ADVERSARIAL_REVIEW': '3'}):
            with self.subTest(env=env):
                result, state, calls = self.run_panel(config='adversarial-review.slices off\n', env=env)
                self.assert_ok(result, state)
                self.assertEqual(len(calls), 12)

    def test_failed_slice_retried_once_without_whole_lens(self):
        for driver in ('stagegate', 'change-workflow'):
            with self.subTest(driver=driver):
                result, state, calls = self.run_panel(driver=driver, config='adversarial-review.slices 3\n', mode='retry')
                self.assert_ok(result, state)
                counts = collections.Counter(c['name'] for c in calls)
                self.assertEqual(len(calls), 13)
                self.assertEqual(counts['adversarial-review-worker-regression-slice-2-retry'], 1)
                self.assertEqual(set(counts.values()), {1})
                self.assertTrue(all('-slice-' in name for name in counts))
                self.assert_document(state)

    def test_retry_overlaps_slow_sibling(self):
        result, state, calls = self.run_panel(config='adversarial-review.slices 3\n', mode='overlap')
        self.assert_ok(result, state)
        self.assertEqual(len(calls), 13)
        self.assert_document(state)

    def test_persistent_failure_cannot_publish_partial_review(self):
        for driver in ('stagegate', 'change-workflow'):
            with self.subTest(driver=driver):
                result, state, calls = self.run_panel(driver=driver, config='adversarial-review.slices 3\n', mode='failed')
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual(len(calls), 13)
                for artifact in ('ADVERSARIAL_REVIEW.json', 'ADVERSARIAL_REVIEW_WORKERS.json'):
                    self.assertFalse((state / 'documents' / artifact).exists())
                self.assertFalse((state.parent / 'docs/ADVERSARIAL_REVIEW.md').exists())

    def test_completion_order_cannot_change_ids(self):
        result, state, calls = self.run_panel(config='adversarial-review.slices 3\n', mode='reverse')
        self.assert_ok(result, state)
        self.assertEqual(len(calls), 12)
        self.assert_document(state)

    def test_empty_slices_preserve_empty_document(self):
        result, state, calls = self.run_panel(config='adversarial-review.slices 3\n', mode='empty')
        self.assert_ok(result, state)
        self.assertEqual(len(calls), 12)
        self.assertEqual((state.parent / 'docs/ADVERSARIAL_REVIEW.md').read_text(),
                         '## Overall assessment\n\nNo findings.\n')

    def test_plan_view_opt_in_remains_the_slice_input(self):
        result, state, calls = self.run_panel(config='adversarial-review.slices 3\n',
                                               env={'WORKFLOW_AGENT_PLAN_VIEW': '1'})
        self.assert_ok(result, state)
        self.assertEqual(len(calls), 12)
        self.assertTrue(all('VIEW-ROW-1' in call['prompt'] for call in calls))


class SchemaTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        env = patch.dict(os.environ, {'UNCLE_CONFIG': str(self.root / 'config'),
                                     'UNCLE_PROJECT_ROOT': str(self.root)}, clear=True)
        env.start()
        self.addCleanup(env.stop)
        self.values = {'base_url': 'http://unused.invalid/v1', 'api_key': 'fixture', 'model': 'fixture'}
        self.packet = {'schema': 'uncle.artifact/v1', 'kind': KIND, 'findings': []}
        self.schema = self_hosted.REVIEWER_SCHEMAS[KIND]

    def run_review(self):
        return http_agent.run_agent(self.values, 'All review inputs are inline.', http_agent.Policy(self.root),
                                    32768, turns=3, final_schema=self.schema,
                                    final_name='adversarial_review_worker_packet')

    def test_slice_starts_with_one_constrained_answer_and_no_tool_draft(self):
        with patch.dict(os.environ, {'UNCLE_ADVERSARIAL_SLICE': '1'}), \
                patch.object(http_agent, 'chat', side_effect=AssertionError('slice opened an unbounded tool loop')), \
                patch.object(http_agent, 'constrained_completion',
                             return_value=(json.dumps(self.packet), 'stop', {}, 'json_schema')) as constrained:
            text, requests = self.run_review()
        self.assertEqual(json.loads(text), self.packet)
        self.assertEqual((requests, constrained.call_count), (1, 1))
        self.assertEqual(constrained.call_args.kwargs.get('skip', ()), ())

    def test_unsliced_review_keeps_existing_tool_path(self):
        reply = {'choices': [{'message': {'role': 'assistant', 'content': json.dumps(self.packet)},
                              'finish_reason': 'stop'}]}
        with patch.object(http_agent, 'chat', return_value=reply) as chat, \
                patch.object(http_agent, 'constrained_completion') as constrained:
            text, requests = self.run_review()
        self.assertEqual(json.loads(text), self.packet)
        self.assertEqual((requests, chat.call_count, constrained.call_count), (1, 1, 0))


class MergeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        (self.root / 'slices').mkdir()
        self.env = {k: v for k, v in os.environ.items() if not k.startswith(('WORKFLOW_', 'UNCLE_'))}
        self.env['UNCLE_CONFIG'] = str(self.root / 'config')

    def command(self, *args):
        return subprocess.run([sys.executable, '-B', str(ROOT / 'scripts/lib/adversarial_slices.py'), *map(str, args)],
                              env=self.env, capture_output=True, text=True, timeout=10)

    def packet(self, lens, number, findings, kind=KIND):
        path = self.root / 'slices' / f'{lens}-{number}.json'
        path.write_text(json.dumps({'schema': 'uncle.artifact/v1', 'kind': kind, 'findings': findings}))
        return path

    def finding(self, summary, evidence='REQ-1', severity='Medium'):
        return {'id': 'AR-001', 'summary': summary, 'evidence': evidence, 'severity': severity}

    def test_dedupe_combines_evidence_and_keeps_strongest_severity(self):
        for lens in LENSES:
            self.packet(lens, 1, [self.finding('Missing input validation.', 'REQ-1', 'Low')])
            self.packet(lens, 2, [self.finding('missing INPUT validation!', 'REQ-2', 'Critical')])
            self.packet(lens, 3, [self.finding('Missing rollback.', 'STEP-2')])
        result = self.command('merge', self.root, 3)
        self.assertEqual(result.returncode, 0, result.stderr)
        for lens in LENSES:
            findings = json.loads((self.root / (lens + '.json')).read_text())['findings']
            self.assertEqual(len(findings), 2)
            self.assertEqual([f['id'] for f in findings], ['AR-001', 'AR-002'])
            self.assertEqual(findings[0]['severity'].lower(), 'critical')
            self.assertIn('REQ-1', findings[0]['evidence'])
            self.assertIn('REQ-2', findings[0]['evidence'])
            self.assertEqual(findings[1]['summary'], 'Missing rollback.')

    def test_different_observations_with_same_local_id_are_not_fused(self):
        for lens in LENSES:
            self.packet(lens, 1, [self.finding('Lost save.'), self.finding('Missing cancel.')])
            self.packet(lens, 2, [])
        result = self.command('merge', self.root, 2)
        self.assertEqual(result.returncode, 0, result.stderr)
        for lens in LENSES:
            findings = json.loads((self.root / (lens + '.json')).read_text())['findings']
            self.assertEqual([f['summary'] for f in findings], ['Lost save.', 'Missing cancel.'])
            self.assertEqual(len({f['id'] for f in findings}), 2)

    def test_wrong_kind_and_blank_finding_are_rejected(self):
        for kind, finding in (('test-review-worker-packet', self.finding('A defect.')),
                              (KIND, self.finding('   '))):
            with self.subTest(kind=kind, finding=finding):
                path = self.packet('requirements', 1, [finding], kind)
                self.assertNotEqual(self.command('validate', path).returncode, 0)

    def test_missing_last_slice_cannot_publish_partial_lenses(self):
        for lens in LENSES:
            self.packet(lens, 1, [])
            if lens != 'testability':
                self.packet(lens, 2, [])
        result = self.command('merge', self.root, 2)
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(any((self.root / (lens + '.json')).exists() for lens in LENSES))


class TuiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        spec = importlib.util.spec_from_file_location('slice_tui', ROOT / 'uncle_tui.py')
        cls.tui = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.tui)

    def panel(self, sliced=False, active=False, candidates=False, mixed=False, lenses=LENSES, failed=False):
        app = self.tui.UncleTUI.__new__(self.tui.UncleTUI)
        records, live = [], {}
        for lens in lenses:
            for number in (range(1, 5) if sliced else (0,)):
                name = 'adversarial-review-worker-' + lens + (f'-slice-{number}' if number else '')
                for candidate in ((1, 2) if candidates else (0,)):
                    stage = name + (f'-candidate-{candidate}' if candidate else '')
                    if active or (mixed and lens == 'security' and number in (0, 4)):
                        live[stage] = 1000
                    else:
                        records.append({'stage': stage, 'started_at': 1000, 'ended_at': 1100,
                                        'elapsed_seconds': 100,
                                        'process_exit': 1 if failed and lens == 'security' and number in (0, 1) else 0,
                                        'total_tokens': 25 if sliced else 100})
        app.session_stats = {'records': records, 'active': live,
                             'live': {name: {'total_tokens': 25 if sliced else 100}
                                      for name in live} if mixed else {}}
        with patch.object(self.tui.time, 'time', return_value=1100):
            lines = app._session_panel_lines()
        return lines, app._panel_indicator_styles, app._panel_stage_styles

    def test_slices_keep_four_visible_lens_indicators(self):
        for active in (False, True):
            with self.subTest(active=active):
                self.assertEqual(self.panel(sliced=True, active=active), self.panel(active=active))

    def test_candidate_slices_keep_existing_lens_rows(self):
        for active in (False, True):
            with self.subTest(active=active):
                self.assertEqual(self.panel(sliced=True, active=active, candidates=True),
                                 self.panel(active=active, candidates=True))

    def test_lens_stays_active_until_last_slice_completes(self):
        self.assertEqual(self.panel(sliced=True, mixed=True), self.panel(mixed=True))

    def test_first_admitted_lens_keeps_existing_row(self):
        for active in (False, True):
            with self.subTest(active=active):
                self.assertEqual(self.panel(sliced=True, active=active, lenses=('security',)),
                                 self.panel(active=active, lenses=('security',)))

    def test_failed_slice_keeps_lens_failure_visible(self):
        for lenses in (LENSES, ('security',)):
            with self.subTest(lenses=lenses):
                self.assertEqual(self.panel(sliced=True, failed=True, lenses=lenses),
                                 self.panel(failed=True, lenses=lenses))

    def test_footer_keeps_existing_lens_name(self):
        def draw(stage, root):
            app = self.tui.UncleTUI.__new__(self.tui.UncleTUI)
            writes = []
            app.stdscr = SimpleNamespace(addnstr=lambda y, x, text, *args: writes.append((y, x, text)))
            app.state = 'running'
            app.status_stage = stage
            app.chat_composer = app.chat_error = ''
            app.chat_choices = []
            app.chat_focus = 'output'
            app._control_hint = lambda *_: 'Workflow controls'
            app._composer_cursor_cell = lambda *_: (0, 0)
            app._next_run_unattended = lambda: False
            app.test_execution_status = lambda: ''
            app._draw_file_picker = lambda *_: None
            with patch.object(self.tui, '_project_root', return_value=root):
                app._draw_chat_composer(1, 20, 240, 0, 238)
            return writes
        with tempfile.TemporaryDirectory() as root:
            original = draw('adversarial-review-worker-security', root)
            self.assertTrue(any('adversarial-review-worker-security' in text for _, _, text in original))
            self.assertEqual(draw('adversarial-review-worker-security-slice-2', root), original)


if __name__ == '__main__':
    unittest.main()
