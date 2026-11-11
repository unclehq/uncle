# Change spec: Issue 254

Omitted sections: Performance, Migration, Prototype isolation (none applicable)

## 1. Change type
Bug fix.

## 2. Problem statement
PRs carry `Closes` regardless of audit verdict, override, or BLOCKED acceptance, so merging closes unfinished issues (#235, #236).

## 3. Current behavior
Baseline B-1..B-3.

## 4. Desired behavior
`Closes <origin>` only for finished work; otherwise `Refs <origin>` plus a "Still open" list.

## 5. Observable behavior table
| ID | Class | Trigger | Current behavior | Expected behavior | Verification |
|---|---|---|---|---|---|
| SB-1 | MODIFY | Verdict NOT_READY or override recorded or release_skipped set | Closes | `Refs owner/repo#N` + Still open list | shell test |
| SB-2 | MODIFY | READY_WITH_NON_BLOCKING_ISSUES with a required acceptance row BLOCKED | Closes | Refs + Still open naming the row ID | shell test |
| SB-3 | PRESERVE | READY, nothing blocked | Closes | unchanged Closes | shell test |
| SB-4 | PRESERVE | No bound origin | no line | no Closes/Refs/Still open | existing tests |
| SB-5 | PRESERVE | attach_body / re-read body | strips Closes trailer | strips both Closes and Refs trailers | attestation-test.py |
| SB-6 | MODIFY | Docs | README says Closes for eligible origin | README states when Closes vs Refs used | review of README text |

## 6. Invariant table
| ID | Status | Invariant | Scope | Enforcement point | Verification |
|---|---|---|---|---|---|
| SI-1 | NEW | A PR body contains `Closes` only if verdict is READY/READY_WITH_NON_BLOCKING_ISSUES, no override, release_skipped unset, no required BLOCKED acceptance row | PR body | change-pr.sh body assembly | shell test |
| SI-2 | EXISTING | Attestation block precedes trailer lines | body | attestation.py attach_body | attestation-test.py |
| SI-3 | NEW | Uncertainty (unreadable verdict) resolves to Refs, never Closes | body | change-pr.sh | shell test |

No RELAXED or REMOVED invariants.

## 7. Compatibility
Journals already in phase `prepared` keep their stored body; unchanged.

## 8. Failure behavior
Missing/unreadable FINAL_AUDIT or malformed acceptance tables when a verdict cannot be determined: write Refs. Never raise from this logic.

## 10. Security
Still-open text derived from repo files is single-line sanitized (newlines stripped), consistent with existing banner.

## 12. Rollback
Revert the commit; bodies of already published PRs are unaffected.

## 14. Non-goals
Changing verdicts, draft logic, release gating; reopening issues #235/#236 (manual follow-up check).

## 15. Assumptions
Verdict is readable from FINAL_AUDIT.md or journal state; confirmed during implementation.

## Acceptance criteria

| ID | Criterion | Verification |
|---|---|---|
| AC-1 | A journal with NOT_READY verdict and an override record (or release_skipped) yields a body with `Refs owner/repo#N` and no `Closes` line. | New shell suite pr-closes-refs-test.sh asserts body content. |
| AC-2 | READY_WITH_NON_BLOCKING_ISSUES with one required acceptance row BLOCKED yields `Refs` and a "Still open" list naming that row ID, plus any FINAL_AUDIT finding saying the issue stays open. | New shell suite asserts Refs and the named row. |
| AC-3 | READY with nothing blocked still yields the unchanged `Closes owner/repo#N` ending; no-origin runs get neither line. | New shell suite plus existing pr-auto-publish-test.sh. |
| AC-4 | attestation.attach_body keeps the attestation block before, and preserves, trailing `Closes` and `Refs` lines (including a Still open section after Refs when present). | scripts/tests/attestation-test.py new cases. |
| AC-5 | scripts/README.md states when `Closes` versus `Refs` is written. | Inspect README lines near 405; grep for Refs. |
| AC-6 | Existing shell and Python suites show no new regressions versus baseline. | Driver verification commands. |

