# Baseline report: issue 165 (bare `uncle --noui` REPL)

Omitted sections: Reproduction (feature, not a bug); Baseline test results as run output (the driver supplies them)

## 1. Change-request summary
See .uncle/docs/CHANGE_REQUEST.md. Bare `--noui` (no startup action) currently refused with exit 2; it must start a plain-text interactive chat that can start builds via the validated home actions. One-shot forms unchanged.

## 2. Repository architecture
- `uncle` (bash launcher, 1001 lines): parses flags, resolves attended/unattended, execs TUI (`uncle_tui.py`, 8367 lines, curses) or headless runner.
- `scripts/lib/uncle_headless.py` (378 lines): `run()` streams a driver with an escape filter, signal forwarding, attended gate pass-through on stdin; `main()`/`_driver_from_env()` build driver argv from `UNCLE_STARTUP_*`.
- `scripts/lib/run_duties.py`: shared TUI/headless duties (`build_driver_command`, banners, `startup_brief_document`, `write_change_request`).
- `scripts/lib/home_actions.py` (`prompt`, `parse_reply`, action schema), `home_chat.py`, `home_agent_session.py` (persistent home agent), `supervisor_chat.py`, `supervisor_runner.py`.
- Home-action *execution* (`_home_action`, `_stop_build`, `_resume_build`, `_clear_build`, `run_named_stage`) lives inside `uncle_tui.py` class methods, not in a shared module.

## 3. Relevant code paths
- `uncle:232-233` --noui + --noinput refusal; `uncle:208-212` refusal exit code 2 under --noui; `uncle:385-413` mode resolution; `uncle:415-425` bare-noui refusal (`exit 2`) and exec of headless.
- `uncle_headless.py:137-175` `run()` (refuses attended without tty; SIGINT/SIGTERM -> 128+n); `:293-316` `main`; `:319-367` `_driver_from_env`.
- `uncle_tui.py:153` `ISSUE_REQUEST_RE`; `:3603` `send_home_chat`; `:3412` `_agent_turn`; `:4304` `_apply_home_action`; `:4360` `_home_action`; `:5148` `run_named_stage`; `:5201/5220/5352` stop/resume/clear; `:6377-6521` slash command handling.
- `home_actions.py:73` `parse_reply` (ACTIONS allowlist, strict schema).

## 4. Current observable behavior
| ID | Trigger | Current result | Evidence | Must preserve? |
|---|---|---|---|---|
| B-1 | `uncle --noui --application T` / `--issue` / `--change-request` | One headless run, plain output, exit 0/1/2/3/128+n | uncle_headless.py:1-8; headless-run-test.py | Yes |
| B-2 | `uncle --noui` bare, or `UNCLE_NOUI=1 uncle` | stderr error + usage, exit 2 | uncle:419-424; launcher-noui-test.sh:13-14 | No (MODIFY) |
| B-3 | `--noui --noinput` | Error, exit 2 | uncle:232; launcher-noui-test.sh:15 | Yes |
| B-4 | `--noui --attended` with non-tty stdin | exit 2 | uncle_headless.py:142; launcher-noui-test.sh | Yes |
| B-5 | TUI home chat | Curses chat; NL requests -> validated actions; slash commands | uncle_tui.py:3603-4360, 6377+ | Yes |
| B-6 | Multiple startup actions | exit 1 | launcher-noui-test.sh:19 | Yes |
| B-7 | Headless vs TUI equivalence | Same artifacts/attestation fields | headless-equivalence-test.py | Yes |

## 5. Existing invariants
| ID | Invariant | Current enforcement | Existing test | Confidence |
|---|---|---|---|---|
| EI-1 | --noui never imports curses | headless module imports no curses | headless-run-test.py | Medium |
| EI-2 | Model cannot start a driver; only validated actions | `parse_reply` allowlist; TUI `_apply_home_action` requires home intent | home-actions-test.py, tui-home-agent-test.py | High |
| EI-3 | Child driver not left behind on exit/signal | `run()` killpg with grace | headless-run-test.py | Medium |
| EI-4 | Output has only printable text, TAB, LF | `EscapeFilter` | headless-run-test.py | High |
| EI-5 | Gate answers via stdin recorded as human | UNCLE_ATTENDED_STDIN path in `_stream` | headless-run-test.py | Medium |

## 6. Interface contracts
Launcher env: `UNCLE_NOUI`, `UNCLE_STARTUP_ACTION/TEXT/TEXT_FILE`, `UNCLE_STARTUP_ATTENDED/UNATTENDED`, `UNCLE_PROJECT_ROOT`, `UNCLE_RUNTIME_ROOT`. Headless exit codes: 0 completed, 1 failure, 2 refusal, 3 stopped at gate, 128+n signal. Action schema: `home_actions.ACTIONS` with `uncle_action`, `message`, `document`, `start`, `issue`.

## 7. Existing automated-test coverage
`scripts/tests/`: `launcher-noui-test.sh`, `headless-run-test.py`, `headless-equivalence-test.py`, `home-actions-test.py`, `home-chat-test.py`, `home-agent-session-test.py`, `tui-home-agent-test.py`. The shell and Python runners use separate temp dirs and bind no shared ports, so they form one parallel group (per runner docs: run-python-tests.sh does not overlap run-shell-tests.sh).

## 9. Baseline test results
Commands come from `scripts/run-shell-tests.sh` and `scripts/run-python-tests.sh` (repository runners, CLAUDE.md-mandated). Not run here; the driver baseline (`.uncle/workflow/green-check.baseline.tsv`) is authoritative. Known: some Python suites already fail on a clean checkout (per runner guidance).

## 10. Existing failures/flakiness
None documented in-repo beyond the note above. UNRESOLVED until driver baseline lands.

## 12. Likely change surface
`uncle` (bare-noui branch, usage text); new `scripts/lib/uncle_repl.py` (loop + I/O), new REPL action/chat modules; `uncle_headless.py` (extract `prepare_driver`); `home_actions.py` + one import line in `uncle_tui.py` (shared `ISSUE_REQUEST_RE`); `launcher-noui-test.sh` rows B-2 (request explicitly changes #160 N-6); new tests.

## 13. Regression-sensitive components
`uncle` launcher arg parsing and mode resolution; `uncle_headless.run` signal handling; TUI home chat issue-regex handling.

## 14. Outside the change
Curses TUI behavior, driver scripts, gates, verification, PRs, supervisor tool capabilities (#164), machine protocol, `/set` editing.

## 15. Unknowns and assumptions
- A1: `/date` and `/mode` do not exist in the TUI (grep: no `/mode` handler); REPL defines `/mode`; `/date` is omitted.
- A2: HomeAgentSession/SupervisorRequest threading APIs are driven synchronously by the REPL; exact binding confirmed at implementation.
- A3: TUI-only `/triage` and `/do` depend on TUI triage state; REPL maps them to the same stage rerun/resume driver paths or prints that they need the TUI.

## 16. Initial risk
Medium-high: action execution is TUI-embedded, so extraction must not alter TUI behavior; stdin sharing between REPL and attended gates; Ctrl-C semantics across child process groups.

## Exact build and test commands executed

```sh
bash scripts/run-shell-tests.sh
bash scripts/run-python-tests.sh
```

## Parallel verification groups

```text
1 2
```

