# Baseline Report (Issue 188)

Omitted sections: Reproduction result (not a bug); Flaky behavior (none documented)

## 1. Change-request summary
See `.uncle/docs/CHANGE_REQUEST.md`. Warm the home agent (claude session with tools) and preload project context in a background thread when the curses UI runs; never under `--noui`.

## 2. Repository architecture
- `uncle_tui.py`: curses UI class `UncleTUI`; home agent glue (lines 3564-3750), `run()` at 8870.
- `scripts/lib/home_agent_session.py`: `HomeAgentSession(SupervisorSession)`, `build_command`, `persistent_session` (lines 155-179). Read-only base tools plus session grants; deny patterns.
- `scripts/lib/supervisor_runner.py`: `SupervisorSession` (`prime` 420, `turn` ~447 holds `self.lock` for the whole turn, honours a `cancelled` Event and a deadline), `SupervisorRequest` (186; `_run` 224 calls `session.turn`).
- `uncle` (bash launcher): `--noui`/`UNCLE_NOUI=1` runs headless action at lines 420-438 and does not start curses/`UncleTUI`.

## 3. Relevant code paths
- `uncle_tui.py:8879` starts `_warm_supervisor` (4107) thread; warms the old supervisor session only.
- `_home_agent_session` 3604: honours `UNCLE_HOME_AGENT=0` (3607) and non-`claude` runner (3617); closes+restarts on project-root change (3612-3614); bumps `agent_generation`.
- `_close_home_agent` 3634, `_agent_quiesce` 3657 (build/recovery start), `_quit` 8860 and `run()` finally 8885 close the agent.
- `_agent_turn` 3677 creates the `SupervisorRequest` with `session=` so its turn queues on `session.lock`.

## 4. Current observable behavior
| ID | Trigger | Current result | Evidence | Must preserve? |
|---|---|---|---|---|
| B-1 | UI starts | Only supervisor session warmed; no home agent process | uncle_tui.py:8879 | Yes (supervisor warm) |
| B-2 | First homepage message | Home agent spawned lazily; first turn pays start + exploration (~25s in log from issue) | uncle_tui.py:3679 | MODIFY (faster) |
| B-3 | `UNCLE_HOME_AGENT=0` | `_home_agent_session` returns None; supervisor chat used | 3607 | Yes |
| B-4 | runner != claude | Note once, supervisor chat fallback | 3617-3620 | Yes |
| B-5 | Build/recovery start | `_agent_quiesce` kills agent, clears grants/pending | 3657 | Yes |
| B-6 | Project root changes | Next `_home_agent_session` closes with handoff and restarts | 3612 | Yes |
| B-7 | Quit | Agent closed in `_quit` and `run()` finally | 8866, 8885 | Yes |
| B-8 | `--noui` | No curses UI, no `UncleTUI` | uncle:420-438 | Yes |

## 5. Existing invariants
| ID | Invariant | Current enforcement | Existing test | Confidence |
|---|---|---|---|---|
| I-1 | One turn at a time on an agent's stdin | `SupervisorSession.turn` holds `self.lock` | none direct found | Medium |
| I-2 | No home agent process after quiesce/exit | `_close_home_agent` returns `not session.alive()`; quiesce raises otherwise | none direct found | Medium |
| I-3 | Agent uses only read-only base tools + granted rules | `build_command` allow/deny lists | none in scope reviewed | Medium |
| I-4 | Application-sent turns authorize nothing | wording of `prime()` text | none | Low |

## 6. Current API, schema, and interface contracts
No external schema. Env: `UNCLE_HOME_AGENT` (`0` opt-out), `UNCLE_HOME_AGENT_TIMEOUT`, `UNCLE_NOUI`. `SupervisorSession.turn(prompt, log, deadline, cancelled, progress=None)` returns lines or None.

## 7. Existing automated-test coverage
- Python suites `scripts/tests/*-test.py` via `scripts/run-python-tests.sh`; shell suites via `scripts/run-shell-tests.sh`. Both use separate temp dirs and no shared ports, so run in parallel (group `1 2`).
- `home-actions-test.py` and `startup-action-test.py` set `UNCLE_HOME_AGENT=0`. No test calls `UncleTUI.run()` (grep), so wiring in `run()` is not exercised by existing tests.
- No existing test of `_home_agent_session`, `_agent_quiesce` or home-agent preload.

## 9. Baseline test results
Commands from CLAUDE.md/scripts. Not run in this stage by design; the driver's baseline (`.uncle/workflow/green-check.baseline.tsv`) is authoritative. Some Python suites may already fail on a clean checkout (per workflow notes).

## 10. Existing failures, warnings, and flaky behavior
None documented in repo for this area; defer to driver baseline.

## 12. Likely change surface
`uncle_tui.py` (`run`, `_home_agent_session`, `_close_home_agent`, new `_preload_home_agent`); new `scripts/lib/home_preload.py`; new `scripts/tests/home-preload-test.py`.

## 13. Regression-sensitive components
`_home_agent_session` lifecycle/generation counter, `_agent_quiesce`, `_agent_turn` ordering with session lock, thread safety of `self.agent_*` state touched from a new thread.

## 14. Areas explicitly outside the change
`_agent_handoff_text`, `prompts/home-agent.md`, supervisor warm-up, `uncle` launcher.

## 15. Unknowns and assumptions
- Assumed `--noui` never constructs `UncleTUI` (launcher inspected, not run).
- `gh` may be absent/unauthenticated; preload must tolerate it.
- Exact claude stdin behavior on kill mid-turn assumed same as for existing cancel path.

## 16. Initial risk assessment
| Risk | Level |
|---|---|
| Race between preload thread and main-thread close/start of agent state | High |
| Prompt injection from issue titles/branch names in preload text | Medium |
| Startup slowdown if preload work runs on UI thread | Medium |
| Leaked process on quiesce during preload | Medium |

## Exact build and test commands executed

```sh
bash scripts/run-shell-tests.sh
bash scripts/run-python-tests.sh
```

## Parallel verification groups

```text
1 2
```

