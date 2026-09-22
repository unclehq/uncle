"""Focused final-audit evidence and format-only validation."""
import hashlib
import importlib.util
from pathlib import Path
import re
import sys


def normalize_findings_shape(text):
    """Coerce a close-but-malformed audit into the exact shape `findings()`
    requires, without touching a finding's content, evidence, or verdict.

    Seen twice on the same real audit: a well-formed table (six rows, real
    evidence citations) under a `# Final audit` heading instead of the
    required `## Findings`, and a `Correction` column instead of `Required
    correction`. Both retries this file already has -- the driver's own
    one-shot format retry, and self_hosted.py's generic invalid-document
    retry -- reproduced the identical wrong shape a second time: asking
    again does not fix a model that believes the top-level heading already
    satisfies the requirement. Returns the corrected text, or the original
    text unchanged when no recognizable table is found (validate() then
    reports the real problem).
    """
    lines = text.splitlines()
    # Self-hosted reviewers commonly return complete F-identified prose
    # findings instead of the table the driver consumes.  This is structured
    # enough to render deterministically: retain every stated field, escape
    # table separators, and never manufacture a finding, correction or block.
    prose = []
    current = None
    for line in lines:
        found = re.match(r'^###\s+(F[0-9]+)\s*:\s*(.+)$', line)
        if found:
            if current: prose.append(current)
            current = {'id': found.group(1), 'title': found.group(2), 'evidence': '', 'correction': '', 'blocks': ''}
            continue
        if current:
            field = re.match(r'^-\s+\*\*(Evidence|Correction|Blocks)\*\*:\s*(.*)$', line, re.I)
            if field:
                key = {'evidence': 'evidence', 'correction': 'correction', 'blocks': 'blocks'}[field.group(1).lower()]
                value = field.group(2).strip()
                # `Blocks: YES — reason` is a common prose spelling. The
                # machine column receives only YES/NO; retain the reason in
                # evidence so no audit information is lost.
                if key == 'blocks':
                    marker = re.match(r'^(YES|NO)\b\s*(?:—|-)?\s*(.*)$', value, re.I)
                    if marker:
                        current[key] = marker.group(1).upper()
                        if marker.group(2):
                            current['evidence'] += (' ' if current['evidence'] else '') + 'Blocks rationale: ' + marker.group(2)
                    else:
                        current[key] = value
                else:
                    current[key] = value
    if current: prose.append(current)
    if prose and all(item['evidence'] and item['correction'] and item['blocks'].upper() in ('YES', 'NO') for item in prose):
        verdict = re.search(r'^(?:NOT READY|READY WITH NON-BLOCKING ISSUES|READY)\b', text.strip().splitlines()[-1].strip(), re.I)
        if verdict:
            esc = lambda value: value.replace('|', r'\|').replace('\n', ' ')
            table = ['## Findings', '', '| ID | Severity | Evidence | Affected requirement | Required correction | Blocks |',
                     '|---|---|---|---|---|---|']
            for item in prose:
                table.append('| %s | %s | %s | %s | %s | %s |' %
                             (item['id'], 'Unspecified', esc(item['evidence']), 'Not stated',
                              esc(item['correction']), item['blocks'].upper()))
            return '\n'.join(table + ['', verdict.group(0).upper()]) + '\n'
    table_start = None
    for i in range(len(lines) - 1):
        line = lines[i].strip()
        if not (line.startswith('|') and line.endswith('|')):
            continue
        header = [cell.strip('*_ ').lower() for cell in line[1:-1].split('|')]
        if 'id' not in header or not any(cell in ('blocks', 'blocks completion') for cell in header):
            continue
        if re.fullmatch(r'\|(?:\s*:?-{3,}:?\s*\|)+', lines[i + 1].strip()):
            table_start = i
            break
    if table_start is None:
        return text
    # Independent of each other: a real audit has shown up missing the
    # heading with a correct column name, and -- reproduced on a separate
    # run -- with the heading present and only the column name wrong. An
    # early return on "heading already there" skipped the column check
    # entirely that second time and let this exact failure straight through.
    has_heading = re.search(r'^##\s+Findings\s*$', text, re.M)
    if not has_heading:
        lines[table_start:table_start] = ['## Findings', '']
        table_start += 2
    header_index = table_start
    cells = lines[header_index][1:-1].split('|')
    for i, cell in enumerate(cells):
        if cell.strip('*_ ').lower() in ('correction', 'fix', 'required fix', 'suggested correction'):
            cells[i] = ' Required correction '
    lines[header_index] = '|' + '|'.join(cells) + '|'
    return '\n'.join(lines) + ('\n' if text.endswith('\n') else '')


def export_json(payload, path, project='.'):
    """Write the reviewer's structured verdict as the canonical artifact and
    render the deterministic Markdown the rest of the driver still reads."""
    import json
    target = Path(project) / '.uncle/workflow/documents/FINAL_AUDIT.json'
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(dict(payload, schema='uncle.artifact/v1', kind='final-audit'), indent=2) + '\n')
    artifact = Path(__file__).with_name('artifact_json.py')
    spec = importlib.util.spec_from_file_location('artifact_json', artifact)
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    Path(path).write_text(module.render_final_audit(payload), encoding='utf-8')


def validate(path, project='.'):
    path = Path(path)
    text = path.read_text(encoding='utf-8')
    stripped = text.strip()
    if stripped.startswith('{'):
        # The reviewer returned the structured verdict directly: no prose or
        # table shape to coerce, because there is no prose or table -- the
        # normalize_findings_shape() heuristics below exist only to recover
        # meaning from free text, and a JSON response was never free text.
        import json as _json
        try:
            payload = _json.loads(stripped)
        except ValueError as error:
            raise ValueError('Invalid final-audit JSON response: ' + str(error)) from error
        if payload.get('schema') != 'uncle.artifact/v1' or payload.get('kind') != 'final-audit':
            raise ValueError('wrong final-audit JSON schema')
        required = ('id', 'severity', 'evidence', 'required_correction', 'blocks')
        for finding in payload.get('findings', []):
            if not isinstance(finding, dict) or any(not finding.get(key) for key in required):
                raise ValueError('invalid final-audit finding: missing a required field')
            if finding['blocks'] not in ('YES', 'NO'):
                raise ValueError('finding blocks must be YES or NO')
        if payload.get('verdict') not in ('READY', 'READY WITH NON-BLOCKING ISSUES', 'NOT READY'):
            raise ValueError('missing or invalid final-audit verdict')
        blocking = [f for f in payload.get('findings', []) if f['blocks'] == 'YES']
        if blocking and payload['verdict'] != 'NOT READY':
            raise ValueError('Ready verdict contradicts blocking findings')
        if not blocking and payload['verdict'] == 'NOT READY':
            raise ValueError('NOT READY verdict requires at least one blocking finding')
        export_json(payload, path, project)
        return
    last = text.strip().splitlines()[-1].strip().strip('#*_ ')
    last = re.sub(r'^Conclusion:[ \t]*', '', last).strip('*_ ')
    # Normalize a complete prose audit before enforcing the machine verdict.
    # This is driver-owned rendering, not a second model request.
    if last not in ('READY', 'READY WITH NON-BLOCKING ISSUES', 'NOT READY'):
        rendered = normalize_findings_shape(text)
        if rendered != text:
            text = rendered
            last = text.strip().splitlines()[-1].strip()
    if last not in ('READY', 'READY WITH NON-BLOCKING ISSUES', 'NOT READY'):
        raise ValueError('Missing final audit verdict')
    spec = importlib.util.spec_from_file_location('audit_findings', Path(__file__).with_name('audit-findings.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    # Normalize only the verdict decoration accepted by the driver's classifier.
    body = text.strip().rsplit('\n', 1)[0] + '\n' + last + '\n'
    try:
        blockers = module.findings(body, require_blockers=last == 'NOT READY')
    except ValueError:
        normalized = normalize_findings_shape(body)
        if normalized == body:
            raise
        blockers = module.findings(normalized, require_blockers=last == 'NOT READY')
        # Only reached once the normalized shape actually parses: write the
        # corrected document back so downstream stages read the same text
        # this validation just accepted, exactly like the manual repair this
        # replaces.
        path.write_text(normalized, encoding='utf-8')
    else:
        if text != path.read_text(encoding='utf-8'):
            path.write_text(text, encoding='utf-8')
    if blockers and last != 'NOT READY':
        raise ValueError('Ready verdict contradicts blocking findings')


def fallback(path, reason='reviewer response could not be parsed'):
    """Persist an unparseable reviewer response as a safe blocking audit."""
    Path(path).write_text(
        '# Final audit\n\n## Findings\n\n'
        '| ID | Severity | Evidence | Affected requirement | Required correction | Blocks |\n'
        '|---|---|---|---|---|---|\n'
        f'| AUDIT-FORMAT | Blocking | {reason.replace("|", "/")} | Audit artifact | Produce a complete audit with observed findings and a supported verdict. | YES |\n\n'
        'NOT READY\n', encoding='utf-8')


def render(project, state):
    project, state = Path(project).resolve(), Path(state).resolve()
    files = [(project / n, 3000) for n in ('.uncle/docs/VERIFICATION_REPORT.md', '.uncle/docs/DEFECTS.md', '.uncle/docs/MANUAL_CHECKLIST.md')]
    files += [(state / n, 3000) for n in ('delivery-summary.tsv', 'implementation-completion.txt', 'checklist-driver-checks/results.tsv')]
    files += [(state / 'change.diff', 0), (state / 'checklist-driver-checks/output.log', 0)]
    files += [(p, 1000) for p in sorted((state / 'waivers').glob('*')) if p.is_file()]
    lines = ['\n## Driver final-audit evidence packet',
             'Current inventory; hashes are identities, not PASS evidence.',
             'Excerpts may omit rows. Read required inputs and relevant evidence directly.']
    budget = 24000
    for path, limit in files:
        if not path.resolve().is_relative_to(project):
            continue
        try:
            digest, excerpt, size = hashlib.sha256(), b'', 0
            with path.open('rb') as stream:
                while chunk := stream.read(65536):
                    digest.update(chunk)
                    size += len(chunk)
                    excerpt += chunk[:max(0, min(limit, budget) - len(excerpt))]
            lines.append(f'\n{path}: {size} bytes; SHA-256 {digest.hexdigest()}')
            lines.append(excerpt.decode('utf-8', errors='replace'))
            budget -= len(excerpt)
            if len(excerpt) < size:
                lines.append('[Read remaining contents directly.]')
        except OSError:
            lines.append(f'{path}: unavailable; no evidence inferred.')
    return '\n'.join(lines) + '\n'


if __name__ == '__main__':
    if sys.argv[1] == '--fallback':
        fallback(sys.argv[2], ' '.join(sys.argv[3:]) or 'reviewer response could not be parsed')
        raise SystemExit(0)
    if sys.argv[1] == '--validate':
        try:
            validate(sys.argv[2])
        except (OSError, ValueError, IndexError) as error:
            print(f'Audit format invalid: {error}. Correct .uncle/docs/FINAL_AUDIT.md and resume; no checks need rerunning.', file=sys.stderr)
            raise SystemExit(1)
    else:
        print(render(*sys.argv[1:3]), end='')
