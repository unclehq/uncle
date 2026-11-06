# Change Request

Issue 149

Seeded from [unclehq/uncle#149](https://github.com/unclehq/uncle/issues/149).

## Change Type

Feature | Bug Fix | Prototype | Refactor | Performance | Security | Upgrade

## Summary

Uncle must not edit .gitignore at the end of a change request; the repo must be clean when the PR is pushed

## Motivation

## Problem

When Uncle finishes a change request, it edits `.gitignore` one more time. Depending on the run, that last edit is left uncommitted in the checkout, or goes out with the PR. Either way the repository is not in the state the audit approved:

- **Uncommitted:** the checkout reads as modified (` M .gitignore`) after the PR is pushed. The same condition makes `git worktree remove` and Uncle's own post-PR removal guard (`auto_removal_content_refusal`: "uncommitted changes to tracked files") refuse to clean up. It also pollutes the operator's next `git status` and `git diff`.
- **Pushed:** the PR carries a `.gitignore` change nobody reviewed or asked for, so the diff the human approved is not the diff that merges.

I confirmed the symptom (` M .gitignore` in the checkout, in the Uncle repo itself) but have not traced which call makes the last edit. Candidates in the current code:

- `uncle_tui.py` calls `_ensure_uncle_gitignored(...)` at startup (around line 1556), which runs `uncle_gitignore.ensure(project_root)`.
- `scripts/lib/worktrees.sh` runs `uncle_gitignore.py` on every new worktree.
- `change-pr.sh` already special-cases `.gitignore` in its snapshot and strips Uncle's managed lines, which suggests the file keeps changing during a run.

Part of the work is finding the exact trigger for the end-of-run edit.

## Requested behavior

At the end of a change request, and when the PR is pushed:

1. Uncle makes **no further edit** to `.gitignore` (or any tracked file) after the final audit snapshot is taken.
2. The checkout and the worktree are **clean and unmodified**, apart from files the PR commit contains. The commit tree equals the audited tree.
3. If a `.gitignore` update is needed for Uncle to work, it happens **before** the audit snapshot and is part of what the human reviews, or it is made through a mechanism that never touches tracked files (see open questions).

## Observable behaviors

| Id | Trigger | Expected result | Failure behavior |
|---|---|---|---|
| G-1 | A change request finishes and the PR is published | `git status --porcelain` is empty in the worktree apart from the committed files; `.gitignore` is byte-identical to the audited tree | If a tracked file differs after publish, the run reports which file and why instead of ending as COMPLETE |
| G-2 | The PR is created | `.gitignore` in the PR matches the version that was audited, with no line added after the audit | If the PR tree differs from the audited tree, publish stops and says so |
| G-3 | Post-PR worktree removal | Not blocked by a modified `.gitignore` | A different dirty file is still refused, as today |
| G-4 | A project's `.gitignore` lacks Uncle's managed block | The block is added before the audit snapshot, or Uncle uses a non-tracked ignore (`.git/info/exclude`); the audit shows the change | Never added silently at the end |
| G-5 | A run with no PR (COMPLETE, no PR) | The checkout is clean; no `.gitignore` edit is left behind | Same as G-1 |
| G-6 | Starting the TUI or a driver in a clean project | Same rule applies at startup: no tracked file is modified without it appearing in a reviewed diff | Refuse or defer the edit with a message |

## Invariants

- **I-1:** no tracked file is modified after the final audit snapshot until the PR is published. Enforced by comparing the working tree to the audited tree immediately before and after publish.
- **I-2:** the PR commit tree equals the audited tree. (Publish already validates this; the check must also hold for `.gitignore`.)
- **I-3:** Uncle's end-of-run bookkeeping never writes to a tracked file; run state stays under `.uncle/workflow/`, which is ignored.
- **I-4:** a worktree that finished a PR has no tracked-file modifications, so the removal guards pass without any special case.

## Open questions

- **Where should the ignore rules live?** Writing them to `.git/info/exclude` never touches tracked files and would remove this class of problem. The catch is that the `!.uncle/docs/` negation exists specifically so the approved documents stay visible to git and to the removal guard; confirm that `info/exclude` can express this, and that the PR snapshot still sees `.uncle/docs/`.
- **If `.gitignore` must stay the mechanism:** apply the change once, before the first audit snapshot, as its own visible entry in the plan or the diff, so it is reviewed rather than appended at the end.
- **Existing runs:** the snapshot code strips managed lines from `.gitignore` before comparing. Decide whether to keep that tolerance for in-flight runs or remove it once the final edit is gone.

## Verification

- A regression test using a fixture repo: run a change to completion (with and without a PR) and assert that `git status --porcelain` is empty and `.gitignore` is unchanged from the audited tree.
- A test that fails when any code path writes a tracked file between the final audit and publish.
- A driver test where the base `.gitignore` lacks the managed block, and one where it is already canonical.
- Defect injection: reintroduce a final `ensure()` call and confirm the test fails.
- Manual check: complete a real change request and confirm that the worktree is removed automatically after the PR.

## Non-goals

- Changing which paths Uncle ignores (the canonical block stays as is).
- Changing the PR snapshot's treatment of `.uncle/workflow/`.
- Other cleanup of the worktree, such as stale `parallel/step-*` registrations; that is a separate problem.

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
