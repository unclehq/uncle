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
        if not re.fullmatch(r"AC-\d+", cells[0]):
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
        if not isinstance(row, dict) or not re.fullmatch(r'AC-\d+', str(row.get('id', ''))):
            raise ValueError('change-spec has malformed acceptance criteria')
        identifier = row['id']
        if identifier in result:
            raise ValueError(f'Duplicate criterion {identifier}')
        result[identifier] = [row.get('criterion', ''), row.get('verification', '')]
    if not result:
        raise ValueError('change-spec has no acceptance criteria')
    return result


def json_delivered(payload):
    result = {}
    for fragment in _fragments(payload):
        for row in fragment.get('deliveries') or []:
            if not isinstance(row, dict) or not re.fullmatch(r'AC-\d+', str(row.get('id', ''))):
                raise ValueError('implementation-notes has malformed acceptance delivery')
            identifier = row['id']
            if identifier in result:
                raise ValueError(f'Duplicate delivery criterion {identifier}')
            result[identifier] = [row.get('status', ''), row.get('changed_code', ''),
                                  row.get('observed_verification', '')]
    if not result:
        raise ValueError('implementation-notes has no acceptance delivery rows')
    return result


def canonical_rows(spec_path, notes_path):
    return json_required(_json(spec_path)), json_delivered(_json(notes_path))


def check(spec, notes):
    required = rows(section(spec, "Acceptance criteria"), ["ID", "Criterion", "Verification"])
    delivered = rows(section(notes, "Acceptance delivery"),
                     ["ID", "Status", "Changed code", "Observed targeted verification"])
    return check_rows(required, delivered)


def check_rows(required, delivered):
    problems = []
    if required.keys() != delivered.keys():
        problems.append("Acceptance IDs must match .uncle/docs/CHANGE_SPEC.md exactly")
    for key in required:
        if len(required[key]) != 2 or not all(required[key]):
            problems.append(f"{key}: malformed specification criterion")
        row = delivered.get(key, [])
        if len(row) != 3 or row[0] != "IMPLEMENTED" or not all(row[1:]):
            problems.append(f"{key}: requires IMPLEMENTED, changed code, and observed targeted verification; got {row}")
    return problems


if __name__ == "__main__":
    try:
        if len(sys.argv) != 3:
            raise ValueError('usage: implementation-completion.py SPEC NOTES')
        spec_path, notes_path = map(Path, sys.argv[1:])
        if spec_path.suffix == '.json' or notes_path.suffix == '.json':
            if spec_path.suffix != '.json' or notes_path.suffix != '.json':
                raise ValueError('acceptance completion requires both canonical JSON artifacts')
            required, delivered = canonical_rows(spec_path, notes_path)
            problems = check_rows(required, delivered)
        else:
            problems = check(spec_path.read_text(), notes_path.read_text())
    except (OSError, ValueError) as exc:
        problems = [str(exc)]
    for problem in problems:
        print(problem)
    sys.exit(bool(problems))
