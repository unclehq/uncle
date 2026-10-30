#!/usr/bin/env python3
"""Fail closed on missing or incomplete change acceptance evidence.

This validates the handoff contract, not the truth of the agent's claims;
driver verification and independent review still establish correctness.
"""
import json
import re
import sys
from pathlib import Path


def section(text, title):
    matches = list(re.finditer(r"^##\s+(?:\d+\.\s*)?" + re.escape(title) + r"\s*$", text, re.M | re.I))
    if len(matches) != 1:
        raise ValueError(f"Expected exactly one '{title}' section")
    rest = text[matches[0].end():]
    return re.split(r"^#{1,2}\s", rest, maxsplit=1, flags=re.M)[0]


# One optional trailing lowercase letter (AC-4b) for a closely related
# sub-criterion added after the original numbering was set -- a reasonable,
# recurring model convention (issue 97: a spec that regenerates AC-4b every
# cycle). Rejecting it as "malformed" rather than a normal per-row mismatch
# sent the whole run back through ANALYZE to rebuild baseline, spec, plan and
# review from scratch, every single time this exact ID appeared again.
ACCEPTANCE_ID = r"AC-\d+[a-z]?"


def rows(text, header):
    result = {}
    headers = 0
    for line in text.splitlines():
        if not line.strip().startswith("|"):
            continue
        cells = [cell.strip().replace(r"\|", "|")
                 for cell in re.split(r"(?<!\\)\|", line.strip().strip("|"))]
        if cells == header:
            headers += 1
            continue
        if not re.fullmatch(ACCEPTANCE_ID, cells[0]):
            continue
        if cells[0] in result:
            raise ValueError(f"Duplicate criterion {cells[0]}")
        result[cells[0]] = cells[1:]
    if headers != 1:
        raise ValueError(f"Expected table header: {' | '.join(header)}")
    if not result:
        raise ValueError("Missing AC-numbered acceptance rows")
    return result


def _json(path):
    try:
        return json.loads(Path(path).read_text(encoding='utf-8'))
    except json.JSONDecodeError as exc:
        raise ValueError(f'Invalid canonical JSON: {exc}') from exc


def _fragments(payload):
    """Flatten an implementation-notes accumulator, including old nested ones."""
    if not isinstance(payload, dict) or payload.get('schema') != 'uncle.artifact/v1' \
            or payload.get('kind') != 'implementation-notes':
        raise ValueError('wrong implementation-notes JSON schema')
    children = payload.get('fragments')
    if children is None:
        return [payload]
    if not isinstance(children, list):
        raise ValueError('implementation-notes fragments must be an array')
    result = []
    for child in children:
        result.extend(_fragments(child))
    return result


def json_required(payload):
    if not isinstance(payload, dict) or payload.get('schema') != 'uncle.artifact/v1' \
            or payload.get('kind') != 'change-spec':
        raise ValueError('wrong change-spec JSON schema')
    result = {}
    for row in payload.get('acceptance_criteria') or []:
        if not isinstance(row, dict) or not re.fullmatch(ACCEPTANCE_ID, str(row.get('id', ''))):
            raise ValueError('change-spec has malformed acceptance criteria')
        identifier = row['id']
        if identifier in result:
            raise ValueError(f'Duplicate criterion {identifier}')
        result[identifier] = [row.get('criterion', ''), row.get('verification', '')]
    if not result:
        raise ValueError('change-spec has no acceptance criteria')
    return result


def json_delivered(payload):
    # Two isolated parallel/serial steps, each unable to see the other's
    # output, can each independently deliver real work for the same
    # criterion -- issue 116's AC-3 was genuinely covered twice, once by an
    # existing test step 2 pointed at and once by step 5's own new work on
    # the residue gate. Rejecting that outright sent the whole implementation
    # phase back to redo all steps from scratch every cycle, discarding
    # completed, correct work over a bookkeeping disagreement. A true
    # same-fragment duplicate (one step claiming its own id twice) is still
    # a real mistake and stays rejected; two different fragments agreeing the
    # criterion is IMPLEMENTED are merged into one row instead, combining
    # the evidence rather than picking one arbitrarily. Fragments disagreeing
    # on status (one claims IMPLEMENTED, another does not) is a genuine
    # conflict neither side can resolve by itself, so that still fails.
    seen_in_fragment = {}
    merged = {}
    for fragment_index, fragment in enumerate(_fragments(payload)):
        for row in fragment.get('deliveries') or []:
            if not isinstance(row, dict) or not re.fullmatch(ACCEPTANCE_ID, str(row.get('id', ''))):
                raise ValueError('implementation-notes has malformed acceptance delivery')
            identifier = row['id']
            if seen_in_fragment.get(identifier) == fragment_index:
                raise ValueError(f'Duplicate delivery criterion {identifier}')
            seen_in_fragment[identifier] = fragment_index
            status = row.get('status', '')
            changed_code = row.get('changed_code', '')
            observed = row.get('observed_verification', '')
            # issue 119: a step claimed IMPLEMENTED while its own evidence
            # said "Full suite DRIVER PENDING" -- a self-contradiction, not a
            # second step's independent claim. The step's own stated
            # evidence is authoritative over its stated status; never the
            # reverse, so this never lets a real pending check get waved
            # through as done. This brought the row back in line with three
            # other, honest fragments that had already deferred the same
            # check, instead of raising an unresolvable conflict between a
            # row and itself.
            if status == 'IMPLEMENTED' and 'DRIVER PENDING' in str(observed):
                status = 'INCOMPLETE'
            existing = merged.get(identifier)
            if existing is None:
                merged[identifier] = [status, changed_code, observed]
                continue
            if existing[0] != status:
                raise ValueError(
                    f'Conflicting delivery status for {identifier}: {existing[0]!r} vs {status!r}')
            existing[1] = '; '.join(part for part in (existing[1], changed_code) if part)
            existing[2] = '; '.join(part for part in (existing[2], observed) if part)
    if not merged:
        raise ValueError('implementation-notes has no acceptance delivery rows')
    return merged


def canonical_rows(spec_path, notes_path):
    return json_required(_json(spec_path)), json_delivered(_json(notes_path))


def check(spec, notes, allow_driver_pending=False):
    required = rows(section(spec, "Acceptance criteria"), ["ID", "Criterion", "Verification"])
    delivered = rows(section(notes, "Acceptance delivery"),
                     ["ID", "Status", "Changed code", "Observed targeted verification"])
    return check_rows(required, delivered, allow_driver_pending)


# A step that legitimately has no narrow check of its own is explicitly told
# (prompts/change/implement.md's reconciliation boundary) to record
# `DRIVER PENDING` and defer to the driver's own later full-suite run, rather
# than inventing or skipping verification. The very first completion check
# (WAIT_IMPLEMENT_APPROVAL) runs immediately after implementation, before
# that driver run has ever executed -- so a row written exactly as instructed
# always failed this check, sending the whole implementation phase back to
# redo every step from scratch on issue 119. allow_driver_pending lets that
# one early check accept the placeholder as provisional; every later check
# (CHECKLIST, FINAL_AUDIT, ...), once driver verification has actually run,
# still requires the real IMPLEMENTED row and rejects a pending one.
def _driver_pending(row):
    # A merged row's evidence may have other text ahead of the marker (e.g.
    # "Full suite DRIVER PENDING; ..."), not only a leading "DRIVER PENDING:".
    return len(row) == 3 and row[0] != "IMPLEMENTED" and "DRIVER PENDING" in str(row[2])


def check_rows(required, delivered, allow_driver_pending=False):
    problems = []
    if required.keys() != delivered.keys():
        problems.append("Acceptance IDs must match .uncle/docs/CHANGE_SPEC.md exactly")
    for key in required:
        if len(required[key]) != 2 or not all(required[key]):
            problems.append(f"{key}: malformed specification criterion")
        row = delivered.get(key, [])
        if allow_driver_pending and _driver_pending(row):
            continue
        if len(row) != 3 or row[0] != "IMPLEMENTED" or not all(row[1:]):
            problems.append(f"{key}: requires IMPLEMENTED, changed code, and observed targeted verification; got {row}")
    return problems


if __name__ == "__main__":
    try:
        if len(sys.argv) not in (3, 4) or (len(sys.argv) == 4 and sys.argv[3] != '--allow-driver-pending'):
            raise ValueError('usage: implementation-completion.py SPEC NOTES [--allow-driver-pending]')
        allow_pending = len(sys.argv) == 4
        spec_path, notes_path = map(Path, sys.argv[1:3])
        if spec_path.suffix == '.json' or notes_path.suffix == '.json':
            if spec_path.suffix != '.json' or notes_path.suffix != '.json':
                raise ValueError('acceptance completion requires both canonical JSON artifacts')
            required, delivered = canonical_rows(spec_path, notes_path)
            problems = check_rows(required, delivered, allow_pending)
        else:
            problems = check(spec_path.read_text(), notes_path.read_text(), allow_pending)
    except (OSError, ValueError) as exc:
        problems = [str(exc)]
    for problem in problems:
        print(problem)
    sys.exit(bool(problems))
