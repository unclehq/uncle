#!/usr/bin/env python3
"""Authoritative structured workflow artifact storage and Markdown rendering."""
import json
from pathlib import Path
import re

_JSON_FENCE = re.compile(r'```(?:json)?\s*\n(.*?)\n```', re.S | re.I)
_WHOLE_JSON_FENCE = re.compile(r'^```(?:json)?\s*\n(.*?)\n```\s*$', re.S | re.I)

def _extract_balanced_object(text):
    """The LAST top-level {...} object in TEXT, honoring string quoting so a
    brace inside a JSON string value never miscounts nesting depth. None if
    TEXT has no top-level object at all.

    Last, not first: a model that narrates its reasoning before answering
    commonly echoes the schema contract itself as a reminder partway through
    -- often with placeholder or example field values -- before giving its
    real, complete answer at the end. Observed live: a response whose final
    answer was fully valid and self-consistent (six findings, all
    non-blocking, verdict READY WITH NON-BLOCKING ISSUES) got rejected
    because an earlier in-narration schema example ({"...","blocks":"YES"},
    verdict "READY") was extracted instead -- self-contradictory only
    because it was never meant to be read as an answer."""
    best = None
    position = 0
    length = len(text)
    while position < length:
        start = text.find('{', position)
        if start == -1:
            break
        depth = 0
        in_string = False
        escape = False
        end = None
        for index in range(start, length):
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
                    end = index
                    break
        if end is None:
            break
        best = text[start:end + 1]
        position = end + 1
    return best

_TRAILING_BACKTICK_SPAN = re.compile(r'`([^`]*)`\s*$', re.S)
_BARE_OBJECT_KEY = re.compile(r'([,{]\s*)([A-Za-z_$][A-Za-z0-9_$-]*)(\s*:)')
_TRAILING_COMMA = re.compile(r',\s*([}\]])')


def validate_protected_verification_paths(paths):
    """Validate the executable plan field, not its rendered Markdown view.

    This field is consumed as one repository-relative path per line by the
    verification-integrity guard.  Accepting prose here delayed a plan error
    until after implementation, where a whole sentence was treated as a path
    and incorrectly sent the run into REPAIR.
    """
    if not isinstance(paths, str) or not paths.strip():
        raise ValueError('plan is missing protected_verification_paths')
    for path in paths.splitlines():
        path = path.strip()
        normalized = path[:-1] if path.endswith('/') else path
        if (not path or ',' in path or path.startswith(('/', '-'))
                or '//' in path or '\\' in path
                or any(part in ('', '.', '..') for part in normalized.split('/'))
                or normalized == '.git' or normalized.startswith('.git/')
                or normalized == '.uncle' or normalized.startswith('.uncle/')):
            raise ValueError('protected_verification_paths must contain one valid repository-relative path per line: ' + path)


def _stream_envelope_text(candidate):
    """Return a model reply carried by a standard streamed-event envelope.

    Native clients and OpenCode may preserve their final assistant event as a
    JSON object whose actual reply is ``message.content[].text`` (or as a
    ``result`` string).  That envelope is transport, never an Uncle artifact;
    callers should validate the contained JSON instead of rejecting an
    otherwise complete plan/report merely because it was streamed.
    """
    try:
        event = json.loads(candidate)
    except (TypeError, ValueError):
        return candidate
    if not isinstance(event, dict):
        return candidate
    if event.get('type') == 'assistant':
        content = (event.get('message') or {}).get('content')
        if isinstance(content, list):
            texts = [part.get('text', '') for part in content
                     if isinstance(part, dict) and part.get('type') == 'text'
                     and isinstance(part.get('text'), str)]
            if texts:
                return '\n'.join(texts).strip()
    if event.get('type') == 'result' and isinstance(event.get('result'), str):
        return event['result'].strip()
    return candidate

def unfence_json(text):
    """A model asked for a bare JSON object commonly wraps it in a Markdown
    code fence anyway (the same habit every prompt in this codebase already
    has to guard against for the documents JSON is replacing), and just as
    commonly adds narration before or after it -- sometimes a lot of it --
    despite being told the object must be its entire reply. Observed live: a
    long response that narrated its reasoning at length, echoed the schema
    contract itself as a reminder partway through (its own decoy JSON-shaped
    example), and only gave the real, complete, self-consistent answer --
    wrapped in a single backtick -- as its very last line.

    A single fence-search-then-extract pass cannot handle that: whichever
    fenced or backtick-wrapped region it finds first may not be the answer
    at all. So build an ordered list of candidates, most-specific/rightmost
    first, and use the first one that is actually JSON-shaped:

    1. a backtick-wrapped span anchored at the end of the message (the
       common shape for "here is my final answer: `{...}`");
    2. each triple-backtick fenced block, most recent first;
    3. the whole message with one leading/trailing backtick stripped (a
       short response consisting of little but the wrapped object);
    4. the whole message as-is (an unwrapped bare object).

    Each candidate is accepted only if it starts with '{' -- a document
    that never looks JSON-shaped anywhere is returned unchanged, so a
    genuinely non-JSON response still falls through to its own parser, and
    an incidental brace inside ordinary prose (a code example mentioning a
    JS object literal, say) is never mistaken for an attempted answer."""
    stripped = text.strip()
    candidates = []
    trailing = _TRAILING_BACKTICK_SPAN.search(stripped)
    if trailing:
        candidates.append(trailing.group(1).strip())
    for match in reversed(list(_JSON_FENCE.finditer(stripped))):
        candidates.append(match.group(1).strip())
    candidates.append(stripped.strip('`').strip())
    candidates.append(stripped)
    for candidate in candidates:
        unwrapped = _stream_envelope_text(candidate)
        if unwrapped != candidate:
            # The event payload can be a fence, a narrated object, or bare
            # JSON; run the same candidate selection on its actual text.
            return unfence_json(unwrapped)
        candidate = unwrapped
        if candidate.startswith('{'):
            obj = _extract_balanced_object(candidate)
            if obj:
                return obj

    # A few self-hosted review models narrate their conclusion and then append
    # the requested bare JSON object on the same response, without a fence or
    # backticks.  That is still recoverable when the embedded object is real
    # JSON.  Require a successful parse here so ordinary Markdown that happens
    # to mention a JavaScript-looking `{foo: 1}` remains ordinary Markdown.
    embedded = _extract_balanced_object(stripped)
    if embedded:
        try:
            json.loads(embedded)
        except json.JSONDecodeError:
            pass
        else:
            return embedded
    return stripped


def standalone_json_document(text):
    """Return JSON only when the entire file is one JSON document.

    ``unfence_json`` intentionally recovers an object embedded in an LLM chat
    reply.  That behavior is wrong for a rendered Markdown artifact: plans
    may legitimately include a JSON launch-metadata example.  File-backed
    handoffs accept bare JSON or one complete JSON fence only; Markdown with
    an inline object stays Markdown.
    """
    candidate = text.strip()
    fence = _WHOLE_JSON_FENCE.match(candidate)
    if fence:
        candidate = fence.group(1).strip()
    if not candidate.startswith('{'):
        return None
    extracted = unfence_json(candidate)
    # Do not silently discard diagnostic prose after an apparent object.
    # Invalid JSON itself remains eligible so the caller can report the real
    # syntax error rather than treating it as Markdown.
    return extracted if extracted == candidate else None


def loads_response_json(text):
    """Parse a model JSON reply, repairing only unambiguous inner quotes.

    Some local models emit valid structure but forget to escape quotation marks
    in prose evidence (for example, ``input like "1+alert(1)"``).  A quote
    inside a JSON string is unambiguously not its terminator when the next
    non-whitespace character is not a JSON structural delimiter.  Escape only
    that narrow case, then let normal JSON/schema validation decide validity.
    """
    candidate = unfence_json(text)
    try:
        return json.loads(candidate)
    except json.JSONDecodeError as original:
        out, in_string, escaped = [], False, False
        length = len(candidate)
        changed = False
        for index, char in enumerate(candidate):
            if not in_string:
                out.append(char)
                if char == '"':
                    in_string = True
                continue
            if escaped:
                out.append(char); escaped = False; continue
            if char == '\\':
                out.append(char); escaped = True; continue
            if char != '"':
                out.append(char); continue
            next_index = index + 1
            while next_index < length and candidate[next_index].isspace():
                next_index += 1
            next_char = candidate[next_index] if next_index < length else ''
            if next_char in ',}]:':
                out.append(char); in_string = False
            else:
                out.append('\\"'); changed = True
        repaired = ''.join(out) if changed else candidate
        try:
            return json.loads(repaired)
        except json.JSONDecodeError:
            # A few models emit a JavaScript-object-looking response:
            # `{ schema: "...", kind: "...", }`.  Quoting only identifier
            # keys and dropping a comma immediately before ] or } is
            # unambiguous.  Do not attempt broader syntax recovery: malformed
            # strings, truncated arrays, and prose still fail closed below.
            structural = _TRAILING_COMMA.sub(r'\1', _BARE_OBJECT_KEY.sub(r'\1"\2"\3', repaired))
            if structural == repaired:
                raise original
            try:
                return json.loads(structural)
            except json.JSONDecodeError:
                raise original

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
    # Rows are the sole authoritative representation of the acceptance gate.
    # Some models redundantly paste a complete Markdown gate into `narrative`;
    # retaining it would render two gates and make an otherwise valid JSON
    # artifact fail its presentation-only validator.
    if narrative:
        narrative = re.split(r'^## Acceptance gate[ \t\r]*$', narrative, maxsplit=1, flags=re.M)[0].rstrip()
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

def _render_dispositions_table(dispositions):
    """Build the '## Adversarial review dispositions' table lines, shared by
    render_plan() and render_change_plan(). Every field access is checked and
    raises a clear ValueError naming the finding and field, rather than
    crashing with an unhandled KeyError -- seen live when a model wrote
    disposition objects keyed "id"/"status"/"rationale" instead of
    "finding"/"disposition"/"reason"/"plan_change": the bare `row['finding']`
    lookup took down the whole driver process instead of failing the
    document validation the way every other malformed-field case here does."""
    seen = set()
    lines = ['## Adversarial review dispositions', '',
             '| Finding | Disposition | Reason | Exact plan change |', '|---|---|---|---|']
    esc = lambda value: str(value).replace('|', r'\|').replace('\n', ' ')
    for index, row in enumerate(dispositions):
        if not isinstance(row, dict):
            raise ValueError('disposition entry %d is not an object' % index)
        finding = row.get('finding')
        if not finding:
            raise ValueError('disposition entry %d is missing "finding"' % index)
        if finding in seen:
            raise ValueError('duplicate disposition for finding: ' + finding)
        seen.add(finding)
        disposition = row.get('disposition')
        if disposition not in ('Accepted', 'Partially accepted', 'Rejected', 'Deferred'):
            raise ValueError('invalid disposition for %s: %r' % (finding, disposition))
        for field in ('reason', 'plan_change'):
            if field not in row:
                raise ValueError('disposition for %s is missing "%s"' % (finding, field))
        lines.append('| %s | %s | %s | %s |' % (finding, disposition, esc(row['reason']), esc(row['plan_change'])))
    lines.append('')
    return lines


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
        validate_protected_verification_paths(paths)
        lines += ['## Protected verification paths', '', '```text', paths.strip('\n'), '```', '']
    dispositions = payload.get('dispositions')
    if dispositions:
        lines += _render_dispositions_table(dispositions)
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
    # The driver runs this field verbatim as shell input (verify_commands()),
    # never just reads it. Observed (canopy issue #4): a line written as
    # "pytest -q  => 28 passed" -- command and claimed result on one line --
    # is not a comment to a shell; it is a syntax error, so the driver's own
    # re-run of that line fails every time while the line's own trailing text
    # still looks like a passing result to anyone reading it, which is a
    # regression check silently turned off, not a loud one. `=>` has no
    # meaning in sh/bash, so its presence on a command line is unambiguous.
    bad = [line for line in commands.splitlines() if '=>' in line]
    if bad:
        raise ValueError(
            'verification_commands has a result appended to a command line '
            '(contains "=>"), which the driver would run verbatim and fail '
            'on every re-execution -- put only the bare command on each '
            'line and report what it produced in section 9 instead: '
            + '; '.join(bad)
        )
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
    # An explicit empty list is the correct, deliberate answer when the
    # adversarial review had zero findings -- there is nothing to
    # disposition. Only an omitted key (None) is the actual contract
    # violation this guards against. `not dispositions` used to reject both
    # the same way, failing a plan that had faithfully reported no findings.
    if require_dispositions and dispositions is None:
        # Observed (canopy issue #4): an agent wrote a complete, correctly
        # structured disposition table under a plausible but wrong key
        # (`disposition_table`) and got this same generic message back on
        # retry. Nothing in it said *which* key was wrong, so it read as "add
        # more content" rather than "rename the field", and the retry failed
        # identically. Naming the exact required key and what was actually
        # found lets the agent fix the one thing that matters in one turn.
        found = ', '.join(sorted(payload.keys())) if isinstance(payload, dict) else 'not an object'
        raise ValueError(
            'change-plan is missing dispositions for the adversarial review: '
            'the JSON key must be exactly "dispositions" (a list); this payload\'s '
            'top-level keys are: %s' % found
        )
    lines = [narrative.strip(), '']
    if dispositions:
        lines += _render_dispositions_table(dispositions)
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
