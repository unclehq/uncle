## files changed
| ID | File / symbol | Purpose of each change | Approved-plan step | Behavior or invariant affected |
|---|---|---|---|---|
| F-1 | `scripts/from-issue.sh:write_new_project_brief` | Create absent requirements with subshell noclobber; print success after writing. | S-2, P-1/P-8 | AC-1, I-1/I-4/I-5; T-6 barriers pass. |
| F-2 | `scripts/tests/issue-project-root-test.sh` | Add seed, reseed, refusal, fetch/parse/write error, auto-routing, sentinel and pipe-barrier assertions. | S-1/S-3 | T-1–T-4/T-6; regression failed before F-1 and passes afterward. |
| F-3 | `scripts/tests/menu-input-test.py:test_issue_new_forwarding` | Assert shell n and TUI new selection forward `--new`. | S-1/S-3 | T-5; nine tests pass. |
| F-4 | `scripts/README.md:from-issue.sh` | Document creation, refusal, partial-write recovery and seed-only behavior. | S-2 | P-5/P-6/P-8/P-10. |
| F-5 | `IMPLEMENTATION_NOTES.md` | Record implementation scope and limitations. | User-required artifact | Traceability to CHANGE_PLAN.md. |
| F-6 | `CHANGE_TEST_REPORT.md` | Record executed checks and gaps. | User-required artifact, S-3 | P-15/M-1 evidence. |

## purpose of each change
F-1–F-6: recorded in the purpose column above.

## approved-plan step
F-1–F-6: recorded in the step column above.

## behavior or invariant affected
F-1–F-6: recorded in the behavior column above; commands and outcomes are in CHANGE_TEST_REPORT.md.

## deviations
| ID | Disposition / evidence |
|---|---|
| D-1 | Initial `git status --short` recorded existing modifications to `.gitignore`, `ADVERSARIAL_REVIEW.md`, `BASELINE_REPORT.md`, `CHANGE_PLAN.md`, `CHANGE_REQUEST.md`, `CHANGE_SPEC.md`; left untouched. |
| D-2 | F-5/F-6 are explicitly required by this implementation request despite CHANGE_PLAN.md FN-1 excluding workflow-document edits. |
| D-3 | M-1 used six scratch shell/TUI launch checks; the TUI screen was not rendered. Settle visual interaction by running the terminal UI interactively. |
| D-4 | The initial baseline batch reached BASELINE_REPORT.md §8 command 6 after F-1 was applied; the separate S-1 regression established the pre-fix failure. |
| D-5 | Rollback fixture initially omitted `prompts/`; corrected the temporary fixture and reran successfully. No repository change was needed. |

## unresolved concerns
| ID | Concern / evidence / settlement |
|---|---|
| U-1 | CHANGE_PLAN.md R-1 settled: F-2 compares every `##` heading from repository `REQUIREMENTS.md` with generated output; command passes. Driver execution remains untested because new mode only seeds. |
| U-2 | BASELINE_REPORT.md U-1 remains unverified: original reporter UI steps were unavailable; settle with the reporter fixture. |
| U-3 | CHANGE_PLAN.md P-9 leaves existing-marker concurrency unchanged; F-1 only adds the absent-target branch, as inspected with `git diff -- scripts/from-issue.sh`. |
