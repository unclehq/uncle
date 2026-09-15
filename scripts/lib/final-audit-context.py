"""Focused final-audit evidence and format-only validation."""
import hashlib
import importlib.util
from pathlib import Path
import re
import sys


def validate(path):
    text = Path(path).read_text(encoding='utf-8')
    last = text.strip().splitlines()[-1].strip().strip('#*_ ')
    if last not in ('READY', 'READY WITH NON-BLOCKING ISSUES', 'NOT READY'):
        raise ValueError('Missing final audit verdict')
    spec = importlib.util.spec_from_file_location('audit_findings', Path(__file__).with_name('audit-findings.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    # Normalize only the verdict decoration accepted by the driver's classifier.
    body = text.strip().rsplit('\n', 1)[0] + '\n' + last + '\n'
    blockers = module.findings(body, require_blockers=last == 'NOT READY')
    if blockers and last != 'NOT READY':
        raise ValueError('Ready verdict contradicts blocking findings')


def render(project, state):
    project, state = Path(project).resolve(), Path(state).resolve()
    files = [(project / n, 3000) for n in ('VERIFICATION_REPORT.md', 'DEFECTS.md', 'MANUAL_CHECKLIST.md')]
    files += [(state / n, 3000) for n in ('delivery-summary.tsv', 'implementation-completion.txt', 'checklist-driver-checks/results.tsv')]
    files += [(state / 'change.diff', 0), (state / 'checklist-driver-checks/output.log', 0)]
    files += [(p, 1000) for p in sorted((state / 'waivers').glob('*')) if p.is_file()]
    lines = ['\n## Driver final-audit evidence packet',
             'Current inventory; hashes are identities, not PASS evidence.',
             'Excerpts may omit rows. Read required inputs and relevant evidence directly.']
    budget = 24000
    for path, limit in files:
        if not path.resolve().is_relative_to(project):
            continue
        try:
            digest, excerpt, size = hashlib.sha256(), b'', 0
            with path.open('rb') as stream:
                while chunk := stream.read(65536):
                    digest.update(chunk)
                    size += len(chunk)
                    excerpt += chunk[:max(0, min(limit, budget) - len(excerpt))]
            lines.append(f'\n{path}: {size} bytes; SHA-256 {digest.hexdigest()}')
            lines.append(excerpt.decode('utf-8', errors='replace'))
            budget -= len(excerpt)
            if len(excerpt) < size:
                lines.append('[Read remaining contents directly.]')
        except OSError:
            lines.append(f'{path}: unavailable; no evidence inferred.')
    return '\n'.join(lines) + '\n'


if __name__ == '__main__':
    if sys.argv[1] == '--validate':
        try:
            validate(sys.argv[2])
        except (OSError, ValueError, IndexError) as error:
            print(f'Audit format invalid: {error}. Correct FINAL_AUDIT.md and resume; no checks need rerunning.', file=sys.stderr)
            raise SystemExit(1)
    else:
        print(render(*sys.argv[1:3]), end='')
