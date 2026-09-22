#!/usr/bin/env python3
"""Authoritative structured workflow artifact storage and Markdown rendering."""
import json
from pathlib import Path

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

def render_checklist(payload):
    out = ['# Manual checklist', '']
    for check in payload['checks']:
        out += [f"### {check['id']}: {check['title']}"]
        out += [f"- {key}: {check.get(key.lower().replace(' ', '_'), '')}" for key in ('Exact action', 'Expected result', 'Evidence to capture', 'Status')]
        out.append('')
    return '\n'.join(out)

def write_checklist(project, checks):
    return write(project, 'MANUAL_CHECKLIST.md', {'schema':'uncle.artifact/v1', 'kind':'manual-checklist', 'checks':checks})
