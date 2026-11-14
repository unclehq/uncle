#!/usr/bin/env python3
"""Create conservative JSON-first implementation handoffs without an LLM retry."""
import argparse
import json
import subprocess
import sys
from pathlib import Path


def changed_files(project):
    result = subprocess.run(['git', 'status', '--porcelain'], cwd=project,
                            text=True, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    if result.returncode:
        return ['Git status unavailable; inspect the working tree directly.']
    entries = [line[3:] for line in result.stdout.splitlines() if line[3:] and not line[3:].startswith('.uncle/')]
    return entries or ['No non-workflow working-tree changes were recorded by this fallback.']


def notes(files):
    return {'schema': 'uncle.artifact/v1', 'kind': 'implementation-notes',
            # Driver-synthesized, not agent-authored: it can never carry an
            # acceptance-delivery table (there is no agent claim to report),
            # so implementation_complete() would otherwise retry or escalate
            # forever on a document that structurally can never pass. This
            # marker lets callers recognize that and stop instead.
            'driver_fallback': True,
            'changed_files': [{'path': name, 'purpose': 'Observed by driver fallback; implementation handoff was missing.',
                               'plan_step': '', 'behavior_or_invariant': ''} for name in files],
            'deviations': [],
            'unresolved_concerns': ['Requirement and test traceability were not established by the missing implementation handoff.']}


def tests(kind):
    return {'schema': 'uncle.artifact/v1',
            'kind': 'change-test-report' if kind == 'change' else 'automated-test-report',
            'commands': [{'command': 'Implementation handoff', 'status': 'NOT RUN',
                          'output': 'The implementation stage omitted its required test handoff; no command result is inferred.',
                          'requirements': []}],
            'coverage_gaps': ['All changed behavior requires review against the approved plan and fresh observed test evidence.'],
            'next_action': 'Run the approved verification commands and replace this incomplete record with actual results.'}


def usable(path, kind):
    """Whether an existing canonical artifact can be handed on as-is.

    --missing-only used to mean "present and non-empty", which an agent that
    invented its own shape satisfies: a change-test-report written as
    {"source": ..., "rows": [...]} is preserved, fails the validation below,
    and -- because errexit is suspended for the whole function in the driver's
    `run_stepwise_implementation ... || step_status=$?` call -- surfaces as a
    traceback that does not stop the stage. Treat an artifact that is not the
    kind its consumer validates as missing, and rewrite it conservatively.
    """
    try:
        payload = json.loads(path.read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return False
    return (isinstance(payload, dict)
            and payload.get('schema') == 'uncle.artifact/v1'
            and payload.get('kind') == kind)


def passes(command):
    """Whether a validation command succeeds. Silent: the caller decides what a failure means."""
    return subprocess.run(command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode == 0


def check(command, description):
    """Report a failed validation as an operator-readable stop, not a traceback."""
    if subprocess.run(command).returncode:
        raise SystemExit('Implementation handoff fallback: %s. The conservative '
                         'record this stage wrote did not validate; the run cannot '
                         'hand on an artifact its own schema rejects.' % description)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--project', default='.')
    parser.add_argument('--kind', choices=('change', 'application'), required=True)
    parser.add_argument('--missing-only', action='store_true')
    args = parser.parse_args()
    project = Path(args.project).resolve(); docs = project / '.uncle/docs'; docs.mkdir(parents=True, exist_ok=True)
    test_name = 'CHANGE_TEST_REPORT.md' if args.kind == 'change' else 'AUTOMATED_TEST_REPORT.md'
    canonical_notes = project / '.uncle/workflow/documents/IMPLEMENTATION_NOTES.json'
    canonical_notes.parent.mkdir(parents=True, exist_ok=True)
    canonical_tests = project / '.uncle/workflow/documents' / test_name.replace('.md', '.json')
    root = Path(__file__).resolve().parent
    notes_rel = '.uncle/workflow/documents/IMPLEMENTATION_NOTES.json'
    tests_rel = '.uncle/workflow/documents/' + test_name.replace('.md', '.json')
    # The same commands that judge the handoff at the end of this script. An existing report is kept only if it passes them: one
    # whose schema and kind are right but whose content the validator rejects (a status word it does not know) used to be
    # preserved, fail the check below, and end the run. Now it is set aside as .invalid and replaced by the conservative record.
    outputs = ((canonical_notes, notes(changed_files(project)),
                ['python3', str(root / 'implementation_notes.py'), 'validate', str(project), notes_rel, '--require-json']),
               (canonical_tests, tests(args.kind),
                ['python3', str(root / 'test_report.py'), 'validate', str(project), args.kind, tests_rel]))
    for path, content, validate in outputs:
        if args.missing_only and usable(path, content['kind']):
            if passes(validate):
                continue
            kept = path.with_name(path.name + '.invalid')
            kept.write_bytes(path.read_bytes())
            print('Implementation handoff fallback: %s did not validate; kept it at %s and recorded a conservative one.'
                  % (path.name, kept.relative_to(project)), file=sys.stderr)
        path.write_text(json.dumps(content) + '\n', encoding='utf-8')
    check(['python3', str(root / 'implementation_notes.py'), 'validate', str(project),
           '.uncle/workflow/documents/IMPLEMENTATION_NOTES.json', '--require-json'],
          'the implementation notes did not validate')
    check(['python3', str(root / 'implementation_notes.py'), 'render', str(project),
           '.uncle/docs/IMPLEMENTATION_NOTES.md'],
          'the implementation notes could not be rendered')
    check(['python3', str(root / 'test_report.py'), 'validate', str(project), args.kind,
           '.uncle/workflow/documents/' + test_name.replace('.md', '.json')],
          'the %s test report did not validate' % args.kind)


if __name__ == '__main__':
    main()
