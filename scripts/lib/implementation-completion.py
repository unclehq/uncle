#!/usr/bin/env python3
"""Fail closed on missing or incomplete change acceptance evidence.

This validates the handoff contract, not the truth of the agent's claims;
driver verification and independent review still establish correctness.
"""
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


def check(spec, notes):
    required = rows(section(spec, "Acceptance criteria"), ["ID", "Criterion", "Verification"])
    delivered = rows(section(notes, "Acceptance delivery"),
                     ["ID", "Status", "Changed code", "Observed targeted verification"])
    problems = []
    if required.keys() != delivered.keys():
        problems.append("Acceptance IDs must match CHANGE_SPEC.md exactly")
    for key in required:
        if len(required[key]) != 2 or not all(required[key]):
            problems.append(f"{key}: malformed specification criterion")
        row = delivered.get(key, [])
        if len(row) != 3 or row[0] != "IMPLEMENTED" or not all(row[1:]):
            problems.append(f"{key}: requires IMPLEMENTED, changed code, and observed targeted verification; got {row}")
    return problems


if __name__ == "__main__":
    try:
        problems = check(Path(sys.argv[1]).read_text(), Path(sys.argv[2]).read_text())
    except (OSError, ValueError) as exc:
        problems = [str(exc)]
    for problem in problems:
        print(problem)
    sys.exit(bool(problems))
