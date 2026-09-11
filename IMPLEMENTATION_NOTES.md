## files changed
<<<<<<< HEAD
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
=======
| ID | File | Purpose | Approved-plan step | Behavior or invariant affected |
|---|---|---|---|---|
| F-1 | IMPLEMENTATION_NOTES.md | Record stopped implementation and existing work | S-1; STOP-1 | README.md B-1/B-2 remain unchanged |
| F-2 | CHANGE_TEST_REPORT.md | Record executed checks and blocked checks | S-1; STOP-1 | T-1 remains red; T-2/T-3 baseline passes |

## purpose of each change
F-3: F-1/F-2 are the reporting artifacts required by the implementation-stage instruction.

## approved-plan step
S-1: Completed repository inspection, README snapshot, baseline checks, and T-1 red; see CHANGE_TEST_REPORT.md.
S-2: Not started: required M-1 browser preview probe exited 134; CHANGE_PLAN.md STOP-1 applies.

## behavior or invariant affected
| ID | Observation | Evidence |
|---|---|---|
| B-1 | README.md:4,28 match P-1 preconditions; both token-count assertions passed | CHANGE_PLAN.md T-1 failed only at final equality assertion |
| B-2 | README.md is unchanged; specification B-3–B-6 and I-1/I-2 retain baseline behavior | Snapshot comparison; baseline T-2/T-3; CHANGE_TEST_REPORT.md |
| B-3 | Existing uncommitted modifications: ADVERSARIAL_REVIEW.md, BASELINE_REPORT.md, CHANGE_PLAN.md, CHANGE_REQUEST.md, CHANGE_SPEC.md | Initial `git status --short`; no initial untracked files |
| B-4 | Existing modifications were preserved | SHA-256 comparison before/after; final `git status --short` |

## deviations
| ID | Disposition | Reason |
|---|---|---|
| D-1 | S-2/S-3 implementation and acceptance incomplete | STOP-1: Chrome headless preview probe exited 134 without diagnostic output |
| D-2 | Updated only F-1/F-2 despite F-3 protecting other tracked paths | Implementation-stage instruction explicitly requires these reports |

## unresolved concerns
| ID | Unverified item | Settled by |
|---|---|---|
| U-1 | M-1 rendered README capitalization/markup and remote assets are unverified | Restore browser preview capability and complete M-1 |
| U-2 | AC-1/AC-2 remain unsatisfied; README.md:4,28 still use lowercase display tokens | Resume S-1–S-3 after resolving U-1; rerun T-1–T-3 |
>>>>>>> b449b41 (changes uncle to Uncle)
