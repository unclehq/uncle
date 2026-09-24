#!/usr/bin/env python3
"""JSON ingestion for the plan family: PROJECT_PLAN.md, UPDATED_PROJECT_PLAN.md,
CHANGE_SPEC.md, CHANGE_PLAN.md, BASELINE_REPORT.md.

Unlike the reviewer-authored artifacts (ADVERSARIAL_REVIEW.md, FINAL_AUDIT.md,
TEST_REVIEW.md), these are written by an agent with Write-tool access and the
drivers have never run a structural validator against them beyond existence
and size -- there is no baseline to make stricter without risking a
currently-valid plan being rejected for a shape nobody has ever checked.

So this module is purely additive: it only acts when the document is JSON
(after stripping a possible fence), which never happens for a plan an agent
wrote directly with its Write tool. A Markdown plan -- the entire existing
population of them -- passes through untouched. Only a plan returned as chat
text (the self-hosted fallback path, or any runner a future prompt points at
this contract) takes the JSON route.
"""
import importlib.util
import re
from pathlib import Path

_LIB = Path(__file__).resolve().parent


def _artifact_json():
    spec = importlib.util.spec_from_file_location('artifact_json', _LIB / 'artifact_json.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _fenced_block(heading, lang):
    return re.compile(r'^## ' + re.escape(heading) + r'\s*\n+```' + lang + r'\n(.*?)\n```', re.M | re.S)


_VERIFICATION_COMMANDS_RE = _fenced_block('Verification commands', 'sh')
_PROJECT_VERIFICATION_COMMANDS_RE = re.compile(
    r'^#{1,6}\s+(?:Exact\s+)?Verification commands(?:\s+block)?\s*\n+```sh\n(.*?)\n```', re.M | re.S | re.I)
_PROTECTED_PATHS_RE = _fenced_block('Protected verification paths', 'text')
_DISPOSITIONS_TABLE_RE = re.compile(
    r'^## Adversarial review dispositions\s*\n\n\|.*\|\n\|[-| ]+\|\n((?:\|.*\|\n?)*)', re.M)
_ACCEPTANCE_CRITERIA_TABLE_RE = re.compile(
    r'^## Acceptance criteria\s*\n\n\|.*\|\n\|[-| ]+\|\n((?:\|.*\|\n?)*)', re.M)


def _table_rows(match, width):
    if not match:
        return None
    rows = []
    for line in match.group(1).splitlines():
        line = line.strip()
        if not line.startswith('|'):
            continue
        cells = [cell.strip().replace(r'\|', '|') for cell in re.split(r'(?<!\\)\|', line.strip('|'))]
        if len(cells) == width:
            rows.append(cells)
    return rows or None


def _parse_dispositions(text):
    rows = _table_rows(_DISPOSITIONS_TABLE_RE.search(text), 4)
    if not rows:
        return None
    return [{'finding': f, 'disposition': d, 'reason': r, 'plan_change': p} for f, d, r, p in rows]


def _parse_acceptance_criteria(text):
    rows = _table_rows(_ACCEPTANCE_CRITERIA_TABLE_RE.search(text), 3)
    if not rows:
        return None
    return [{'id': i, 'criterion': c, 'verification': v} for i, c, v in rows]


def export_plan(path, project='.', protected=True):
    """Re-derive PROJECT_PLAN.md / UPDATED_PROJECT_PLAN.md's canonical JSON
    from its current approved bytes, for approval_export.py's gate refresh.

    This only succeeds on our own render_plan() output: narrative, then a
    fixed sequence of '## Verification commands' / '## Protected
    verification paths' / '## Adversarial review dispositions' headings, in
    that order. A plan an agent wrote directly as Markdown (never JSON) will
    not match and raises, which the caller treats as a silent no-op -- there
    is no reverse-parser for arbitrary prose, by the same reasoning
    ingest_plan() above stays purely additive on generation."""
    text = Path(path).read_text(encoding='utf-8')
    module = _artifact_json()
    narrative = text.split('## Verification commands', 1)[0].strip()
    commands = _VERIFICATION_COMMANDS_RE.search(text)
    if not commands:
        raise ValueError('missing ## Verification commands fenced block')
    payload = {'schema': 'uncle.artifact/v1', 'kind': 'plan', 'narrative': narrative,
               'verification_commands': commands.group(1)}
    if protected:
        paths = _PROTECTED_PATHS_RE.search(text)
        if not paths:
            raise ValueError('missing ## Protected verification paths fenced block')
        payload['protected_verification_paths'] = paths.group(1)
    dispositions = _parse_dispositions(text)
    if dispositions:
        payload['dispositions'] = dispositions
    module.render_plan(payload, protected=protected)  # raises on a malformed table before anything is written
    module.write(project, Path(path).name, payload)
    return payload


def export_project_plan(path, project='.'):
    # The self-hosted investigation is valid Markdown with either top-level
    # heading style. Normalize it when rendering instead of rejecting a plan
    # solely because it used `#` rather than `##` for this final section.
    text = Path(path).read_text(encoding='utf-8')
    commands = _PROJECT_VERIFICATION_COMMANDS_RE.search(text)
    if not commands:
        raise ValueError('missing Verification commands fenced block')
    narrative = re.split(r'^#{1,6}\s+(?:Exact\s+)?Verification commands(?:\s+block)?\s*$',
                         text, maxsplit=1, flags=re.M | re.I)[0].strip()
    payload = {'schema': 'uncle.artifact/v1', 'kind': 'plan', 'narrative': narrative,
               'verification_commands': commands.group(1)}
    _artifact_json().render_plan(payload, protected=False)
    _artifact_json().write(project, Path(path).name, payload)
    return payload


def export_updated_project_plan(path, project='.'):
    return export_plan(path, project, protected=True)


def export_change_plan(path, project='.', require_dispositions=False):
    """Re-derive CHANGE_PLAN.md's canonical JSON from its current approved
    bytes. Same purely-additive, own-render-format-only contract as
    export_plan()."""
    text = Path(path).read_text(encoding='utf-8')
    module = _artifact_json()
    marker = '## Adversarial review dispositions'
    narrative = (text.split(marker, 1)[0] if marker in text else text).strip()
    if not narrative:
        raise ValueError('change-plan has no narrative')
    payload = {'schema': 'uncle.artifact/v1', 'kind': 'change-plan', 'narrative': narrative}
    dispositions = _parse_dispositions(text)
    if dispositions:
        payload['dispositions'] = dispositions
    module.render_change_plan(payload, require_dispositions=require_dispositions)
    module.write(project, Path(path).name, payload)
    return payload


def export_change_spec(path, project='.'):
    """Re-derive CHANGE_SPEC.md's canonical JSON from its current approved
    bytes. Same purely-additive, own-render-format-only contract as
    export_plan()."""
    text = Path(path).read_text(encoding='utf-8')
    module = _artifact_json()
    marker = '## Acceptance criteria'
    narrative = (text.split(marker, 1)[0] if marker in text else text).strip()
    criteria = _parse_acceptance_criteria(text)
    if not criteria:
        raise ValueError('missing ## Acceptance criteria table')
    payload = {'schema': 'uncle.artifact/v1', 'kind': 'change-spec', 'narrative': narrative,
               'acceptance_criteria': criteria}
    module.render_change_spec(payload)
    module.write(project, Path(path).name, payload)
    return payload


def ingest_plan(path, project='.', protected=True):
    """PROJECT_PLAN.md / UPDATED_PROJECT_PLAN.md / CHANGE_PLAN.md. Returns
    True if the document was JSON (rendered and exported either way --
    ValueError propagates so the caller reports the real defect), False if
    it was left alone as ordinary Markdown."""
    import json
    module = _artifact_json()
    text = Path(path).read_text(encoding='utf-8')
    stripped = module.unfence_json(text)
    if not stripped.startswith('{'):
        return False
    try:
        payload = module.loads_response_json(text)
    except ValueError as error:
        raise ValueError('Invalid plan JSON response: ' + str(error)) from error
    if payload.get('schema') != 'uncle.artifact/v1' or payload.get('kind') != 'plan':
        raise ValueError('wrong plan JSON schema')
    rendered = module.render_plan(payload, protected=protected)
    Path(path).write_text(rendered, encoding='utf-8')
    module.write(project, Path(path).name, dict(payload, schema='uncle.artifact/v1', kind='plan'))
    return True


def canonicalize_json_plan(path, project='.', protected=True):
    """Write a canonical mirror for a raw JSON plan without rewriting its
    approval-view file.  This migrates an already-approved pre-render plan
    safely: changing that file would invalidate the human approval hash."""
    import json
    module = _artifact_json()
    text = Path(path).read_text(encoding='utf-8')
    stripped = module.unfence_json(text)
    if not stripped.startswith('{'):
        return False
    try:
        payload = module.loads_response_json(text)
    except ValueError as error:
        raise ValueError('Invalid plan JSON response: ' + str(error)) from error
    if payload.get('schema') != 'uncle.artifact/v1' or payload.get('kind') != 'plan':
        raise ValueError('wrong plan JSON schema')
    module.render_plan(payload, protected=protected)
    module.write(project, Path(path).name, dict(payload, schema='uncle.artifact/v1', kind='plan'))
    return True


def ingest_change_plan(path, project='.', require_dispositions=False):
    """CHANGE_PLAN.md, both before a review exists (require_dispositions=False,
    the initial 'change-plan' stage) and after one (require_dispositions=True,
    'updated-change-plan'). Same purely-additive contract as ingest_plan()."""
    import json
    module = _artifact_json()
    text = Path(path).read_text(encoding='utf-8')
    stripped = module.unfence_json(text)
    if not stripped.startswith('{'):
        return False
    try:
        payload = module.loads_response_json(text)
    except ValueError as error:
        raise ValueError('Invalid change-plan JSON response: ' + str(error)) from error
    if payload.get('schema') != 'uncle.artifact/v1' or payload.get('kind') != 'change-plan':
        raise ValueError('wrong change-plan JSON schema')
    rendered = module.render_change_plan(payload, require_dispositions=require_dispositions)
    Path(path).write_text(rendered, encoding='utf-8')
    module.write(project, Path(path).name, dict(payload, schema='uncle.artifact/v1', kind='change-plan'))
    return True


def render_canonical(path, project='.', protected=True, change=False, require_dispositions=False):
    """Regenerate human-facing plan Markdown from its authoritative JSON."""
    module = _artifact_json()
    json_path = module.path(project, Path(path).name)
    if not json_path.exists():
        return False
    payload = module.read(project, Path(path).name)
    expected = 'change-plan' if change else 'plan'
    if payload.get('kind') != expected:
        raise ValueError('canonical artifact has wrong kind: ' + str(payload.get('kind')))
    rendered = (module.render_change_plan(payload, require_dispositions=require_dispositions)
                if change else module.render_plan(payload, protected=protected))
    Path(path).write_text(rendered, encoding='utf-8')
    return True


def ingest_baseline_report(path, project='.'):
    """BASELINE_REPORT.md. Same purely-additive contract as ingest_plan()."""
    import json
    module = _artifact_json()
    text = Path(path).read_text(encoding='utf-8')
    stripped = module.unfence_json(text)
    if not stripped.startswith('{'):
        return False
    try:
        payload = json.loads(stripped)
    except ValueError as error:
        raise ValueError('Invalid baseline-report JSON response: ' + str(error)) from error
    if payload.get('schema') != 'uncle.artifact/v1' or payload.get('kind') != 'baseline-report':
        raise ValueError('wrong baseline-report JSON schema')
    rendered = module.render_baseline_report(payload)
    Path(path).write_text(rendered, encoding='utf-8')
    module.write(project, Path(path).name, dict(payload, schema='uncle.artifact/v1', kind='baseline-report'))
    return True


def export_baseline_report(path, project='.'):
    """Re-derive BASELINE_REPORT.md's canonical JSON from its current approved
    bytes, for approval_export.py's gate refresh. Same own-render-format-only
    contract as export_plan()."""
    text = Path(path).read_text(encoding='utf-8')
    module = _artifact_json()
    marker = '## Exact build and test commands executed'
    narrative = (text.split(marker, 1)[0] if marker in text else text).strip()
    commands = _fenced_block('Exact build and test commands executed', 'sh').search(text)
    if not commands:
        raise ValueError('missing ## Exact build and test commands executed fenced block')
    payload = {'schema': 'uncle.artifact/v1', 'kind': 'baseline-report', 'narrative': narrative,
               'verification_commands': commands.group(1)}
    groups = _fenced_block('Parallel verification groups', 'text').search(text)
    if groups:
        payload['parallel_groups'] = groups.group(1)
    module.render_baseline_report(payload)
    module.write(project, Path(path).name, payload)
    return payload


def ingest_change_spec(path, project='.'):
    """CHANGE_SPEC.md. Same purely-additive contract as ingest_plan()."""
    import json
    module = _artifact_json()
    text = Path(path).read_text(encoding='utf-8')
    stripped = module.unfence_json(text)
    if not stripped.startswith('{'):
        return False
    try:
        payload = json.loads(stripped)
    except ValueError as error:
        raise ValueError('Invalid change-spec JSON response: ' + str(error)) from error
    if payload.get('schema') != 'uncle.artifact/v1' or payload.get('kind') != 'change-spec':
        raise ValueError('wrong change-spec JSON schema')
    rendered = module.render_change_spec(payload)
    Path(path).write_text(rendered, encoding='utf-8')
    module.write(project, Path(path).name, dict(payload, schema='uncle.artifact/v1', kind='change-spec'))
    return True


if __name__ == '__main__':
    import sys
    action, path = sys.argv[1], sys.argv[2]
    project = sys.argv[3] if len(sys.argv) > 3 else '.'
    try:
        if action == 'plan':
            ingest_plan(path, project, protected=True)
        elif action == 'plan-unprotected':
            ingest_plan(path, project, protected=False)
        elif action == 'canonicalize-project-plan':
            canonicalize_json_plan(path, project, protected=False)
        elif action == 'export-project-plan':
            export_project_plan(path, project)
        elif action == 'change-spec':
            ingest_change_spec(path, project)
        elif action == 'change-plan':
            ingest_change_plan(path, project, require_dispositions=False)
        elif action == 'updated-change-plan':
            ingest_change_plan(path, project, require_dispositions=True)
        elif action == 'render-plan':
            render_canonical(path, project, protected=True)
        elif action == 'render-project-plan':
            render_canonical(path, project, protected=False)
        elif action == 'render-change-plan':
            render_canonical(path, project, change=True)
        elif action == 'render-change-plan-unreviewed':
            render_canonical(path, project, change=True, require_dispositions=False)
        elif action == 'baseline-report':
            ingest_baseline_report(path, project)
        else:
            raise SystemExit('unknown action: ' + action)
    except ValueError as error:
        print(f'{path}: {error}. Correct the saved document and resume.', file=sys.stderr)
        raise SystemExit(1)
