# Change Request

Issue 168

Seeded from [unclehq/uncle#168](https://github.com/unclehq/uncle/issues/168).

## Change Type

Feature | Bug Fix | Prototype | Refactor | Performance | Security | Upgrade

## Summary

--noui: expand one-character slash commands when the prefix is unique

## Motivation

## Problem
Under `uncle --noui`, a slash command must be typed in full. `/q` is refused with `unknown command: /q`, although only one command starts with `q`.

## Requested behavior
In the `--noui` REPL (`scripts/lib/uncle_repl.py`, `slash()`), if the user types a slash command that is a single character and exactly one command starts with that character, run that command.

Commands: help, quit, exit, mode, issue, stop, resume, clear, triage, do, settings.

| Input | Result |
|---|---|
| `/q` | runs `/quit` (only `q` match) |
| `/h` | `/help` |
| `/m` | `/mode` |
| `/i` | `/issue` (still needs its `N` argument) |
| `/c` | `/clear` |
| `/t` | `/triage` |
| `/d` | `/do` |
| `/e` | `/exit` |
| `/s` | ambiguous (stop, settings): not run; refuse and list the matches |
| `/r` | `/resume` |

## Details
- Only one-character names expand. `/qu` and other longer abbreviations stay unknown.
- Arguments are kept: `/m unattended` is `/mode unattended`.
- An ambiguous or unmatched character keeps today's refusal (exit code 2), and the ambiguous case names the candidates.
- Update `HELP` if useful, and add tests to `scripts/tests/repl-session-test.py` covering `/q` quitting, an ambiguous `/s`, and `/qu` still being refused.
- Related: the TUI slash handling may deserve the same rule; out of scope here.

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
