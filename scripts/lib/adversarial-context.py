"""Focused planning evidence and structural review validation."""
import hashlib
from pathlib import Path
import re
import sys


def validate(path):
    text = Path(path).read_text(encoding='utf-8')
    matches = list(re.finditer(r'^##[ \t]+(AR-[A-Za-z0-9]+)(?:[ \t]+\([^\n)]+\))?[ \t]*(?::|—|–|-)[ \t]+\S[^\n]*$', text, re.M))
    seen = set()
    for index, match in enumerate(matches):
        identifier = match[1]
        if identifier in seen:
            raise ValueError('Duplicate finding ID: ' + identifier)
        seen.add(identifier)
        body = text[match.end():matches[index+1].start() if index+1 < len(matches) else len(text)]
        body = re.split(r'^##[ \t]+', body, maxsplit=1, flags=re.M)[0]
        fields = list(re.finditer(
            r'^[ \t]*(?:[-*+][ \t]+)?(?:\*\*)?'
            r'(Severity|References|Failure|Fix|Verify|Observation)(?:\*\*)?:', body, re.M))
        values = {}
        for i, field in enumerate(fields):
            value = body[field.end():fields[i+1].start() if i+1 < len(fields) else len(body)]
            values[field[1]] = value.strip().strip('*').strip()
        for field in ('Severity', 'References', 'Failure', 'Fix', 'Verify'):
            if not values.get(field) or not re.search(r'\w', values[field]):
                raise ValueError(identifier + ' missing ' + field)
    if not re.search(r'^##[ \t]+(?:\d+[.)][ \t]+)?(?:\*\*)?Overall assessment(?:\*\*)?[ \t]*#*[ \t]*\r?\n(?:(?:[ \t]*\r?\n)*)(?![ \t]*#)[ \t]*[^\s#]', text, re.M | re.I):
        raise ValueError('Missing nonempty Overall assessment section')
    malformed = re.findall(r'^##\s+AR[^\n]*', text, re.M)
    if len(malformed) != len(matches):
        raise ValueError('Malformed finding heading; use ## AR-001: Title')
    if not matches and not re.search(r'\bno findings\b', text, re.I):
        raise ValueError('Clean review must explicitly state No findings')


def render(project, family):
    root = Path(project).resolve()
    names = ('CHANGE_SPEC.md', 'CHANGE_PLAN.md', 'BASELINE_REPORT.md') if family == 'change' else (
        'REQUIREMENTS.md', 'REQUIREMENTS_INTERPRETATION.md', 'PROJECT_PLAN.md')
    lines = ['\n## Driver adversarial-review evidence packet',
             'These are excerpts, not conclusions. Independently challenge the plan.',
             'Read omitted portions and referenced code when needed; avoid unrelated tree discovery.']
    for name in names:
        path = root/name
        if not path.resolve().is_relative_to(root):
            continue
        try:
            digest = hashlib.sha256()
            with path.open('rb') as stream:
                excerpt = stream.read(10000)
                digest.update(excerpt)
                while chunk := stream.read(65536):
                    digest.update(chunk)
            lines += [f'\n{name}: SHA-256 {digest.hexdigest()}', excerpt.decode('utf-8', errors='replace')]
            if path.stat().st_size > len(excerpt):
                lines.append('[Truncated; read remaining input directly.]')
        except OSError:
            lines.append(name + ': unavailable; do not assume its requirements are satisfied.')
    return '\n'.join(lines) + '\n'


if __name__ == '__main__':
    if sys.argv[1] == '--validate':
        try:
            validate(sys.argv[2])
        except (OSError, ValueError) as error:
            print(f'Review format invalid: {error}. Correct the saved review and resume; investigation will not rerun.', file=sys.stderr)
            raise SystemExit(1)
    else:
        print(render(*sys.argv[1:3]), end='')
