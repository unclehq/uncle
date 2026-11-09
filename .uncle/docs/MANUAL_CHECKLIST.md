# Manual checklist

## Coverage: change branch

### MC-104
- Required for acceptance: YES
- Exclusive resources: none
- Depends on: none
- Exact action: In a scratch repo on main with no remote, run a change request with WORKFLOW_WORKTREE=0; then repeat on a feature branch, and re-run/resume on the created branch.
- Expected result: Each first run prints `Branch: <name>` and `git branch --show-current` shows a new branch before the first stage; the resume creates no further branch.
- Evidence to capture: Branch name before/after and `git branch` listing after resume.
- Actual result: 
- Status: NOT RUN

## Coverage: issue worktree

### MC-106
- Required for acceptance: YES
- Exclusive resources: none
- Depends on: none
- Exact action: In a scratch repo with a stubbed or available issue, run `./scripts/from-issue.sh N --worktree`, then `./scripts/from-issue.sh --new --worktree`.
- Expected result: The first creates a worktree on a new branch as before; the second exits 1 with `--worktree and --worktree-dir require --change`.
- Evidence to capture: Command output, exit statuses and `git worktree list`.
- Actual result: 
- Status: NOT RUN

## Invariants

### MC-203
- Required for acceptance: YES
- Exclusive resources: none
- Depends on: none
- Exact action: In a scratch repo on main with no remote, run a change request with WORKFLOW_WORKTREE=0, then check `git branch --show-current` and `git branch` before the first stage proceeds and after.
- Expected result: The run is on a newly created branch (not main) and 'Branch: <name>' is printed. Main's SHA is unchanged and no other branch is created or deleted.
- Evidence to capture: Terminal output, branch listings before and after, and main's SHA before and after.
- Actual result: 
- Status: NOT RUN

### MC-204
- Required for acceptance: YES
- Exclusive resources: none
- Depends on: MC-203
- Exact action: Resume the change run from MC-203 on its recorded branch. Separately, plant a stale `.uncle/workflow/run-branch` naming main (or a nonexistent branch) in a fresh scratch repo on main and start a change run.
- Expected result: The resumed run creates no further branch. The planted marker does not suppress the guard, so the run still moves to a new branch.
- Evidence to capture: Branch listings before and after each run and the terminal output.
- Actual result: 
- Status: NOT RUN

### MC-206
- Required for acceptance: YES
- Exclusive resources: none
- Depends on: none
- Exact action: Run `./scripts/from-issue.sh <N> --worktree` in a scratch repo, then `./scripts/from-issue.sh --new --worktree`.
- Expected result: The first creates a sibling worktree on a new branch with a copy of .uncle/config. The second exits 1 with '--worktree and --worktree-dir require --change'.
- Evidence to capture: Terminal output, exit codes, and worktree listing.
- Actual result: 
- Status: NOT RUN

## Resources: change run

### MC-304
- Required for acceptance: YES
- Exclusive resources: dir:scratch-change
- Depends on: none
- Exact action: In a scratch repo on main with no remote, run a change request with WORKFLOW_WORKTREE=0, and check `git branch --show-current` once the first stage has started.
- Expected result: The checkout is on a newly created branch, not main, and a 'Branch: <name>' line was printed. Main is unchanged.
- Evidence to capture: Console output, current branch name, and `git branch` listing.
- Actual result: 
- Status: NOT RUN

### MC-305
- Required for acceptance: YES
- Exclusive resources: dir:scratch-change
- Depends on: MC-304
- Exact action: Stop and resume that change run on the same branch, then check `git branch`.
- Expected result: No further branch is created on resume.
- Evidence to capture: `git branch` listing before and after resume.
- Actual result: 
- Status: NOT RUN

## Resources: preserved behavior

### MC-306
- Required for acceptance: YES
- Exclusive resources: dir:scratch-issue
- Depends on: none
- Exact action: Run `./scripts/from-issue.sh <N> --worktree` in a scratch repo, then `./scripts/from-issue.sh --new --worktree`.
- Expected result: The first creates a worktree on a new branch as before. The second exits 1 with '--worktree and --worktree-dir require --change'.
- Evidence to capture: Console output, exit status, and `git worktree list`.
- Actual result: 
- Status: NOT RUN

## Regressions

### MC-401
- Required for acceptance: YES
- Exclusive resources: none
- Depends on: none
- Exact action: In a scratch git repo with a remote, run `from-issue.sh <N> --worktree` (or `--worktree-dir <path>`) against a stubbed/local issue, then run `git worktree list` and `git branch`.
- Expected result: An opt-in issue worktree is created on a new branch exactly as before, with a copy of .uncle/config; no policy refusal or 'worktrees not used' notice appears.
- Evidence to capture: Command output plus git worktree list and git branch listings.
- Actual result: 
- Status: NOT RUN

### MC-402
- Required for acceptance: YES
- Exclusive resources: none
- Depends on: none
- Exact action: Run `from-issue.sh --new --worktree` in a scratch repo.
- Expected result: Exits 1 with message `--worktree and --worktree-dir require --change`, unchanged from before.
- Evidence to capture: Exit status and message text.
- Actual result: 
- Status: NOT RUN

### MC-403
- Required for acceptance: YES
- Exclusive resources: none
- Depends on: none
- Exact action: In a scratch repo with a remote on clean main, start a change run with default settings (no WORKFLOW_WORKTREE override) and note `git worktree list` and the working directory it reports.
- Expected result: The change run still gets its default worktree on a new branch, and main's ref is unchanged.
- Evidence to capture: Launcher output, git worktree list, git branch, SHA of main before and after.
- Actual result: 
- Status: NOT RUN
