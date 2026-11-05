# Change Request

Issue 160

Seeded from [unclehq/uncle#160](https://github.com/unclehq/uncle/issues/160).

## Change Type

Feature | Bug Fix | Prototype | Refactor | Performance | Security | Upgrade

## Summary

Add --noui: run the whole workflow without the curses UI, doing everything else

## Motivation

## Problem

Today a launcher run with a startup action (`--application`, `--issue`, `--change-request`, `--housekeeping`) always runs inside the full-screen curses TUI. When there is no real terminal, `uncle` still forces the TUI (`uncle_tui.py --noinput`) because the TUI is what starts the driver. That makes Uncle awkward or unusable in places where a curses screen is wrong:

- CI jobs, cron, `ssh` with no pty, `docker run` without `-t`;
- scripts that want to capture plain stdout and an exit code;
- terminals that cannot render curses, or editors and log collectors that mangle escape sequences;
- anyone who wants to see the driver's log directly in scrollback.

The drivers (`stagegate.sh`, `from-issue.sh`, `change-workflow.sh`, `housekeeping-workflow.sh`) can be run directly, but doing so skips everything the launcher and TUI add around them, so \"run the driver by hand\" is not equivalent to \"run Uncle\".

## Requested behavior

`uncle --noui` runs the selected workflow without drawing a curses UI, and does everything else a normal run does. Output is plain text on stdout and stderr, and the exit status says whether the run finished.

\"Everything else\" means the run produces the same results as a TUI run with the same inputs:

- the same workflow selection from `--application`, `--issue`, `--change-request` or `--housekeeping`, with the same text and stdin handling;
- the same worktree creation, locking, state, stage order, gates, verification, checklist, audit, PR publication and worktree removal;
- the same artifacts, envelopes, attestation and PR body;
- the same attended or unattended behavior as the mode flags select (see the default-mode issue); under `--noui` attended gates are answered on stdin, line by line;
- the finished-build summary that the TUI prints on exit after an unattended run;
- the terminal title (when a terminal exists) and the desktop preview and launch decision (when the desktop-launch feature applies), using the same decision functions the TUI uses.

## What the TUI does around a run today (needs inventory)

The plan must list each duty the TUI performs for a run and decide where it lives under `--noui`. From the code:

- starts the driver for the startup action and passes `--unattended` through;
- the homepage supervisor drafts `REQUIREMENTS.md` from `--application` text before the build starts;
- dialogs: completion, support and star offer, signing handoff, desktop launch, recovery, stage prompts, steering channels;
- terminal title begin and end;
- the finished-build line for an unattended finish, and the exit code handling (`workflow_exit_code`);
- the persistent housekeeping and supervisor sessions;
- config editing, which stays TUI-only.

Duties that are really part of the run (drafting `REQUIREMENTS.md`, the finish summary, the desktop decision) should move into shared code that both the TUI and the headless path call, not be reimplemented a second time.

## Observable behaviors

| Id | Trigger | Expected result | Failure behavior |
|---|---|---|---|
| N-1 | `uncle --noui --application TEXT` | The build runs with plain-text progress; no curses screen is drawn, no alternate screen is entered | Exit non-zero when the run does not finish, with the reason printed |
| N-2 | `uncle --noui --issue N` / `--change-request` / `--housekeeping` | Same, for each workflow | Same |
| N-3 | `--noui` with no terminal (CI, cron, pipe) | Works; never requires a tty and never forces the TUI | Never hangs waiting on a terminal |
| N-4 | `--noui` unattended | Runs to completion with no prompt and prints the finished-build summary | A failing check stops the run and returns non-zero, as today |
| N-5 | `--noui --attended` | Gates print their prompt and read the answer from stdin | No stdin available: refuse with a message and exit non-zero; never fall back to unattended |
| N-6 | `--noui` with no startup action (interactive menu would have appeared) | Refuse with usage: the headless mode needs a task | Exit non-zero, nothing started |
| N-7 | Output of a `--noui` run | Plain text with no cursor-control or alternate-screen escape sequences; stable enough to parse | Progress lines carry stage names and a timestamp or elapsed time |
| N-8 | Exit status | 0 only for a finished run; distinct non-zero codes for failed, blocked and refused, documented | Never 0 for a run that stopped at a gate or a failed check |
| N-9 | Run with the TUI versus `--noui`, same inputs | Same artifacts, state, attestation fields and PR content, ignoring timestamps | A difference is a defect |
| N-10 | Ctrl+C or SIGTERM during a `--noui` run | The run stops, the state is left resumable, and the reason is recorded as today | No orphaned child processes |
| N-11 | `--noui` and `UNCLE_*` environment | Behaves identically to the flag; `UNCLE_NOUI=1` is the environment form | Flag wins when both are given |

## Invariants

- **I-1:** `--noui` never changes what is built, checked, approved or published. It changes only how progress is displayed and how prompts are answered.
- **I-2:** every gate is recorded identically in both paths; a person-approved gate in `--noui --attended` is still recorded as human, and a delegated one as delegated.
- **I-3:** the headless path and the TUI path call the same shared functions for the duties listed above; none is duplicated.
- **I-4:** `--noui` never writes escape sequences that move the cursor, clear the screen or switch screens.
- **I-5:** exit status reflects the run result and nothing else.

## Open questions

- **Entry point:** should `--noui` run the driver directly from `uncle` (the launcher already knows which driver each startup action selects), or run a headless mode of `uncle_tui.py`? Running the driver directly avoids loading curses at all, but needs the TUI-owned duties extracted first.
- **Prompts:** how should attended gates, signing handoffs and dialogs be presented as plain text, and with what escape hatch when stdin is a pipe?
- **Output format:** human text only, or also a machine-readable form (for example `--noui --json` events)? Suggest text first and leave JSON as a follow-up.
- **Relationship to `--noinput`:** the existing `uncle_tui.py --noinput` is a different thing (a TUI with no keyboard). Decide whether to keep, rename or document it so the two flags are not confused.
- **Interactive menu:** should the line-based menu remain as the non-TTY fallback, or should it be retired in favor of `--noui` plus a startup action?
- **Progress detail:** what the log shows by default (stage banners only, or driver output as it streams).

## Verification

- Launcher tests with a fake driver and a stubbed TUI: `--noui` never imports or starts curses, for each of the four startup actions.
- A pty-free test run (stdin and stdout piped): exits with the correct status, and the output contains no cursor-control or alternate-screen escapes (assert on the bytes).
- A pty test for `--noui --attended`: a gate prints its prompt, accepts a line, and records a human approval.
- An equivalence test (N-9) that runs a fixture build through the TUI path and the `--noui` path and compares the artifacts, state and attestation fields.
- Exit-code tests for finished, failed check, blocked gate, refused input, signal, and missing stdin.
- Defect injection: have the headless path skip the finished-build summary, or the desktop decision, and confirm a test fails.
- Manual check: run a real small build under `ssh` without a pty, and under `docker run` without `-t`.

## Non-goals

- Replacing the TUI or removing any of its features.
- A web or GUI front end.
- Machine-readable event streams (a follow-up).
- Changing any workflow stage, gate or check.

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
