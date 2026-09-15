"""Bounded checklist inputs; base generation never inspects in-progress code."""
import hashlib
import importlib.util
from pathlib import Path
import re
import sys


def render(project, state, stage):
    project, state = Path(project).resolve(), Path(state).resolve()
    base = stage == 'manual-checklist-base'
    names = ['CHANGE_SPEC.md', 'CHANGE_PLAN.md'] if base else [
        'REQUIREMENTS.md', 'UPDATED_PROJECT_PLAN.md', 'CHANGE_SPEC.md', 'CHANGE_PLAN.md']
    lines = ['\n## Driver checklist evidence packet',
             'This is input evidence, not a PASS declaration. Keep all required criteria.',
             'Base mode: frozen specification only.' if base else
             'Use current driver evidence to identify gaps; prior reports are not fresh test results.']
    for name in names:
        path = project / name
        if not path.is_file() or not path.resolve().is_relative_to(project):
            continue
        data = path.read_bytes()
        lines += [f'\n{name}: SHA-256 {hashlib.sha256(data).hexdigest()}']
        used = 0
        for number, line in enumerate(data[:262144].decode('utf-8', errors='replace').splitlines(), 1):
            if re.search(r'\b(?:AC|REQ|FR|MC|AR)-\d+\b', line):
                lines.append(f'{name}:{number}: {line[:400]}')
                used += len(line[:400])
                if used >= 3000:
                    lines.append('[Criterion excerpt truncated; read remaining criteria directly.]')
                    break
    if not base:
        spec = importlib.util.spec_from_file_location('review_context', Path(__file__).with_name('test-review-context.py'))
        context = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(context)
        lines.append(context.render(project, state))
        for path in (state / 'MANUAL_CHECKLIST.base.md', project / 'IMPLEMENTATION_NOTES.md',
                     project / 'TEST_REVIEW.md', state / 'change.diff'):
            if path.is_file() and path.resolve().is_relative_to(project):
                data = path.read_bytes()
                lines.append(f'{path}: {len(data)} bytes; SHA-256 {hashlib.sha256(data).hexdigest()}; read relevant sections directly.')
    return '\n'.join(lines) + '\n'


if __name__ == '__main__':
    print(render(*sys.argv[1:4]), end='')
