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


def findings(text):
    """Read the Findings table; reject ambiguity rather than omit blockers."""
    sections = re.split(r'^##\s+Findings\s*$', text, flags=re.M)
    if len(sections) != 2:
        raise ValueError('Expected exactly one ## Findings section')
    section = re.split(r'^##\s+', sections[1], maxsplit=1, flags=re.M)[0]
    # A bare final verdict belongs to the report, not the table. Reviewers
    # also sometimes wrap the table in a Markdown fence. Neither changes rows.
    lines = []
    verdict_seen = False
    for raw in section.splitlines():
        line = raw.strip()
        if not line or re.fullmatch(r"```(?:markdown|md)?|~~~(?:markdown|md)?", line):
            continue
        if re.fullmatch(r"(?:\*\*|__)?NOT READY(?:\*\*|__)?", line):
            if verdict_seen or not lines:
                raise ValueError('Unexpected audit verdict in findings table')
            verdict_seen = True
            continue
        if verdict_seen:
            raise ValueError('Unexpected content after the audit verdict')
        lines.append(line)
    if len(lines) < 3 or any(not line.startswith('|') or not line.endswith('|') for line in lines):
        raise ValueError('Findings must be a table with ID and Blocks columns')
    rows = [[cell.strip().replace(r'\|', '|') for cell in re.split(r'(?<!\\)\|', line[1:-1])] for line in lines]
    header = [cell.lower() for cell in rows[0]]
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
        if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_./-]*', identifier) or identifier in seen:
            raise ValueError('Invalid or duplicate finding ID: ' + identifier)
        if blocks not in ('YES', 'NO') or not item['evidence'] or not item['required correction']:
            raise ValueError('Missing finding evidence, correction, or YES/NO blocking status')
        seen.add(identifier)
        if blocks == 'YES':
            result.append(item)
    if not result:
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


def accepted(record, identifier):
    return record['decisions'].get(identifier, {}).get('decision') in ACCEPTED_DECISIONS


def review(report, state_dir, check_only=False):
    original = report.read_bytes()
    sha = hashlib.sha256(original).hexdigest()
    blockers = findings(original.decode('utf-8'))
    path = state_dir / 'audit-dispositions' / (sha + '.json')
    record = {'audit_sha256': sha, 'auditor_verdict': 'NOT_READY', 'effective_verdict': 'NOT_READY', 'decisions': {}}
    if path.exists():
        record = json.loads(path.read_text(encoding="utf-8"))
        if record.get('audit_sha256') != sha or not isinstance(record.get('decisions'), dict):
            raise ValueError('Invalid saved audit decisions')
    if check_only:
        return 0 if all(accepted(record, item['id']) for item in blockers) else 1
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
    args = parser.parse_args()
    try:
        return review(args.report, args.state_dir, args.check)
    except (OSError, ValueError, KeyError, TypeError) as error:
        print('Audit finding review stopped: ' + str(error), flush=True)
        return 2


if __name__ == '__main__':
    import sys
    sys.stdout.reconfigure(encoding="utf-8", newline="\n")
    raise SystemExit(main())
