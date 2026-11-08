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
