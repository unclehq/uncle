# Two issues on one project: worktrees

One run per directory is the rule. To work a second issue at the same time,
run it in a git worktree beside the project:

```sh
./scripts/from-issue.sh 64 --worktree          # creates ../<project>-issue-64 on a new branch
uncle --runs                                    # #64  IMPLEMENT  locked  /path/<project>-issue-64
```

`--worktree-dir PATH` and `--branch NAME` override the defaults. The worktree
gets a copy of `.uncle/config` and its own workflow state; the branch becomes
the PR head. When the run completes, Uncle offers to remove the directory
(never the branch); `bash scripts/lib/worktrees.sh remove <dir>` does the same
later and refuses while a run holds the lock or is not `COMPLETE`. Every
worktree runs the one installed `uncle`, so do not upgrade it mid-run. Details
in [scripts/README.md](../scripts/README.md#--worktree---worktree-dir---branch--run-an-issue-in-a-git-worktree).

## Branch and worktree policy

- **New-application builds (`app`) run on `main` in the project checkout.** No
  worktree is created. A build is refused, with the reason stated, when the
  checkout is not on `main`, has uncommitted changes, or has a detached HEAD.
  `WORKFLOW_WORKTREE=1` on a fresh app start does not create a worktree; the
  driver prints a "worktree not used" notice once.
- **Change runs get their own branch.** An in-place change run on `main` or on
  a branch that is not a run branch switches to a new run branch first, with or
  without a git remote.
- **Other launches** (issue runs, `--worktree`) keep creating a worktree.
- Resume is unaffected. `UNCLE_RUN_POLICY=off` disables the app preflight and
  the change-branch guard (the shared test runners set it for legacy suites).
