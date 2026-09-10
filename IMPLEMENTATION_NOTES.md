## files changed

| ID | File / symbol | Purpose | Approved-plan step | Behavior / invariant |
|---|---|---|---|---|
| N-1 | `scripts/change-workflow.sh`: FINAL_AUDIT, COMPLETE | Freeze/bind audit; route Git completion to PR handoff under existing lock | S-2 / P-1 | B-1; AC-7–10 |
| N-2 | `scripts/from-issue.sh`: close_issue_if_ready | Suppress Git fallback closing | S-2 / P-2 | I-6; no-Git close retained |
| N-3 | `scripts/lib/issue-close.sh`: issue_close_eligible | Share eligibility without invoking close mutation | S-2 / P-3 | I-1–3; B-6,8 |
| N-4 | `scripts/lib/change-pr.sh`: change_pr_engine | Raw-byte temporary index; atomic journal; consented commit-tree/push; exact repository/SHA PR reconciliation | S-2 / P-5 | AC-1,4,7–10; commit-tree does not run commit hooks |
| N-5 | `uncle_tui.py`: _detect_prompt | Prefill editable title; wait for complete prompt chunks | S-3 / P-4 | AC-3; existing user edits retained |
| N-6 | `scripts/tests/close-flow-test.sh`: new_case, setup_audit_stage, HandoffTests | Repair finding fixtures; cover close gates, Git routing, publication, drift and recovery; supply test-only timeout | S-1,4 / P-6 | T-1–3,5–9 |
| N-7 | `scripts/tests/pr-prompt-test.py`: PromptTests | Unicode/default editing, chunk boundaries, generic prompts | S-3,4 / P-7 | T-4 |
| N-8 | `scripts/README.md`: issue completion contract | Document routing, consent, identity restrictions, recovery and rollback | S-3 / P-8 | B-1–8 |
| N-9 | `IMPLEMENTATION_NOTES.md` | Record scope, preservation and limitations | S-4 | Review evidence |
| N-10 | `CHANGE_TEST_REPORT.md` | Record executed checks and gaps | S-4 | Test evidence |

## purpose of each change

See N-1–10, Purpose column.

## approved-plan step

See N-1–10, Step column; `CHANGE_PLAN.md` §20.

## behavior or invariant affected

See N-1–8; observed results are in `CHANGE_TEST_REPORT.md`.

## deviations

| ID | Disposition |
|---|---|
| D-1 | S-4 live M-1/M-2 remain unrun; local Git/fake-GitHub tests substitute only for automated coverage, not merge/UI acceptance. |
| D-2 | Broader test failures were investigated against a temporary pre-change copy; protected tests and implementation paths were not repaired. |

## unresolved concerns

| ID | Evidence / resolution |
|---|---|
| U-1 | ASSUMPTION: GitHub merge closes the qualified source issue (`CHANGE_PLAN.md` R-1); unverified against GitHub. Settle with M-1 in a disposable upstream/fork and live CLI/TUI. |
| U-2 | Initial `git status --short`: nine pre-existing modified paths—`ADVERSARIAL_REVIEW.md`, `BASELINE_REPORT.md`, `CHANGE_PLAN.md`, `CHANGE_REQUEST.md`, `CHANGE_SPEC.md`, `PREREQUISITES.md`, `scripts/lib/self_hosted.py`, `scripts/tests/self-hosted-test.py`, `uncle_tui.py`; retained. |
| U-3 | Later `git status --short` showed staging changes with unchanged HEAD; writer unverified. Staging retained; `git diff HEAD` includes both staged and unstaged work. Settle attribution with the concurrent workflow operator. |
| U-4 | `change_pr_engine`: corrupt journals and unresolved create outcomes fail closed; independently resolve prior PR outcome before repairing/removing a corrupt journal and obtaining a fresh audit. |
