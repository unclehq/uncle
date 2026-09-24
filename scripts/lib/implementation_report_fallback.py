#!/usr/bin/env python3
"""Create conservative JSON-first implementation handoffs without an LLM retry."""
import argparse
import json
import subprocess
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
    outputs = ((canonical_notes, notes(changed_files(project))),
               (canonical_tests, tests(args.kind)))
    for path, content in outputs:
        if not args.missing_only or not path.is_file() or path.stat().st_size == 0:
            path.write_text(json.dumps(content) + '\n', encoding='utf-8')
    root = Path(__file__).resolve().parent
    subprocess.run(['python3', str(root / 'implementation_notes.py'), 'validate', str(project),
                    '.uncle/workflow/documents/IMPLEMENTATION_NOTES.json', '--require-json'], check=True)
    subprocess.run(['python3', str(root / 'implementation_notes.py'), 'render', str(project),
                    '.uncle/docs/IMPLEMENTATION_NOTES.md'], check=True)
    subprocess.run(['python3', str(root / 'test_report.py'), 'validate', str(project), args.kind,
                    '.uncle/workflow/documents/' + test_name.replace('.md', '.json')], check=True)


if __name__ == '__main__':
    main()
