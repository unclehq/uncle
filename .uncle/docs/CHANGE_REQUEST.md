# Change Request

Issue 155

Seeded from [unclehq/uncle#155](https://github.com/unclehq/uncle/issues/155).

## Change Type

Feature | Bug Fix | Prototype | Refactor | Performance | Security | Upgrade

## Summary

Make unattended the default and replace --unattended with --attended

## Motivation

## Problem

Every run starts attended: each human gate waits for a person, and you must remember `--unattended` to have a run finish on its own. In practice most runs are meant to finish without a person at the keyboard, so the flag that matters is the one for the exception. The current default makes the common case the one that needs an extra flag, in every command in the README.

## Requested behavior

- **Unattended is the default** for all workflows: new application, issue, change request, and housekeeping.
- **`--attended`** replaces `--unattended`. It forces human interaction at every gate, as the old default did.
- **`--unattended`** is deprecated, not silently removed. See migration below.
- The mode applies uniformly: one flag, parsed once by the launcher, and passed to whichever driver runs.

## Current plumbing (from the code)

- `uncle` parses `--unattended` (sets `UNCLE_UNATTENDED=1` and appends `--unattended` to `UNCLE_ARGS`); the TUI reads `UNCLE_STARTUP_UNATTENDED`, and `from-issue.sh`, `stagegate.sh` and `change-workflow.sh` each parse `--unattended` themselves.
- The drivers use `UNATTENDED=1` to delegate approvals (`approved_by` empty, `delegated_by: unattended`), to waive human-only checks (`waivers.sh`), and to skip or auto-answer dialogs.
- `WORKFLOW_UNATTENDED_HUMAN_WAIVER` and the TUI's auto mode text describe what unattended does and does not do.
- `upgrade-check.sh` skips the interactive upgrade prompt when `--unattended` is present.
- About 44 occurrences of `--unattended` across the launcher, drivers and libs, 22 test files, and the README (`--unattended` appears in every example).

## Observable behaviors

| Id | Trigger | Expected result | Failure behavior |
|---|---|---|---|
| A-1 | `uncle --application TEXT` with no mode flag | Runs unattended end to end | Same failure and stop rules as today's unattended mode; failing tests still stop the run |
| A-2 | `uncle --application TEXT --attended` | Every human gate waits for a person, as the old default | No TTY available: refuse with a message, never hang and never fall back to unattended |
| A-3 | `uncle --unattended ...` | Works as the new default and prints a one-line deprecation notice to stderr | Combined with `--attended`: refuse as contradictory |
| A-4 | `--attended` with `--unattended` | Refused with a message naming both | Nothing starts |
| A-5 | Interactive `uncle` (menu or TUI) with no flag | Auto mode is on by default; a visible toggle switches to attended for the session | The current mode is always shown, so nobody is surprised |
| A-6 | `from-issue.sh`, `stagegate.sh`, `change-workflow.sh` run directly | Same default and same `--attended` flag as the launcher | Drivers never disagree with the launcher about the mode |
| A-7 | Environment variable for the mode (`UNCLE_ATTENDED=1`, replacing `UNCLE_UNATTENDED`) | Equivalent to `--attended`; the old variable is honored with a notice | Both set: `--attended` / `UNCLE_ATTENDED` wins |
| A-8 | Attestation, PR body and final report | Still state plainly that nobody reviewed the run (`APPROVED (unattended)`, delegated gates) | Never shows a delegated approval as human |
| A-9 | Upgrade check at start | Behaves per the decision in open questions | Never blocks an unattended run on a prompt |

## Invariants

- **I-1:** any gate satisfied without a person is recorded as delegated and reported as unreviewed, in the run state, the attestation and the PR body. Flipping the default must not change what is recorded.
- **I-2:** `--attended` never degrades to unattended. If it cannot reach a person, it stops.
- **I-3:** the mode is decided once, at launch, and every stage and subprocess sees the same value.
- **I-4:** the same safety rules apply in the new default as in today's unattended mode (a failing test stops the run; the `Waived by an unattended run; no person assessed this check` wording is unchanged).
- **I-5:** a resumed run keeps the mode it started with unless the operator passes a flag, and the mode in use is printed on resume.

## Risks

This is a significant change in what Uncle does when someone types the shortest command. Previously you had to opt in to a run that approves its own plan; now you must opt out. Specific concerns to decide in the plan:

- **Habit and surprise:** an operator used to being asked at gates will not be asked. Print the mode at startup (for example `Mode: unattended (use --attended to review each gate)`) in every entry point.
- **Housekeeping and other external actions:** where an operation has side effects outside the repository (see the housekeeping issue), unattended-by-default must not weaken that issue's allowlist and disallow-list checks.
- **Shared and CI use:** scripts that relied on the old default to pause for a person (a launcher in a terminal) now run through. Release notes must say so.

## Open questions

- **Deprecation window for `--unattended`:** accept it as a no-op with a notice for one or two releases, then remove it, or keep it permanently as an alias. Suggest a notice for now and a removal date in the release notes.
- **Environment variables:** keep honoring `UNCLE_UNATTENDED` and `WORKFLOW_UNATTENDED` (with a notice) while introducing `UNCLE_ATTENDED`?
- **Upgrade check:** it currently prompts unless `--unattended` is present. With unattended as the default, it would never prompt. Options: skip the prompt but print an available-upgrade notice; or prompt only when attended or when a TTY is present.
- **Interactive TUI:** should the default for a person sitting in the TUI also be unattended, or should the TUI default to attended while the non-interactive entry points (`--application`, `--issue`, `--change-request`, `--housekeeping`) default to unattended? The request says default everywhere; confirm.
- **PR behavior:** the TUI's auto-mode help says nothing is committed, pushed or opened as a PR, whereas issue runs publish a PR from an unattended run. The default flip makes this difference visible to everyone, so it needs a decision.
- **Startup with no TTY:** with piped input and unattended as the default, there is no longer a way to tell \"I forgot the flag\" from intent. Confirm that is acceptable.

## Verification

- Launcher tests with a fake driver for each row A-1 to A-9, across all four entry points and the TUI startup path.
- A test that every driver (`stagegate.sh`, `from-issue.sh`, `change-workflow.sh`, housekeeping) resolves the mode identically from the same flags and environment, including combinations that conflict.
- A pty test for A-2 and I-2: `--attended` without a terminal refuses instead of running.
- A record test for I-1: the attestation and PR body fields are identical to today's unattended output when the default applies.
- Update the 22 existing tests that pass `--unattended`: those that mean \"unattended\" keep passing under the default, and those that meant \"attended\" get `--attended`.
- Defect injection: make a gate skip recording its delegation and confirm the record test fails.
- Manual check: run `uncle --application TEXT` with no flags, then with `--attended`, and confirm the first finishes alone and the second waits at the first gate.

## Non-goals

- Changing what unattended mode does or which checks it waives.
- Removing human gates; `--attended` keeps them.
- Per-gate mode selection.
- Changing how approvals are recorded beyond the flag rename.

## Documentation

Update the README examples (they all pass `--unattended`), QUICK_START, GITHUB_INTEGRATION (which discusses auto/unattended mode), `uncle --help`, the TUI help text, and the release notes with the migration note.

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
