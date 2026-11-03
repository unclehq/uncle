# Manual checklist

## Coverage

### MC-100
- Required for acceptance: YES
- Exclusive resources: none
- Depends on: none
- Exact action: In a scratch git repo (clean main on a branch that is an ancestor of the run branch), run a real `--worktree` change via scripts/from-issue.sh that completes with no PR, from an interactive terminal in attended mode, with an untracked file among the output.
- Expected result: No y/N prompt appears; the worktree dir is gone, the main project is on the run branch and shows the changed and untracked files, and exactly one line `Branch <b>: worktree removed; project switched.` prints.
- Evidence to capture: Terminal transcript, `git branch --show-current`, `ls` of the worktree path, and `git show --stat HEAD` in main.
- Actual result: 
- Status: NOT RUN

### MC-101
- Required for acceptance: YES
- Exclusive resources: none
- Depends on: none
- Exact action: Repeat the no-PR COMPLETE run in a fresh scratch repo with `--unattended` and with stdin piped (no tty).
- Expected result: Same outcome as attended: commit made, worktree removed, main switched, the success summary line printed once, no prompt, and the old `Worktree ... kept; remove with:` line absent.
- Evidence to capture: Output of both runs and `git log -1 --stat` plus `git branch --show-current` in the main project.
- Actual result: 
- Status: NOT RUN

### MC-102
- Required for acceptance: YES
- Exclusive resources: none
- Depends on: none
- Exact action: In a fresh scratch repo, make the main project dirty (once with a modified tracked file, once with an untracked-only file), then run a no-PR COMPLETE worktree run.
- Expected result: The worktree is kept, main is not switched and the dirty file is untouched, and the summary line is `Branch <b>: worktree kept; project not switched.` with `git switch <b>` and `scripts/lib/worktrees.sh remove <dir>` printed.
- Evidence to capture: Output for both variants, `git status` in main, and a listing showing the worktree dir exists.
- Actual result: 
- Status: NOT RUN

### MC-103
- Required for acceptance: YES
- Exclusive resources: none
- Depends on: none
- Exact action: In a scratch repo, put main on a branch that is not an ancestor of the run branch, then run a no-PR COMPLETE worktree run. Separately, detach main's HEAD and repeat.
- Expected result: Both cases keep the worktree and do not switch. The summary says `worktree kept; project not switched`, and `git switch <b>` is printed. Main's branch or detached HEAD is unchanged.
- Evidence to capture: Output, `git rev-parse HEAD` and `git branch --show-current` in main before and after.
- Actual result: 
- Status: NOT RUN

### MC-106
- Required for acceptance: YES
- Exclusive resources: none
- Depends on: none
- Exact action: Run worktree flows where the run ends with a PR created, where the driver exits non-zero, and where state is not COMPLETE. Check a source checkout that is already on the run branch.
- Expected result: The PR run auto-removes the worktree as before with no commit or switch. Failure and non-COMPLETE runs commit, remove and switch nothing, and the exit status equals the driver's. A source already on the run branch skips the switch and reports `project switched`. The branch survives everywhere.
- Evidence to capture: Output, exit codes, and `git branch --list` and `git log` for each scenario.
- Actual result: 
- Status: NOT RUN

### MC-201
- Exclusive resources: none
- Depends on: none
- Exact action: Run the same no-PR COMPLETE scenario with main dirty: once with a modified tracked file in main and once with an untracked-only file in main (reset between runs). Then repeat with main on a branch that is not an ancestor of the run branch, and with main on a detached HEAD.
- Expected result: Each case keeps the worktree, does not switch main, leaves the main file edits intact, and prints exactly one 'Branch <b>: worktree kept; project not switched.' line plus the literal `git switch <b>` command; the branch still exists.
- Evidence to capture: Transcript for each case, git status and branch in main after each, existence of the worktree directory and run branch.
- Actual result: 
- Status: NOT RUN

### MC-203
- Exclusive resources: none
- Depends on: none
- Exact action: Run the no-PR COMPLETE scenario with a rejecting pre-commit hook in the repo, then with a worktree containing untracked work and a source checkout made unreachable before finalization (or worktree path replaced by a symlink).
- Expected result: Hook rejection keeps the worktree with its files intact, prints 'worktree kept; project not switched.' and the remove command, and no --no-verify is used. The symlink/unreachable cases commit nothing, keep the worktree, and print the keep summary and remove command.
- Evidence to capture: Transcripts, worktree git status and HEAD sha before and after, worktree directory presence.
- Actual result: 
- Status: NOT RUN

### MC-205
- Exclusive resources: none
- Depends on: none
- Exact action: Run the no-PR COMPLETE scenario on a pty (attended) and with `--unattended`/no tty, in a clean main, and also with main already on the run branch and with a clean-tree worktree (nothing to commit).
- Expected result: No 'Remove worktree ...? [y/N]' prompt and no old 'kept; remove with:' line in any mode; results match MC-200. A clean tree creates no commit (HEAD unchanged) and still removes and switches; main already on the run branch reports 'project switched' without error.
- Evidence to capture: Transcripts of each mode and HEAD sha before and after the clean-tree run.
- Actual result: 
- Status: NOT RUN

## resources

### MC-301
- Required for acceptance: YES
- Exclusive resources: dir:scratch-repo-unattended
- Depends on: none
- Exact action: Repeat a no-PR COMPLETE run with `--unattended` (no tty) in a separate scratch repo, with no prompt possible.
- Expected result: Same outcome as attended: commit created, worktree removed, main switched to the run branch, summary line `removed; switched`, and the script exit status equals the driver's.
- Evidence to capture: Captured stdout, `echo $?`, `git branch --show-current`, and worktree-directory existence check.
- Actual result: 
- Status: NOT RUN

### MC-302
- Required for acceptance: YES
- Exclusive resources: dir:scratch-repo-dirty
- Depends on: none
- Exact action: In a scratch repo, make the main project dirty (once with a modified tracked file, once with an untracked-only file) and run a no-PR COMPLETE worktree run.
- Expected result: Worktree is kept, main is not switched and the dirty files are untouched, output contains `Branch <b>: worktree kept; project not switched.` plus literal `git switch <b>` and `scripts/lib/worktrees.sh remove <dir>` commands.
- Evidence to capture: Transcript for both variants, `git status` of main, and the existing worktree directory listing.
- Actual result: 
- Status: NOT RUN

### MC-303
- Required for acceptance: YES
- Exclusive resources: dir:scratch-repo-otherbranch
- Depends on: none
- Exact action: In a scratch repo, put main on an unrelated branch whose tip is not an ancestor of the run branch (and, separately, detach main's HEAD), then run a no-PR COMPLETE worktree run.
- Expected result: Worktree kept, project not switched, exactly one `kept; not switched` summary line, and the manual `git switch <b>` and remove commands printed; the run branch still exists.
- Evidence to capture: Transcript, `git branch --show-current`/`git rev-parse HEAD` of main before and after, and `git branch --list`.
- Actual result: 
- Status: NOT RUN

### MC-304
- Required for acceptance: YES
- Exclusive resources: dir:scratch-repo-dirty
- Depends on: MC-302
- Exact action: Run the manual recovery commands printed in a kept-worktree outcome: `git switch <b>` in the (clean) main project and `scripts/lib/worktrees.sh remove <dir>`, using the transcript from the dirty-main check after cleaning main.
- Expected result: Removal succeeds with `Removed worktree <dir> (branch kept)`, the branch remains, and `git switch <b>` succeeds showing the committed run output.
- Evidence to capture: Command output of both commands and `git branch --list` afterward.
- Actual result: 
- Status: NOT RUN

### MC-306
- Required for acceptance: YES
- Exclusive resources: dir:scratch-repo-hook
- Depends on: none
- Exact action: In a scratch repo with a rejecting pre-commit hook, run a no-PR COMPLETE worktree run; also run a run that ends in a failed driver / non-COMPLETE state.
- Expected result: Hook-rejected run: worktree kept with its uncommitted output intact, `kept; not switched` and remove command printed. Failed/non-COMPLETE run: no commit created, no removal, no switch, no summary line, exit status equals driver's.
- Evidence to capture: Transcripts, `git log` in the worktree, `git status` there, main's branch, and exit codes.
- Actual result: 
- Status: NOT RUN

## Regressions

### MC-401
- Required for acceptance: YES
- Exclusive resources: none
- Depends on: none
- Exact action: In a scratch repo, run a `--worktree` change whose stub driver ends COMPLETE with a valid fresh PR journal (phase created, matching head_branch and URL). Observe the final output and the filesystem.
- Expected result: The worktree directory is removed, the run branch still exists, no prompt appears, no new commit is made on the run branch, the main project is not switched, and no `Branch ...:` summary line is printed.
- Evidence to capture: Terminal output, `git branch --list`, `git -C <source> branch --show-current`, and the run branch's HEAD sha before and after.
- Actual result: 
- Status: NOT RUN

### MC-402
- Required for acceptance: YES
- Exclusive resources: none
- Depends on: none
- Exact action: Run a `--worktree` change where the driver exits non-zero, and a second one where the final state is not COMPLETE. Leave uncommitted output in each worktree.
- Expected result: Each worktree is kept with its uncommitted output intact. No commit is created, the main project is not switched, no no-PR summary line is printed, and the script exit status equals the driver's.
- Evidence to capture: Exit codes, terminal output, `git -C <worktree> status --porcelain`, and the run branch HEAD sha before and after.
- Actual result: 
- Status: NOT RUN

### MC-403
- Required for acceptance: YES
- Exclusive resources: none
- Depends on: none
- Exact action: Run a PR-created `--worktree` run with an untracked file left in the worktree, then another with a local commit not pushed to any remote. Observe the output.
- Expected result: Each worktree is kept. The existing refusal strings are printed unchanged: `the worktree contains untracked files` and `the worktree has N commit(s) not pushed to a remote`. The `Worktree <dir> kept; remove with: scripts/lib/worktrees.sh remove <dir>` line is printed.
- Evidence to capture: Terminal output showing the exact refusal and keep lines.
- Actual result: 
- Status: NOT RUN

### MC-404
- Required for acceptance: YES
- Exclusive resources: none
- Depends on: none
- Exact action: Run `scripts/lib/worktrees.sh remove <dir>` directly. Do it on a finished COMPLETE worktree with a lock file present, then on a worktree with a dirty tracked file, then on a clean COMPLETE worktree with no lock.
- Expected result: The first two attempts refuse with the existing messages and keep the worktree. The third removes the worktree and prints `Removed worktree <dir> (branch kept)`, and the branch survives.
- Evidence to capture: Output and exit code of each invocation, `git worktree list`, and `git branch --list`.
- Actual result: 
- Status: NOT RUN

### MC-405
- Required for acceptance: YES
- Exclusive resources: none
- Depends on: none
- Exact action: Run a no-PR COMPLETE `--worktree` run with a clean main project, once under a pty and once with `--unattended`. Then run `scripts/lib/worktrees.sh remove` manually on a kept worktree.
- Expected result: No `Remove worktree <dir>? [y/N]` prompt and no `Worktree <dir> kept; remove with:` line appears on the no-PR path. The final output has exactly one line, `Branch <b>: worktree removed; project switched.`, and the exit status matches the driver's.
- Evidence to capture: Captured pty and unattended terminal transcripts, plus exit codes.
- Actual result: 
- Status: NOT RUN
