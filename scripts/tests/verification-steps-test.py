#!/usr/bin/env python3
"""Only a step that runs the suites and nothing else is skipped; the driver runs those commands itself."""
import importlib.util
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('verification_steps', ROOT / 'scripts/lib/verification_steps.py')
vs = importlib.util.module_from_spec(spec)
spec.loader.exec_module(vs)

# The four steps of issue 117's plan, verbatim in shape: the last one cost 991 s of a 1,923 s implementation.
ISSUE_117 = [
    'Domain module and tests (redaction, attribution, eligibility, publish, fallback, bundle) — Owns: `scripts/lib/bug_report.py`, `scripts/tests/bug-report-test.py`, `.gitignore` (verify `.uncle/workflow`) — Depends on: 0.',
    'TUI glue: `/report` commands, pending state, panel hint, plus TUI regression tests — Owns: `uncle_tui.py`, `scripts/tests/bug-report-tui-test.py` — Depends on: 1.',
    'Prompt and docs mention — Owns: `prompts/triage.md`, `README.md` — Depends on: 2. Includes an assertion that the prompt diff is exactly the single line.',
    'Verification only: run `bash scripts/run-shell-tests.sh` and `bash scripts/run-python-tests.sh`; failures are routed back to the owning step — Owns: none — Depends on: 3.',
]


class Detector(unittest.TestCase):
    def test_issue_117_skips_only_its_verification_step(self):
        self.assertEqual([vs.is_verification_only(step) for step in ISSUE_117], [False, False, False, True])
        self.assertEqual(vs.skip_set(ISSUE_117), [4])

    def test_phrasings_of_a_pure_verification_step(self):
        for step in ('Verification: run the full test suite — Owns: none',
                     'Run `bash scripts/run-python-tests.sh` — Owns: none — Depends on: 2',
                     'Final verification of all suites. — Owns: n/a',
                     'Verify: execute the regression block — Owns: —',
                     '1. Verification only: run both runners — Owns: none'):
            self.assertTrue(vs.is_verification_only(step), step)

    def test_a_step_that_owns_a_file_is_never_skipped(self):
        self.assertFalse(vs.is_verification_only('Verification only: run the tests — Owns: `scripts/tests/new-test.py`'))
        self.assertFalse(vs.is_verification_only('Run the tests and record results — Owns: `docs/RESULTS.md`'))

    def test_a_step_that_changes_anything_is_never_skipped(self):
        for step in ('Verification: add a regression test then run the suite — Owns: none',
                     'Run the tests, fix any failures — Owns: none',
                     'Verify and update the changelog — Owns: none',
                     'Run the migration — Owns: none'):
            self.assertFalse(vs.is_verification_only(step), step)

    def test_steps_that_do_not_open_with_verification_are_not_skipped(self):
        self.assertFalse(vs.is_verification_only('Refactor the loader — Owns: none'))
        self.assertFalse(vs.is_verification_only('Reconcile the notes with the tests that were run — Owns: none'))

    def test_a_step_with_no_ownership_marker_is_not_skipped(self):
        self.assertFalse(vs.is_verification_only('Verification only: run the tests'))

    def test_the_cli_reads_a_file_or_stdin(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / 'steps.txt'
            path.write_text('\n'.join(ISSUE_117) + '\n')
            for args, stdin in ((['skip-set', str(path)], None), (['skip-set', '-'], '\n'.join(ISSUE_117))):
                done = subprocess.run(['python3', str(ROOT / 'scripts/lib/verification_steps.py'), *args], input=stdin,
                                      capture_output=True, text=True, check=True)
                self.assertEqual(done.stdout.strip(), '4')


if __name__ == '__main__':
    unittest.main()
