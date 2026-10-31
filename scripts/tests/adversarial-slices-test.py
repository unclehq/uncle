#!/usr/bin/env python3
"""Hermetic review panels: unchanged public artifacts, bounded private slices."""
import collections
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
LENSES = ('requirements', 'regression', 'security', 'testability')
KIND = 'adversarial-review-worker-packet'

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


if __name__ == '__main__':
    unittest.main()
