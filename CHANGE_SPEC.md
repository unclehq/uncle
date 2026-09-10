# Change Spec — Startup required-input check
Omitted sections: 10 (negligible); 12 (no data migration); 13 (revert-only); 14 (not applicable)

## 1. Change type
Feature (menu-time input gate). Source: CHANGE_REQUEST.md:13-18; issue #5.

## 2. Problem statement
Selecting New application or Change request launches the workflow without verifying the required input document exists, returning a broken downstream flow (BASELINE B1 / §4, §11).

## 3. Current behavior
Choosing new/change launches regardless of missing inputs (BASELINE B1). Existing dismissible notice mechanism (BASELINE B3). Launch bound to project root (BASELINE I1). Issue selection precedes launch (BASELINE I2).

## 4. Desired behavior
At menu selection, check the required doc at project root before launch:
New application → REQUIREMENTS.md; Change request → CHANGE_REQUEST.md.
Absent → warning popup (existing notice, B3); launch blocked. Present → launch as today (B1 happy path).

## 5. Acceptance criteria
| ID | Criterion |
|---|---|
| AR-1 | New application + REQUIREMENTS.md missing → warning shown, no launch |
| AR-2 | Change request + CHANGE_REQUEST.md missing → warning shown, no launch |
| AR-3 | Both docs present → launch proceeds (B1 happy path preserved) |
| AR-4 | Dismiss warning returns to menu; reselect re-checks |
| AR-5 | CLI/args unchanged (BASELINE C1); helper functions intact |
| AR-6 | I1, I2 still enforced; no outside-root path check |

## 6. Observable behavior table
| ID | Class | Trigger | Current | Expected | Verification |
|---|---|---|---|---|---|
| B-1 | MODIFY | Select New app, REQUIREMENTS.md absent | Launch proceeds | Warning popup; no launch | Menu test (P1) |
| B-2 | MODIFY | Select Change req, CHANGE_REQUEST.md absent | Launch proceeds | Warning popup; no launch | Menu test (P1) |
| B-3 | ADD | Both docs present, choose new/change | Launch | Launch, unchanged | Menu test |
| B-4 | PRESERVE | Dismiss notice | Configure opens (B3) | Unchanged | Existing notice test |
| B-5 | PRESERVE | Change ANALYZE, missing/empty input | Exit 1 (B2) | Unchanged | Existing test |
| B-6 | PRESERVE | Issue selection precedes launch (I2) | Ordering | Unchanged | Issue-root test |

## 7. Invariant table
No RELAXED or REMOVED rows.
| ID | Status | Invariant | Scope | Enforcement | Verification |
|---|---|---|---|---|---|
| I-1 | EXISTING | Launch in project root (BASELINE I1) | Launch | uncle_tui.py:1303 | Issue-root test |
| I-2 | EXISTING | Issue selection precedes launch (BASELINE I2) | Menu | uncle_tui.py:2454 | Issue-root test |
| I-3 | NEW | Required doc present before launch | Menu | Menu selection handler (P1) | AR-1..3 |
| I-4 | NEW | Check confined to project-root relative path | Menu | Same handler | AR-6 |

## 8. Compatibility requirements
Preserve API/args (C1), helpers, B2, B3, I1, I2. Menu surface P1 / uncle:572,612 keeps happy-path semantics.

## 9. Error and failure behavior
Missing doc → non-blocking warning popup; selection cleared, return to menu; no partial launch. Stat/read error treated as missing.
UNRESOLVED: behavior under --unattended (C1) has no dialog surface; needs decide (warn+continue vs fail). Not settled by baseline.

## 11. Security requirements
Existence check only; path from I1 project root; no content read, execution, or absolute-path traversal (I-4).

## 15. Explicit non-goals
No content/resume validation; no auto-create of docs; no CLI change (C1); no README/GitHub-issue scan (issue #5 title) — scope is CHANGE_REQUEST.md filenames only.

## 16. Assumptions and unresolved questions
| ID | Item | Resolution |
|---|---|---|
| AU1 | README/GitHub in issue title out of scope; only REQUIREMENTS.md + CHANGE_REQUEST.md | Confirm PR scope (BASELINE U1, U2) |
| AU2 | Empty file counts as missing | UNRESOLVED (BASELINE U1) |
| AU3 | Unattended-mode missing-doc behavior | UNRESOLVED, see §9 |
