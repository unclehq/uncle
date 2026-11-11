# Change spec: issue 260

Omitted sections: Performance, Migration, Prototype isolation (not applicable)

## 1. Change type
Bug Fix (security/hygiene of workspace).

## 2. Problem statement
Uncle edits tracked `.gitignore` outside the planned, committed diff, leaving an uncommitted change or an unplanned file in the PR (FA-003).

## 3. Current behavior
Baseline B-1..B-4 (`.uncle/docs/BASELINE_REPORT.md`).

## 4. Desired behavior
Once a run has committed (finalize) or pushed (publish), no uncle code path writes `.gitignore` or any tracked file. Pre-commit normalization remains and is part of the committed diff.

## 5. Observable behavior table
| ID | Class | Trigger | Current behavior | Expected behavior | Verification |
|---|---|---|---|---|---|
| S-1 | ADD | Publish pushes the PR | Nothing freezes ignore handling | A freeze marker is recorded immediately after the push succeeds | Unit test on `freeze()`; shell-level check of change-pr push site |
| S-2 | MODIFY | `ensure()`/CLI called while frozen | Rewrites `.gitignore` | Returns False; `.gitignore` byte-identical; `git status` shows no uncle edit | New test `gitignore-post-push` |
| S-3 | ADD | Finalize/merge commit starts (from-issue.sh, stagegate merge) | No freeze | Freeze recorded before the commit | New test (source-level check) + shell suites |
| S-4 | PRESERVE | `ensure()` before freeze | Normalizes block | Unchanged (B-1, B-2, B-3) | `uncle-gitignore-test.sh` |
| S-5 | PRESERVE | TUI start | Writes `info/exclude` only | Unchanged, also when frozen | `gitignore-clean-end-test.py` |
| S-6 | MODIFY | Reused worktree after push (B-4) | Tracked `.gitignore` rewritten again | Not rewritten (frozen); `ensure_exclude` still applies | New test |

## 6. Invariant table
| ID | Status | Invariant | Scope | Enforcement point | Verification |
|---|---|---|---|---|---|
| V-1 | NEW | After freeze, `ensure()` never changes any byte of `<root>/.gitignore` | uncle_gitignore | `ensure()` guard | `gitignore-post-push` |
| V-2 | NEW | Freeze marker is written only under `<root>/.uncle/workflow/` (untracked) and never fails the run | uncle_gitignore.freeze | `freeze()` | `gitignore-post-push` |
| V-3 | EXISTING (I-2) | TUI never edits tracked `.gitignore` | uncle_tui | `ensure_exclude` | `gitignore-clean-end-test.py` |
| V-4 | EXISTING (I-3) | Guard refuses unaudited tracked edits | change-pr.sh | `assert_tree_matches_attested` | `gitignore-clean-end-test.py` |

No RELAXED or REMOVED invariants.

## 7. Compatibility
Pre-freeze behavior unchanged. CLI `uncle_gitignore.py [root]` keeps its signature; `ensure()` keeps its return type. Existing runs without a marker behave as before.

## 8. Error behavior
Freeze write failure is ignored (best effort, as `ensure`); consequence is today's behavior, not a new failure.

## 10. Security
Marker path is constructed inside the project's `.uncle/workflow`; symlinked `.uncle/workflow` is refused (no write).

## 12. Rollback
Revert the commit; marker files under `.uncle/workflow` are inert.

## 14. Non-goals
Changing new-app plan `.gitignore` duty; changing `ensure_exclude`; chasing the unidentified bare-`.uncle` appender beyond freezing uncle's own writers.

## 15. Assumptions and unresolved questions
A-1: The post-push writer is uncle's own `ensure` via worktree reuse (U-1). If the live writer is an external process, this change guarantees only that uncle's code is not it (stated limitation). A-2: Existing test files stay unchanged.

## Acceptance criteria

| ID | Criterion | Verification |
|---|---|---|
| AC-1 | After a freeze marker exists in a project root, uncle_gitignore.ensure() and the CLI return without modifying .gitignore (byte-identical, including legacy/bare-`.uncle` and missing-file cases). | New scripts/tests/gitignore-post-push-test.py compares sha256 of .gitignore before/after ensure() and CLI on a git fixture with signing disabled. |
| AC-2 | Without a marker, ensure() behaves exactly as before (normalization, creation). | scripts/tests/uncle-gitignore-test.sh and gitignore-clean-end-test.py pass unchanged. |
| AC-3 | The freeze is recorded immediately after the PR push succeeds in change-pr.sh, and before the commit in from-issue.sh finalize and the stagegate.sh merge commit. | gitignore-post-push-test.py asserts the freeze call appears after the push line / before the commit lines in those sources, and a fixture run of freeze() then ensure() leaves `git status --porcelain` free of .gitignore. |
| AC-4 | freeze() writes only inside <root>/.uncle/workflow, refuses a symlinked directory, and never raises. | gitignore-post-push-test.py cases for normal, symlinked, and non-git roots. |
| AC-5 | Any .gitignore change is pre-commit and in the committed diff; documentation states this and that change requests have no post-commit ignore duty. | docs/plan-duties.md updated; reviewed in diff. |
| AC-6 | No regression in shell and Python suites relative to baseline. | Driver runs bash scripts/run-shell-tests.sh and bash scripts/run-python-tests.sh and compares to baseline. |

