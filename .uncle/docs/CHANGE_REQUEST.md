# Change Request

Issue 148

Seeded from [unclehq/uncle#148](https://github.com/unclehq/uncle/issues/148).

## Change Type

Feature | Bug Fix | Prototype | Refactor | Performance | Security | Upgrade

## Summary

Add a housekeeping capability: --housekeeping and /housekeeping for non-code tasks (e.g. rename a repository)

## Motivation

## Problem

Uncle only runs code-change pipelines (new application, GitHub issue, change request). Tasks that are not code changes, such as renaming a repository, pruning worktrees, deleting merged branches, or cleaning up labels, have no home. Filed as a change request, they get planned and built as code, then stall at checks that need a human (BLOCKED-HUMAN), or produce an empty PR.

## Requested capability

A new entry point and a short, separate driver for housekeeping tasks.

- **CLI:** `uncle --housekeeping` reads the task text from stdin (same limits as `--change-request`: UTF-8, max 1048576 bytes, no NUL or control characters) or from an argument. It composes with `--unattended` and is mutually exclusive with `--application`, `--issue` and `--change-request`. Add it to the usage text and the did-you-mean list.
- **TUI:** a `/housekeeping` slash command, with a startup action so the CLI flag opens the same flow.
- **Driver:** a new `scripts/housekeeping-workflow.sh` that reuses the shared libraries in `scripts/lib/` (state, gates, locking, document layout). It does not copy stage plumbing out of `change-workflow.sh`.

## Stages

1. **Plan:** the model proposes the exact operations (for example `gh repo rename old new`), each with its expected result and how it will be checked.
2. **Policy check:** every proposed operation is matched against the allowlist and the disallow list (see below). A violation stops the run before anything executes.
3. **Approval:** attended, a human approves the exact commands. Unattended, the gate is satisfied automatically and recorded as unattended, as the other drivers do.
4. **Execute:** run the approved operations in order, stopping at the first failure.
5. **Verify:** read the resulting state back (for example `gh repo view`, `git worktree list`) and compare it with the expected result. A check that was not performed is never reported as passed.
6. **Report:** what ran, what changed, evidence, and what was skipped or failed.

Repo-side follow-ups after a rename (README links, package names, CI config) are ordinary code changes and stay in the existing change workflow.

## Allowlist and disallow list

- **Allowlist (first version):** a small set of named operations, each with its own verify step: repository rename, worktree prune and removal of finished worktrees, deletion of merged branches (local and remote), label cleanup, and issue triage (labels, assignees, close with reason).
- **Disallow list:** explicit patterns for destructive shell and `gh` actions, checked against every command the plan proposes. A match refuses the operation, even if it also appears on the allowlist. Defaults cover at least:
  - shell: `rm -rf` (and `rm -r`/`-f` variants), `sudo`, `dd`, `mkfs`, `chmod -R`, `chown -R`, `git push --force`/`-f`, `git push --delete` outside the branch-cleanup operation, `git reset --hard`, `git clean -fd`, `git filter-branch`, `git branch -D` on an unmerged branch, redirects that overwrite files outside the project, `curl|sh`;
  - `gh`: `gh repo delete`, `gh repo archive`, `gh repo edit --visibility`, `gh release delete`, `gh secret`/`gh variable` writes, `gh ssh-key` and `gh auth` changes, `gh api -X DELETE`, and `gh api` with `PATCH`/`PUT`/`POST` against endpoints that change settings, collaborators, or deploy keys.
- **Matching:** commands are parsed into words and matched on the program, subcommand and flags, not on substrings, so quoting and flag order cannot dodge a rule. Anything the parser cannot read (pipes into a shell, command substitution, `eval`, here-docs) is refused. An operation not on the allowlist is refused.
- **Editable in the TUI:** Configure > Miscellaneous gets a new "Housekeeping disallow list" entry to view, add, edit, remove and reset-to-defaults patterns. It is stored in `.uncle/config`. The line-based menu (`uncle` option 3, Miscellaneous) gets the same.

## Unattended mode

`--unattended` performs the allowlisted operations automatically, with no human approval. The disallow list and allowlist are therefore the safety boundary, so:

- the policy check runs before execution in every mode, and is never skipped by `--unattended`;
- a refused operation fails the run with the matching rule named, and nothing after it runs;
- the report states that nobody approved the plan, and lists every operation that ran.

## Observable behaviors

| Id | Trigger | Expected result | Failure behavior |
|---|---|---|---|
| H-1 | `uncle --housekeeping` with task text on stdin | Plan is drafted and shown; attended, the user is asked to approve | Empty, oversized or control-character input is refused with the reason; nothing runs |
| H-2 | `/housekeeping <task>` in the TUI | Same flow as H-1 | Same as H-1 |
| H-3 | Plan contains only allowlisted, non-disallowed operations, attended | Runs after approval, then verifies | Declined approval: nothing runs, state recorded as declined |
| H-4 | Same plan with `--unattended` | Runs with no prompt; the report says it was unattended | A failing operation stops the run and is reported; later operations do not run |
| H-5 | Plan contains an operation matching the disallow list | Whole plan refused before execution, naming the rule and the command | Applies in every mode, unattended included |
| H-6 | Plan contains an operation not on the allowlist | Refused, naming the operation | Same as H-5 |
| H-7 | Command the parser cannot read (pipe to shell, `eval`, substitution) | Refused as unparseable | Same as H-5 |
| H-8 | Verify step finds state different from expected | Reported as FAIL with the observed state | Never reported as success |
| H-9 | User edits the disallow list in Configure > Miscellaneous | Change is saved to `.uncle/config` and applies to the next run | Invalid pattern is rejected with a message; the old list is kept |
| H-10 | Housekeeping run while another workflow holds the checkout | Refused through the existing driver lock | No state is changed |

## Invariants

- **I-1:** no operation executes unless it is on the allowlist and matches no disallow pattern. Enforced in one function called by the driver before the execute stage, with a test that fails if any code path runs a command without calling it.
- **I-2:** the policy check runs in unattended mode exactly as in attended mode.
- **I-3:** a verify step that was not run or could not be read is never reported as passed.
- **I-4:** the disallow list is read from `.uncle/config` at run time; a missing or corrupt list falls back to the defaults, never to an empty list.
- **I-5:** the run record lists every command executed, in order, with exit status.
- **I-6:** a housekeeping run never modifies tracked project files.

## Open questions

- **Built-in floor:** the disallow list is user-editable, and unattended mode acts without review. Should a small built-in floor of catastrophic patterns (`gh repo delete`, `rm -rf /`, force-push to the default branch) stay in force even if a user removes them from the list? Suggest yes, shown in the TUI as locked.
- **Scope of the allowlist:** is the first set above right? Suggest starting with repository rename, worktree pruning and branch cleanup, and adding the rest later.
- **Where records live:** a housekeeping run touches no code, so artifacts go under `.uncle/workflow/` and are not committed. Confirm this is right, or decide whether a record belongs in the repo.
- **Stage models:** should plan and verify be configurable per stage in `.uncle/config` like the other drivers?

## Verification

- Unit tests for the command parser and policy check: each default disallow pattern, flag-order and quoting variants, unreadable constructs, and operations missing from the allowlist.
- Driver tests with stub `gh` and `git`: attended approve and decline, unattended, refusal, mid-run failure, verify mismatch, and lock contention.
- TUI tests for editing the disallow list: add, remove, reset to defaults, invalid pattern, and persistence.
- Defect-injection evidence that I-1 and I-2 reject representative violations.
- Manual check: rename a scratch repository end to end, attended and unattended.

## Non-goals

- Arbitrary shell execution or a general automation runner.
- Reverting a completed operation; the report says what changed instead.
- Housekeeping for repositories outside the one Uncle was started in.
- Code changes that follow a housekeeping task (use the change workflow).

## Observed Current Behavior

Describe what the system currently does.

## Desired Behavior

Describe what the system should do after the change.

## Reproduction

For a bug, provide exact steps to reproduce it.

For other change types, write "Not applicable."

## Constraints

List compatibility, security, performance, timing, or scope constraints.

## Known Relevant Files

List files or components if known.

## Out of Scope

List behavior or components that must not be changed.

## Success Criteria

Describe the observable evidence that proves the change works.
