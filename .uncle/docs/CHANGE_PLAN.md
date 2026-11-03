# Change Plan - Issue 141

Issue 141

Seeded from [unclehq/uncle#141](https://github.com/unclehq/uncle/issues/141).

Omitted sections: Schema/persistence (none); Migration (none); Concurrency (single process; existing lock guard); Feature flag (none, see containment)

## 1. Selected technical approach

Add `finalize_no_pr_worktree <dir> <source>` to `scripts/from-issue.sh` (after `auto_removal_refusal`). Replace the no-PR branches (prompt and kept-message) in the post-run block (`from-issue.sh:864-873`) with one call, for all modes. Flow:

1. Path guards (run first, before any `git add` or commit): extract only the path, symlink and managed-root checks of `auto_removal_refusal` (from-issue.sh:243-266: path resolution, worktree is not the source, worktree does not contain the source, managed root, symlink) into `worktree_path_refusal <dir> <source>`, keeping the same refusal strings. The untracked-file, tracked-change and unpushed-commit checks (lines 267-295) stay in `auto_removal_refusal`, which becomes `worktree_path_refusal` followed by those unchanged checks in the same order with the same refusal strings. `finalize_no_pr_worktree` calls only `worktree_path_refusal` (untracked or unpushed work does not block it, since it commits first); the PR path keeps calling `auto_removal_refusal`. Also require registration and a non-empty current branch. If any guard refuses (unresolvable path, symlinked worktree path, unregistered worktree, detached HEAD), nothing is committed (no `git add`, no commit, no switch), the worktree is kept, and the keep summary line (`worktree kept; project not switched`) and the manual remove command `scripts/lib/worktrees.sh remove <dir>` are printed. Symlinks inside the tree are committed by `add -A` as ordinary link entries (never followed). Each refusal has its own test asserting HEAD unchanged and the worktree kept.
2. Commit: `git -C dir add -A -- . ':(exclude).uncle/workflow'` so driver run state under `.uncle/workflow` (lock, state, journal) is never committed; a failure of `git add` is a commit failure (S-8) and keeps the worktree. If nothing is staged (clean tree), the commit is skipped silently, no commit is created, HEAD is unchanged, and finalization continues. If changes are staged, record the committed file count (`git diff --cached --name-only | wc -l`) and run `git commit -m "uncle: issue N change"` with the user's git config, normal hooks, filter drivers and signing enabled; a failure of `git commit` (including a hook or filter failure) is S-8 and keeps the worktree. No bypass flag (e.g. --no-verify, --no-gpg-sign) is ever used. Untracked non-ignored files are committed as-is (not filtered for secrets); the summary reports the committed file count. The clean-status check in step 3 likewise uses `git status --porcelain -- . ':(exclude).uncle/workflow'`; a remaining lock or non-COMPLETE state is still refused by `worktree_remove`.
3. Verify `git status --porcelain --untracked-files=all -- . ':(exclude).uncle/workflow'` in the worktree is empty (N-1); driver state under .uncle/workflow is excluded from this check; else keep.
4. Main-project check in source, in this order; any failure keeps the worktree and prints `git switch <branch>`: (a) the run branch name must pass `git check-ref-format --branch` and not start with `-`, and is passed to git only after `--` or via `refs/heads/` so it can never parse as an option; (b) source HEAD must be on a named branch (`git -C source branch --show-current` non-empty; a detached source HEAD keeps the worktree so the detached position is never lost); (c) `git -C source status --porcelain --untracked-files=all` must print nothing (any non-ignored entry, including untracked files and the project's own .uncle/ state, counts as dirty); (d) HEAD is an ancestor of the run branch (`git merge-base --is-ancestor HEAD <branch>`, which succeeds for equal commits, so it covers a source already on the run branch or at its tip). If the source is already on the run branch (`git branch --show-current` equals the branch), skip the switch in step 6 and report `project switched`. Tests cover a modified tracked file, an untracked-only file, a detached HEAD, an option-like branch name, and the already-on-run-branch case.
5. `worktree_remove` (unchanged); it refuses while `.uncle/workflow/lock` exists or state is not COMPLETE, and a remaining lock keeps the worktree. Failure keeps and prints the remove command.
6. `git -C source switch <branch>`; failure prints the manual command.
7. Print exactly one summary line on every no-PR COMPLETE outcome: `Branch <b>: worktree removed|kept; project switched|not switched.` Outcomes: success is `removed; switched`; any guard refusal, commit/add failure, non-clean status, dirty or non-ancestor main, or removal failure is `kept; not switched`; switch failure after removal is `removed; not switched`. On keep and failure paths also print the literal manual commands: `git switch <b>` when the project was not switched, and `scripts/lib/worktrees.sh remove <dir>` when the worktree was kept. The old `Worktree <dir> kept; remove with:` and `Remove worktree <dir>? [y/N]` lines are no longer printed on the no-PR path.

Exit status is never altered.

## 2. Alternatives considered
| Alt | Rejected because |
|---|---|
| Switch first, then remove | Git refuses to check out a branch held by a worktree |
| Keep prompt for attended runs | Issue asks for no-pile-up; TUI/unattended cannot answer |
| Record base branch at worktree creation | Needs state changes in creation code; ancestry check is sufficient |
| `git worktree remove --force` | Could discard work |

## 3. Why preferred
Smallest surface, reuses `worktree_remove` and guards, all checks happen before any destructive step.

## 4. Components to modify
See change-impact table.

## 5. Not modified
`change-workflow.sh`, `scripts/lib/worktrees.sh`, `change-pr.sh`, PR auto-removal logic semantics, TUI.

## 6. Data-flow changes
No-PR COMPLETE runs now mutate the source checkout (branch switch) and create one commit on the run branch.

## 7. State-transition changes
None to driver state; only post-run script behavior.

## 8. Interface changes
Output text only: new summary line and manual commands. No flags.

## 10. Compatibility strategy

`offer_worktree_removal` retained (tests source it). PR path code untouched except that `auto_removal_refusal` now calls `worktree_path_refusal` first and then runs its unchanged remaining checks in the same order with the same refusal strings, so PR-path results are identical.

## 12. Error and recovery
Spec S-4 to S-8. Order guarantees nothing is lost: commit precedes removal; removal precedes switch; a switch failure leaves branch intact.

## 14. Rollback plan
Revert the commit. Runs finalized meanwhile keep their branch; recover with `git worktree add <dir> <branch>`.

## 15. Containment

Any doubt (unresolvable path, symlinked worktree path, detached HEAD in the worktree or in the source checkout, missing or invalid or option-like branch name, unregistered worktree, dirty main) takes the keep path. The source checkout must be on a named branch, and the validated branch name is always passed to git after `--`. Guard refusals happen before any add/commit, so nothing is committed; each prints the keep summary and the remove command (for a detached source HEAD it also prints `git switch <branch>`) and has a dedicated test (symlink, unregistered, detached HEAD in worktree, detached HEAD in source checkout, invalid or option-like branch name, unresolvable path).

## 16. Automated-test strategy

New cases in `scripts/tests/worktree-run-test.sh` using the existing stub driver and fixture helpers (signing disabled per header): no-pr-switch, untracked-output-committed, pty attended, unattended, dirty-main, other-branch, failed-removal, commit-fail (hook rejecting commit), switch-fail, PR-created unchanged. Failure induction is fixed: failed-removal puts a PATH-shimmed `git` first that delegates everything to the real git except `worktree remove`, which exits non-zero; switch-fail uses the same shim failing only `switch`. Both cases assert the exact manual command text printed (`scripts/lib/worktrees.sh remove <dir>` for removal failure; `git switch <branch>` for switch failure) and that the script's exit status equals the status of the same run without the failure. Defect-injection: dirty-main case must fail if the main-clean check is removed.

- Summary-line assertions: each outcome (success `removed; switched`; guard refusal, commit failure, dirty main, other branch, removal failure all `kept; not switched`; switch failure `removed; not switched`) is asserted by exact full-line match, exactly once per run (line count of `Branch ...:` lines equals 1), never by loose substring.
- Dirty-main has two cases, modified-tracked-file and untracked-only file in the source; each asserts no switch, worktree kept, `git switch <branch>` printed; defect injection (removing the main-clean check or its untracked-files option) must fail both.
- Clean-tree no-op case: run branch HEAD sha unchanged, worktree removed, project switched.
- Runtime-state case: the new commit contains no `.uncle/workflow` paths and the worktree is still removed after the commit.
- commit-fail uses a rejecting pre-commit hook; asserts worktree kept, exact remove command, unchanged exit status.

## 17. Regression-test strategy

Existing PR auto-removal cases (~690-810) and `worktree_remove` cases must pass unchanged. Existing expectations that conflict with this change (around lines ~341-342 kept message, ~654 prompt under pty, ~663-666 unattended kept; line numbers are approximate locators only) are updated; these are protected test paths edited under the authority of the change request's success criteria ("Tests cover the no-PR path..."). Each updated expectation is replaced by an equally strict assertion of the new behavior (never deleted, loosened or made optional), and every one is listed individually in IMPLEMENTATION_NOTES.md with: test case name, the old assertion, the new assertion, and the requirement that forces the change. Helper-level `offer_worktree_removal` tests remain. A new regression case asserts that when the driver fails or the final state is not COMPLETE, `finalize_no_pr_worktree` does not run: no commit is created, the worktree is kept, the source checkout is not switched, and the exit status is unchanged.

Protected PR-path regression checks: the existing PR auto-removal cases that exercise the untracked-file refusal and the unpushed-commit refusal must continue to assert their exact refusal strings unchanged after `auto_removal_refusal` is split; they are named in IMPLEMENTATION_NOTES.md as protected regression checks and must pass without edits.

## 18. Manual verification
Run a real `--worktree` change against a scratch repo with no PR: confirm worktree gone, main on branch, file visible, summary text; repeat with a dirty main.

## 19. Observability
Summary line and manual recovery commands, printed on stdout.

## Restrictions

| ID | source_kind | Source | Reqs | Property | Mechanism | Rationale | CAP | Feasibility evidence | Phase |
|---|---|---|---|---|---|---|---|---|---|
| R-1 | USER | CHANGE_REQUEST Constraints | AC-1, N-1 | Never discard work | commit then clean-status check | issue text | CAP-GIT | git add/commit in fixtures (worktree-run-test.sh commit_worktree helper) | CODING |
| R-2 | USER | CHANGE_REQUEST Constraints | AC-2, N-2 | No switch on dirty or other branch | porcelain + ancestor check; path guards run before the commit so a guard refusal commits nothing | issue text | CAP-GIT | git merge-base --is-ancestor used at from-issue.sh:286 | CODING |
| R-3 | USER | CHANGE_REQUEST Constraints | N-3 | Keep branch | only worktree_remove used | issue text | CAP-GIT | worktrees.sh:233 | CODING |
| R-4 | USER | CHANGE_REQUEST Constraints | AC-3, N-4 | Failures keep state, exit unchanged | each step guarded, no set -e effect | issue text | CAP-GIT | from-issue.sh:870 pattern | CODING |
| R-5 | DESIGN | plan | AC-2 | Dirty main means any non-ignored porcelain entry, including untracked files (--untracked-files=all); the check runs before removal and again immediately before `git switch` (never --force); a switch failure after removal follows S-7 (worktree removed, project not switched, manual `git switch <branch>` printed) | `git -C <source> status --porcelain --untracked-files=all`; any output line means dirty; tests cover a modified tracked file and an untracked-only case | Untracked files can collide with run-branch files and make the switch fail; conservative and revisable | CAP-GIT | git CLI | CODING |
| R-6 | DESIGN | plan | AC-1 | No prompt in any mode | single code path | TUI cannot answer | CAP-GIT | from-issue.sh:864 comment | CODING |
| R-7 | PLATFORM | git signing | AC-3 | Commit honors user signing config and normal hooks/filters; any failure (signing, hook, filter) = keep worktree (S-8) | plain `git add`/`git commit`, no --no-verify, no --no-gpg-sign, no hook or filter overrides | do not bypass user policy | CAP-GIT | worktree-run-test.sh header | CODING (tests disable signing) |
| R-8 | DESIGN | AR-016 | AC-2, AC-3, N-2 | Main-clean check re-run immediately before switch; switch never forced | Repeat the main-project porcelain check (including untracked files) immediately before `git switch`; if no longer clean, skip the switch, keep the branch, print `git switch <branch>` and report not switched. The switch never uses --force, --discard-changes or --merge; a switch failure follows S-7. | Closes the window between the pre-removal checks and the switch | CAP-GIT | git switch refuses to overwrite local changes unless forced; the plan's i4 check precedes worktree_remove, so main may change before the switch | CODING |

CAP-GIT: git CLI available. No live-authentication prerequisites; no LIVE_VERIFICATION checks beyond `bash scripts/run-shell-tests.sh` and `bash scripts/run-python-tests.sh`.

## Decisions

| ID | Decision | Reason |
|---|---|---|
| D-1 | Automatic commit in all modes | resolves open question 1 |
| D-2 | Applies to attended and unattended | resolves open question 2 |
| D-3 | Ignored files not committed; untracked non-ignored files are committed as-is, and .uncle/workflow state is excluded by pathspec | git semantics; removal allowed by git; AC-1 requires all non-ignored output kept, so no secret filtering is attempted |
| D-5 | Summary line reports the number of files committed by the automatic commit | Makes committing untracked non-ignored files (possible secrets such as .env) visible to the user before any later push (AR-013) |
| D-4 | Commit message `uncle: issue <N> change` | simple, identifiable |

## Change-impact table

| Component | Planned change | Reason | Regression risk | Test coverage |
|---|---|---|---|---|
| `scripts/from-issue.sh` | Extract `worktree_path_refusal`; add `finalize_no_pr_worktree`; replace no-PR branches in post-run block | Core feature | PR auto-removal shares path helper | worktree-run-test.sh PR and new cases |
| `scripts/tests/worktree-run-test.sh` | Add no-PR cases; update conflicting expectations | AC-1..5 | Test weakening risk; keep asserts strict | self + defect injection |
| `scripts/README.md` | Document new no-PR behavior | AC-6 | None | manual read |

## Traceability

| Requirement | Behavior | Invariant | Component | Automated test | Manual check |
|---|---|---|---|---|---|
| AC-1 | S-1, S-2, S-3 | N-1 | from-issue.sh | no-pr-switch, pty, unattended cases, clean-tree-no-commit (nothing staged: HEAD unchanged, finalization continues) | scratch run |
| When any guard refuses (path/registration/branch guards before the commit, or dirty or non-ancestor main afterwards), the worktree is kept and the project is not switched. A path-guard refusal happens before the commit, so nothing is committed on that path; a refusal from the main-project checks happens after the commit, so the run output is already committed on the run branch. The summary says `worktree kept; project not switched`. | S-4, S-5 | N-2 | from-issue.sh | dirty-main, other-branch | scratch dirty run |
| AC-3 | S-6, S-7, S-8 | N-4, N-5 | from-issue.sh | failed-removal (PATH-shimmed git failing `worktree remove`; asserts exact remove command text and unchanged exit status), commit-fail, add-fail, clean-tree-no-commit (HEAD unchanged; silent skip), switch-fail (PATH-shimmed git failing `switch`; asserts exact `git switch <branch>` text and unchanged exit status), dirty-main-tracked (modified tracked file in source), dirty-main-untracked (untracked-only file in source) | - |
| Every no-PR COMPLETE run prints exactly one summary line `Branch <b>: worktree removed\|kept; project switched\|not switched.` with these outcomes: success `removed; switched`; guard refusal, commit failure, non-clean status, dirty/non-ancestor main or removal failure `kept; not switched`; switch failure `removed; not switched`. Keep and failure paths also print the literal `git switch <b>` and/or `scripts/lib/worktrees.sh remove <dir>` command. | S-9 | - | from-issue.sh | expect_out in all | scratch run |
| AC-5 | S-10 | N-3, N-6 | from-issue.sh | existing PR cases, driver-failure/non-COMPLETE: no commit, no removal, no switch, guard-refusal cases (symlink, unregistered worktree, detached HEAD, unresolvable path): no commit, worktree kept, remove command printed | - |
| AC-6 | - | - | README.md | - | README read |

## Implementation sequence

1. Core helper and call-site: extract `worktree_path_refusal`, add `finalize_no_pr_worktree`, replace no-PR branches. Gating: `finalize_no_pr_worktree` runs only when WORKTREE=1, workflow state is COMPLETE and PR_CREATED=0 (the existing `from-issue.sh:845` gate plus the PR_CREATED check); on driver failure or any non-COMPLETE state it is never called, so nothing is committed, removed or switched. `finalize_no_pr_worktree` must `cd` to the source checkout (`$SOURCE_PROJECT_ROOT`) before `worktree_remove`, so the process is never standing in the directory it deletes; if that `cd` fails the source is unreachable, so keep the worktree, print the keep summary and the `scripts/lib/worktrees.sh remove <dir>` command, and leave the exit status unchanged (mirrors the PR path at from-issue.sh:854-856). Add a test with an unreachable source asserting the worktree is kept.
   Owns: `scripts/from-issue.sh`
2. Tests: add new cases, update conflicting expectations (record in IMPLEMENTATION_NOTES.md).
   Owns: `scripts/tests/worktree-run-test.sh`
   Depends on: 1
3. Docs: rewrite the README removal sections.
   builds on step 1's final output wording
   Owns: `scripts/README.md`
   Depends on: 1
4. Notes: list each updated test expectation one by one (case name, old assertion, new equally strict assertion, forcing requirement) plus any other material deviations.
   
   Steps 2 and 3 are independent of each other (different files) and can run in parallel after step 1.
   Owns: `.uncle/docs/IMPLEMENTATION_NOTES.md`
   Depends on: 2, 3

## Scope cuts under time pressure
Cut first: switch-fail test, then attended-pty case, then README polish. Never cut: commit-before-remove, dirty-main refusal, exit-status preservation.

## Risks and unresolved questions

- Risk: pinentry/signing hang in unattended runs if user config signs commits; accepted, honors user policy (R-7).
- Risk: ancestor rule refuses when main moved ahead of the run's base; safe failure (prints command).
- No blocking planning decisions remain.
- Accepted risk: untracked non-ignored files (e.g. .env) are committed as-is to the run branch; mitigated only by the committed-file count in the summary (D-5).

## Adversarial review dispositions

| Finding | Disposition | Reason | Exact plan change |
|---|---|---|---|
| AR-001 | Accepted | Real gap: main already on the run branch makes the switch a no-op and the summary ambiguous; skipping the switch and reporting switched is safe. | Edit s1.2.i4 (accept HEAD at or on the run branch) and insert a skip-switch step after it; update the AC-1 requirement. |
| AR-002 | Accepted | Plain porcelain is ambiguous for untracked files that could collide with run-branch files and break the switch; defining dirty as any entry incl. untracked is safer. | R-5 now requires --untracked-files=all (any entry dirty); AC-3 covers post-removal switch failure; tests row adds modified-tracked and untracked-only cases. |
| AR-003 | Accepted | The plan left failed `git add` and the clean-tree commit step unspecified; settling both removes ambiguity for tests and S-8. | Edit s1.2.i2 to classify add/commit failure as S-8 and a clean tree as a silent skip; align AC-3 traceability. |
| AR-004 | Accepted | Guards run before the commit, so on a guard refusal nothing is committed; AC-2 wording claiming output is already committed was wrong. | Edit s1.2.i1, R-2 and AC-2 to state guards precede commit, nothing is committed on refusal, and the summary says kept; not switched. |
| AR-005 | Accepted | Real: the existing guard also refuses untracked files and unpushed commits, which would block the no-PR flow; a precise boundary is needed. | s1.2.i1 now defines worktree_path_refusal as path/symlink/managed-root checks only, with auto_removal_refusal keeping the rest unchanged. |
| AR-006 | Accepted | Summary outcomes were not enumerated, so tests and README could assert different strings. | Step 7 (s1.2.i7) now enumerates the exact summary line per outcome; AC-4 requirement states the same strings. |
| AR-007 | Accepted | The split of auto_removal_refusal was unspecified; stating it exactly keeps the PR path's checks, order and strings unchanged. | Edit s1.2.i1 and s9.1 to define worktree_path_refusal as path checks only and auto_removal_refusal as that plus the unchanged remaining checks. |
| AR-008 | Accepted | Real: worktree_remove refuses on a lock or non-COMPLETE state, and committing .uncle/workflow runtime files would pollute the branch and the clean check. | Edit s1.2.i2 and s1.2.i3 to exclude .uncle/workflow by pathspec from add and the clean-status check; s1.2.i5 keeps the worktree if a lock remains. |
| AR-009 | Accepted | Real gap: switching a detached source HEAD away could lose its position; keeping is the safe, conservative choice. | Edit s1.2.i4 to keep the worktree and print `git switch <branch>` when source HEAD is detached; s12.1 containment updated. |
| AR-010 | Accepted | The call site gates only on WORKTREE and COMPLETE state, and no test covers driver failure or non-COMPLETE state. | Add gating statement to step-1, and a no-commit/no-switch test case for driver failure or non-COMPLETE state to s14.1 and AC-5 traceability. |
| AR-011 | Accepted | The plan never specified the working directory for removal; the helper must leave the worktree and handle an unreachable source, as the PR path does. | Edited step-1 text to require cd to the source checkout before removal and keep the worktree if that cd fails. |
| AR-012 | Accepted | Hooks and filters can run in the unattended commit; policy must be explicit: normal hooks on, hook failure is a commit failure, no bypass flags. | Commit step s1.2.i2 and restriction R-7 state hooks/filters run normally, hook failure keeps the worktree, no bypass flags. |
| AR-013 | Accepted | Committing untracked non-ignored files could capture secrets, but AC-1 requires all output be kept, so commit them as-is, disclose the count, and exclude driver state. | Edit s1.2.i2 (count in summary, .uncle/workflow pathspec exclusion), D-3, and add a new decision D-5. |
| AR-014 | Accepted | Real gap: worktree_remove reads .uncle/workflow lock/state and N-1 needs a clean status, so run state must be explicitly excluded. | Edit s1.2.i2 to exclude .uncle/workflow via pathspec from both the commit and the clean-status check in step 3. |
| AR-015 | Accepted | Detached source HEAD and option-like branch names were unspecified; keeping the worktree is the safe default. | Edit s1.2.i4 to require a named source branch and a validated branch name passed after `--`; add the same rule to Containment s12.1. |
| AR-016 | Accepted | Main can change between the pre-removal checks and the switch, so the main-clean check must be repeated immediately before the switch, which must never be forced. | Add restriction R-8 to s17.1: repeat the main-clean check immediately before git switch; never use --force. |
| AR-017 | Accepted | Real gap: guard-before-commit ordering and refusal behavior were only implicit. | Edit s1.2.i1 to state guards run first, no add/commit on refusal, and that symlinks are refused by the path guard. |
| AR-018 | Accepted | The plan left the nothing-staged case unspecified; a clean tree must skip the commit and continue, with HEAD unchanged. | Edit s1.2.i2 to specify no commit and continue when nothing is staged; add HEAD-unchanged assertion to AC-1 tests. |
| AR-019 | Accepted | Failure tests need a deterministic induction mechanism; PATH-shimmed git is hermetic and exercises the real manual-command output. | Edit s13.1 and AC-3 tests to fix PATH-shim mechanisms for failed-removal and switch-fail with exact command text and exit-status assertions. |
| AR-020 | Accepted | Output wording was undefined; fixing one summary line format plus literal manual commands makes tests and README agree. | Edit s1.2.i7 to define the single summary line and literal commands, and state the old kept line no longer prints. |
| AR-021 | Accepted | Guard refusals (symlink, unregistered worktree, detached HEAD, unresolvable path) were unspecified and untested; ordering before commit needed stating. | Edit s1.2.i1 to state guards run before any add/commit and print keep summary plus remove command; s12.1 and AC-5 gain guard-refusal tests. |
| AR-022 | Accepted | Dirty-main was ambiguous for untracked files; a single explicit definition plus two test fixtures removes the ambiguity. | Edit s1.2.i4 and R-5: dirty means any porcelain entry including untracked (--untracked-files=all); tests cover modified-tracked and untracked-only. |
| AR-023 | Accepted | Approximate line numbers make a weakened assertion indistinguishable from a required update; an equal-strictness rule with itemized notes fixes that. | Rewrote s14.1 so each updated expectation is replaced by an equally strict assertion and listed one by one in IMPLEMENTATION_NOTES.md; step-4 now owns that listing. |
