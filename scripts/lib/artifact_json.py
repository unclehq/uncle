#!/usr/bin/env python3
"""Authoritative structured workflow artifact storage and Markdown rendering."""
import json
from pathlib import Path
import re

_JSON_FENCE = re.compile(r'^```(?:json)?\s*\n(.*)\n```\s*$', re.S)

def unfence_json(text):
    """A model asked for a bare JSON object commonly wraps it in a Markdown
    code fence anyway (the same habit every prompt in this codebase already
    has to guard against for the documents JSON is replacing). Strip one
    wrapping ```/```json fence if present; otherwise return the text
    unchanged, so a genuinely bare object still works."""
    stripped = text.strip()
    match = _JSON_FENCE.match(stripped)
    return match.group(1).strip() if match else stripped

def path(project, name):
    return Path(project) / '.uncle/workflow/documents' / (Path(name).stem + '.json')

def write(project, name, payload):
    target = path(project, name); target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(payload, indent=2, sort_keys=True) + '\n', encoding='utf-8')
    return target

def read(project, name):
    value = json.loads(path(project, name).read_text(encoding='utf-8'))
    if not isinstance(value, dict) or value.get('schema') != 'uncle.artifact/v1':
        raise ValueError('invalid workflow artifact schema')
    return value

def render_adversarial(payload):
    rows = []
    for finding in payload.get('findings', []):
        rows += [f"## {finding['id']}: {finding['title']}", '',
                 f"- Severity: {finding['severity']}", f"- References: {finding['references']}",
                 f"- Failure: {finding['failure']}", f"- Fix: {finding['fix']}", f"- Verify: {finding['verify']}", '']
    rows += ['## Overall assessment', '', payload['overall_assessment'], '']
    return '\n'.join(rows)

def parse_adversarial_response(text):
    payload = json.loads(text)
    if payload.get('schema') != 'uncle.artifact/v1' or payload.get('kind') != 'adversarial-review':
        raise ValueError('wrong adversarial-review JSON schema')
    return payload

REQUIREMENTS_SECTIONS = ('Required functionality', 'Optional functionality', 'Constraints',
                          'User-visible behaviors', 'System behaviors', 'Failure behaviors',
                          'Ambiguities', 'Assumptions', 'Explicit non-goals', 'Definition of done')

def render_requirements(payload):
    sections = payload['sections']
    rows = []
    for index, name in enumerate(REQUIREMENTS_SECTIONS, 1):
        key = name.lower().replace(' ', '_').replace('-', '_')
        rows += [f'## {index}. {name}', '', sections[key].strip(), '']
    return '\n'.join(rows)

def render_final_audit(payload):
    findings = payload.get('findings', [])
    rows = ['## Findings', '']
    if findings:
        rows += ['| ID | Severity | Evidence | Affected requirement | Required correction | Blocks |',
                  '|---|---|---|---|---|---|']
        esc = lambda value: str(value).replace('|', r'\|').replace('\n', ' ')
        for finding in findings:
            rows.append('| %s | %s | %s | %s | %s | %s |' % (
                finding['id'], finding['severity'], esc(finding['evidence']),
                finding.get('affected_requirement', 'Not stated'), esc(finding['required_correction']),
                finding['blocks']))
        rows.append('')
    verdict = payload['verdict']
    if verdict not in ('READY', 'READY WITH NON-BLOCKING ISSUES', 'NOT READY'):
        raise ValueError('invalid final-audit verdict: ' + repr(verdict))
    rows.append(verdict)
    return '\n'.join(rows) + '\n'

def parse_final_audit_response(text):
    payload = json.loads(text)
    if payload.get('schema') != 'uncle.artifact/v1' or payload.get('kind') != 'final-audit':
        raise ValueError('wrong final-audit JSON schema')
    return payload

ACCEPTANCE_STATUSES = ('PASS', 'FAIL', 'BLOCKED-SETUP', 'BLOCKED-HUMAN', 'BLOCKED-IMPOSSIBLE', 'NOT RUN', 'N/A')

def render_acceptance(payload):
    rows = payload['rows']
    if not rows:
        raise ValueError('acceptance report has no rows')
    seen = set()
    lines = []
    narrative = payload.get('narrative')
    if narrative:
        lines += [narrative.strip(), '']
    lines += ['## Acceptance gate', '', '| ID | Required | Status | Evidence |', '|---|---|---|---|']
    for row in rows:
        identifier = row['id']
        if identifier in seen:
            raise ValueError('duplicate acceptance row id: ' + identifier)
        seen.add(identifier)
        status = row['status']
        if status not in ACCEPTANCE_STATUSES:
            raise ValueError('invalid acceptance status: ' + repr(status))
        if not row.get('evidence'):
            raise ValueError(identifier + ' has empty evidence')
        required = 'YES' if row['required'] else 'NO'
        evidence = str(row['evidence']).replace('|', r'\|').replace('\n', ' ')
        lines.append('| %s | %s | %s | %s |' % (identifier, required, status, evidence))
    return '\n'.join(lines) + '\n'

def render_plan(payload, protected=True):
    commands = payload.get('verification_commands')
    if not commands or not commands.strip():
        raise ValueError('plan is missing verification_commands')
    lines = []
    narrative = payload.get('narrative')
    if narrative:
        lines += [narrative.strip(), '']
    lines += ['## Verification commands', '', '```sh', commands.strip('\n'), '```', '']
    if protected:
        paths = payload.get('protected_verification_paths')
        if not paths or not paths.strip():
            raise ValueError('plan is missing protected_verification_paths')
        lines += ['## Protected verification paths', '', '```text', paths.strip('\n'), '```', '']
    dispositions = payload.get('dispositions')
    if dispositions:
        seen = set()
        lines += ['## Adversarial review dispositions', '',
                  '| Finding | Disposition | Reason | Exact plan change |', '|---|---|---|---|']
        for row in dispositions:
            finding = row['finding']
            if finding in seen:
                raise ValueError('duplicate disposition for finding: ' + finding)
            seen.add(finding)
            if row['disposition'] not in ('Accepted', 'Partially accepted', 'Rejected', 'Deferred'):
                raise ValueError('invalid disposition for %s: %r' % (finding, row['disposition']))
            esc = lambda value: str(value).replace('|', r'\|').replace('\n', ' ')
            lines.append('| %s | %s | %s | %s |' % (finding, row['disposition'], esc(row['reason']), esc(row['plan_change'])))
        lines.append('')
    return '\n'.join(lines)


def render_change_plan(payload, require_dispositions=False):
    """CHANGE_PLAN.md has no verification_commands convention of its own --
    change-workflow.sh's Verification commands come from BASELINE_REPORT.md
    (verify_commands() runs against it, not the plan) -- so unlike
    render_plan() this never requires that field. The only thing CHANGE_PLAN.md
    structurally owes is the disposition table, and only once a review exists
    to disposition (require_dispositions=True for the post-review revision)."""
    narrative = payload.get('narrative')
    if not narrative or not narrative.strip():
        raise ValueError('change-plan has no narrative')
    dispositions = payload.get('dispositions')
    if require_dispositions and not dispositions:
        raise ValueError('change-plan is missing dispositions for the adversarial review')
    lines = [narrative.strip(), '']
    if dispositions:
        seen = set()
        rows = ['## Adversarial review dispositions', '',
                '| Finding | Disposition | Reason | Exact plan change |', '|---|---|---|---|']
        for row in dispositions:
            finding = row['finding']
            if finding in seen:
                raise ValueError('duplicate disposition for finding: ' + finding)
            seen.add(finding)
            if row['disposition'] not in ('Accepted', 'Partially accepted', 'Rejected', 'Deferred'):
                raise ValueError('invalid disposition for %s: %r' % (finding, row['disposition']))
            esc = lambda value: str(value).replace('|', r'\|').replace('\n', ' ')
            rows.append('| %s | %s | %s | %s |' % (finding, row['disposition'], esc(row['reason']), esc(row['plan_change'])))
        lines += rows + ['']
    return '\n'.join(lines)


def render_change_spec(payload):
    criteria = payload.get('acceptance_criteria')
    if not criteria:
        raise ValueError('change-spec has no acceptance_criteria')
    seen = set()
    lines = []
    narrative = payload.get('narrative')
    if narrative:
        lines += [narrative.strip(), '']
    lines += ['## Acceptance criteria', '', '| ID | Criterion | Verification |', '|---|---|---|']
    for row in criteria:
        identifier = row['id']
        if identifier in seen:
            raise ValueError('duplicate acceptance criterion id: ' + identifier)
        seen.add(identifier)
        if not row.get('criterion') or not row.get('verification'):
            raise ValueError(identifier + ' is missing criterion or verification')
        esc = lambda value: str(value).replace('|', r'\|').replace('\n', ' ')
        lines.append('| %s | %s | %s |' % (identifier, esc(row['criterion']), esc(row['verification'])))
    lines.append('')
    return '\n'.join(lines)

def render_checklist(payload):
    out = ['# Manual checklist', '']
    for check in payload['checks']:
        out += [f"### {check['id']}: {check['title']}"]
        out += [f"- {key}: {check.get(key.lower().replace(' ', '_'), '')}" for key in ('Exact action', 'Expected result', 'Evidence to capture', 'Status')]
        out.append('')
    return '\n'.join(out)

def write_checklist(project, checks):
    return write(project, 'MANUAL_CHECKLIST.md', {'schema':'uncle.artifact/v1', 'kind':'manual-checklist', 'checks':checks})
