#!/usr/bin/env python3
"""The implementation handoff fallback must never end a run over a report the agent really wrote.

A change-test-report whose fifth command read BLOCKED-SETUP was kept by --missing-only (its schema and kind were right), failed the
validation at the end of the script, and ended the run with `command result 5 has invalid status`."""
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
FALLBACK = ROOT / 'scripts/lib/implementation_report_fallback.py'
DOCS = '.uncle/workflow/documents'


class Fallback(unittest.TestCase):
    def project(self, fifth_status):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        project = Path(directory.name)
        subprocess.run(['git', 'init', '-q', str(project)], check=True)
        (project / 'a.txt').write_text('x')
        (project / DOCS).mkdir(parents=True)
        commands = [{'command': 'cmd %d' % i, 'status': 'PASS', 'output': 'ok', 'requirements': ['AC-1']} for i in range(1, 5)]
        commands.append({'command': 'npx http-server . -p 4173', 'status': fifth_status, 'output': 'no browser here', 'requirements': ['AC-5']})
        (project / DOCS / 'CHANGE_TEST_REPORT.json').write_text(json.dumps(
            {'schema': 'uncle.artifact/v1', 'kind': 'change-test-report', 'commands': commands, 'coverage_gaps': [], 'next_action': 'None.'}))
        (project / DOCS / 'IMPLEMENTATION_NOTES.json').write_text(json.dumps(
            {'schema': 'uncle.artifact/v1', 'kind': 'implementation-notes', 'deviations': [], 'unresolved_concerns': [],
             'changed_files': [{'path': 'a.txt', 'purpose': 'x', 'plan_step': '1', 'behavior_or_invariant': 'x'}]}))
        return project

    def run_fallback(self, project):
        return subprocess.run([sys.executable, '-B', str(FALLBACK), '--project', str(project), '--kind', 'change', '--missing-only'],
                              capture_output=True, text=True, timeout=120)

    def report(self, project):
        return json.loads((project / DOCS / 'CHANGE_TEST_REPORT.json').read_text())

    def test_a_blocked_setup_status_keeps_the_real_report(self):
        project = self.project('BLOCKED-SETUP')
        result = self.run_fallback(project)
        self.assertEqual(result.returncode, 0, result.stderr)
        commands = self.report(project)['commands']
        self.assertEqual(len(commands), 5)                                   # the agent's evidence is kept, not replaced
        self.assertEqual((commands[4]['status'], commands[4]['status_detail']), ('BLOCKED', 'BLOCKED-SETUP'))
        self.assertFalse((project / DOCS / 'CHANGE_TEST_REPORT.json.invalid').exists())

    def test_an_unclear_status_is_set_aside_and_the_run_goes_on(self):
        for word in ('PARTIAL', 'PASS WITH WARNINGS'):
            project = self.project(word)
            result = self.run_fallback(project)
            self.assertEqual(result.returncode, 0, word + ': ' + result.stderr)
            commands = self.report(project)['commands']
            self.assertEqual([c['status'] for c in commands], ['NOT RUN'], word)      # conservative: never a pass
            kept = json.loads((project / DOCS / 'CHANGE_TEST_REPORT.json.invalid').read_text())
            self.assertEqual(len(kept['commands']), 5, word)                            # the original is not lost
            self.assertIn('kept it at', result.stderr)

    def test_a_valid_report_is_left_as_it_is(self):
        project = self.project('PASS')
        result = self.run_fallback(project)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual([c['status'] for c in self.report(project)['commands']], ['PASS'] * 5)
        self.assertFalse((project / DOCS / 'CHANGE_TEST_REPORT.json.invalid').exists())

    def test_a_missing_report_still_gets_the_conservative_record(self):
        project = self.project('PASS')
        (project / DOCS / 'CHANGE_TEST_REPORT.json').unlink()
        self.assertEqual(self.run_fallback(project).returncode, 0)
        self.assertEqual([c['status'] for c in self.report(project)['commands']], ['NOT RUN'])


if __name__ == '__main__':
    unittest.main()
