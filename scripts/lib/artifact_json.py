#!/usr/bin/env python3
"""Authoritative structured workflow artifact storage and Markdown rendering."""
import json
from pathlib import Path
import re

_JSON_FENCE = re.compile(r'```(?:json)?\s*\n(.*?)\n```', re.S)

def _extract_balanced_object(text):
    """The first {...} object in TEXT, honoring string quoting so a brace
    inside a JSON string value never miscounts nesting depth. None if TEXT
    has no top-level object at all."""
    start = text.find('{')
    if start == -1:
        return None
    depth = 0
    in_string = False
    escape = False
    for index in range(start, len(text)):
        char = text[index]
        if in_string:
            if escape:
                escape = False
            elif char == '\\':
                escape = True
            elif char == '"':
                in_string = False
            continue
        if char == '"':
            in_string = True
        elif char == '{':
            depth += 1
        elif char == '}':
            depth -= 1
            if depth == 0:
                return text[start:index + 1]
    return None

def unfence_json(text):
    """A model asked for a bare JSON object commonly wraps it in a Markdown
    code fence anyway (the same habit every prompt in this codebase already
    has to guard against for the documents JSON is replacing), and just as
    commonly adds a sentence of narration before or after it despite being
    told the object must be its entire reply. Find a fenced block anywhere
    in the text (not only when the fence is the whole message) and, whether
    fenced or bare, extract the first balanced {...} object rather than
    requiring the object to be the only content -- trailing narration after
    a closing fence or a closing brace must not turn a genuinely valid
    response into a rejected one. Text that never looks JSON-shaped (no
    fenced or bare object starting the candidate) is returned unchanged, so
    a genuinely non-JSON document still falls through to its own parser."""
    stripped = text.strip()
    fenced = _JSON_FENCE.search(stripped)
    candidate = fenced.group(1).strip() if fenced else stripped
    # A model as often reaches for a single inline-code backtick around the
    # object (`{...}`) as a triple-backtick block fence; strip that too
    # before giving up on it looking JSON-shaped.
    unbacked = candidate.strip('`').strip()
    if unbacked.startswith('{'):
        candidate = unbacked
    if not candidate.startswith('{'):
        return stripped
    return _extract_balanced_object(candidate) or candidate

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


def render_baseline_report(payload):
    """BASELINE_REPORT.md's command block must sit under a heading matching
    'verification commands' or 'build and test commands' (green-check.sh's
    verify_commands()); the optional parallel-groups block is its own fixed
    heading. Both are consumed by the driver's own re-execution of the
    approved commands, not merely read."""
    commands = payload.get('verification_commands')
    if not commands or not commands.strip():
        raise ValueError('baseline report is missing verification_commands')
    narrative = payload.get('narrative')
    lines = []
    if narrative:
        lines += [narrative.strip(), '']
    lines += ['## Exact build and test commands executed', '', '```sh', commands.strip('\n'), '```', '']
    groups = payload.get('parallel_groups')
    if groups and groups.strip():
        lines += ['## Parallel verification groups', '', '```text', groups.strip('\n'), '```', '']
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

# (JSON key, rendered label). Both the app-workflow and change-workflow
# checklists share this schema; a field neither variant's prompt asked the
# model to fill in is simply absent from the check dict and its bullet line
# is skipped, rather than forced to a literal "none" -- only exact_action and
# expected_result are ever mandatory.
_CHECKLIST_FIELDS = (
    ('priority', 'Priority'),
    ('required', 'Required for acceptance'),
    ('behavior_classification', 'Behavior classification'),
    ('related_requirement', 'Related requirement'),
    ('related_behavior', 'Related behavior'),
    ('related_invariant', 'Related invariant'),
    ('prerequisites', 'Prerequisites'),
    ('preconditions', 'Preconditions'),
    ('needs', 'Needs'),
    ('exclusive_resources', 'Exclusive resources'),
    ('depends_on', 'Depends on'),
    ('exact_action', 'Exact action'),
    ('expected_result', 'Expected result'),
    ('evidence_to_capture', 'Evidence to capture'),
)
_CHECKLIST_LIST_FIELDS = ('exclusive_resources', 'depends_on')

def render_checklist(payload):
    checks = payload.get('checks')
    if not checks:
        raise ValueError('manual checklist has no checks')
    seen = set()
    out = ['# Manual checklist', '']
    section = None
    for check in checks:
        identifier = check['id']
        if identifier in seen:
            raise ValueError('duplicate checklist id: ' + identifier)
        seen.add(identifier)
        if not check.get('exact_action') or not check.get('expected_result'):
            raise ValueError(identifier + ' is missing exact_action or expected_result')
        if check.get('section') and check['section'] != section:
            section = check['section']
            out += [f"## {section}", '']
        out.append(f"### {identifier}")
        for key, label in _CHECKLIST_FIELDS:
            if key in _CHECKLIST_LIST_FIELDS:
                if key not in check:
                    continue
                value = ', '.join(check[key]) if check[key] else 'none'
            elif key == 'required':
                if key not in check:
                    continue
                value = 'YES' if check[key] else 'NO'
            else:
                value = check.get(key)
                if value in (None, ''):
                    continue
            out.append(f"- {label}: {value}")
        status = check.get('status') or 'NOT RUN'
        if status not in ('NOT RUN', 'BLOCKED-SETUP', 'BLOCKED-HUMAN', 'BLOCKED-IMPOSSIBLE'):
            raise ValueError(identifier + ': a checklist entry may only start NOT RUN or BLOCKED-*, not ' + repr(status))
        out += ['- Actual result: ' + (check.get('evidence_of_unavailability') or ''), f'- Status: {status}', '']
    traceability = payload.get('traceability')
    if traceability and traceability.strip():
        out += ['## Traceability', '', traceability.strip(), '']
    return '\n'.join(out)

def write_checklist(project, checks):
    return write(project, 'MANUAL_CHECKLIST.md', {'schema':'uncle.artifact/v1', 'kind':'manual-checklist', 'checks':checks})
