# CHANGE_SPEC.md
Omitted sections: Performance (no new cost beyond change-pr.sh:301); Migration (journal schema C-1 unchanged); Prototype-isolation (not a prototype).

## 1. Change type
Feature (seeded unclehq/uncle#6).

## 2. Problem statement
PR handoff exists (BASELINE_REPORT.md B-1) but PR name/description are not pre-filled from the originating issue/change-request name, and the description is not guaranteed to carry the work summary and manual-verify steps.

## 3. Current behavior
B-1..B-7, per BASELINE_REPORT.md §4.

## 4. Desired behavior
On Git completion, the PR dialog pre-fills the name from the shortened issue name, or from the change-request name when that seeded the flow (CR#1), and pre-fills the description with a brief work summary plus manual-verify steps (CR#2). Merging the PR adds a comment that closes the issue (CR#3). No `.git` → no PR process (CR#4).

## 5. Acceptance criteria
| ID | Criterion |
|---|---|
| AR-1 | Name pre-filled from issue or change-request origin (CR#1) |
| AR-2 | Pre-fill is an editable default (P-4) |
| AR-3 | Description carries work summary + manual-verify steps (CR#2) |
| AR-4 | Post-merge comment closes the issue (CR#3) |
| AR-5 | Missing `.git` → no PR process (CR#4) |
| AR-6 | Content matches audit before publication (I-1) |
| AR-7 | Decline/EOF/auth failure keeps PR pending (B-4) |

## 6. Observable behavior table
| ID | Class | Trigger | Current behavior | Expected behavior | Verification |
|---|---|---|---|---|---|
| B-1 | PRESERVE | Git completion | PR with closing reference | unchanged | CF:1128 |
| B-2 | MODIFY | Title prompt | 72-char summary or fallback (PR:193) | pre-fill from issue/change-request name | CF:1309 |
| B-3 | MODIFY | Publication prompt | requests summary/manual steps/consent (PR:338) | description pre-filled; consent retention unresolved (§16) | CF:1308 |
| B-4 | PRESERVE | Decline/EOF/auth fail | PR pending | unchanged | CF:1174 |
| B-5 | PRESERVE | No `.git` | no PR path | unchanged, incl. no dialog | CF:822 |
| B-6 | PRESERVE | Disabled/unattended | no PR prompt | unchanged | PR:4 |
| B-7 | PRESERVE | Resume created PR | no duplicate | unchanged | CF:1150 |

## 7. Invariant table
| ID | Status | Invariant | Scope | Enforcement point | Verification |
|---|---|---|---|---|---|
| I-1 | EXISTING | Content matches audit | PR | PR:153 | CF:1183 |
| I-2 | EXISTING | Unknown outcome blocks recreate | PR | PR:321 | CF:1249 |
| I-3 | EXISTING | PR leaves issue open until merge | PR | PR:301 | CF:1150 |
| I-4 | EXISTING | Legacy close requires owned READY/hash/origin | issue-close | issue_close_eligible | CF:892,919 |
| I-5 | NEW | Name pre-filled from issue/change-request name | PR | P-4 prompt | new test |
| I-6 | NEW | Description carries work summary + manual-verify | PR | PR create | new test |

None RELAXED or REMOVED.

## 8. Compatibility requirements
Keep Bash ≥3.2/Python ≥3.9/Git/jq/gh (debian/control:7); journal v1 (C-1); flag WORKFLOW_CLOSE_ISSUE=0 (C-4) unchanged.

## 9. Error and failure behavior
Decline/EOF/auth failure → PR pending (B-4). No `.git` → abort before dialog (B-5, CR#4). Unknown outcome → no recreate (I-2).

## 11. Security requirements
PR content must match audit before publication (I-1); name/description treated as untrusted, validated at PR:153.

## 13. Rollback expectations
Revert the change commit; feature remains behind the existing close flag (C-4); journal v1 readable, no migration (C-1).

## 15. Explicit non-goals
No new-app driver/installer/adapters (BASELINE §14). No change to close-on-merge timing. No name-generation heuristics beyond shortening the existing title.

## 16. Assumptions and unresolved questions
ASSUMPTION: "good name in the CHANGE_REQUEST" = its Summary title.
UNRESOLVED: B-3 consent prompt retained or fully auto (BASELINE §15).
UNRESOLVED: live merge closure and TTY behavior need platform checks (BASELINE §15).