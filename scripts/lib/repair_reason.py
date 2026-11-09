#!/usr/bin/env python3
"""Say why a repair is about to run and exactly what it is meant to fix.

    repair_reason.py <state-dir> <repair-source> <attempt> <limit>

Read-only. `repair-source` is the file the driver recorded as the trigger; the findings come from the driver's own records
(green-check.tsv, TEST_REVIEW.md, VERIFICATION_INTEGRITY.md, ...), never from a model. Prints Markdown to stdout.
"""
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import failure_severity as severity  # noqa: E402

MAX_ITEMS = 8
MAX_TEXT = 220


def read(path):
    try:
        with open(path, encoding='utf-8', errors='replace') as handle:
            return handle.read()
    except OSError:
        return ''


def clip(text):
    text = re.sub(r'\s+', ' ', text).strip()
    return text if len(text) <= MAX_TEXT else text[:MAX_TEXT - 1].rstrip() + '…'


def table_rows(text):
    for line in text.splitlines():
        if line.startswith('|') and not re.match(r'^\|[\s:-]+\|', line):
            yield [cell.strip() for cell in line.strip().strip('|').split('|')]


def failing_rows(text, id_col=0, status_col=2, evidence_col=3):
    """Rows of a 'ID | Required | Status | Evidence' table whose status is a failure."""
    out = []
    for cells in table_rows(text):
        if len(cells) > max(status_col, evidence_col) and cells[status_col].upper() in ('FAIL', 'FAILED', 'BLOCKED', 'NOT RUN'):
            out.append((cells[id_col], cells[status_col], cells[evidence_col]))
    return out


def green_failures(state):
    out = []
    for line in read(os.path.join(state, 'green-check.tsv')).splitlines():
        status, _, command = line.partition('\t')
        if status and status != 'PASS' and command:
            label = 'defect-injection check did not pass' if status == 'MUTATION' else 'failed'
            out.append('`%s` -- %s (%s)' % (command, label, status))
    return out


def integrity_files(state):
    """Protected files that differ from the recorded manifest, read from the unified diff the check wrote."""
    plus, minus = {}, {}
    for line in read(os.path.join(state, 'verification-integrity.log')).splitlines():
        match = re.match(r'^([+-])([0-9a-f]{64}|ABSENT|DIRECTORY)\t(.+)$', line)
        if match:
            (plus if match.group(1) == '+' else minus)[match.group(3)] = match.group(2)
    changed = []
    for path in sorted(set(plus) | set(minus)):
        before, after = minus.get(path), plus.get(path)
        if before and after:
            changed.append('`%s` -- content changed' % path)
        elif before:
            changed.append('`%s` -- deleted' % path)
        else:
            changed.append('`%s` -- appeared' % path)
    return changed


def lines_matching(text, pattern):
    return [clip(line) for line in text.splitlines() if re.search(pattern, line)]


def explain(state, source, attempt, limit):
    name = os.path.basename(source) if source else ''
    out = ['## Why repair is running', '']
    out.append('Repair attempt %s of %s.' % (attempt, limit))
    items, trigger, deferred = [], '', []
    if name == 'green-check.md':
        trigger = "The driver's own verification commands failed."
        items = green_failures(state)
    elif name == 'TEST_REVIEW.md':
        trigger = 'The independent test review failed required rows.'
        rows = failing_rows(read(os.path.join(os.path.dirname(state), 'docs', 'TEST_REVIEW.md')))
        items = ['**%s** %s: %s' % (i, s, clip(e)) for i, s, e in rows if True]
    elif name == 'VERIFICATION_INTEGRITY.md':
        trigger = 'A protected verification input changed (tests, fixtures, oracles or test configuration), and the check allows no such change.'
        items = integrity_files(state)
    elif name == 'FINAL_AUDIT.md':
        trigger = 'The final audit did not say the build is ready.'
        repair, left = severity.audit_split(os.path.join(state, 'documents', 'FINAL_AUDIT.json'))
        items = severity.critical_items(os.path.join(state, 'green-check.tsv'), os.path.join(state, 'logs', 'green-check.log')) \
            + [severity.audit_line(f) for f in repair]
        deferred = [(f.get('id'), str(f.get('severity', '')).upper(), why) for f, why in left]
        if not items and not left:
            items = lines_matching(read(os.path.join(os.path.dirname(state), 'docs', 'FINAL_AUDIT.md')), r'NOT_READY|\bBLOCK|blocking')
    elif name == 'VERIFICATION_REPORT.md' or source == 'checklist-fail':
        trigger = 'Manual checklist checks failed.'
        report = read(os.path.join(os.path.dirname(state), 'docs', 'VERIFICATION_REPORT.md'))
        report = report.rpartition('## Acceptance gate')[2] or report
        rows = failing_rows(report, 0, 2, 3)
        items = ['**%s** %s: %s' % (i, s, clip(e)) for i, s, e in rows]
    elif name == 'runtime-unrunnable-application':
        trigger = 'The application could not be started.'
        items = lines_matching(read(source), r'\S')[:MAX_ITEMS]
    else:
        trigger = 'Trigger recorded as `%s`.' % (source or 'unknown')
        items = lines_matching(read(source), r'\S')[:MAX_ITEMS] if source and os.path.exists(source) else []
    if name in ('TEST_REVIEW.md', 'green-check.md') and os.environ.get('WORKFLOW_REPAIR_SEVERITY', 'critical') == 'critical':
        # Repair is for critical failures only: say which ones, and which failing rows it will leave alone.
        critical = severity.critical_items(os.path.join(state, 'green-check.tsv'), os.path.join(state, 'logs', 'green-check.log'))
        if critical:
            items = critical
            trigger += ' Critical: the driver verification itself fails.'
        deferred = (severity.deferred_commands(os.path.join(state, 'green-check.tsv'), os.path.join(state, 'logs', 'green-check.log'))
                    + severity.deferred_rows(os.path.join(state, 'documents', 'TEST_REVIEW.json')))
    out.append('')
    out.append(trigger)
    out.append('')
    if items:
        out.append('To repair (%d):' % len(items))
        out.extend('- ' + item for item in items[:MAX_ITEMS])
        if len(items) > MAX_ITEMS:
            out.append('- ... and %d more (see `%s`)' % (len(items) - MAX_ITEMS, source))
    else:
        out.append('No individual item could be extracted; the agent will read `%s`.' % source)
    if deferred:
        out.append('')
        out.append('Not repaired (not critical; the final audit reads them):')
        out.extend('- **%s** (%s): %s' % (i, sev, clip(e)) for i, sev, e in deferred[:MAX_ITEMS])
    out.append('')
    notes = []
    if os.path.exists(os.path.join(state, 'REPAIR_BRIEF.md')):
        notes.append('A previous repair changed none of the files its findings name; `REPAIR_BRIEF.md` lists what is still open.')
    if os.path.exists(os.path.join(state, 'tests.lock')):
        notes.append('The tests stage is active: the repair must fix the source. A frozen test may change only with a reason recorded in `tests/amendments.tsv`.')
    out.extend('Note: ' + n for n in notes)
    out.append('Source of this decision: `%s`.' % source)
    return '\n'.join(out) + '\n'


def main(argv):
    if len(argv) != 5:
        print(__doc__, file=sys.stderr)
        return 2
    sys.stdout.write(explain(argv[1], argv[2], argv[3], argv[4]))
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))
