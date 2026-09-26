#!/usr/bin/env python3
"""Render safe checklist reports when an execution agent omitted them.

This is deliberately a *fallback*, not a result inference engine.  The
workflow has already recorded whether driver evidence is available, but a
command-level result cannot safely be assigned to an arbitrary manual check.
Accordingly every required checklist item is rendered as ``NOT RUN`` until a
worker supplies check-specific evidence.  That gives the acceptance gate a
valid, actionable state (rather than an opaque "missing file" failure) and
never turns absent evidence into a PASS.
"""
import argparse
from pathlib import Path
import re
import sys
import json

# Loaded both as a normal script (sys.path[0] is this directory already) and
# via importlib.util.spec_from_file_location (which does not add it), so the
# sibling import below needs the directory on sys.path explicitly.
sys.path.insert(0, str(Path(__file__).resolve().parent))
from checklist_groups import parse


def checks(path):
    text = path.read_text(encoding='utf-8')
    rows, _, _ = parse(text)
    if not rows:
        raise ValueError('manual checklist has no check IDs')
    return [row.id for row in rows]


def verification(ids):
    out = ['# Verification report', '',
           '## Driver-owned incomplete result', '',
           'The execution stage did not produce a check-specific report. No status has been inferred from command-level output.',
           'Each required check is therefore recorded as `NOT RUN` and must be executed or explicitly classified before release.', '']
    for identifier in ids:
        out += [f'### {identifier}: evidence not recorded', '',
                '- **Actual result:** No check-specific execution result was produced.',
                '- **Status:** NOT RUN',
                '- **Evidence:** The execution stage omitted its verification report; driver fallback created this incomplete record.', '']
    out += ['## Acceptance gate', '', '| ID | Required | Status | Evidence |',
            '|---|---|---|---|']
    out += [f'| {identifier} | YES | NOT RUN | No check-specific execution evidence was recorded. |' for identifier in ids]
    return '\n'.join(out) + '\n'


def defects(ids):
    listed = ', '.join(ids)
    return ('# Defects\n\n'
            '## CHECKLIST-EVIDENCE-MISSING\n\n'
            '- **Severity:** blocking verification gap\n'
            f'- **Affected checks:** {listed}\n'
            '- **Reproduction/evidence:** The execute-checklist stage completed without the required check-specific verification report.\n'
            '- **Current status:** open\n'
            '- **Owner/next action:** Run each listed check and replace the NOT RUN rows with observed evidence, or record the applicable blocker class.\n'
            '- **Disposition:** release blocked until required checks have evidence.\n')


# A per-check Findings block a model writes and this module can extract
# reliably: one heading per check ID, then the same bullet fields render_from_json
# would otherwise have to invent. Anything the model omits stays empty rather
# than guessed -- this only recovers what was actually stated.
_FINDING_HEADING = re.compile(r'^###\s+(\S+?)\s*(?::.*)?$', re.M)
_FINDING_FIELD = re.compile(r'^\s*-\s+\*\*(Action|Expected result|Actual result|Defect(?:s)?):\*\*\s*(.*)$', re.M | re.I)


def _findings_by_id(text):
    """{id: {action, expected_result, actual_result, defect_ids}} parsed from
    a Findings section's per-check blocks, when the model wrote one."""
    start = text.find('## Findings')
    end = text.find('## Acceptance gate')
    if start == -1:
        return {}
    text = text[start:end if end != -1 else len(text)]
    headings = list(_FINDING_HEADING.finditer(text))
    found = {}
    for index, match in enumerate(headings):
        identifier = match.group(1)
        body = text[match.end():headings[index + 1].start() if index + 1 < len(headings) else len(text)]
        fields = {'action': '', 'expected_result': '', 'actual_result': '', 'defect_ids': []}
        for field_match in _FINDING_FIELD.finditer(body):
            name, value = field_match.group(1).lower(), field_match.group(2).strip()
            if name == 'action':
                fields['action'] = value
            elif name == 'expected result':
                fields['expected_result'] = value
            elif name == 'actual result':
                fields['actual_result'] = value
            elif name.startswith('defect'):
                fields['defect_ids'] = [d.strip() for d in re.split(r'[,\s]+', value) if d.strip() and d.strip().lower() != 'none']
        found[identifier] = fields
    return found


def render_from_json(project):
    project = Path(project).resolve(); docs = project/'.uncle/docs'
    payload = json.loads((project/'.uncle/workflow/documents/EXECUTE_CHECKLIST.json').read_text())
    if payload.get('schema') != 'uncle.artifact/v1' or payload.get('kind') != 'execute-checklist':
        raise ValueError('invalid execute-checklist JSON')
    rows = payload['results']
    findings = ['### %s\n\n- **Action:** %s\n- **Expected result:** %s\n- **Actual result:** %s\n- **Defects:** %s\n' %
                (r['id'], r.get('action') or 'Not recorded.', r.get('expected_result') or 'Not recorded.',
                 r.get('actual_result') or 'Not recorded.', ', '.join(r.get('defect_ids') or []) or 'None')
                for r in rows]
    table = ''.join('| %s | %s | %s | %s |\n' % (r['id'], 'YES' if r['required'] else 'NO', r['status'], r['evidence'].replace('|', '/')) for r in rows)
    (docs/'VERIFICATION_REPORT.md').write_text(
        '# Verification report\n\n## Findings\n\n' + '\n'.join(findings) +
        '\n## Acceptance gate\n\n| ID | Required | Status | Evidence |\n|---|---|---|---|\n' + table, encoding='utf-8')
    blockers = [r for r in rows if r['status'] != 'PASS']
    (docs/'DEFECTS.md').write_text('# Defects\n\n' + ('No defects found.\n' if not blockers else '\n'.join(
        '## %s\n\n- **Status:** %s\n- **Evidence:** %s\n- **Expected result:** %s\n- **Actual result:** %s\n' %
        (', '.join(r.get('defect_ids') or [r['id']]), r['status'], r['evidence'],
         r.get('expected_result') or 'Not recorded.', r.get('actual_result') or 'Not recorded.')
        for r in blockers)), encoding='utf-8')


def export_from_markdown(project):
    project = Path(project).resolve(); text = (project/'.uncle/docs/VERIFICATION_REPORT.md').read_text()
    findings = _findings_by_id(text)
    rows = []
    active = False
    for line in text.splitlines():
        if line.strip() == '## Acceptance gate': active = True; continue
        if active and line.startswith('|'):
            cells = [x.strip() for x in line.strip('|').split('|')]
            if len(cells) == 4 and cells[0] not in ('ID', '---') and not cells[0].startswith('---'):
                row = {'id': cells[0], 'required': cells[1] == 'YES', 'status': cells[2], 'evidence': cells[3]}
                row.update(findings.get(cells[0], {}))
                rows.append(row)
    if not rows: raise ValueError('verification report has no acceptance rows')
    target = project/'.uncle/workflow/documents/EXECUTE_CHECKLIST.json'; target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps({'schema':'uncle.artifact/v1','kind':'execute-checklist','results':rows}, indent=2)+'\n')


def main(argv):
    parser = argparse.ArgumentParser()
    parser.add_argument('--project', default='.')
    parser.add_argument('--missing-only', action='store_true')
    args = parser.parse_args(argv)
    project = Path(args.project).resolve()
    docs = project / '.uncle/docs'
    checklist = docs / 'MANUAL_CHECKLIST.md'
    try:
        ids = checks(checklist)
    except (OSError, ValueError) as error:
        print(f'Cannot render checklist fallback: {error}', file=sys.stderr)
        return 1
    docs.mkdir(parents=True, exist_ok=True)
    report, defect = docs / 'VERIFICATION_REPORT.md', docs / 'DEFECTS.md'
    # True when the execution stage's own report is on disk and --missing-only
    # kept it. prompts/change/execute-change-checklist.md asks the agent for
    # Markdown only -- it never names a canonical JSON -- so this is where a
    # real run's evidence actually is.
    delivered = args.missing_only and report.is_file() and report.stat().st_size > 0
    if not delivered:
        report.write_text(verification(ids), encoding='utf-8')
    if not args.missing_only or not defect.is_file() or defect.stat().st_size == 0:
        defect.write_text(defects(ids), encoding='utf-8')
    artifact = project / '.uncle/workflow/documents/EXECUTE_CHECKLIST.json'
    artifact.parent.mkdir(parents=True, exist_ok=True)
    rows = None
    if delivered:
        # The canonical artifact must be derived from that report, never
        # fabricated over it. These three writes used to be unconditional, so
        # a stage that had executed every check still produced 42 rows of
        # NOT RUN -- and VALIDATE_CHECKLIST then re-rendered the Markdown from
        # those empty rows, destroying the evidence --missing-only had just
        # preserved. export_from_markdown is the existing parser for exactly
        # this; nothing here infers a status the report did not state.
        try:
            export_from_markdown(project)
            rows = json.loads(artifact.read_text(encoding='utf-8'))['results']
        except (OSError, ValueError, KeyError) as error:
            print(f'Could not read the execution report ({error}); recording NOT RUN.', file=sys.stderr)
            rows = None
    if rows is None:
        rows = [{'id': identifier, 'required': True, 'status': 'NOT RUN',
                 'evidence': 'No check-specific execution evidence was recorded.'}
                for identifier in ids]
        artifact.write_text(json.dumps({'schema': 'uncle.artifact/v1', 'kind': 'execute-checklist',
                                        'results': rows}, indent=2) + '\n', encoding='utf-8')
    state = project / '.uncle/workflow/documents'
    (state / 'VERIFICATION_REPORT.json').write_text(json.dumps(
        {'schema': 'uncle.artifact/v1', 'kind': 'acceptance-report',
         'rows': [{'id': row['id'], 'required': row.get('required', True),
                   'status': row.get('status') or 'NOT RUN',
                   'evidence': row.get('evidence') or 'No check-specific execution evidence was recorded.'}
                  for row in rows]},
        indent=2) + '\n', encoding='utf-8')
    (state / 'DEFECTS.json').write_text(json.dumps(
        {'schema': 'uncle.artifact/v1', 'kind': 'defects', 'defects': []}, indent=2) + '\n', encoding='utf-8')
    return 0


if __name__ == '__main__':
    raise SystemExit(main(sys.argv[1:]))
