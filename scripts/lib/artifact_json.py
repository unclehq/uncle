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
