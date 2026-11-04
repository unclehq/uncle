# Change Spec: Housekeeping capability (Issue 148)

Omitted sections: Migration (no persisted format changes beyond one new optional config key); Prototype isolation (not a prototype); Performance (no stated requirement)

## 1. Change type
Feature.

## 2. Problem statement
Non-code tasks (rename repo, prune worktrees, delete merged branches, label cleanup, issue triage) have no pipeline; filed as change requests they stall or yield empty PRs.

## 3. Current behavior
See baseline B-1..B-7: only application, issue and change-request entry points exist.

## 4. Desired behavior
A separate driver plans exact operations, policy-checks them against an allowlist and disallow list, gets approval (attended) or records unattended, executes in order stopping at first failure, verifies by reading state back, and reports.

## 5. Observable behavior table
| ID | Class | Trigger | Current behavior | Expected behavior | Verification |
|---|---|---|---|---|---|
| H-1 | ADD | `uncle --housekeeping` with stdin or argument text | flag unknown (did-you-mean) | plan drafted and shown; attended asks approval; empty/oversized/control-char input refused with reason, nothing runs | AC-1, AC-2 |
| H-2 | ADD | `/housekeeping <task>` in TUI | unknown command | same flow as H-1 | AC-3 |
| H-3 | ADD | allowlisted plan, attended | n/a | runs after approval then verifies; decline: nothing runs, state declined | AC-5 |
| H-4 | ADD | same plan, `--unattended` | n/a | runs without prompt, report says unattended and lists all ops; failure stops run | AC-6 |
| H-5 | ADD | operation matches disallow pattern | n/a | whole plan refused before execution naming rule and command, every mode | AC-7 |
| H-6 | ADD | operation not on allowlist | n/a | refused naming operation | AC-8 |
| H-7 | ADD | unparseable command (pipe to shell, eval, substitution, here-doc) | n/a | refused as unparseable | AC-9 |
| H-8 | ADD | verify finds differing state | n/a | FAIL with observed state; never success | AC-10 |
| H-9 | ADD | edit disallow list in Configure > Miscellaneous (TUI and line menu) | n/a | saved to `.uncle/config`, applies next run; invalid pattern rejected, old list kept | AC-12 |
| H-10 | ADD | housekeeping while another workflow holds checkout | n/a | refused via existing driver lock, no state changed | AC-11 |
| H-11 | MODIFY | `--housekeeping` with --application/--issue/--change-request | n/a | mutually exclusive error | AC-1 |
| H-12 | PRESERVE | existing flags, slash commands, Configure items, lock | B-1..B-7 | unchanged | AC-14 |

## 6. Invariant table
| ID | Status | Invariant | Scope | Enforcement point | Verification |
|---|---|---|---|---|---|
| I-1 | NEW | No command executes unless allowlisted and matching no disallow pattern | driver | single policy function called before execute; static test that execute path only runs commands returned by it | AC-7, AC-13 |
| I-2 | NEW | Policy check identical in attended and unattended | driver | same call site, no mode branch | AC-6, AC-13 |
| I-3 | NEW | Unrun or unreadable verify is never reported passed | verify/report | verify result enum | AC-10 |
| I-4 | NEW | Disallow list read from `.uncle/config` at run time; missing/corrupt falls back to defaults, never empty | policy config | loader | AC-12 |
| I-5 | NEW | Run record lists every executed command in order with exit status | record | execute stage | AC-5, AC-6 |
| I-6 | NEW | Run never modifies tracked project files | driver | records under `.uncle/workflow/`; test compares tracked tree | AC-5 |
| I-7 | NEW | Built-in floor patterns (gh repo delete, rm -rf /, force-push to default branch, plus the issue's default catastrophic set) cannot be removed by editing the list | policy config | loader merges floor | AC-12 |
| I-8 | EXISTING | One driver per checkout | lock | driver.lock | AC-11 |
No RELAXED or REMOVED invariants.

## 7. Compatibility requirements
Additive only: existing flags, usage lines, slash commands, config keys and Configure item order keep behavior. `--housekeeping` composes with `--unattended`.

## 8. Error and failure behavior
Input refusals print `Error: ...` exit 1, nothing runs. Policy refusal fails the run naming rule and command; nothing executes. Mid-run failure stops, later ops not run, reported. Verify mismatch or unreadable state is FAIL.

## 10. Security requirements
Parser is word-based (program, subcommand, flags), not substring; quotes and flag order cannot evade; anything unreadable refused. Verify commands are also policy-checked and must be read-only. Plan-proposed commands are never run through a shell string; executed as argv.

## 12. Rollback expectations
Completed operations are not reverted; report states what changed. Code rollback = revert the added files and small launcher/TUI hunks.

## 14. Explicit non-goals
Arbitrary shell runner; reverting operations; other repositories; code changes after housekeeping.

## 15. Assumptions and resolved questions
- Built-in floor: YES, locked, shown as locked in the TUI.
- First allowlist: all five named operations (rename, worktree prune/removal, merged-branch deletion local+remote, label cleanup, issue triage) per the request's list; each with a verify template.
- Records under `.uncle/workflow/housekeeping/`, not committed.
- Stage models: plan stage uses stage-config key `housekeeping-plan`; verify is deterministic read-back and needs no model.
- UNRESOLVED (non-blocking): exact floor pattern list beyond the three named; chosen in plan.

## Acceptance criteria

| ID | Criterion | Verification |
|---|---|---|
| AC-1 | `uncle --housekeeping` reads stdin (UTF-8, <=1048576 bytes, no NUL/control chars, non-empty) or takes an argument; is mutually exclusive with --application/--issue/--change-request; composes with --unattended; appears in usage and did-you-mean list. | housekeeping-input tests plus launcher test with stubbed TUI: each rejection path, exclusivity, usage text, `--housekeepin` suggestion. |
| AC-2 | Empty, oversized or control-character input is refused with the reason and nothing runs or is written. | Python/shell test on the input validator and launcher exit status. |
| AC-3 | TUI `/housekeeping <task>` and the startup action `housekeeping` start the same flow; slash help and completion list it. | TUI Python test driving command dispatch and startup action with the driver stubbed. |
| AC-4 | A new `scripts/housekeeping-workflow.sh` runs stages plan, policy, approval, execute, verify, report and sources shared `scripts/lib/` state/gate/lock code rather than copying change-workflow stage plumbing. | Driver test with stub agent, gh, git; grep test that the script sources lib files. |
| AC-5 | Attended approve runs ops in order then verifies and reports every command with exit status; decline runs nothing and records declined; tracked project files are unchanged. | Driver test with stub gh/git: approve and decline, command log order, `git status` of tracked files, record contents. |
| AC-6 | With --unattended the plan runs with no prompt, the policy check still runs, and the report states nobody approved and lists every operation; a failing operation stops the run and later ops do not run. | Driver test unattended success and mid-run failure with stub call log. |
| AC-7 | Every default disallow pattern (shell and gh lists in the change request) refuses the whole plan before execution, naming rule and command, in attended and unattended modes, including flag-order and quoting variants; a disallow match beats the allowlist. | Parameterized unit tests per pattern and variant; driver test that stub call log is empty on refusal. |
| AC-8 | An operation not on the allowlist is refused naming the operation; allowlisted operations (repo rename, worktree prune/remove, merged-branch delete local/remote, label cleanup, issue triage) are accepted only in their exact command shapes. | Unit tests for accept and reject shapes per operation, including `git branch -D` and `git push --delete` outside branch cleanup. |
| AC-9 | Commands with pipes into a shell, command substitution, eval, here-docs, redirects, or unbalanced quotes are refused as unparseable. | Unit tests over unreadable constructs. |
| AC-10 | Verify compares read-back state to the expected result; mismatch is reported FAIL with observed state; verify not run or unreadable is reported NOT VERIFIED, never passed. | Driver tests with stub gh returning mismatching, failing and matching output. |
| AC-11 | A housekeeping run while another workflow holds the checkout is refused via driver.lock and changes nothing. | Driver test holding the lock; assert exit status, empty call log. |
| AC-12 | Configure > Miscellaneous (TUI and line menu) offers Housekeeping disallow list: view, add, edit, remove, reset to defaults; stored in `.uncle/config`; invalid pattern rejected keeping old list; missing/corrupt list falls back to defaults; built-in floor shown locked and cannot be removed. | Config module unit tests (add/remove/reset/invalid/corrupt/floor) plus TUI and line-menu persistence tests. |
| AC-13 | Defect injection: removing the policy call from the execute path, or skipping it when unattended, makes tests fail; a static test fails if any code path executes a plan command without calling the policy function. | Mutation-style test that patches a copy of the driver and asserts the suite detects it; recorded in the test report. |
| AC-14 | Existing behavior preserved: existing shell and Python suites pass as at baseline. | `bash scripts/run-shell-tests.sh` and `bash scripts/run-python-tests.sh` compared with baseline. |
| AC-15 | Manual: rename a scratch repository end to end, attended and unattended, and read back the new name. | Manual checklist item on a scratch GitHub repository. |

