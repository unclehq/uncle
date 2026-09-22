#!/usr/bin/env python3
"""Create conservative implementation handoff artifacts without an LLM retry.

An implementation turn that edits code but forgets its Markdown handoff must
not be repeated merely to obtain prose.  These records describe only durable
driver evidence and deliberately leave test/requirement coverage unresolved.
"""
import argparse
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
    lines = ['# Implementation notes', '', '## Driver-owned handoff', '',
             'The implementation stage did not provide its required handoff. This fallback records durable working-tree evidence only.', '',
             '## Changed files observed', '']
    lines += [f'- `{name}`' for name in files]
    lines += ['', '## Requirement and test traceability', '',
              '- Not established: the missing agent handoff did not cite plan rows or check-specific evidence.', '',
              '## Unresolved blockers', '',
              '- Review the changed files and replace this fallback with a complete implementation record before relying on it for release.']
    return '\n'.join(lines) + '\n'


def tests(kind):
    title = '# Change test report' if kind == 'change' else '# Automated test report'
    return (title + '\n\n## Driver-owned incomplete test evidence\n\n'
            'The implementation stage omitted its required test handoff. No command result or requirement coverage is inferred by this fallback.\n\n'
            '## Coverage gaps\n\n'
            '- All changed behavior requires review against the approved plan and fresh observed test evidence.\n\n'
            '## Next action\n\n'
            '- Run the approved verification commands and replace this incomplete record with their actual results.\n')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--project', default='.')
    parser.add_argument('--kind', choices=('change', 'application'), required=True)
    parser.add_argument('--missing-only', action='store_true')
    args = parser.parse_args()
    project = Path(args.project).resolve(); docs = project / '.uncle/docs'; docs.mkdir(parents=True, exist_ok=True)
    test_name = 'CHANGE_TEST_REPORT.md' if args.kind == 'change' else 'AUTOMATED_TEST_REPORT.md'
    outputs = ((docs / 'IMPLEMENTATION_NOTES.md', notes(changed_files(project))),
               (docs / test_name, tests(args.kind)))
    for path, content in outputs:
        if not args.missing_only or not path.is_file() or path.stat().st_size == 0:
            path.write_text(content, encoding='utf-8')


if __name__ == '__main__':
    main()
