"""Reject progress messages and incomplete checklist artifacts before execution."""
from pathlib import Path
import re
import sys

# Loaded both as a normal script (sys.path[0] is this directory already) and
# via importlib.util.spec_from_file_location (which does not add it), so the
# sibling import below needs the directory on sys.path explicitly.
sys.path.insert(0, str(Path(__file__).resolve().parent))
from checklist_groups import parse

# A self-hosted reviewer twice wrote a checklist with real, complete content
# under prose-style bold labels ("**Checks:**", "**Pass condition:**")
# instead of the required bullet fields -- every check was fully specified,
# just spelled differently, and got rejected for it. checklist_groups.py's
# own FIELD regex already tolerates bold markup for "Exclusive resources"/
# "Depends on"; this extends the same tolerance to the two fields whose
# absence this file's sanity check treats as "not a checklist at all".
# Deliberately label-only: no action, expected result, or any other content
# is invented or altered.
def _label_pattern(words):
    # The colon lands either inside or outside the closing bold marker
    # ("**Checks:**" vs "**Checks**:") in the wild; match both explicitly
    # rather than guess, so no markup is ever left dangling in the output.
    return re.compile(
        r'^(\s*)(?:[-*+]\s*)?'
        r'(?:\*\*(?:%s):\*\*|\*\*(?:%s)\*\*:|__(?:%s):__|__(?:%s)__:|(?:%s):)'
        r'\s*' % ((words,) * 5), re.I | re.M)


LABEL_SYNONYMS = (
    (_label_pattern(r'Checks?|Steps?'), r'\g<1>- Exact action: '),
    (_label_pattern(r'Pass\s+condition'), r'\g<1>- Expected result: '),
)

# Workflows complete before a project makes its first commit. A checklist
# action requiring history is an invalid contract, not an environment setup
# task: current-tree workflow snapshots are the supported evidence source.
COMMIT_BASELINE_ACTION = re.compile(
    r'\b(?:git\s+(?:history|log|diff)|prior\s+(?:checked[ -]in|committed)\s+(?:version|revision)|'
    r'diff\s+current\b[^\n]{0,180}\bversions?\s+referenced)\b', re.I)


def normalize_labels(text):
    for pattern, replacement in LABEL_SYNONYMS:
        text = pattern.sub(replacement, text)
    return text


def validate(path, project='.'):
    path = Path(path)
    text = path.read_text(encoding='utf-8')
    import importlib.util
    _spec = importlib.util.spec_from_file_location('artifact_json', Path(__file__).with_name('artifact_json.py'))
    _artifact_json = importlib.util.module_from_spec(_spec); _spec.loader.exec_module(_artifact_json)
    stripped = _artifact_json.unfence_json(text)
    if stripped.startswith('{'):
        import json
        try:
            payload = json.loads(stripped)
        except ValueError as error:
            raise ValueError('Invalid manual-checklist JSON response: ' + str(error)) from error
        if payload.get('schema') != 'uncle.artifact/v1' or payload.get('kind') != 'manual-checklist':
            raise ValueError('wrong manual-checklist JSON schema')
        for check in payload.get('checks', []):
            if not check.get('id'):
                raise ValueError('a checklist entry is missing id')
        rendered = _artifact_json.render_checklist(payload)
        path.write_text(rendered, encoding='utf-8')
        _artifact_json.write(project, 'MANUAL_CHECKLIST.md', dict(payload, schema='uncle.artifact/v1', kind='manual-checklist'))
        return validate_text(rendered)
    try:
        return validate_text(text)
    except ValueError:
        normalized = normalize_labels(text)
        if normalized == text:
            raise
        checks = validate_text(normalized)
        path.write_text(normalized, encoding='utf-8')
        return checks


def validate_text(text):
    checks,_,warnings=parse(text)
    if not checks:
        raise ValueError('No checklist rows: return the complete checklist, not a filename or progress message')
    if len({c.id for c in checks}) != len(checks):
        raise ValueError('Duplicate checklist IDs')
    # Both supported layouts must describe actions and their observable results.
    # Resource/dependency errors continue to use the existing serial fallback.
    if not re.search(r'\b(?:exact action|action|steps)\b',text,re.I) or not re.search(r'\bexpected(?: result)?\b',text,re.I):
        raise ValueError('Checklist lacks actions or expected results')
    if COMMIT_BASELINE_ACTION.search(text):
        raise ValueError('Checklist requires Git history or a prior committed version; use current-tree workflow snapshots instead')
    return checks


def export_json(path, project='.'):
    import json
    checks = validate(path)
    payload = {'schema': 'uncle.artifact/v1', 'kind': 'manual-checklist',
               'checks': [{'id': check.id, 'exclusive_resources': sorted(check.resources or []),
                           'depends_on': check.depends} for check in checks]}
    target = Path(project) / '.uncle/workflow/documents/MANUAL_CHECKLIST.json'
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(payload, indent=2) + '\n', encoding='utf-8')


def validate_canonical(path):
    import json
    payload = json.loads(Path(path).read_text(encoding='utf-8'))
    if payload.get('schema') != 'uncle.artifact/v1' or payload.get('kind') != 'manual-checklist':
        raise ValueError('wrong manual-checklist JSON schema')
    checks = payload.get('checks')
    if not isinstance(checks, list) or not checks:
        raise ValueError('manual checklist has no checks')
    seen = set()
    for check in checks:
        if not isinstance(check, dict) or not check.get('id') or not check.get('exact_action') or not check.get('expected_result'):
            raise ValueError('every checklist entry needs id, exact_action, and expected_result')
        if check['id'] in seen:
            raise ValueError('Duplicate checklist IDs')
        seen.add(check['id'])
    return payload


def render_canonical(path, view):
    payload = validate_canonical(path)
    import importlib.util
    spec = importlib.util.spec_from_file_location('artifact_json', Path(__file__).with_name('artifact_json.py'))
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    target = Path(view); target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(module.render_checklist(payload), encoding='utf-8')

if __name__=='__main__':
    args = sys.argv[1:]
    if len(args) == 2 and args[0] == '--validate-json':
        validate_canonical(args[1]); raise SystemExit(0)
    if len(args) == 3 and args[0] == '--render-json':
        render_canonical(args[1], args[2]); raise SystemExit(0)
    if args and args[0] == '--validate':
        args = args[1:]
    try:validate(args[0])
    except (OSError,ValueError) as error:
        print(f'Checklist artifact invalid: {error}. Correct .uncle/docs/MANUAL_CHECKLIST.md and resume; resume only revalidates this saved file and does not regenerate it. Execution has not started.',file=sys.stderr)
        raise SystemExit(1)
