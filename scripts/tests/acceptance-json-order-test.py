#!/usr/bin/env python3
import json
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

class AcceptanceJsonOrder(unittest.TestCase):
    def test_json_with_heading_like_narrative_renders_one_gate(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / 'TEST_REVIEW.md'
            path.write_text(json.dumps({'schema':'uncle.artifact/v1','kind':'acceptance-report',
                'narrative':'Summary only; never a gate.',
                'rows':[{'id':'RESULTS','required':True,'status':'PASS','evidence':'driver'}]}))
            subprocess.run(['python3', str(ROOT/'scripts/lib/acceptance_context.py'), str(path), temp], check=True)
            self.assertEqual(path.read_text().count('## Acceptance gate'), 1)

    def test_embedded_gate_in_json_narrative_is_not_rendered_twice(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / 'TEST_REVIEW.md'
            path.write_text(json.dumps({'schema':'uncle.artifact/v1','kind':'acceptance-report',
                'narrative':'## Summary\ntext\n\n## Acceptance gate\n\n| stale | table |',
                'rows':[{'id':'RESULTS','required':True,'status':'PASS','evidence':'driver'}]}))
            subprocess.run(['python3', str(ROOT/'scripts/lib/acceptance_context.py'), str(path), temp], check=True)
            rendered = path.read_text()
            self.assertEqual(rendered.count('## Acceptance gate'), 1)
            self.assertNotIn('stale | table', rendered)


class IngestionIsolationAndPrecedence(unittest.TestCase):
    GATE = ROOT / 'scripts/lib/acceptance-gate.sh'
    REPORT = {'schema': 'uncle.artifact/v1', 'kind': 'acceptance-report', 'narrative': '## Summary\n\nTR-1 fails.',
              'rows': [{'id': 'COVERAGE', 'required': True, 'status': 'PASS', 'evidence': 'ok'},
                       {'id': 'RESULTS', 'required': True, 'status': 'FAIL', 'evidence': 'TR-1 fails'}]}
    PLACEHOLDER = {'schema': 'uncle.artifact/v1', 'kind': 'acceptance-report', 'narrative': 'Summary only; never a gate.',
                   'rows': [{'id': 'RESULTS', 'required': True, 'status': 'PASS', 'evidence': 'driver'}]}

    def test_the_project_argument_is_where_the_canonical_file_goes_not_the_working_directory(self):
        # A test run inside a live worktree overwrote that run's canonical TEST_REVIEW.json because this argument was ignored.
        with tempfile.TemporaryDirectory() as cwd, tempfile.TemporaryDirectory() as project:
            view = Path(project) / 'TEST_REVIEW.md'
            view.write_text(json.dumps(self.REPORT))
            subprocess.run(['python3', str(ROOT / 'scripts/lib/acceptance_context.py'), str(view), project], cwd=cwd, check=True)
            self.assertFalse((Path(cwd) / '.uncle').exists(), 'the working directory was written to')
            self.assertTrue((Path(project) / '.uncle/workflow/documents/TEST_REVIEW.json').is_file())

    def gate(self, view_text, stale):
        """Run the real ensure/transition code over a project whose canonical review is stale; returns (states, canonical rows)."""
        with tempfile.TemporaryDirectory() as project:
            root = Path(project)
            (root / '.uncle/docs').mkdir(parents=True)
            (root / '.uncle/workflow/documents').mkdir(parents=True)
            canonical = root / '.uncle/workflow/documents/TEST_REVIEW.json'
            if stale:
                canonical.write_text(json.dumps(self.PLACEHOLDER))
            (root / '.uncle/docs/TEST_REVIEW.md').write_text(view_text)
            script = ('ROOT="%s"; STATE_DIR=.uncle/workflow; set_state() { echo "STATE:$1"; }; supervision_validation_failed() { :; }; '
                      'acceptance_problem() { :; }; . "$ROOT/scripts/lib/acceptance-gate.sh"; '
                      "acceptance_transition .uncle/docs/TEST_REVIEW.md CHECKLIST 'COVERAGE RESULTS' IMPLEMENT" % ROOT)
            done = subprocess.run(['bash', '-c', script], cwd=project, capture_output=True, text=True)
            states = [line for line in done.stdout.splitlines() if line.startswith('STATE:')]
            rows = [r['status'] for r in json.loads(canonical.read_text())['rows']] if canonical.is_file() else None
            return states, rows, (root / '.uncle/workflow/test-review-format-retry.md').is_file()

    def test_a_reviewers_raw_json_replaces_a_stale_canonical_review(self):
        states, rows, _ = self.gate(json.dumps(self.REPORT), stale=True)
        self.assertEqual(rows, ['PASS', 'FAIL'], 'the stale PASS was kept instead of the reviewer\'s review')
        self.assertEqual(states, ['STATE:IMPLEMENT'], 'a FAIL finding must route to repair')

    def test_a_reviewers_raw_json_is_ingested_when_there_is_no_canonical_review(self):
        states, rows, _ = self.gate(json.dumps(self.REPORT), stale=False)
        self.assertEqual((states, rows), (['STATE:IMPLEMENT'], ['PASS', 'FAIL']))

    def test_raw_json_that_does_not_ingest_drops_the_stale_review_and_asks_again(self):
        states, rows, retry = self.gate('{"schema": "uncle.artifact/v1", "kind": "acceptance-report", "rows": [', stale=True)
        self.assertIsNone(rows, 'the stale canonical review was left to decide the gate')
        self.assertTrue(retry)
        self.assertEqual(states, ['STATE:TEST_REVIEW'])


if __name__ == '__main__': unittest.main()
