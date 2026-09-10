# CHANGE_PLAN.md

| Finding | Disposition | Reason | Exact plan change |
|---|---|---|---|
| AR-1: Overall assessment | Accepted | ADVERSARIAL_REVIEW.md reports no findings; acceptance awaits execution. | Exact acceptance criteria; Post-implementation checks |
Omitted sections: none

## 1. Selected technical approach
P-1: Plan: copy the real repair helper into the standalone fixture.

## 2. Alternative approaches considered
| ID | Alternative | Rejection reason |
|---|---|---|
| A-1 | Stub repair | Hides dependency |
| A-2 | Skip repair | Violates CHANGE_SPEC.md §15 |
| A-3 | Copy all helpers | Obscures dependencies |

## 3. Why the selected approach is preferred
P-2: Inspected `scripts/lib/gates.sh:402` calls repair before checking budgets; `scripts/lib/repair-acceptance.py:main` uses only standard-library imports.

## 4. Exact components to modify
| Component | Planned change | Reason | Regression risk | Test coverage |
|---|---|---|---|---|
| C-1: scripts/tests/document-budget-test.sh:164 | Add quoted "$ROOT/scripts/lib/repair-acceptance.py" to cp sources | I-4 | Further fixture failures | T-1 |

## 5. Components explicitly not to modify
P-3: Preserve `scripts/lib/{gates.sh,repair-acceptance.py,compact-review.py}`, `scripts/codex-{review-plan,create-checklist}.sh`, `.github/workflows/installers.yml`, packaging, other tests, README.md and approved inputs.

## 6. Data-flow changes
P-4: Plan: helper reaches `standalone/scripts/lib/`; output reaches repair then budget checking (`scripts/lib/gates.sh:402-406`).

## 7. State-transition changes
P-5: Plan: replace helper failure with overflow rejection at `scripts/tests/document-budget-test.sh:188-191`; retain success at :193.

## 8. Interface and API changes
None; preserve CHANGE_SPEC.md §8.

## 9. Schema or persistence changes
None; retain cleanup (`scripts/tests/document-budget-test.sh:7`).

## 10. Compatibility strategy
P-6: Verify Darwin/Bash 3.2 and Windows Git Bash via T-1/M-1.

## 11. Concurrency implications
None; retain mktemp in `scripts/tests/document-budget-test.sh:6`.

## 12. Error and recovery behavior
P-7: Retain overflow status and diagnostic assertions; suppress no helper errors.

## 13. Migration plan
None; fixture only.

## 14. Rollback plan
RB-1: Revert only C-1; run T-1 and expect the baseline failure.

## 15. Feature-flag or containment strategy
P-8: Keep C-1 inside the temporary fixture with its stub reviewer; no flag.

## 16. Automated-test strategy
Run from repository root.

| ID | Command | Required result |
|---|---|---|
| T-0 | `bash -n scripts/tests/document-budget-test.sh` | Exit 0 |
| T-1 | `bash scripts/tests/document-budget-test.sh` | Before: exit 1 at :191 (BASELINE_REPORT.md T-2); after: exit 0 |
| T-2 | `bash scripts/tests/document-budget-prompt-test.sh` | Exit 0 |

Traceability references CHANGE_SPEC.md.

| Requirement | Behavior | Invariant | Component | Automated test | Manual check |
|---|---|---|---|---|---|
| R-1: §5 local pass | B-1, B-3 | I-4 | C-1 | T-1: both reviewers; 1-byte rejection, 100-byte success | M-2 |
| R-2: §5 Windows pass | B-4 | I-4 | C-1 | CI runs T-1 | M-1 |
| R-3: §5 preservation | B-2, B-3 | I-1, I-2, I-3 | C-1 | T-1, T-2 | M-2 |

## 17. Regression-test strategy
P-9: Retain T-1 assertions as the fail-before/pass-after regression.
P-10: Run T-2 for approval, decline, EOF and fingerprint scoping.

## 18. Manual-verification strategy
| ID | Planned check |
|---|---|
| M-1 | Read Windows installers CI Git Bash log; require `PASS: document-budget`; investigate remaining failures |
| M-2 | Inspect `git diff -- scripts/tests/document-budget-test.sh`; require only C-1 |

## 19. Observability changes
None; use T-1/M-1 output.

## 20. Implementation sequence
| ID | Planned action |
|---|---|
| S-1 | Run T-1; confirm baseline failure |
| S-2 | Apply C-1 |
| S-3 | Run T-0, T-1, T-2; require exit 0 |
| S-4 | Perform M-2 and M-1 on candidate |

## 21. Scope cuts under time pressure
P-11: Retain T-1 and M-1; defer refactoring.

## 22. Risks and unresolved questions
| ID | Status / settlement |
|---|---|
| Q-1 | ASSUMPTION: C-1 suffices; settle with T-1 after editing |
| Q-2 | UNRESOLVED: Windows equivalence (BASELINE_REPORT.md §11); settle with M-1 |

## Frozen change scope
FS-1: Plan: implement only C-1; retain CHANGE_SPEC.md §15 non-goals.

## Files expected to change
FC-1: Plan: change only `scripts/tests/document-budget-test.sh` per C-1.

## Files that must not change
FP-1: Plan: preserve every other implementation file, including §5 paths, and approved inputs.

## Expected behavioral differences
BD-1: Plan: deliver CHANGE_SPEC.md B-1 through P-4/P-5; verify with T-1.

## Expected unchanged behavior
BU-1: Plan: preserve CHANGE_SPEC.md B-2–B-4 and I-1–I-3; verify through §16 traceability.

## Exact acceptance criteria
| ID | Required evidence |
|---|---|
| AC-1 | T-0 exits 0. |
| AC-2 | T-1 exits 0, including §16 reviewer rejection/success assertions. |
| AC-3 | T-2 exits 0. |
| AC-4 | M-1 records candidate Windows Git Bash `PASS: document-budget` with zero failures for this suite. |
| AC-5 | M-2 confirms only C-1; preserve §5 and CHANGE_SPEC.md §8 contracts. |

## Pre-implementation checks
PC-1: Plan: execute S-1 before C-1; stop if T-1 fails for a different reason.

## Post-implementation checks
PO-1: Plan: execute S-3/S-4 and record AC-1–AC-5 evidence; keep Q-2 UNRESOLVED until candidate CI settles M-1.

## First features to cut if time expires
CT-1: Plan: cut no acceptance checks; C-1 is indivisible and refactoring remains excluded by P-11.

## Conditions that require stopping implementation
ST-1: Plan: stop if C-1 requires edits outside FC-1 or contract changes; report failed checks and unavailable Windows evidence without claiming acceptance.
