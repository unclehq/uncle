#!/usr/bin/env python3
"""Collect explicit per-finding decisions without rewriting the auditor's report."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import tempfile


def findings(text, require_blockers=True):
    """Read the Findings table; reject ambiguity rather than omit blockers."""
    sections = re.split(r'^##\s+Findings\s*$', text, flags=re.M)
    if len(sections) != 2:
        raise ValueError('Expected exactly one ## Findings section')
    section = re.split(r'^##\s+', sections[1], maxsplit=1, flags=re.M)[0]
    # A bare final verdict belongs to the report, not the table. Reviewers
    # also sometimes wrap the table in a Markdown fence. Neither changes rows.
    lines = []
    verdict_seen = False
    commentary = []
    table_ended = False
    for raw in section.splitlines():
        line = raw.strip()
        line = re.sub(r'^Conclusion:[ \t]*', '', line)
        if not line:
            if len(lines) >= 3:
                table_ended = True
            continue
        if re.fullmatch(r"```(?:markdown|md)?|~~~(?:markdown|md)?", line):
            continue
        if re.fullmatch(r"(?:\*\*|__)?(?:NOT READY|READY WITH NON-BLOCKING ISSUES|READY)(?:\*\*|__)?", line):
            if verdict_seen or not lines:
                raise ValueError('Unexpected audit verdict in findings table')
            verdict_seen = True
            continue
        if verdict_seen:
            raise ValueError('Unexpected content after the audit verdict')
        # Preserve separated prose in the human review; never silently drop it.
        # Table-shaped content after prose is ambiguous and remains an error.
        if table_ended and not line.startswith('|') and not line.endswith('|'):
            commentary.append(line)
            continue
        if commentary:
            raise ValueError('Unexpected table row after audit commentary')
        lines.append(line)
    if len(lines) < 2 or any(not line.startswith('|') or not line.endswith('|') for line in lines):
        raise ValueError('Findings must be a table with ID and Blocks columns')
    rows = [[cell.strip().replace(r'\|', '|') for cell in re.split(r'(?<!\\)\|', line[1:-1])] for line in lines]
    # Bold/italic header cells ("**ID**", "__Blocks__") are a recurring model
    # habit this codebase already tolerates for other table headers
    # (checklist_document.py's LABEL_SYNONYMS, envelope.py's SEVERITY_FIELD);
    # matching column names is about their content, not their markup.
    header = [cell.strip('*_ ').lower() for cell in rows[0]]
    if len(set(header)) != len(header) or 'id' not in header:
        raise ValueError('Missing or duplicate finding columns')
    block_columns = [i for i, cell in enumerate(header) if cell in ('blocks', 'blocks completion')]
    if len(block_columns) != 1 or 'evidence' not in header or 'required correction' not in header:
        raise ValueError('Expected Evidence, Required correction, and Blocks columns')
    if len(rows[1]) != len(header) or any(not re.fullmatch(r':?-{3,}:?', cell) for cell in rows[1]):
        raise ValueError('Invalid findings table separator')
    result, seen = [], set()
    for row in rows[2:]:
        if len(row) != len(header):
            raise ValueError('Invalid findings row width; escape descriptions without literal pipes')
        item = dict(zip(header, row))
        identifier, blocks = item['id'], row[block_columns[0]].upper()
        # A trailing "(High)"/"(Blocking)" annotation echoes the same
        # severity marker FINDING_HEADING already tolerates on the review's
        # own heading (envelope.py) -- a model carrying that shape into its
        # own ID cell here is still naming one finding, not adding noise to
        # its identity.
        match = re.fullmatch(r'([A-Za-z0-9][A-Za-z0-9_./-]*)(?:\s*\([^()\n]*\))?', identifier)
        if not match or match.group(1) in seen:
            raise ValueError('Invalid or duplicate finding ID: ' + identifier)
        identifier = item['id'] = match.group(1)
        if blocks not in ('YES', 'NO') or not item['evidence'] or not item['required correction']:
            raise ValueError('Missing finding evidence, correction, or YES/NO blocking status')
        seen.add(identifier)
        if blocks == 'YES':
            if commentary:
                item['evidence'] += ' — Audit commentary: ' + ' '.join(commentary)
            result.append(item)
    if require_blockers and not result:
        raise ValueError('NOT READY audit has no explicit blocking findings')
    return result


def findings_payload(payload, require_blockers=True):
    """Read blocking findings from the canonical final-audit packet."""
    if (not isinstance(payload, dict) or payload.get('schema') != 'uncle.artifact/v1'
            or payload.get('kind') != 'final-audit'):
        raise ValueError('Invalid final-audit JSON')
    if payload.get('verdict') != 'NOT READY':
        return []
    result, seen = [], set()
    for item in payload.get('findings', []):
        if not isinstance(item, dict):
            raise ValueError('Invalid audit finding')
        identifier = item.get('id')
        if not isinstance(identifier, str) or not identifier or identifier in seen:
            raise ValueError('Invalid or duplicate finding ID: ' + str(identifier))
        seen.add(identifier)
        if item.get('blocks') not in ('YES', 'NO') or not item.get('evidence') or not item.get('required_correction'):
            raise ValueError('Missing finding evidence, correction, or YES/NO blocking status')
        if item['blocks'] == 'YES':
            entry = {'id': identifier, 'evidence': item['evidence'],
                     'required correction': item['required_correction'], 'blocks': 'YES'}
            if isinstance(item.get('severity'), str):
                entry['severity'] = item['severity']
            result.append(entry)
    if require_blockers and not result:
        raise ValueError('NOT READY audit has no explicit blocking findings')
    return result


def save(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(dir=path.parent, prefix='.decisions-')
    try:
        with os.fdopen(fd, 'w', encoding='utf-8', newline='\n') as stream:
            json.dump(data, stream, indent=2)
            stream.write('\n')
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


ACCEPTED_DECISIONS = {'ignore', 'skip', 'human-reviewed'}


def accepted(record, identifier, allow_unattended=False):
    """A machine waiver (mode: unattended) counts only for an unattended run."""
    entry = record['decisions'].get(identifier, {})
    if entry.get('mode') == 'unattended' and not allow_unattended:
        return False
    return entry.get('decision') in ACCEPTED_DECISIONS


def ledger_text(sha, identifier):
    return identifier + ' accepted without human review (audit ' + sha[:12] + ')'


def reconcile_ledger(ledger, sha, record, blockers):
    """Ledger every unattended waiver that has no line yet; never duplicate."""
    if ledger is None:
        return
    try:
        existing = ledger.read_text(encoding='utf-8') if ledger.exists() else ''
    except OSError:
        existing = ''
    lines = []
    for item in blockers:
        entry = record['decisions'].get(item['id'], {})
        if entry.get('mode') != 'unattended':
            continue
        detail = ledger_text(sha, item['id'])
        if ('\taudit-finding-skipped\t' + detail) in existing:
            continue
        lines.append('\t'.join((datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'),
                                'audit-finding-skipped', detail)) + '\n')
    if lines:
        ledger.parent.mkdir(parents=True, exist_ok=True)
        with open(ledger, 'a', encoding='utf-8', newline='\n') as stream:
            stream.writelines(lines)


def review_unattended(report, original, sha, path, record, blockers, ledger):
    """Record a labelled skip for every unaccepted blocker; never prompt."""
    print('AUDIT REVIEW (unattended): ' + str(report), flush=True)
    for item in blockers:
        identifier = item['id']
        if accepted(record, identifier, True):
            continue
        record['decisions'][identifier] = {
            'decision': 'skip',
            'mode': 'unattended',
            'recorded_at': datetime.now(timezone.utc).isoformat(),
            'approved_by': 'unattended',
            'finding': item,
        }
    if report.read_bytes() != original:
        raise ValueError('Audit changed during review; review the updated report')
    record['effective_verdict'] = 'READY'
    save(path, record)
    reconcile_ledger(ledger, sha, record, blockers)
    waived = [item for item in blockers if record['decisions'][item['id']].get('mode') == 'unattended']
    print(f'{len(waived)} blocking audit findings skipped', flush=True)
    for item in waived:
        severity = item.get('severity')
        print('  ' + item['id'] + (' (' + severity + ')' if severity else '') + ': accepted without human review', flush=True)
    print('Build verdict: READY - ' + str(len(waived)) + ' blocking findings WAIVED WITHOUT HUMAN REVIEW (the auditor said NOT READY)')
    print('Audit decisions: ' + str(path))
    return 0


def review(report, state_dir, check_only=False, unattended=False, ledger=None):
    original = report.read_bytes()
    sha = hashlib.sha256(original).hexdigest()
    if report.suffix == '.json':
        blockers = findings_payload(json.loads(original.decode('utf-8')))
    else:
        blockers = findings(original.decode('utf-8'))
    path = state_dir / 'audit-dispositions' / (sha + '.json')
    record = {'audit_sha256': sha, 'auditor_verdict': 'NOT_READY', 'effective_verdict': 'NOT_READY', 'decisions': {}}
    if path.exists():
        record = json.loads(path.read_text(encoding="utf-8"))
        if record.get('audit_sha256') != sha or not isinstance(record.get('decisions'), dict):
            raise ValueError('Invalid saved audit decisions')
    if check_only:
        machine = [item['id'] for item in blockers if record['decisions'].get(item['id'], {}).get('mode') == 'unattended']
        if machine:
            print('Unattended waivers (no human review): ' + ', '.join(machine), flush=True)
        return 0 if all(accepted(record, item['id'], unattended) for item in blockers) else 1
    if unattended:
        return review_unattended(report, original, sha, path, record, blockers, ledger)
    print('AUDIT REVIEW REQUIRED: ' + str(report), flush=True)
    for index, item in enumerate(blockers, 1):
        identifier = item['id']
        previous = record['decisions'].get(identifier, {})
        if accepted(record, identifier):
            print(identifier + ': already accepted (' + previous['decision'] + ') for this audit.', flush=True)
            continue
        # One unterminated line is the existing TUI modal protocol. Keep the
        # full evidence in scrollback and the complete correction in the modal.
        print('\n' + identifier + ': ' + item['evidence'], flush=True)
        prompt = (f'Audit finding {identifier} ({index}/{len(blockers)}). '
                  f'Evidence: {item["evidence"]} '
                  f'Required correction: {item["required correction"]} '
                  'Choose [s] Skip, [r] Human reviewed — OK, [n] Keep blocking: ')
        # Attended path only: --unattended never reaches this prompt (see
        # review_unattended). Under the TUI stdin is a live modal pipe, so this
        # prompt is answered by the owner; EOF leaves the audit pending.
        while True:
            try:
                answer = input(prompt).strip().lower()
            except EOFError:
                print('\nNo decision received; audit remains pending.', flush=True)
                return 1
            if answer in ('s', 'r', 'y', 'n'):
                break
            print('Choose S to skip, R to confirm human review, or N to keep blocking.', flush=True)
        if report.read_bytes() != original:
            raise ValueError('Audit changed during review; review the updated report')
        record['decisions'][identifier] = {
            'decision': {'s': 'skip', 'r': 'human-reviewed', 'y': 'ignore'}.get(answer, 'keep'),
            'recorded_at': datetime.now(timezone.utc).isoformat(),
            'approved_by': os.environ.get('UNCLE_APPROVAL_NAME', ''),
            'finding': item,
        }
        record['effective_verdict'] = 'NOT_READY'
        save(path, record)
    if report.read_bytes() != original:
        raise ValueError('Audit changed during review; review the updated report')
    ready = all(accepted(record, item['id']) for item in blockers)
    record['effective_verdict'] = 'READY' if ready else 'NOT_READY'
    save(path, record)
    if ready:
        print(f'Build verdict: READY — all {len(blockers)} blocking audit findings accepted by the human.')
    else:
        remaining = [item['id'] for item in blockers if not accepted(record, item['id'])]
        print('Build verdict: NOT READY — still blocking: ' + ', '.join(remaining))
    print('Audit decisions: ' + str(path))
    return 0 if ready else 1


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('report', type=Path)
    parser.add_argument('state_dir', type=Path)
    parser.add_argument('--check', action='store_true', help='Validate saved decisions without prompting')
    parser.add_argument('--unattended', action='store_true',
                        help='Record every unaccepted blocker as a labelled skip without prompting')
    parser.add_argument('--ledger', type=Path, help='Unattended-gates ledger to append skipped findings to')
    args = parser.parse_args()
    try:
        return review(args.report, args.state_dir, args.check, args.unattended, args.ledger)
    except (OSError, ValueError, KeyError, TypeError) as error:
        print('Audit finding review stopped: ' + str(error), flush=True)
        return 2


if __name__ == '__main__':
    import sys
    sys.stdout.reconfigure(encoding="utf-8", newline="\n")
    raise SystemExit(main())
