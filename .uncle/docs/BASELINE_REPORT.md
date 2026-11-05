# Baseline report - Issue 160 (`--noui`)

Omitted sections: Reproduction result (feature, not a bug); Flaky behavior (none documented)

## 1. Change-request summary
See CHANGE_REQUEST.md (Issue 160). Add `uncle --noui` / `UNCLE_NOUI=1`: run a startup action (`--application|--issue|--change-request|--housekeeping`) with no curses, plain text on stdout/stderr, documented exit codes, same results as the TUI path.

**Tree state (important):** HEAD is a127f35, but the working tree already holds an UNCOMMITTED earlier attempt at this issue: modified `uncle`, `uncle_tui.py`, `README.md`; untracked `scripts/lib/run_duties.py`, `scripts/lib/uncle_headless.py`, `scripts/tests/{run-duties-test.py,headless-run-test.py,headless-equivalence-test.py,launcher-noui-test.sh,pty_helper.py}`. `.uncle/docs/IMPLEMENTATION_NOTES.md` records steps 1-5 of that attempt. It is treated as a starting point to audit and complete, not as passing evidence. The driver baseline measures the tree as it is now.

## 2. Repository architecture
- `uncle` (bash launcher, 1017 lines): parses flags, resolves startup action/text (private 0600 file for stdin text), exports `UNCLE_STARTUP_*`, then runs `uncle_tui.py` (with `--noinput` when no tty) or a line menu.
- `uncle_tui.py` (8164 lines, curses): owns worktree entry, driver command, driver process, dialogs, title, finish summary, desktop preview/launch.
- Drivers: `scripts/stagegate.sh` (app), `from-issue.sh`, `change-workflow.sh`, `housekeeping-workflow.sh`.
- Shared pure libs in `scripts/lib/` (`desktop_launch.py`, `terminal_title.py`, `worktrees.sh`, `worktree_runs.py`, ...).

## 3. Relevant code paths
| Duty | Location |
|---|---|
| Launcher flag parse / startup action / text file | `uncle:140-340` |
| Mode resolution (`UNCLE_STARTUP_ATTENDED/UNATTENDED`) | `uncle:382-391` |
| Prior-attempt `--noui` branch (`exec python3 .../uncle_headless.py` with NO args) | `uncle:394-411` |
| TUI launch (`--noinput` forced for startup action without tty) | `uncle:464-475` |
| Startup-action dispatch | `uncle_tui.py:4197-4246` (`_handle_startup_action`) |
| Change-request O_EXCL write then workflow idx 2 | `uncle_tui.py:4255-4275`; private-file read `:4277-4311` |
| Brief creation (create_app) | `uncle_tui.py:4330-4336`; shared piece `run_duties.startup_brief_document` |
| Driver argv (`cmd_for`, `--attended` only when attended) | `uncle_tui.py:1568-1583`; WORKFLOWS `:143-145` |
| Run entry, `_enter_run_worktree` via `worktrees.sh worktree_auto` (not for issue runs) | `uncle_tui.py:7818-7855`, `:2061-2092` |
| Follow driver-created issue worktree | `uncle_tui.py:2095-2115` |
| Banner/finish parse | `uncle_tui.py:2790+` (`_read_banner`) -> `run_duties.read_banner`/`BannerCollector` (prior attempt) |
| `finish_decision` | moved to `scripts/lib/run_duties.py:65`, re-exported by TUI |
| Terminal title push/pop | `uncle_tui.py:55-80`, `:1988-2008` |
| Desktop preview/launch | `uncle_tui.py:2380-2510`, `scripts/lib/desktop_launch.py` (`run_duties.desktop_decision`) |
| Exit/summary printing | `uncle_tui.py:8118-8164` |
| Prior headless runner (run/stream/signals/escape filter) | `scripts/lib/uncle_headless.py:37-310` |

## 4. Current observable behavior
| ID | Trigger | Current result | Evidence | Must preserve? |
|---|---|---|---|---|
| B-1 | `uncle --application/--issue/--change-request/--housekeeping` on a tty | Curses TUI starts driver, unattended by default, `--attended` passes through | `uncle:382-391`, `uncle_tui.py:1568` | Yes |
| B-2 | Same, no tty | TUI forced with `uncle_tui.py --noinput` | `uncle:471-475` | Yes |
| B-3 | No startup action, no tty | Line-based menu | `uncle:464+` | Yes |
| B-4 | Unattended finish | TUI leaves curses, prints Finished-build line + token summary | `uncle_tui.py:8118-8164` | Yes |
| B-5 | Non-issue run start | TUI creates worktree via `worktree_auto`, sets `UNCLE_PROJECT_ROOT[_LOCKED]` | `uncle_tui.py:2061` | Yes |
| B-6 | `--change-request` with existing CHANGE_REQUEST.md | Refused (`CHANGE_REQUEST_EXISTS`) | `uncle_tui.py:4255` | Yes |
| B-7 | Existing mutual-exclusion/usage errors | exit 1 | `uncle:165-221` | Yes |
| B-8 | `--noui` at HEAD | Unknown flag | `git show HEAD:uncle` | n/a (changing) |

## 5. Existing invariants
| ID | Invariant | Current enforcement | Existing test | Confidence |
|---|---|---|---|---|
| V-1 | Startup text file is trusted only if regular, user-owned, in 0700 dir; deleted after read | `uncle_tui.py:4277` | launcher/TUI startup tests in `scripts/tests` | Medium |
| V-2 | Exactly one startup action | `uncle:165-221` | launcher shell tests | High |
| V-3 | Unattended run exits TUI only when completed and exit 0 | `run_duties.finish_decision` | `finish_decision` tests (Issue 107) | High |
| V-4 | One worktree per run, locked via `UNCLE_PROJECT_ROOT_LOCKED` | `uncle_tui.py:2061`, drivers | worktree shell tests | Medium |
| V-5 | Gates recorded human vs delegated by drivers | drivers/attestation libs | attestation tests | Medium |

## 6. Interface contracts
Launcher CLI and env (`UNCLE_STARTUP_ACTION` in `app|create_app, github_issue, change_request, housekeeping`; `UNCLE_STARTUP_TEXT[_FILE]`; `UNCLE_STARTUP_ATTENDED/UNATTENDED`). Driver env contract (`UNCLE_PROJECT_ROOT`, `UNCLE_STEERING`, `UNCLE_SIGNING_JSON`, `UNCLE_ATTENDED_STDIN`). Driver argv per `cmd_for`. `uncle_tui.py` exports `finish_decision` (monkeypatched by tests).

## 7. Existing automated-test coverage
`scripts/run-shell-tests.sh` (parallel shell suites incl. launcher tests) and `scripts/run-python-tests.sh` (`scripts/tests/*-test.py`). They use separate temp dirs and bind no shared ports, so they form one parallel group. Prior-attempt suites (untracked) are collected by the same runners: `run-duties-test.py`, `headless-run-test.py`, `headless-equivalence-test.py`, `launcher-noui-test.sh`.

## 9. Baseline test results
Commands come from `scripts/run-shell-tests.sh` and `scripts/run-python-tests.sh` (documented runners per stage instructions). Not executed here; the driver baseline (`.uncle/workflow/green-check.baseline.tsv`) is the authority. Some Python suites are documented as failing on a clean checkout; none run by me.

## 10. Existing failures, warnings
None established by me. UNRESOLVED: which prior-attempt suites pass today; the driver baseline will say.

## 12. Likely change surface
`uncle` (headless branch must pass driver selection), `scripts/lib/run_duties.py`, `scripts/lib/uncle_headless.py`, `uncle_tui.py` (delegate duties only), `README.md`, new tests under `scripts/tests/`.

## 13. Regression-sensitive components
TUI startup path and `finish_decision` import (tests patch `uncle_tui.finish_decision`); `_read_banner`; `cmd_for`; launcher argument/mode resolution order; terminal title.

## 14. Outside the change
Drivers and every stage/gate/check; TUI dialogs, config editing; `--noinput` behavior; line menu; JSON event streams.

## 15. Unknowns and assumptions
- Prior-attempt gap found by inspection: `uncle:410` execs `uncle_headless.py` with no `-- DRIVER` argv, and `main()` returns 2 without one; the launcher therefore never reaches a driver. Also no worktree creation (B-5), no CHANGE_REQUEST write (B-6), no brief write, and the desktop decision is only recorded as skipped (`uncle_headless.py:280`). UNRESOLVED: full contents of `_stream` (lines 183-279) not read.
- The CR says the supervisor drafts REQUIREMENTS.md for `--application`; the code actually uses the direct path (`uncle_tui.py:4205-4210`, `_startup_brief_turn` is not called from startup). Assumption: direct path is the parity target.

## 16. Initial risk
Medium-high: duties are inline in a 8k-line TUI; the equivalence claim (N-9) depends on replicating worktree/brief/env setup exactly.

## Exact build and test commands executed

```sh
bash scripts/run-shell-tests.sh
bash scripts/run-python-tests.sh
```

## Parallel verification groups

```text
1 2
```

