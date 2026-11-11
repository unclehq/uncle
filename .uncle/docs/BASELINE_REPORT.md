# Baseline: Issue 246 (--noui shows preview and app)

Omitted sections: Reproduction (feature, not a bug); Areas outside change folded into 12

## 1. Change-request summary
See `.uncle/docs/CHANGE_REQUEST.md` (Issue 246): `--noui` builds must print the preview and app locations/status while building, as the TUI shows them, without curses and without changing exit codes.

## 2. Repository architecture
- `uncle` launcher dispatches `--noui` / `UNCLE_NOUI=1` to `scripts/lib/uncle_headless.py` (493 lines), which spawns the driver (`stagegate.sh`, `change-workflow.sh`) with piped stdout/stderr and streams filtered, redacted, `[+HH:MM:SS]`-prefixed text.
- The TUI (`uncle_tui.py`, 9659 lines) polls for a previewable page and opens it itself; the driver also owns a preview server.
- Driver-side preview: `scripts/lib/preview-build.sh:48-57` starts `preview_server.py start` which writes `.uncle/workflow/preview-server.pid` and `.url` (`preview_server.py:209-271`), updating the URL on static-to-Vite handoff, and removing both at shutdown. `existing_development_url` (`preview_server.py:405`) reads `app-server.{pid,url}` / `preview-vite.{pid,url}`.
- App launch metadata: `.uncle/launch.json` read by `completion_preview.launch_spec` (`completion_preview.py:232`).

## 3. Relevant code paths
- `uncle_headless.py:139-176` `run`; `:185-377` `_stream` select loop (stdout/stderr/stdin), `_Writer.emit` (`:125-136`), `redact` (`:100`), post-reap tail (`:344-377`), `_record_skipped` (`:380`).
- `uncle_tui.py:2908-3095` early-preview polling (`_poll_early_preview`, `_previewable_page`, `_show_early_preview`); `:2740` completion preview; `:197` `_workflow_family`.
- `docs/noui.md` documents `--noui`.

## 4. Current observable behavior
| ID | Trigger | Current result | Evidence | Must preserve? |
|---|---|---|---|---|
| B-1 | `--noui` build runs | Only driver stdout/stderr lines are streamed; no preview URL or app status line is added by the headless runner | `uncle_headless.py:185-377` has no preview/launch handling | Modify (add lines) |
| B-2 | Driver exit/signal/gate | Exit 0/1/2/3/128+n per `docs/noui.md`; precedence signal>gate>driver>0 | `classify_exit` `:109`, docs table | Yes |
| B-3 | Output redaction and escape filtering | KEY/TOKEN/SECRET/PASSWORD env values masked; no escape sequences | `redact` `:100`, `EscapeFilter` `:39` | Yes |
| B-4 | `--noui` never reads stdin unless `--attended` | stdin DEVNULL | `run` `:166` | Yes |
| B-5 | Under `--noui` desktop launch | Skipped, `desktop-launch.json` decision=skipped reason=noui | `_record_skipped` | Yes |
| B-6 | UI (TUI) build | Opens browser tab on preview; driver preview server writes `preview-server.url` | `uncle_tui.py:2952`, `preview_server.py:216-219` | Yes (unchanged) |

## 5. Existing invariants
| ID | Invariant | Current enforcement | Existing test | Confidence |
|---|---|---|---|---|
| I-1 | Headless never imports/starts curses | module imports only stdlib | `headless-run-test.py` | Medium |
| I-2 | Exit-code mapping/precedence unchanged | `classify_exit` | `headless-run-test.py`, `launcher-noui-test.sh` | High |
| I-3 | No escape sequences or unmasked secrets in output | `EscapeFilter`, `redact` | `headless-run-test.py` | High |
| I-4 | Output line framing: elapsed prefix at line start only | `_Writer` | `headless-run-test.py` | Medium |
| I-5 | Process group fully reaped on exit/signal | `_killpg` | `headless-run-test.py` | High |

## 6. Interface contracts
`uncle_headless.run(cmd, root, attended, env, out, err, stdin_fd, grace, idle, install_signals, desktop_decision)` returns int exit code. State files under `<root>/.uncle/workflow/` and `.uncle/launch.json` are driver-owned and read-only here.

## 7. Existing automated-test coverage
`scripts/tests/headless-run-test.py` (fake drivers via `run()`), `launcher-noui-test.sh`, `repl-session-test.py`, `home-preload-test.py`. Both are in `critical-suites.txt` (headless-run line 95, launcher-noui line 86). Shell and Python runners use separate temp dirs and share no ports, so they run as one parallel group.

## 9. Baseline test results
Commands come from `scripts/run-shell-tests.sh` and `scripts/run-python-tests.sh` (CLAUDE.md/stage rules). Not run here; the driver baseline in `.uncle/workflow/green-check.baseline.tsv` is authoritative. No repository-documented failures were found by inspection; some Python suites may already fail on a clean tree.

## 10. Existing failures, warnings, flaky behavior
None recorded beyond the possible pre-existing Python failures noted above.

## 12. Likely change surface
`scripts/lib/uncle_headless.py` (new watcher inside `_stream`), `docs/noui.md`, one new test suite `scripts/tests/headless-preview-test.py`.

## 13. Regression-sensitive components
`_stream` select loop and `_Writer` line framing; end-of-run output ordering (finished-build block printed after reap); exit classification.

## 14. Outside the change
TUI code (`uncle_tui.py`), driver shell scripts, `preview_server.py`, `completion_preview.py`, launcher, exit codes, `--attended`, `--noinput`.

## 15. Unknowns and assumptions
- A1: Reading driver state files is sufficient; the headless runner will not start its own servers.
- A2: "App" status = the driver's app/dev server URL while building and the `.uncle/launch.json` spec at the end.
- A3: Change-request runs do not run preview-build, so they typically show nothing unless state files exist; acceptable.

## 16. Initial risk assessment
Low-medium: interleaving extra lines mid-partial-line; stale state files from earlier runs being announced.

## Exact build and test commands executed

```sh
bash scripts/run-shell-tests.sh
bash scripts/run-python-tests.sh
bash scripts/run-python-tests.sh -- headless-preview
```

