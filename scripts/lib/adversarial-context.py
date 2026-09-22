"""Focused planning evidence and structural review validation."""
import hashlib
from pathlib import Path
import re
import sys
import json

# Content-preserving synonyms for the five required per-finding fields, the
# same tolerance checklist_document.py's LABEL_SYNONYMS already gives
# .uncle/docs/MANUAL_CHECKLIST.md: a reviewer that fully specifies a finding under a
# differently-spelled label should not lose it to a strict word match.
FIELD_SYNONYMS = {
    'Observation': 'Failure',
    'Repro': 'Failure',
    'Reproduction': 'Failure',
    'Remediation': 'Fix',
    'Suggested fix': 'Fix',
    'Verification': 'Verify',
}


def validate(path, project='.'):
    text = Path(path).read_text(encoding='utf-8')
    artifact = Path(__file__).with_name('artifact_json.py')
    import importlib.util
    _spec = importlib.util.spec_from_file_location('artifact_json', artifact)
    _artifact_json = importlib.util.module_from_spec(_spec); _spec.loader.exec_module(_artifact_json)
    stripped = _artifact_json.unfence_json(text)
    if stripped.startswith('{'):
        # The reviewer returned its structured findings directly. Every
        # regex-based table/heading check below exists to recover meaning
        # from prose; a JSON response was never prose, so validate its
        # schema instead and render the deterministic Markdown other stages
        # (and humans in the PR) still read.
        try:
            payload = json.loads(stripped)
        except ValueError as error:
            raise ValueError('Invalid adversarial-review JSON response: ' + str(error)) from error
        if payload.get('schema') != 'uncle.artifact/v1' or payload.get('kind') != 'adversarial-review':
            raise ValueError('wrong adversarial-review JSON schema')
        required = ('id', 'title', 'severity', 'references', 'failure', 'fix', 'verify')
        for finding in payload.get('findings', []):
            if not isinstance(finding, dict) or any(not finding.get(key) for key in required):
                raise ValueError('invalid adversarial finding: missing a required field')
        if not isinstance(payload.get('overall_assessment'), str) or not payload['overall_assessment'].strip():
            raise ValueError('missing nonempty overall_assessment')
        _artifact_json.write(project, 'ADVERSARIAL_REVIEW.md', dict(payload, schema='uncle.artifact/v1', kind='adversarial-review'))
        Path(path).write_text(_artifact_json.render_adversarial(payload), encoding='utf-8')
        return
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
            r'(Severity|References|Failure|Fix|Verify|Observation|Repro(?:duction)?|'
            r'Remediation|Suggested fix|Verification)(?:\*\*)?:', body, re.M))
        values = {}
        for i, field in enumerate(fields):
            value = body[field.end():fields[i+1].start() if i+1 < len(fields) else len(body)]
            values[FIELD_SYNONYMS.get(field[1], field[1])] = value.strip().strip('*').strip()
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
    _export(text, project)


def _export(text, project='.'):
    """Capture already-validated review fields as the workflow's structured artifact."""
    findings = []
    matches = list(re.finditer(r'^##[ \t]+(AR-[A-Za-z0-9]+)[ \t]*(?::|—|–|-)[ \t]+(.+)$', text, re.M))
    for index, match in enumerate(matches):
        body = text[match.end():matches[index + 1].start() if index + 1 < len(matches) else len(text)]
        values = {}
        for key in ('Severity', 'References', 'Failure', 'Fix', 'Verify'):
            found = re.search(r'^[ \t]*(?:[-*+]\s+)?(?:\*\*)?' + key + r'(?:\*\*)?:\s*(.+)$', body, re.M)
            values[key.lower()] = found.group(1).strip() if found else ''
        findings.append(dict(id=match.group(1), title=match.group(2).strip(), **values))
    assessment = re.search(r'^##[ \t]+(?:\d+[.)][ \t]+)?(?:\*\*)?Overall assessment(?:\*\*)?[ \t]*#*[ \t]*\r?\n(?:[ \t]*\r?\n)*([^\n#][^\n]*)', text, re.M | re.I)
    if not assessment:
        raise ValueError('Missing nonempty Overall assessment section')
    target = Path(project) / '.uncle/workflow/documents/ADVERSARIAL_REVIEW.json'; target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps({'schema':'uncle.artifact/v1','kind':'adversarial-review','findings':findings,'overall_assessment':assessment.group(1).strip()}, indent=2) + '\n')


def export_json(path, project='.'):
    """Validate a review, which captures its fields into the canonical JSON artifact as a side effect."""
    validate(path, project)


def render_json(project='.', destination='.uncle/docs/ADVERSARIAL_REVIEW.md'):
    artifact = Path(__file__).with_name('artifact_json.py')
    import importlib.util
    spec = importlib.util.spec_from_file_location('artifact_json', artifact)
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    payload = module.read(project, 'ADVERSARIAL_REVIEW.md')
    if payload.get('kind') != 'adversarial-review':
        raise ValueError('wrong artifact kind')
    required = ('id', 'title', 'severity', 'references', 'failure', 'fix', 'verify')
    for finding in payload.get('findings', []):
        if not isinstance(finding, dict) or any(not finding.get(key) for key in required):
            raise ValueError('invalid adversarial finding')
    if not isinstance(payload.get('overall_assessment'), str) or not payload['overall_assessment'].strip():
        raise ValueError('missing overall assessment')
    Path(destination).write_text(module.render_adversarial(payload), encoding='utf-8')


def findings_json(project='.'):
    """Structured findings for downstream workflow consumers."""
    from pathlib import Path
    return json.loads((Path(project)/'.uncle/workflow/documents/ADVERSARIAL_REVIEW.json').read_text(encoding='utf-8'))['findings']


def render(project, family):
    root = Path(project).resolve()
    names = ('.uncle/docs/CHANGE_SPEC.md', '.uncle/docs/CHANGE_PLAN.md', '.uncle/docs/BASELINE_REPORT.md') if family == 'change' else (
        'REQUIREMENTS.md', '.uncle/docs/REQUIREMENTS_INTERPRETATION.md', '.uncle/docs/PROJECT_PLAN.md')
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
    if sys.argv[1] == '--export-json':
        export_json(sys.argv[2], sys.argv[3] if len(sys.argv) > 3 else '.')
        raise SystemExit(0)
    if sys.argv[1] == '--render-json':
        render_json(sys.argv[2] if len(sys.argv) > 2 else '.', sys.argv[3] if len(sys.argv) > 3 else '.uncle/docs/ADVERSARIAL_REVIEW.md')
        raise SystemExit(0)
    if sys.argv[1] == '--validate':
        try:
            validate(sys.argv[2], sys.argv[3] if len(sys.argv) > 3 else '.')
        except (OSError, ValueError) as error:
            print(f'Review format invalid: {error}. Correct the saved review and resume; investigation will not rerun.', file=sys.stderr)
            raise SystemExit(1)
    else:
        print(render(*sys.argv[1:3]), end='')
