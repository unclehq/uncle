# Change Specification

Omitted sections: Performance (none), Migration (none), Prototype isolation (n/a)

## 1. Change type
Feature (with a bug fix for option-as-text).

## 2. Problem statement
`--application` cannot read stdin and swallows a following option as its text; `--housekeeping`'s stdin fallback is untested and unchecked.

## 3. Current behavior
See baseline B-1..B-10.

## 4. Desired behavior
For `--application` and `--housekeeping`: with no value (option last, or next argument starts with `--`) read stdin; a value wins and leaves stdin unread; a TTY with no value is refused promptly naming the option and both forms; text from stdin gets the `--change-request` checks (UTF-8, <=1048576 bytes, no NUL/control except tab/LF/CR, non-empty). `--option=VALUE` form passes a value starting with `--`. One trailing newline is stripped from piped text.

## 5. Observable behavior table
| ID | Class | Trigger | Current behavior | Expected behavior | Verification |
|---|---|---|---|---|---|
| S-1 | MODIFY | `echo brief \| uncle --application` | refused: requires an argument | starts build with `brief` | launcher test, fake TUI records text |
| S-2 | MODIFY | `uncle --application < brief.md` | refused | file contents are text | launcher test |
| S-3 | PRESERVE | `uncle --application "brief"` | starts | unchanged | existing launcher-args-test.sh:45 |
| S-4 | MODIFY | `uncle --application --unattended < f` (either order) | `--unattended` becomes text | text from stdin, unattended set | launcher test both orders |
| S-5 | MODIFY | `uncle --application`, TTY stdin | refused, `requires an argument` | exit non-zero, message names option and both forms, no read, no hang | pty test |
| S-6 | MODIFY | S-1..S-5 for `--housekeeping` | stdin path unchecked | same behavior as application | launcher tests |
| S-7 | ADD | stdin >1048576 B, NUL/control, invalid UTF-8 | housekeeping accepts; application n/a | refused with reason, nothing starts, no temp residue | boundary tests |
| S-8 | ADD | value plus piped stdin | n/a | value used, stdin unread | I-4 test |
| S-9 | PRESERVE | `--application` with `--issue`/`--change-request`/`--housekeeping` | mutually exclusive | unchanged | existing tests plus new order cases |
| S-10 | MODIFY | `--help`, README, quickstart, did-you-mean | no stdin form | describe stdin form and `--opt=VALUE`; did-you-mean unchanged | grep tests |
| S-11 | ADD | `--application=--text` | unknown argument | `--text` used as text | launcher test |
| S-12 | MODIFY | piped text ending in one newline | n/a / `$(cat)` strips all | exactly one trailing newline removed | launcher test |
| S-13 | PRESERVE | `--change-request` flows | validated stdin | unchanged | existing launcher-args-test.sh |

## 6. Invariant table
| ID | Status | Invariant | Scope | Enforcement point | Verification |
|---|---|---|---|---|---|
| I-1 | NEW | A recognized option name is never consumed as another option's value | launcher parsing | uncle arg loop (`--*` guard) | `--application --unattended` tests |
| I-2 | STRENGTHENED | Launcher never blocks on stdin when stdin is a TTY | the three stdin options | `-t 0` check before any read | pty test |
| I-3 | STRENGTHENED | Stdin text passes identical validation for all three options | helpers | shared limits across helpers | cross-helper parity boundary tests |
| I-4 | NEW | With a value present stdin is not read | launcher | branch order in arg loop | test with pipe left unread |
| I-5 | EXISTING | Mode flags mutually exclusive | launcher | existing checks | existing tests |

No invariant is RELAXED or REMOVED.

## 7. Compatibility
`--application TEXT`, `--housekeeping TEXT`, `--issue`, `--change-request` and their messages unchanged. The housekeeping TTY message keeps the substring `empty input`. Previously-erroring `--application` with no value now reads stdin.

## 8. Error behavior
Every rejection exits non-zero with `Error: <option> ...` on stderr, starts nothing, and leaves no temp files. Empty/whitespace text: `--application text cannot be empty`. A non-TTY empty stdin (e.g. `/dev/null`) reports the same empty message.

## 10. Security
Text is untrusted input to tool-using agents; limits are mandatory. Stdin text travels via a private 0600 file, not argv/env, so it is absent from `ps`.

## 12. Rollback
Revert the commit; no persistent state or schema.

## 14. Non-goals
Interactive prompting; stdin for `--issue`; changing `--change-request` behavior.

## 15. Assumptions
- Trailing-newline strip applies to stdin text only and to exactly one newline (LF after CRLF normalization).
- `--option=VALUE` is added only for these two options.
- Shared reader: extend `housekeeping_input.py` with a label; `change_request_stdin.py` stays untouched.

## Acceptance criteria

| ID | Criterion | Verification |
|---|---|---|
| AC-1 | `--application` with no value (last arg or next arg starting with `--`) and piped/redirected stdin starts the application build with the stdin text, in either option order relative to `--unattended`; `--unattended` is never used as text. | Launcher test with fake python3 TUI: assert action=create_app, text equals stdin, unattended=1, for `--application --unattended` and `--unattended --application`. |
| AC-2 | `--housekeeping` behaves identically for no-value stdin and option-order cases and applies the same checks. | Same launcher tests parameterized for housekeeping; assert action=housekeeping. |
| AC-3 | With no value and a terminal on stdin, both options exit non-zero promptly with a message naming the option and both forms (and, for housekeeping, still containing `empty input`), reading nothing. | pty test with timeout for both options; existing housekeeping TTY test still passes. |
| AC-4 | Stdin text is refused (nothing starts, no temp residue) when over 1048576 bytes, has NUL/control characters, is invalid UTF-8, or is empty/whitespace; exactly 1048576 bytes passes; tab/newline/CR pass. | Boundary launcher tests for both options plus a parity test comparing housekeeping_input.py and change_request_stdin.py verdicts on the same inputs. |
| AC-5 | When a value is given, behavior is unchanged, empty value is refused, and piped stdin is left unread. | Existing launcher-args-test.sh:45 passes; new test checks a pipe's data remains readable after launcher exit. |
| AC-6 | `--application=VALUE` and `--housekeeping=VALUE` pass VALUE (including one beginning with `--`) as text; empty VALUE is refused. | Launcher tests for `=--text` and `=`. |
| AC-7 | Exactly one trailing newline is removed from piped text; internal blank lines and additional trailing newlines are preserved. | Launcher test with heredoc-style input and double-newline input. |
| AC-8 | Mutual exclusivity with `--issue`, `--change-request` and the other text option still holds in all orders, and `--change-request` behavior is unchanged. | Existing launcher-args and housekeeping launcher tests plus new order cases. |
| AC-9 | `uncle --help`, README.md and docs/quickstart.md document the stdin form, the value-wins rule and `--opt=VALUE`. | Grep assertions in launcher test. |
| AC-10 | A stdin brief reaches the TUI for create_app via the private text file, and the TUI reads it with the existing trusted-file check. | startup-action-test.py new case for create_app with text file; manual pipe of a multi-paragraph brief into `uncle --application`. |
| AC-11 | Defect injection: replacing the validated read with a bare `cat` makes the limit/control-character tests fail. | Temporarily inject the defect locally, run the new launcher test, record failures in the implementation notes, then revert. |

