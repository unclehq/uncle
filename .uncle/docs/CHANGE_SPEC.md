# Change Spec

Omitted sections: Performance, Security (beyond redaction), Migration, Prototype isolation (none apply)

## 1. Change type
Bug Fix / Feature.

## 2. Problem statement
In `--noui`, driver errors are merged into stdout, so a caller capturing stderr never sees why a run failed (baseline B-1).

## 3. Current behavior
See baseline B-1..B-7.

## 4. Desired behavior
Driver stderr output is written to the process's stderr, redacted and escape-filtered. It is also displayed in `--noui` (the terminal shows stderr). On failure the final stderr summary includes the driver's last error lines. The TUI build window shows driver errors and an explicit failure line on non-zero exit. Non-zero exit status is preserved.

## 5. Observable behavior table
| ID | Class | Trigger | Current behavior | Expected behavior | Verification |
|---|---|---|---|---|---|
| S-1 | MODIFY | `--noui`, driver writes error to its stderr | goes to stdout (B-1) | appears on process stderr (redacted, no escapes); `2>file` contains it | headless-run-test fake driver |
| S-2 | MODIFY | `--noui`, driver exits non-zero | status line only (B-2) | stderr has driver error text and the status line; exit 1 | headless-run-test |
| S-3 | ADD | TUI driver exits non-zero | no explicit failure line (B-7) | build window shows a failure line with exit status and last error text | python test on TUI helper |
| S-4 | PRESERVE | driver stdout lines | B-4 | unchanged format on stdout | existing tests |
| S-5 | PRESERVE | gates, exit codes, launcher refusals | B-3, B-5 | unchanged | existing tests |
| S-6 | PRESERVE | TUI shows driver stderr in build window | B-6 | unchanged | existing/inspection |

## 6. Invariant table
| ID | Status | Invariant | Scope | Enforcement point | Verification |
|---|---|---|---|---|---|
| V-1 | EXISTING | I-1 exit precedence | headless | classify_exit | existing test |
| V-2 | STRENGTHENED | I-2: secrets/escapes never reach stdout OR stderr | headless | redact/EscapeFilter applied to stderr stream | new test |
| V-3 | EXISTING | I-3 no surviving descendants | headless | _killpg | existing tests |
| V-4 | NEW | Every driver stderr line reaches process stderr; none is dropped at EOF (incl. partial last line) | headless | _stream | new test |

No RELAXED or REMOVED invariants.

## 7. Compatibility
Stdout format, exit codes (0/1/2/3/130/143) unchanged. Callers that read errors from stdout will now find them on stderr only (intentional).

## 8. Error behavior
Failure to start or refusal stays on stderr. Prompts without trailing newline must still display promptly.

## 12. Rollback
Revert the commit; no state or schema.

## 14. Non-goals
Rewording driver errors; touching driver `>&2` sites; changing exit codes; REPL changes.

## 15. Assumptions
Driver stderr is the error channel. Interleaving order between stdout and stderr is not guaranteed.

## Acceptance criteria

| ID | Criterion | Verification |
|---|---|---|
| AC-1 | With --noui, text a driver writes to its stderr appears on the process's stderr and is retrievable with `2>file`. | headless-run-test.py: fake driver writes to sys.stderr; assert text in captured err. |
| AC-2 | Stderr output from the driver is redacted and free of terminal escape sequences, including a final line without trailing newline. | headless-run-test.py: fake driver emits secret, escape codes and partial last line on stderr; assert err clean and complete. |
| AC-3 | On non-zero driver exit under --noui, exit status is 1 and stderr contains both the driver's error text and the status line. | headless-run-test.py fake driver with exit 1. |
| AC-4 | Driver stdout formatting, gate messages, exit codes and launcher refusals are unchanged. | Existing headless-run-test.py and launcher-noui-test.sh pass unmodified in their existing assertions. |
| AC-5 | In UI mode, when the driver exits non-zero the build window shows a failure line with the exit status and the last error text. | New python test calling the TUI output-handling code with a fake process, plus manual check. |
| AC-6 | A defect-injection check shows the new tests fail when stderr is merged back into stdout. | Run the new tests against a temporarily reverted Popen stderr argument; record the failure. |

