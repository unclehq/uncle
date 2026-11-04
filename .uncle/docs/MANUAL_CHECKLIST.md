# Manual checklist

## Coverage

### MC-102
- Required for acceptance: YES
- Exclusive resources: account:scratch-github-repo
- Depends on: MC-101
- Exact action: On a second scratch repo, run `uncle --housekeeping --unattended` with a rename task, then separately run an attended rename and decline at the approval prompt.
- Expected result: Unattended runs with no prompt and the report states nobody approved and lists every operation, ending VERIFIED. Declined run executes nothing, records DECLINED, exits 0, and repo name is unchanged.
- Evidence to capture: Both transcripts, reports, gh repo view output before and after.
- Actual result: 
- Status: NOT RUN

### MC-103
- Required for acceptance: YES
- Exclusive resources: none
- Depends on: none
- Exact action: Run `uncle --housekeeping` (attended, then --unattended) with a task that makes the planner propose a disallowed command such as `gh repo delete` or `git push --force origin main`, and another with an unparseable command piped to a shell.
- Expected result: The whole plan is refused before execution in both modes, naming the rule and the command, exit 1, and nothing is changed on the repository.
- Evidence to capture: Transcripts showing refusal messages, exit status, repo state unchanged.
- Actual result: 
- Status: NOT RUN

### MC-104
- Required for acceptance: YES
- Exclusive resources: none
- Depends on: none
- Exact action: Run `uncle --housekeeping` with empty stdin, with control-character input, and combined with `--issue 1`; also run `uncle --housekeepin`.
- Expected result: Empty and control-character input are refused with a reason and nothing runs; the combination gives a mutually exclusive error with exit 1; the misspelling suggests `--housekeeping`. Usage text lists --housekeeping.
- Evidence to capture: Terminal output and exit statuses for each invocation.
- Actual result: 
- Status: NOT RUN

### MC-105
- Required for acceptance: YES
- Exclusive resources: none
- Depends on: none
- Exact action: In the TUI, type `/housekeeping prune merged worktrees`, check slash help and completion list it, and observe the flow.
- Expected result: The command appears in help and completion and starts the same plan, policy, approval flow as the CLI.
- Evidence to capture: Screenshots or transcript of help, completion and plan screen.
- Actual result: 
- Status: NOT RUN

### MC-106
- Required for acceptance: YES
- Exclusive resources: file:.uncle/config
- Depends on: none
- Exact action: In Configure > Miscellaneous (TUI, then line menu), open Housekeeping disallow list; view it, add a valid pattern, try an empty pattern and bare `*`, edit, remove, try removing a floor entry, then reset to defaults; confirm other config entries still exist.
- Expected result: Floor shown locked and not removable; invalid patterns are rejected keeping the old list; add/edit/remove/reset persist in .uncle/config; the entry is last in each menu and existing items keep their numbers.
- Evidence to capture: Screenshots or transcripts of each step and the config file's housekeeping.disallow line.
- Actual result: 
- Status: NOT RUN

### MC-107
- Required for acceptance: YES
- Exclusive resources: file:.uncle/workflow/driver.lock
- Depends on: none
- Exact action: Start a long-running uncle workflow in the checkout holding driver.lock, then run `uncle --housekeeping` with a task in a second terminal; afterwards run housekeeping again once the first workflow exits.
- Expected result: The concurrent run is refused via the driver lock and changes nothing; the later run starts normally, showing the lock was released.
- Evidence to capture: Both terminal outputs and exit statuses.
- Actual result: 
- Status: NOT RUN

## Invariants

### MC-200
- Required for acceptance: YES
- Exclusive resources: none
- Depends on: none
- Exact action: In a scratch checkout, run `uncle --housekeeping` with a plan containing an allowlisted op plus one disallowed op (e.g. `gh repo delete`), attended and then with `--unattended`, using stub gh/git on PATH that log calls.
- Expected result: Both runs refuse the whole plan before execution, naming the rule and command; the stub call log is empty and exit status is 1.
- Evidence to capture: Terminal output of both runs, exit statuses, and the empty stub call log.
- Actual result: 
- Status: NOT RUN

### MC-201
- Required for acceptance: YES
- Exclusive resources: none
- Depends on: none
- Exact action: Run `uncle --housekeeping` with a plan whose op argv is not an allowlisted exact shape (e.g. `git branch -D x`, `git -c k=v branch -d x`, `git push origin --delete main`) using logging stubs.
- Expected result: Each plan is refused naming the operation or rule; no stub call is logged.
- Evidence to capture: Refusal messages and stub call log for each plan.
- Actual result: 
- Status: NOT RUN

### MC-202
- Required for acceptance: YES
- Exclusive resources: none
- Depends on: none
- Exact action: Run an attended approve of a two-op plan where the second op's stub fails, then view the printed report and run record.
- Expected result: Ops run in order, execution stops at the failure, the later op does not run, verified ops are reported with status, unexecuted ops show NOT_VERIFIED, and the exit status is 1.
- Evidence to capture: Report text, run record with command order and exit statuses, exit code.
- Actual result: 
- Status: NOT RUN

### MC-204
- Required for acceptance: YES
- Exclusive resources: file:.uncle/workflow/driver.lock
- Depends on: none
- Exact action: Hold the driver lock by running one `uncle` workflow in the checkout, then start `uncle --housekeeping` with a valid task in the same checkout; afterwards run an attended decline and confirm `git status` of tracked files.
- Expected result: The concurrent run is refused via the driver lock with no changes and no stub calls; the decline runs nothing and records declined; tracked files are unchanged and the lock is released afterward.
- Evidence to capture: Refusal output, stub call log, decline record, git status output, successful later lock acquisition.
- Actual result: 
- Status: NOT RUN

### MC-205
- Required for acceptance: YES
- Exclusive resources: file:.uncle/config
- Depends on: none
- Exact action: In Configure > Miscellaneous (TUI), open Housekeeping disallow list, try to add an empty pattern, bare `*`, a duplicate and a locked-floor pattern, try to remove a floor entry, then add a valid pattern and restart.
- Expected result: Invalid, duplicate and floor-equal patterns are rejected leaving the list unchanged; floor entries appear locked and cannot be removed; the valid pattern persists and other `.uncle/config` keys are unchanged.
- Evidence to capture: Screenshots or transcript of the TUI screen and `.uncle/config` contents before and after.
- Actual result: 
- Status: NOT RUN

### MC-206
- Required for acceptance: YES
- Exclusive resources: file:.uncle/config
- Depends on: none
- Exact action: Corrupt the `housekeeping.disallow` value in `.uncle/config`, then run a housekeeping plan containing `gh repo delete` and view the disallow list in the line menu.
- Expected result: The list falls back to defaults (never empty), the floor still applies, and the plan is refused.
- Evidence to capture: Line menu output and refusal message.
- Actual result: 
- Status: NOT RUN

### MC-301
- Exclusive resources: file:driver.lock
- Depends on: none
- Exact action: In a scratch git checkout, start `uncle --housekeeping "prune stale worktrees"` (attended) so it holds driver.lock at the approval prompt, then in a second terminal in the same checkout run `uncle --housekeeping "prune stale worktrees"` again.
- Expected result: The second run is refused because another driver holds the checkout (driver.lock), exits nonzero, and runs no commands or state changes. After the first run is declined, the lock is released and a third run starts normally.
- Actual result: 
- Status: NOT RUN

### MC-304
- Exclusive resources: account:github-scratch-repo
- Depends on: none
- Exact action: Run `uncle --housekeeping "delete repo X with gh repo delete"` attended and again with `--unattended`, in a scratch repo.
- Expected result: The whole plan is refused before any command executes, naming the disallow rule and command, in both modes, and exits 1. The repo still exists.
- Actual result: 
- Status: NOT RUN

### MC-305
- Exclusive resources: file:.uncle/config
- Depends on: none
- Exact action: In the TUI, open Configure > Miscellaneous > Housekeeping disallow list. View it, add a valid pattern, try to add an empty pattern and a bare `*`, try to add a duplicate and a floor-equal pattern, try to remove a locked floor entry, then reset to defaults.
- Expected result: The floor entries show as locked and cannot be removed. Invalid, empty, bare `*`, duplicate and floor-equal patterns are rejected and leave the list unchanged. The valid add is persisted and reset restores the defaults. The entry is last in the menu and other items keep their numbers.
- Actual result: 
- Status: NOT RUN

### MC-306
- Exclusive resources: file:.uncle/config
- Depends on: MC-305
- Exact action: Run `uncle` without the TUI so the line-menu Configure screen appears, open Miscellaneous, then use the last numbered Housekeeping disallow list entry to add a pattern and view the list. Then, in the TUI, type `/housekeeping prune worktrees` after checking slash help and completion.
- Expected result: The line-menu entry holds the last number, no existing item is renumbered, and the added pattern is saved and listed. The TUI slash help and completion list /housekeeping, and the command starts the same flow as the CLI.
- Actual result: 
- Status: NOT RUN

## Regressions

### MC-401
- Required for acceptance: YES
- Exclusive resources: file:.uncle/workflow/driver.lock
- Depends on: none
- Exact action: In a scratch checkout, run `uncle --change-request` with a valid request on stdin, then `uncle --application` and `uncle --issue` with their usual inputs, and observe each flow start as before.
- Expected result: Each existing entry point starts its usual flow unchanged; `--unattended` still composes with them as before.
- Evidence to capture: Terminal output or screenshots for each launch showing the normal flow starting.
- Actual result: 
- Status: NOT RUN

### MC-402
- Required for acceptance: YES
- Exclusive resources: none
- Depends on: none
- Exact action: Run `uncle --application --change-request`, `uncle --issue 1 --change-request` and `uncle --application --issue 1`. Then run `uncle --change-requset` (a typo) and `uncle --bogus-flag`.
- Expected result: Each combination prints an `Error: ... mutually exclusive` message and exits 1. Typos print the did-you-mean suggestion as before, and the existing flags still appear in it.
- Evidence to capture: Error text and exit status of each invocation.
- Actual result: 
- Status: NOT RUN

### MC-404
- Required for acceptance: YES
- Exclusive resources: file:.uncle/config
- Depends on: none
- Exact action: Open the TUI and type each existing slash command (`/issue`, `/change`, `/triage` and the rest shown in `/help`). Then open the completion list and `/help`.
- Expected result: Every existing slash command behaves as before. `/help` and completion list the old commands plus `/housekeeping`.
- Evidence to capture: Screenshots of the `/help` output and the completion list.
- Actual result: 
- Status: NOT RUN

### MC-405
- Required for acceptance: YES
- Exclusive resources: file:.uncle/config
- Depends on: none
- Exact action: Open Configure in the TUI and in the line menu (`UNCLE_NO_TUI` fallback or the equivalent). Note the number of each existing item, select the existing Miscellaneous items (e.g. auto_mode, approval_name, Markdown viewer), and change then restore one value.
- Expected result: Every existing item keeps its original number and still works. The Housekeeping disallow list entry takes the last number in each menu. Other config keys are unchanged after the edits.
- Evidence to capture: Menu screenshots or transcripts showing the numbering and the `.uncle/config` contents before and after.
- Actual result: 
- Status: NOT RUN

### MC-406
- Required for acceptance: YES
- Exclusive resources: file:.uncle/workflow/driver.lock
- Depends on: none
- Exact action: Start a first uncle session in a scratch checkout so it holds `driver.lock`. In a second terminal, start a second uncle session and then `uncle --housekeeping 'prune worktrees'`.
- Expected result: Both are refused by the lock as before, with nothing changed. After the first session exits, a new session starts normally, so the lock was not leaked.
- Evidence to capture: Refusal messages from both attempts and the successful start afterward.
- Actual result: 
- Status: NOT RUN
