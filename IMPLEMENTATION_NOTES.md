## files changed
| ID | File | Purpose | Approved-plan step | Behavior or invariant |
|---|---|---|---|---|
| F-1 | scripts/tests/document-budget-test.sh:164 | Copy repair-acceptance.py into standalone/scripts/lib/ | S-2, C-1 | I-4; T-1 passes after failing before the edit |
| F-2 | IMPLEMENTATION_NOTES.md | Record scope and remaining acceptance evidence | User-required artifact | No runtime behavior |
| F-3 | CHANGE_TEST_REPORT.md | Record executed checks and coverage gaps | S-1, S-3, S-4, RB-1 | AC-1–AC-5 evidence |

## purpose of each change
See F-1–F-3.

## approved-plan step
| ID | Evidence |
|---|---|
| P-1 | S-1 reproduced exit 1 at the diagnostic grep; S-3 commands passed; see CHANGE_TEST_REPORT.md. |
| P-2 | S-4/M-2: git diff -- scripts/tests/document-budget-test.sh showed only C-1; M-1 remains unresolved. |

## behavior or invariant affected
| ID | Evidence |
|---|---|
| B-1 | CHANGE_SPEC.md B-1 and I-4 verified by bash scripts/tests/document-budget-test.sh, exit 0. |
| B-2 | Preserved-behavior coverage: BASELINE_REPORT.md §4 B-2/B-3 exercised by both budget suites; B-4 requires Windows CI. |

## deviations
| ID | Disposition |
|---|---|
| D-1 | No implementation deviation: git diff -- scripts/tests/document-budget-test.sh contains only C-1. |
| D-2 | git status --short before editing recorded existing changes in ADVERSARIAL_REVIEW.md, BASELINE_REPORT.md, CHANGE_PLAN.md, CHANGE_REQUEST.md, CHANGE_SPEC.md and README.md; SHA-256 comparison after checks confirmed all six unchanged. |

## unresolved concerns
| ID | Status / settlement |
|---|---|
| Q-1 | CHANGE_PLAN.md Q-1 settled locally: T-1 passes on Darwin/Bash 3.2.57; observed with uname -s and bash --version. |
| Q-2 | UNRESOLVED: AC-4/M-1 requires candidate Windows Git Bash CI output showing PASS: document-budget and zero suite failures; this session has no candidate Windows run. |
