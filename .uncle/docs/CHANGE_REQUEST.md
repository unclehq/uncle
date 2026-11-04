# Change Request

Issue 152

Seeded from [unclehq/uncle#152](https://github.com/unclehq/uncle/issues/152).

## Change Type

Feature | Bug Fix | Prototype | Refactor | Performance | Security | Upgrade

## Summary

Show the project name in the terminal tab title instead of always "uncle"

## Motivation

## Problem

The terminal tab title never says which project Uncle is working on. With several runs open (for example `grove-issue-33` and `grove-issue-34`, or Grove next to Uncle itself), every tab reads `uncle` or `uncle issue #N`, so the tabs cannot be told apart. The status bar already shows the right name (`grove-issue-33`), but the tab title does not.

## Current behavior (from the code)

- `uncle_tui.py` `_write_title` and `scripts/lib/terminal-title.sh` write the title with OSC 2 (`ESC ] 2 ; … BEL`).
- During a run the title is `uncle issue #<N>` (`uncle_tui.py` `_begin_title`; `uncle_title_begin` in `terminal-title.sh`). It is set only when the issue number is known and the run came from `from-issue.sh` or an issue-backed change workflow.
- When the run ends, or on exit, the title is set to the literal string `uncle` (`_end_title`, `uncle_title_end`).
- A run with no issue number (new application, change request, chat session) gets no title at all, so it keeps whatever the shell last set.
- The issue number alone is ambiguous: `#33` in Grove and `#33` in Uncle read the same.

## Requested behavior

The tab title includes the project name, taken from the same source as the status bar so the two always agree.

- **Format:** `<project>` plus the run context, for example `grove-issue-33 · uncle`, or `grove · uncle` for a plain session. Exact format to be settled in the plan; the project name comes first so it survives tab truncation.
- **Project name:** the name of the directory Uncle is running in (the worktree directory for a worktree run, such as `grove-issue-33`), the same value the status bar shows. Consider showing the base project too when running in a worktree.
- **All entry points:** the TUI idle screen, the TUI during a run, the line-based menu, and each driver run directly (`stagegate.sh`, `change-workflow.sh`, `from-issue.sh`), including runs with no issue number.
- **End of run or exit:** restore the previous title instead of writing a bare `uncle`. Where the terminal supports the xterm title stack (`CSI 22;2 t` to save, `CSI 23;2 t` to restore), use it; otherwise fall back to the project-only title.
- **Opt-out:** `UNCLE_TERMINAL_TITLE=0` disables all title writes. The existing guards stay: write only when stdout and stderr are terminals and `TERM` is neither empty nor `dumb`.

## Observable behaviors

| Id | Trigger | Expected result | Failure behavior |
|---|---|---|---|
| T-1 | Start `uncle` in `~/src/grove` | Tab title shows `grove` and Uncle | Not a terminal or `TERM=dumb`: no escape sequence is written |
| T-2 | Start a run in worktree `grove-issue-33` | Title shows `grove-issue-33` and matches the status bar | Name unresolvable: fall back to the directory basename, never to an empty title |
| T-3 | A new-application or change-request run with no issue number | Title still shows the project | No stale title from a previous run |
| T-4 | The run ends or the TUI exits | The previous title is restored, or the project-only title if the terminal cannot restore | Never left on a stale running state |
| T-5 | Two tabs, two projects | The titles differ | n/a |
| T-6 | Project name contains control characters, an escape, or a very long name | The name is sanitized (control characters removed) and truncated to a safe length before it is written | An unsanitized name must never reach the terminal |
| T-7 | `UNCLE_TERMINAL_TITLE=0` | No title is written anywhere | n/a |
| T-8 | Output piped or redirected | Nothing is written | Same as T-1 |

## Invariants

- **I-1:** the title is built from one function shared by the TUI and the shell drivers, so the two cannot drift (today the format lives in two places).
- **I-2:** the project name in the title equals the project name in the status bar.
- **I-3:** no untrusted text (branch names, issue titles, directory names) reaches the terminal unsanitized; the OSC sequence cannot be terminated early or carry escape sequences.
- **I-4:** title writes happen only on an interactive terminal.

## Open questions

- Whether to include the issue number and run state (for example `grove-issue-33 · COMPLETE`) or keep the title to project plus a fixed word.
- Whether to also set the icon name (OSC 1) for terminals that show it.
- How to share the title builder between Python and Bash: a small Python helper called from `terminal-title.sh`, or the reverse.

## Verification

- Unit tests for the title builder: normal names, worktree names, empty and missing names, long names, and names containing control characters or escape sequences.
- A pty test: start the TUI and the drivers under a pseudo-terminal and assert the exact OSC bytes written at start, during a run, at completion, and on exit; and assert nothing is written when output is not a terminal or `UNCLE_TERMINAL_TITLE=0`.
- A consistency test that the title's project name equals the status-bar value for a worktree run.
- Defect injection: reintroduce the literal `uncle` reset and confirm the test fails.
- Manual check: open Uncle in two projects in two tabs and confirm they are distinguishable, then exit and confirm the title is restored.

## Non-goals

- Changing the status bar.
- Window titles for GUI applications Uncle launches.
- Per-stage progress in the title.

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
