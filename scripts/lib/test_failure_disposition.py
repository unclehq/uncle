#!/usr/bin/env python3
"""Write the canonical record for a build that continues after test failures.

The record deliberately separates a failed command from the practical question
of whether the independently reviewed functionality still works.  It is never
a PASS substitute: final audit receives both this file and green-check.tsv.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path


def failures(path: Path) -> list[dict[str, str]]:
    result: list[dict[str, str]] = []
    if not path.is_file():
        return result
    for line in path.read_text(encoding="utf-8").splitlines():
        fields = line.split("\t")
        if fields and fields[0] == "REGRESSION":
            result.append({"classification": fields[0], "command": "\t".join(fields[1:])})
    return result


def functional_evidence(path: Path) -> tuple[str, str]:
    if not path.is_file():
        return "UNVERIFIED", "No canonical TEST_REVIEW.json was available when continuation was recorded."
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return "UNVERIFIED", f"TEST_REVIEW.json could not be read: {exc}"
    rows = {str(row.get("id")): row for row in payload.get("rows", []) if isinstance(row, dict)}
    results = rows.get("RESULTS", {})
    status = str(results.get("status", "UNKNOWN"))
    evidence = str(results.get("evidence", "No RESULTS evidence supplied."))
    if status == "PASS":
        return "ACCEPTED_WITH_FUNCTIONAL_EVIDENCE", evidence
    return "UNVERIFIED", f"TEST_REVIEW RESULTS is {status}: {evidence}"


def main() -> int:
    if len(sys.argv) != 4:
        raise SystemExit("usage: test_failure_disposition.py GREEN.tsv TEST_REVIEW.json OUTPUT.json")
    failed = failures(Path(sys.argv[1]))
    status, evidence = functional_evidence(Path(sys.argv[2]))
    payload = {
        "schema": "uncle.artifact/v1",
        "kind": "test-failure-disposition",
        "status": status,
        "failed_commands": failed,
        "functional_evidence": evidence,
        "continuation": "The workflow continued; failures remain unresolved evidence for final audit.",
    }
    target = Path(sys.argv[3])
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
