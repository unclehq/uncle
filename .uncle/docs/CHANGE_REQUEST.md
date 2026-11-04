# Change Request

Issue 151

Seeded from [unclehq/uncle#151](https://github.com/unclehq/uncle/issues/151).

## Change Type

Feature | Bug Fix | Prototype | Refactor | Performance | Security | Upgrade

## Summary

--application and --housekeeping: read the text from standard input when the option has no value

## Motivation

## Problem

The launcher is inconsistent about where a task's text comes from:

- `--change-request` always reads stdin and refuses a terminal.
- `--application TEXT` requires a value. With none, it fails with `--application requires an argument`, so a long brief has to be passed as a quoted shell argument. Long, multi-line or quote-heavy briefs are awkward there, and shell history and process listings (`ps`) expose the text.
- `--housekeeping` in the working tree already takes a value, or falls back to stdin when none follows. That fallback is not written down or tested, and it skips the input checks `--change-request` applies (see below).

A related bug: `uncle --application --unattended` takes `--unattended` as the application text, because `--application` accepts whatever follows it. `--housekeeping` already guards this with `"$1" != --*`.

## Requested behavior

For `--application` and `--housekeeping`: if the option is followed by no value, read the text from standard input.

- **Value given:** `--application "text"` and `--housekeeping "text"` behave as today.
- **No value, stdin piped or redirected:** read stdin as the text. "No value" means the option is the last argument, or the next argument is another option (starts with `--`).
- **No value, stdin is a terminal:** fail with a clear message naming the option and showing both forms. Never block waiting for typing.
- **Empty or whitespace-only text** from either source is refused, as now.
- **Both a value and piped stdin:** the value wins and stdin is left unread. Document this.
- **`--` handling:** a value that begins with `--` can still be passed as text with `--application=--text` or by piping it in; no option name is ever taken as text.

Both options must apply the same input checks as `--change-request` to stdin text: UTF-8 only, at most 1048576 bytes, and no NUL or control characters (tab, newline and carriage return allowed). The text is untrusted input to tool-using agents, so these limits matter most with `--unattended`. Reuse the existing reader (`scripts/lib/change_request_stdin.py` or a shared helper) instead of adding another `cat`.

`--issue` is out of scope: its value is a short reference, not prose.

## Observable behaviors

| Id | Trigger | Expected result | Failure behavior |
|---|---|---|---|
| S-1 | `echo "brief" \| uncle --application` | Starts a new application build with `brief` as the text | Empty input: `--application text cannot be empty`; nothing starts |
| S-2 | `uncle --application < brief.md` | Same as S-1, file contents as the text | Same as S-1 |
| S-3 | `uncle --application "brief"` | Unchanged | Unchanged |
| S-4 | `uncle --application --unattended < brief.md` | Option order does not matter; the text comes from stdin and `--unattended` is an option | `--unattended` is never used as the text |
| S-5 | `uncle --application` with a terminal on stdin | Exits non-zero with a message naming `--application` and both accepted forms; reads nothing | Never hangs |
| S-6 | Same as S-1 through S-5 for `--housekeeping` | Same behavior | Same |
| S-7 | Stdin over 1048576 bytes, containing NUL or control characters, or invalid UTF-8 | Refused with the reason; nothing starts | No partial text is used |
| S-8 | A value and piped stdin together | The value is used; stdin is not read | No warning needed; documented |
| S-9 | `--application` with `--issue`, `--change-request` or `--housekeeping` | Refused as mutually exclusive, as now | Same as now |
| S-10 | `uncle --help`, the README and `--help`'s did-you-mean list | Describe the stdin form for both options | n/a |

## Invariants

- **I-1:** a recognized option name is never consumed as the value of another option.
- **I-2:** the launcher never blocks on stdin when stdin is a terminal.
- **I-3:** text from stdin passes the same validation, whichever of the three text options reads it.
- **I-4:** with a value present, stdin is not read, so an unrelated pipe cannot be consumed.

## Open questions

- **Shell-quirk risk:** when a script runs `uncle --application` inside a pipeline without meaning to pipe anything, stdin may be an inherited non-terminal (such as `/dev/null` from cron or CI) and give "text cannot be empty". That is correct; confirm the message is clear enough.
- **Trailing newline:** strip one trailing newline from piped text, as `$(cat)` does, so a heredoc does not add a blank line to the brief. Suggest yes, with a test.
- **Sharing the reader:** extend `change_request_stdin.py` to take a destination, or extract a common `read_stdin_text` helper used by all three options.

## Verification

- Launcher tests with a fake driver: each row S-1 to S-9, for both options, including option-order variations (`--unattended` before and after).
- A pty test for S-5 and I-2: with a terminal on stdin, the launcher exits promptly with the message.
- Boundary tests for S-7: exactly 1048576 bytes passes, one more fails, NUL fails, control characters fail, tab and newline pass, invalid UTF-8 fails.
- A test for I-4 that the value case leaves piped stdin unread.
- Defect injection: reintroduce a bare `cat` for the stdin read and confirm the limit and control-character tests fail.
- Manual check: pipe a multi-paragraph brief into `uncle --application` and confirm the app starts from it.

## Non-goals

- Interactive prompting for text.
- Reading stdin for `--issue`.
- Changing `--change-request` behavior; it already reads stdin and stays as is.

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
