# Baseline Report

Omitted sections: Reproduction (feature/bug in launcher parsing, no separate repro run); Existing failures (none documented; driver baseline is authority)

## 1. Change-request summary
Issue 151 (.uncle/docs/CHANGE_REQUEST.md): `--application` and `--housekeeping` read text from stdin when no value follows; apply `--change-request` input checks; never block on a TTY; never take an option name as text.

## 2. Repository architecture
Bash launcher `uncle` parses flags, exports `UNCLE_STARTUP_ACTION/TEXT/TEXT_FILE/UNATTENDED`, launches `uncle_tui.py`, which starts the workflow. Stdin validation helpers live in `scripts/lib/*.py`. Launcher tests are shell scripts under `scripts/tests/`.

## 3. Relevant code paths
- `uncle:57-107` usage text; `uncle:120-237` arg loop; `--change-request` 128-146 (TTY refusal, mktemp dir `UNCLE_CR_DIR`, helper call); `--housekeeping` 147-171 (value if next arg not `--*`, TTY refusal, bare `$(cat)` fallback with only whitespace check); `--application` 172-189 (requires any next arg, even `--unattended`); did-you-mean list 228; env export 249.
- `scripts/lib/change_request_stdin.py`: CAP 1048576, UTF-8, CRLF->LF, control-char regex, empty check, CHANGE_REQUEST.md exists check, 0600 temp file; messages say `--change-request`.
- `scripts/lib/housekeeping_input.py`: same limits, `--text` or stdin, messages say `--housekeeping`; currently unused by the launcher.
- `uncle_tui.py:4042-4081` startup dispatch: `create_app` uses `_startup_text` only (4047); `housekeeping` falls back to `_read_startup_text_file` (4066-4069); `_read_startup_text_file` 4105+ validates trusted private file and error text mentions `--change-request`.
- Docs: README.md:61,69,94,456; docs/quickstart.md:10,18,23,42.

## 4. Current observable behavior
| ID | Trigger | Current result | Evidence | Must preserve? |
|---|---|---|---|---|
| B-1 | `uncle --application "text"` | starts app build with text | uncle:172-189; launcher-args-test.sh:45 | Yes |
| B-2 | `uncle --application` (no value) | `--application requires an argument`, exit 1 | uncle:178 | No (becomes stdin read) |
| B-3 | `uncle --application --unattended` | `--unattended` taken as text | uncle:182-187 | No (bug) |
| B-4 | `uncle --housekeeping "text"` | text used | uncle:153-159; housekeeping-launcher-test.sh | Yes |
| B-5 | `--housekeeping` no value, TTY | exit 1, message contains `empty input` | uncle:160; housekeeping-launcher-test.sh TTY case | Yes (substring) |
| B-6 | `--housekeeping` piped, no value | bare `$(cat)`, whitespace-only refused; no size/UTF-8/control checks | uncle:164-168 | No (gains checks) |
| B-7 | `--change-request` stdin | validated via helper, file handed to TUI | uncle:128-146; launcher-args-test.sh:51-150 | Yes, unchanged |
| B-8 | Two of the four mode flags | `mutually exclusive`, exit 1 | uncle:129,149,174,192 | Yes |
| B-9 | `--issue` | short reference; unchanged | uncle:190-220 | Yes |
| B-10 | `--help`, did-you-mean | list flags | uncle:57,228 | Yes (text updated) |

## 5. Existing invariants
| ID | Invariant | Current enforcement | Existing test | Confidence |
|---|---|---|---|---|
| V-1 | Mode flags mutually exclusive | checks at uncle:129,149,174,192 | launcher-args-test.sh:106-107; housekeeping-launcher-test.sh | High |
| V-2 | `--change-request` never blocks on TTY | `-t 0` refusal uncle:133 | launcher-args-test.sh TTY case | High |
| V-3 | Rejected stdin leaves nothing in TMPDIR/project | helper writes only after validation | cr_clean in launcher-args-test.sh | High |
| V-4 | Startup file trusted only if private regular file | `_read_startup_text_file` | startup-action-test.py (partial) | Medium |

## 6. Interface contracts
CLI flags above; env vars `UNCLE_STARTUP_ACTION`, `UNCLE_STARTUP_TEXT`, `UNCLE_STARTUP_TEXT_FILE`, `UNCLE_STARTUP_UNATTENDED`; helper CLIs `change_request_stdin.py PROJECT_ROOT PRIVATE_DIR` and `housekeeping_input.py PRIVATE_DIR [--text TEXT]` (prints path, errors on stderr exit 1).

## 7. Existing automated-test coverage
Shell: `scripts/tests/launcher-args-test.sh` (fake python3 records TUI env; stdin boundary cases for `--change-request`), `housekeeping-launcher-test.sh` (exclusivity, empty, TTY via pty, did-you-mean), `launcher-tui-lock-test.sh`. Python: `startup-action-test.py`, `preview-placeholder-test.py`. Shell runner and Python runner use separate temp dirs and share no ports, so they run as one parallel group.

## 9. Baseline test results
Commands come from scripts/run-shell-tests.sh and scripts/run-python-tests.sh (CLAUDE.md-mandated runners). Not run here; the driver baseline (`.uncle/workflow/green-check.baseline.tsv`) is authoritative. Some Python suites may already fail on a clean checkout per project guidance.

## 10. Existing failures, warnings, flaky behavior
None recorded in repository docs beyond the note above.

## 12. Likely change surface
`uncle`, `scripts/lib/housekeeping_input.py`, `uncle_tui.py` (create_app file fallback), README.md, docs/quickstart.md, launcher tests.

## 13. Regression-sensitive components
`--change-request` path (must not change); `--housekeeping` TTY message substring `empty input`; `--application TEXT` env contract used by launcher-tui-lock-test.sh and startup-action-test.py.

## 14. Outside the change
`--issue`, `--change-request` behavior and its helper, interactive prompting, driver scripts.

## 15. Unknowns and assumptions
- Assumption: `startup-action-test.py` does not assert that `create_app` ignores a text file.
- Assumption: housekeeping-launcher-test.sh has no case asserting piped housekeeping text arrives in `UNCLE_STARTUP_TEXT` (inspected lines 1-40 only; stdin cases there only check refusal).

## 16. Initial risk assessment
Medium-low: small bash parsing change; risk is option-order edge cases and a TUI path for file text on create_app.

## Exact build and test commands executed

```sh
bash scripts/run-shell-tests.sh
bash scripts/run-python-tests.sh
```

## Parallel verification groups

```text
1 2
```

