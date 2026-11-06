# Implementation notes

### Files changed

- `scripts/lib/uncle_headless.py` — Spawn driver with stderr=PIPE; select on both fds; separate EscapeFilter/line buffer for stderr; redact complete lines; 8192 cap; drain both fds before status line; D-1, D-2, D-5; S-1, S-2, V-2, V-4
- `scripts/tests/headless-run-test.py` — Add stderr cases: routing, redaction, partial last line, nonzero exit, split secret, cap; Automated-test strategy; AC-1, AC-2, AC-3
- `uncle_tui.py` — Add pure format_failure_line and emit failure line on non-zero driver exit; D-3; S-3
- `scripts/tests/tui-failure-line-test.py` — New tests for format_failure_line (0, nonzero, no output, 130/143, redaction); D-3 tests; AC-5
- `uncle` — Help text states errors go to stderr; D-4; S-1

### Unresolved concerns

- Live TUI manual check of the failure line was not performed (AC-5 manual part).
- Full regression suite left to the driver.

## Acceptance delivery

| ID | Status | Changed code | Observed targeted verification |
|---|---|---|---|
| AC-1 | IMPLEMENTED | scripts/lib/uncle_headless.py: stderr piped and written to err | python3 scripts/tests/headless-run-test.py: 37 tests OK |
| AC-2 | IMPLEMENTED | scripts/lib/uncle_headless.py: own EscapeFilter, redact on complete lines, partial flush | python3 scripts/tests/headless-run-test.py: 37 tests OK |
| AC-3 | IMPLEMENTED | scripts/lib/uncle_headless.py: drain then status line, exit 1 | python3 scripts/tests/headless-run-test.py: 37 tests OK |
| AC-4 | IMPLEMENTED | No change to stdout/gate/exit paths | existing headless tests pass; bash scripts/tests/launcher-noui-test.sh all ok lines shown in tail |
| AC-5 | IMPLEMENTED | uncle_tui.py: format_failure_line and its use at driver exit | python3 scripts/tests/tui-failure-line-test.py: 6 tests OK |
| AC-6 | IMPLEMENTED | Temporary stderr=subprocess.STDOUT in Popen, restored afterward | headless-run-test.py produced multiple ERRORs under injection; OK after restore |
