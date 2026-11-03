# Change Spec - Issue 141

Omitted sections: Performance, Security (beyond invariants), Migration (none), Prototype isolation (not a prototype)

## 1. Change type
Feature.

## 2. Problem statement
A COMPLETE `--worktree` run with no PR leaves its result uncommitted in a sibling worktree and the main project looks untouched (CHANGE_REQUEST.md).

## 3. Current behavior
Baseline B-2, B-3.

## 4. Desired behavior
After COMPLETE with no created PR, in every mode (attended, TUI, unattended) with no prompt: commit all run output on the run branch, remove the worktree, switch the main project to the branch, and print a plain summary. Any doubt keeps the worktree and prints a manual command.

## 5. Observable behavior table
| ID | Class | Trigger | Current behavior | Expected behavior | Verification |
|---|---|---|---|---|---|
| S-1 | ADD | COMPLETE, no PR, clean main on a branch that is an ancestor of the run branch | Worktree kept | Uncommitted/untracked output committed, worktree removed, main switched to run branch, change visible | worktree-run-test.sh case no-pr-switch |
| S-2 | MODIFY | COMPLETE, no PR, tty attended | y/N prompt | No prompt; S-1 behavior | pty case |
| S-3 | MODIFY | COMPLETE, no PR, `--unattended` or no tty | Kept, prints remove command | S-1 behavior | unattended case |
| S-4 | ADD | Main project has uncommitted changes | n/a | Worktree kept (work committed on branch), branch name and `git switch <branch>` printed, summary says not switched | dirty-main case |
| S-5 | ADD | Main on a branch whose tip is not an ancestor of the run branch | n/a | Same refusal as S-4 | other-branch case |
| S-6 | ADD | `git worktree remove` fails | n/a | Worktree kept, manual remove command printed, exit status unchanged | failed-removal case |
| S-7 | ADD | `git switch` fails after removal | n/a | Branch and commit intact, manual `git switch` printed, exit unchanged | switch-fail case |
| S-8 | ADD | Commit fails | n/a | Worktree kept, manual commands printed, no removal | commit-fail case |
| S-9 | ADD | Any no-PR outcome | n/a | Final output states branch name, worktree removed or kept, project switched or not | all cases assert text |
| S-10 | PRESERVE | PR created (B-1), driver failure (B-6), non-COMPLETE (B-4) | as baseline | unchanged; no commit, no switch | existing cases |

## 6. Invariant table
| ID | Status | Invariant | Scope | Enforcement point | Verification |
|---|---|---|---|---|---|
| N-1 | NEW | A worktree is never removed unless HEAD commits contain all its tracked and non-ignored untracked content | no-PR finalization | commit step then clean-status check before removal | tests assert tree clean and commit contains file |
| N-2 | NEW | Main project is never switched when dirty or on a non-ancestor branch | no-PR finalization | pre-removal check | S-4, S-5 tests |
| N-3 | EXISTING | Run branch is never deleted | all | no `branch -d` anywhere | branch-exists asserts |
| N-4 | EXISTING | Exit status equals driver status | all | I-1 | status asserts |
| N-5 | EXISTING | Removal guards (lock, COMPLETE, managed root) apply | all | worktree_remove, path guards | existing tests |
| N-6 | EXISTING | PR-created path is unchanged | PR runs | separate branch of if | B-1 tests |

No RELAXED or REMOVED invariants.

## 7. Compatibility
No new flags; `scripts/lib/worktrees.sh remove` CLI unchanged. `offer_worktree_removal` stays defined (sourced by tests).

## 8. Error behavior
See S-4 to S-8; every failure keeps what remains and prints a manual command; exit status unchanged.

## 10. Security
Never use `--force`; never delete the branch; refuse paths outside the managed root or symlinked worktree paths.

## 12. Rollback
Revert the commit; worktrees already removed are recoverable from the kept branch (`git worktree add <dir> <branch>`).

## 14. Non-goals
PR creation changes; deleting branches; pushing; force removal; stashing the main project's changes; recording the run's base branch.

## 15. Assumptions
- Open question 1 resolved: commit is automatic. Open question 2 resolved: applies to attended and unattended runs.
- Ignored files in the worktree are not committed; git removes them with the worktree.
- The commit honors the user's git signing config; a signing failure is a commit failure (S-8).
- "Dirty main" means any non-ignored porcelain entry (conservative).

## Acceptance criteria

| ID | Criterion | Verification |
|---|---|---|
| AC-1 | A COMPLETE --worktree run with no PR, clean main project: all output (including untracked files) is committed on the run branch, the worktree directory is gone, the main project is on the run branch and shows the changed file, with no prompt in attended, pty and unattended modes. | worktree-run-test.sh new cases (pty and unattended included) asserting dir absent, branch checked out in main, file content, commit contains the file |
| AC-2 | A dirty main project, or main on a branch not contained in the run branch, leaves the worktree in place (run output already committed), prints the branch name and `git switch <branch>`, and does not switch. | worktree-run-test.sh dirty-main and other-branch cases |
| AC-3 | A failed worktree removal keeps the worktree and prints the manual removal command; a failed commit keeps the worktree; a failed switch after removal keeps the branch and prints the switch command. The script exit status equals the driver's in all cases. | worktree-run-test.sh failed-removal, commit-fail, switch-fail cases with status asserts |
| AC-4 | Final output for every no-PR outcome states the branch name, whether the worktree was removed, and whether the project was switched. | expect_out assertions in each new case |
| AC-5 | The branch always survives; PR-created, non-COMPLETE and driver-failure behaviors are unchanged and no commit/switch happens in them. | existing worktree-run-test.sh PR cases plus new assertions; bash scripts/run-shell-tests.sh |
| AC-6 | scripts/README.md describes the new no-PR behavior and no longer documents the y/N prompt as the no-PR flow. | manual read of README section; grep for stale prompt text |

