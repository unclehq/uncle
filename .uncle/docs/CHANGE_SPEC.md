# Change spec: branch and worktree policy

Omitted sections: Performance (negligible git calls); Security (no new trust boundary); Migration (none); Prototype isolation (not applicable).

## 1. Change type
Behavior change.

## 2. Problem statement
App builds and change runs both get an Uncle worktree by default, and a change run on a checkout with no remote (or unborn/detached HEAD) gets no branch at all. The operator wants a predictable policy: change work on a new branch, new app builds directly in `main` with no worktree and no branch.

## 3. Current behavior
See baseline B-1..B-9.

## 4. Desired behavior
1. Change run (`change-workflow.sh`, `from-issue.sh` change mode, home actions create_change/run_change/github_issue) is on a newly created branch before any edit, unless already on the branch recorded as created for this run.
2. App build (`stagegate.sh`, create_app/run_app) runs in `main` of the current checkout: no worktree, no branch.
3. Any worktree option/setting requested for an app build is ignored and Uncle says so plainly.
4. App build refuses to start (nothing written) if the checkout is a git repository with commits and is not on `main`, or has uncommitted changes other than Uncle's own files; the message states which and why.
5. Opt-in issue worktrees keep working.

## 5. Observable behavior table
| ID | Class | Trigger | Current behavior | Expected behavior | Verification |
|---|---|---|---|---|---|
| BH-1 | MODIFY | Change run, any launcher, no worktree and no remote (B-4) | Stays on current branch | Switches to a new branch before first stage; prints `Branch: <name>` | run-policy-test.sh |
| BH-2 | PRESERVE | Change run with remote on default branch (B-3) | Engine creates branch | Unchanged; same branch name scheme | early-branch-test.py |
| BH-3 | PRESERVE | Change run resumed on its recorded run branch (B-5) | Adopts branch | No second branch created | run-policy-test.sh |
| BH-4 | MODIFY | App run via `uncle`/TUI/headless | Sibling worktree + new branch | No worktree, no branch; runs in the current checkout on `main` | run-policy-test.sh/.py |
| BH-5 | ADD | App build off `main` | Runs | Exit 1 before any write; message names current branch and `main` | run-policy-test.sh |
| BH-6 | ADD | App build with uncommitted changes (excluding `.uncle/`, `REQUIREMENTS.md`, `CHANGE_REQUEST.md`) | Runs | Exit 1 before any write; message says uncommitted changes and lists up to 10 paths | run-policy-test.sh |
| BH-7 | ADD | App build with `WORKFLOW_WORKTREE=1` set explicitly | Worktree made | Notice `Worktrees are not used for application builds; building in main of this checkout.`; no worktree | run-policy-test.sh |
| BH-8 | PRESERVE | `from-issue.sh N --worktree` | Worktree on new branch | Unchanged | worktree-run-test.sh |
| BH-9 | PRESERVE | `from-issue.sh --new --worktree` | Exit 1 | Unchanged | existing tests |
| BH-10 | PRESERVE | Resumed app run (state file exists) or non-git/unborn-HEAD project | n/a | Preflight skipped; run continues | run-policy-test.sh |
| BH-11 | PRESERVE | Legacy in-flight owned app worktree | Merge-back | Merge code retained and unchanged | worktree-merge tests |
| BH-12 | MODIFY | Docs and home-agent prompt | No policy text | Describe the policy | grep in test |

## 6. Invariant table
| ID | Status | Invariant | Scope | Enforcement point | Verification |
|---|---|---|---|---|---|
| INV-1 | NEW | The branch/worktree decision for a run kind is made only in `scripts/lib/run-policy.sh` | all launchers and drivers | run-policy.sh | run-policy-test.sh (callers delegate) |
| INV-2 | NEW | An app build never creates a worktree or a branch | stagegate path | worktree_auto + driver | run-policy-test.sh (`git worktree list`/`git branch` before = after) |
| INV-3 | NEW | A change run has left the starting branch for a new branch before the first stage | change path | driver guard | run-policy-test.sh |
| INV-4 | NEW | A refused app start writes nothing | stagegate path | preflight before first write | run-policy-test.sh |
| INV-5 | EXISTING | No existing branch or worktree is deleted or force-modified | all | no delete in new code | run-policy-test.sh, worktree tests |
| INV-6 | EXISTING | Approval and verification gates unchanged | drivers | untouched code | existing suites |

No invariant is RELAXED or REMOVED.

## 7. Compatibility
Change runs keep their worktree default (already a new branch). `WORKFLOW_WORKTREE=0`, `--no-worktree`, `--worktree`, `--worktree-dir`, `--branch` keep meaning for change and issue runs.

## 8. Error and failure behavior
App preflight failure: message on stderr, exit 1, no state written. Branch-guard failure (name invalid, switch fails): message, exit 1 before any stage; no branch deleted. Non-git, unborn HEAD: policy skips with no error (`uncle_ensure_project_git` owns repo creation). Detached HEAD on change run: branch created from it.

## 11-12. Migration and rollback
No data migration. Rollback is reverting the commit; branches created by runs are left in place.

## 14. Non-goals
Changing review/plan/verify stages; removing issue worktree support; changing push/PR behavior; editing `from-issue.sh`; removing `worktree-merge.sh`.

## 15. Assumptions
- A1: `main` includes `master` only when no local `main` exists.
- A2: Change runs keep their default worktree (it satisfies 'new branch'); the guard covers runs that proceed in place.
- A3: Uncle's own files excluded from the dirty check: `.uncle/`, `REQUIREMENTS.md`, `CHANGE_REQUEST.md`.

## Acceptance criteria

| ID | Criterion | Verification |
|---|---|---|
| AC-1 | A change run that proceeds in place (WORKFLOW_WORKTREE=0, no remote) is on a newly created branch, shown by `git branch --show-current`, before the first stage runs. | run-policy-test.sh: fixture repo on main, run policy function/driver start, assert branch differs from main and is new. |
| AC-2 | A change run resumed on the branch recorded as created for it creates no further branch. | run-policy-test.sh: run guard twice; branch list unchanged after second call. |
| AC-3 | A new application build started on a clean `main` creates no worktree and no branch. | run-policy-test.sh and run-policy-test.py: `git worktree list` and `git branch` identical before and after the launcher path (worktree_auto with app kind prints nothing). |
| AC-4 | An application build refuses to start, exit 1 with a message naming the cause, when the checkout is not on `main` or has uncommitted changes; nothing is written. | run-policy-test.sh: both refusal cases plus clean-main pass case; assert exit status, message, and no new files under .uncle/workflow. |
| AC-5 | An explicitly requested worktree setting (WORKFLOW_WORKTREE=1) on an app build is ignored and Uncle says plainly that worktrees are not used for application builds. | run-policy-test.sh: assert notice text and no worktree. |
| AC-6 | Opt-in issue worktrees and existing worktree tests are unaffected. | scripts/run-shell-tests.sh and scripts/run-python-tests.sh show no new failures against baseline. |
| AC-7 | The branch/worktree decision is made in one place (scripts/lib/run-policy.sh); uncle, uncle_tui.py, run_duties.py, uncle_headless.py and the drivers delegate to it. | run-policy-test.py asserts launchers pass the run kind to the shared function; code inspection. |
| AC-8 | docs/worktrees.md, prompts/home-agent.md and scripts/README.md describe the policy. | run-policy-test.sh greps for the policy sentences. |
| AC-9 | No existing branch or worktree is deleted or force-modified by the new code. | run-policy-test.sh: pre-existing branch and worktree still present with same SHA. |

