#!/usr/bin/env python3
"""Reconcile an independent checklist draft with what was actually built, as a small set of edits the driver applies.

The manual checklist is drafted from the approved requirements and plan while the code is still being written, by reviewers who never see
the implementation, so it cannot share the code's wrong assumptions. After implementation a reconciler reads the draft, the test review,
the driver's verification record and the built source, and answers with edits instead of a rewritten checklist:

    drop    a draft check that no longer applies (the thing it exercises is gone, or the driver has proved it), with a reason
    modify  fix a draft check that names a selector, file, command or behavior the built app does not have, with a reason
    add     a check the draft missed, found by the test review or by reading the built source, with a reason

Applying edits keeps the draft's independence and its ids, leaves an audit of every change, and makes the weakening moves the
reconciler could be tempted into (dropping most of the checklist, loosening a required check, emptying an expectation) rejections.

A modify may say which rows of the approved plan it follows (`"plan_row": "B-7"`, or `"B-7, I-4"`). The row's expected result is then
being brought into line with what the plan states, which is the one change to an expectation that is not a loosening: the build is
never the authority, the plan is. When the plan is given, every row cited must exist in it, so a made-up citation is a rejection.

    checklist_reconcile.py apply DRAFT.json PACKET.json OUT.json AUDIT.json [PLAN.md]
    (exit 1 with the reason on stderr when the packet cannot be applied; the caller then runs the full panel instead)
"""
import json
import re
import sys
from pathlib import Path

PACKET_KIND = 'manual-checklist-reconcile-packet'
TEXT_FIELDS = ('section', 'exact_action', 'expected_result', 'evidence_to_capture')
LIST_FIELDS = ('depends_on', 'exclusive_resources')
MODIFIABLE = frozenset(TEXT_FIELDS + LIST_FIELDS + ('required',))
MAX_DROP_FRACTION = 0.5          # never more than half the draft, however good each reason sounds
MIN_REASON = 12
MAX_ADDS = 20
PLAN_ROW = re.compile(r'^[A-Z]{1,3}-\d+$')
PLAN_ID = re.compile(r'\b[A-Z]{1,3}-\d+\b')
FIRST_ADDED = 901                # added checks are numbered by the driver, after every range a lens owns


def fail(message):
    raise ValueError(message)


def reason_of(entry, what):
    reason = str(entry.get('reason', '')).strip()
    if len(reason) < MIN_REASON:
        fail('%s needs a reason of at least %d characters' % (what, MIN_REASON))
    return reason


def rows(packet, key):
    value = packet.get(key) or []
    if not isinstance(value, list) or not all(isinstance(row, dict) for row in value):
        fail('"%s" must be a list of objects' % key)
    return value


def plan_rows_of(entry, ident, plan_text):
    """The plan rows a modify cites, as a list. ValueError for a malformed citation, or one the plan does not contain."""
    raw = entry.get('plan_row')
    if raw in (None, '', []):
        return []
    items = raw if isinstance(raw, list) else str(raw).split(',')
    cited = [str(item).strip() for item in items if str(item).strip()]
    for row in cited:
        if not PLAN_ROW.match(row):
            fail('%s: plan_row %r is not a plan row id such as B-7' % (ident, row))
    if plan_text is not None:
        known = set(PLAN_ID.findall(plan_text))
        missing = [row for row in cited if row not in known]
        if missing:
            fail('%s: the plan has no row %s' % (ident, ', '.join(missing)))
    return cited


def apply(draft, packet, plan_text=None):
    """(the final checklist document, the audit of what changed). ValueError when the packet breaks a rule."""
    if not isinstance(draft, dict) or draft.get('kind') != 'manual-checklist' or not isinstance(draft.get('checks'), list):
        fail('the draft is not a manual-checklist document')
    if not isinstance(packet, dict) or packet.get('kind') != PACKET_KIND:
        fail('the packet is not a %s' % PACKET_KIND)
    checks = {check['id']: dict(check) for check in draft['checks'] if isinstance(check, dict) and check.get('id')}
    order = [check['id'] for check in draft['checks'] if isinstance(check, dict) and check.get('id')]
    audit = {'dropped': [], 'modified': [], 'added': [], 'repaired_dependencies': []}

    drops = rows(packet, 'drop')
    dropped_ids = [str(row.get('id', '')) for row in drops]
    if len(set(dropped_ids)) != len(dropped_ids):
        fail('a check is dropped twice')
    for row in drops:
        if row.get('id') not in checks:
            fail('cannot drop %r: the draft has no such check' % row.get('id'))
    if checks and len(drops) > MAX_DROP_FRACTION * len(checks):
        fail('refusing to drop %d of %d draft checks: the draft is the independent part of the review' % (len(drops), len(checks)))

    modified = set()
    for row in rows(packet, 'modify'):
        ident = row.get('id')
        if ident not in checks:
            fail('cannot modify %r: the draft has no such check' % ident)
        if ident in dropped_ids:
            fail('%s is both dropped and modified' % ident)
        if ident in modified:
            fail('%s is modified twice' % ident)
        modified.add(ident)
        reason = reason_of(row, 'modifying %s' % ident)
        cited = plan_rows_of(row, ident, plan_text)
        fields = row.get('fields')
        if not isinstance(fields, dict) or not fields:
            fail('modifying %s names no fields' % ident)
        for key, value in fields.items():
            if key not in MODIFIABLE:
                fail('%s: %r is not a field a reconciler may change' % (ident, key))
            if key in TEXT_FIELDS:
                if not isinstance(value, str):
                    fail('%s: %s must be text' % (ident, key))
                if key in ('exact_action', 'expected_result') and not value.strip():
                    fail('%s: %s cannot be emptied' % (ident, key))
            if key in LIST_FIELDS and not (isinstance(value, list) and all(isinstance(item, str) for item in value)):
                fail('%s: %s must be a list of strings' % (ident, key))
            if key == 'required':
                if not isinstance(value, bool):
                    fail('%s: required must be true or false' % ident)
                if checks[ident].get('required') is True and value is False:
                    fail('%s: a required check cannot be loosened; drop it with a reason instead' % ident)
        checks[ident].update(fields)
        audit['modified'].append({'id': ident, 'fields': sorted(fields), 'reason': reason, **({'plan_row': cited} if cited else {})})

    for ident in dropped_ids:
        reason = reason_of(next(row for row in drops if row['id'] == ident), 'dropping %s' % ident)
        checks.pop(ident)
        order.remove(ident)
        audit['dropped'].append({'id': ident, 'reason': reason})

    adds = rows(packet, 'add')
    if len(adds) > MAX_ADDS:
        fail('at most %d checks may be added, got %d' % (MAX_ADDS, len(adds)))
    number = FIRST_ADDED
    for row in adds:
        reason = reason_of(row, 'adding a check')
        for key in ('exact_action', 'expected_result', 'evidence_to_capture'):
            if not isinstance(row.get(key), str) or not row[key].strip():
                fail('an added check needs %s' % key)
        while 'MC-%d' % number in checks or 'MC-%d' % number in dropped_ids:
            number += 1
        ident = 'MC-%d' % number
        number += 1
        added = {'id': ident, 'section': str(row.get('section') or 'Reconciliation').strip() or 'Reconciliation',
                 'exact_action': row['exact_action'].strip(), 'expected_result': row['expected_result'].strip(),
                 'evidence_to_capture': row['evidence_to_capture'].strip(),
                 'required': row.get('required') is True,
                 'depends_on': [str(item) for item in row.get('depends_on') or []],
                 'exclusive_resources': [str(item) for item in row.get('exclusive_resources') or []]}
        checks[ident] = added
        order.append(ident)
        audit['added'].append({'id': ident, 'reason': reason})

    # A dependency on a check that no longer exists is not a reason to refuse the whole reconciliation; it is removed and recorded.
    for ident in order:
        deps = checks[ident].get('depends_on') or []
        kept = [dep for dep in deps if dep in checks]
        if kept != deps:
            audit['repaired_dependencies'].append({'id': ident, 'removed': [dep for dep in deps if dep not in checks]})
            checks[ident]['depends_on'] = kept
    final = {'schema': 'uncle.artifact/v1', 'kind': 'manual-checklist', 'checks': [checks[ident] for ident in order]}
    audit['draft_checks'] = len(draft['checks'])
    audit['final_checks'] = len(final['checks'])
    return final, audit


def main(argv):
    if len(argv) not in (5, 6) or argv[0] != 'apply':
        print(__doc__, file=sys.stderr)
        return 2
    try:
        draft = json.loads(Path(argv[1]).read_text(encoding='utf-8'))
        packet = json.loads(Path(argv[2]).read_text(encoding='utf-8'))
        plan_text = Path(argv[5]).read_text(encoding='utf-8') if len(argv) == 6 and Path(argv[5]).is_file() else None
        final, audit = apply(draft, packet, plan_text)
    except (OSError, ValueError) as error:
        print('checklist reconciliation refused: %s' % error, file=sys.stderr)
        return 1
    Path(argv[3]).write_text(json.dumps(final, indent=2) + '\n', encoding='utf-8')
    Path(argv[4]).write_text(json.dumps(audit, indent=2) + '\n', encoding='utf-8')
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
