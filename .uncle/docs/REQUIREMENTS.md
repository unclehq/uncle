# Project brief

Issue 111

> Seeded from [unclehq/uncle#111](https://github.com/unclehq/uncle/issues/111).
> Replace the placeholder guidance below with specifics before running the driver.

## Summary

Print total time and the PR it made in Uncle's final results

## Problem

## Summary

When Uncle finishes and prints its final results to stdout, add two things to that output:

1. **Total time** for the build.
2. **The PR it made**, if it made one (URL and number).

This applies to both drivers (new-application builds via `stagegate.sh`, change builds via `change-workflow.sh`), to attended and unattended runs, and to the line the TUI prints after an unattended finish.

## Why

At the end of a build you currently get `Finished build: verdict=… skipped=… path=…`, the "Workflow complete." banner and the artifact list. To learn how long it took you have to add up the cost ledger or the performance records, and to find the PR you have to open `.uncle/workflow/pr/journal.json` or search GitHub. Both are the first things you want after an unattended run, where nobody watched it happen. Issue #107 and the auto-publish path produce PRs with no dialog, so the URL needs to be in the output.

## Requested behavior

**Final output, for a completed build**

```
Finished build: verdict=READY skipped=0 path=/home/me/project
Total time: 47m 12s (stages 41m 03s, waiting at gates 6m 09s)
PR: https://github.com/unclehq/uncle/pull/110 (#110, draft)
```

- **Total time.** Wall-clock from when the run began to when it finished, as `Nh Nm Ns` (drop leading zero units). Include a resumed run's earlier time, so a build that was stopped and resumed reports the whole thing, not just the last session. Where it can be known, also show how much of it was waiting at human gates, since attended and unattended totals are otherwise not comparable.
- **PR.** Print the URL, number and whether it is a draft when the run created one. If the run published nothing, say why in one short line instead of omitting it silently (for example `PR: none (handoff disabled)`, `PR: none (no base commit)`, `PR: not created (publication pending)`). A run that finds an existing PR for the branch should print that PR too.
- **Failures and stops.** A run that stops before completing should still print total time so far, and no PR line unless one already exists.
- **Unattended runs.** The same lines print to stdout, with nothing waiting on input, and after the `Finished build:` line so wrappers that read that first line are unaffected. The new lines come after it, not inside it, so its existing format (`verdict=… skipped=… path=…`) stays stable.

## Where the data already is

- **Time.** `.uncle/workflow/session-totals.json` has per-stage `started_at`, `ended_at` and `elapsed_seconds`. `.uncle/workflow/performance/<run>/run.json` has `started_at`, `ended_at` and `elapsed_seconds` per recorded run. The driver also knows when the run started (the `unattended-enabled` ledger line is stamped at start). A resumed run needs a persisted start time under `.uncle/workflow/` so the clock survives a restart.
- **Gate waiting.** The approval records under `.uncle/workflow/approvals/` and the gate prompts give when each gate opened and was answered. Unattended runs have none.
- **PR.** `.uncle/workflow/pr/journal.json` holds `phase`, `url` and `number` once `change_pr_complete` has run. `phase: created` means the PR exists. It is written after the driver's COMPLETE block, so the print has to come after `change_pr_complete` returns, or re-read the journal at that point.

## Implementation notes

- `scripts/stagegate.sh` and `scripts/change-workflow.sh`: add the lines where `finished_build_line` is called and in the COMPLETE block for attended runs. In the change driver, the PR is published after the summary, so move the final lines after `change_pr_complete`.
- Keep `finished_build_line` itself unchanged. It is asserted by tests and read by the TUI; add a separate `finished_extras` function that prints the time and PR lines.
- `uncle_tui.py`: `finished_build_lines()` collects lines starting with `Finished build:` or `READY - `. Extend it to include `Total time:` and `PR:` so the post-TUI terminal output has them.
- A small helper (a function in `scripts/lib/` or a Python script) to format the duration and read `pr/journal.json` once, shared by both drivers.
- Persist the run's start timestamp in `.uncle/workflow/` on the first run and never overwrite it on resume.

## Acceptance criteria

- A completed unattended build prints `Total time:` with the whole run's duration and a `PR:` line, after the `Finished build:` line, and exits without waiting for input.
- A resumed build reports the total across sessions.
- A change build that created a PR prints its URL and number, and marks a draft PR as a draft. One that created none prints a one-line reason.
- A new-application build prints `PR: none (…)` with a reason where there is no PR concept, or omits the line; whichever is chosen is the same in both drivers and documented.
- The format of `Finished build:` and of the `READY - … WAIVED WITHOUT HUMAN REVIEW` line is unchanged, and existing tests pass.
- Tests cover the duration formatter (including zero units and over an hour), a resumed run, a created PR, a draft PR, and each no-PR reason.

## Scope

What this project covers. Keep it to what must ship.

## Non-goals

What this project explicitly does not do.

## Functional requirements

| ID | Requirement | Priority |
|---|---|---|
| R-001 | | Must |
| R-002 | | Should |
| R-003 | | Could |

## User-visible behavior

| ID | Trigger | Expected result | On failure |
|---|---|---|---|
| B-001 | | | |

## Domain rules and invariants

| ID | Invariant | Consequence if violated |
|---|---|---|
| I-001 | | |

## Data and state

What the authoritative state is, where it lives, what may hold a cached copy,
and what survives a restart.

## Interfaces

APIs, CLI surface, UI entry points, message formats, external services.

## Constraints

Language, runtime, frameworks, libraries, deployment target, budgets,
compatibility that must not break.

## Failure behavior

What must happen on invalid input, unavailable dependencies, partial writes,
concurrent access, and restart mid-operation.

## Verification

How correctness will be demonstrated: test frameworks, commands, and anything
only checkable by hand.

## Definition of done

The concrete conditions under which this is finished.

## Open questions

Anything genuinely undecided.
