# Baseline Report

Omitted sections: Reproduction result (feature/bug is behavioral, not run here); API/schema contracts (no schema; only exit codes and stream contract)

## 1. Change-request summary
Issue 174 (CHANGE_REQUEST.md): every Uncle error goes to stderr, and is also visible in `--noui` and in the TUI build window; callers get stderr text plus non-zero exit.

## 2. Repository architecture
- `uncle` (bash launcher, 1012 lines): parses flags; `--noui`/no-tty with a startup action execs `scripts/lib/uncle_headless.py` (uncle:418-441).
- `scripts/lib/uncle_headless.py` (408 lines): spawns driver (`stagegate.sh`/`change-workflow.sh`), streams output as plain text.
- `uncle_tui.py` (8372 lines): curses UI; spawns driver and feeds the build window.
- Drivers: `scripts/stagegate.sh`, `scripts/change-workflow.sh`, `scripts/workflow.sh`, plus `scripts/lib/*`.

## 3. Relevant code paths
- `uncle_headless.py:167` Popen with `stderr=subprocess.STDOUT` (driver stderr merged into stdout).
- `uncle_headless.py:183-278` `_stream`: select loop on one fd, `handle_line`, `_Writer.emit` to `out` (stdout) with `[+hh:mm:ss]` prefix and `redact`.
- `uncle_headless.py:285-296`: only status-level messages (`driver exited with status N`, gate stop) go to `err`.
- `uncle_headless.py:107-115` `classify_exit`; `uncle:209-213,234` refusals already print to stderr.
- `uncle_tui.py:2213` Popen `stderr=subprocess.STDOUT`; `_reader` 2234; `drain_output` 2249 -> `_absorb_line` (build window); `proc_done` set on EOF.
- Drivers write errors with `>&2` (stagegate.sh 67 sites, change-workflow.sh 47).

## 4. Current observable behavior
| ID | Trigger | Current result | Evidence | Must preserve? |
|---|---|---|---|---|
| B-1 | `--noui` run, driver prints error to its stderr | Appears on stdout (merged), NOT on stderr; `2>file` is empty | uncle_headless.py:167 | No (MODIFY) |
| B-2 | `--noui` driver exits non-zero | stderr gets `driver exited with status N`; exit 1 | uncle_headless.py:288-289; headless-run-test.py:82-91 | Yes |
| B-3 | `--noui` stops at gate | exit 3, stderr names gate | headless-run-test.py:75-87 | Yes |
| B-4 | `--noui` stdout line | `[+hh:mm:ss]` prefix once per line, escapes stripped, secrets redacted | headless-run-test.py:98-137 | Yes |
| B-5 | Launcher refusals | stderr, exit 2 under `--noui` | uncle:209-234 | Yes |
| B-6 | TUI driver stderr | merged into build window via `_absorb_line` | uncle_tui.py:2213,2249 | Yes |
| B-7 | TUI driver exits non-zero | build window shows whatever driver printed; no explicit failure line (to be confirmed in implementation) | uncle_tui.py:2249-2278 | Partly |

## 5. Existing invariants
| ID | Invariant | Current enforcement | Existing test | Confidence |
|---|---|---|---|---|
| I-1 | Exit precedence: signal > nonzero driver > no banner > ok | `classify_exit` | ExitCodes.test_precedence_table | High |
| I-2 | No secret/escape sequence reaches output | `redact`, `EscapeFilter` | Output.test_redaction, Filter tests | High |
| I-3 | No surviving descendants; signals forwarded | `_killpg`, signal handler | Signals tests | High |
| I-4 | `--noui` never imports curses | launcher exec | launcher-noui-test.sh | Medium |

## 7. Existing automated-test coverage
- `scripts/tests/headless-run-test.py` (319 lines) drives `H.run(...)` with fake drivers, capturing `out`/`err` StringIO.
- `scripts/tests/launcher-noui-test.sh` covers launcher.
- Shell suites (run-shell-tests.sh) and Python suites (run-python-tests.sh) use separate temp dirs and no shared ports; they are independent and grouped.

## 9. Baseline test results
Commands from CLAUDE.md/stage instructions: `scripts/run-shell-tests.sh` and `scripts/run-python-tests.sh` both exist. Not executed here; driver baseline (`.uncle/workflow/green-check.baseline.tsv`) is authoritative. Some Python suites may already fail on a clean checkout.

## 10. Existing failures, warnings, flaky behavior
None documented in the files inspected; UNRESOLVED until driver baseline.

## 12. Likely change surface
`scripts/lib/uncle_headless.py`, `uncle_tui.py` (failure line), `scripts/tests/headless-run-test.py`, `scripts/tests/launcher-noui-test.sh` (if needed), `uncle` help text.

## 13. Regression-sensitive components
select loop and EOF handling in `_stream`; output ordering; timestamp prefix; attended prompts (no trailing newline) which must still be shown promptly; redaction of the new stderr stream.

## 14. Outside the change
Driver shell scripts' error wording and `>&2` sites; reviewer scripts; exit-code table.

## 15. Unknowns and assumptions
- Assumption: drivers already write errors to their stderr; the loss happens at the `stderr=STDOUT` merge.
- Unknown: exact TUI behavior on non-zero exit (B-7); resolved by reading `uncle_tui.py` near 2249-2278 and `_absorb_line` during implementation.

## 16. Initial risk assessment
Medium: splitting streams changes interleaving and can deadlock a prompt if a second pipe is mishandled; mitigated by tests.

## Exact build and test commands executed

```sh
bash scripts/run-shell-tests.sh
bash scripts/run-python-tests.sh
```

## Parallel verification groups

```text
1 2
```

