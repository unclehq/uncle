# Change Spec (Issue 188)

Omitted sections: Migration (none); Prototype isolation (not a prototype); Performance numbers beyond criteria (covered by AC)

## 1. Change type
Feature (performance of first homepage message).

## 2. Problem statement
The first homepage message pays home-agent process start, lazy connection and project exploration (~25s vs ~6.6s follow-up).

## 3. Current behavior
Baseline B-1, B-2.

## 4. Desired behavior
When the curses UI runs, a background thread starts the home agent and sends one application-sent preload turn carrying a project snapshot, so it is ready and informed before the operator types. Never under `--noui`; never when `UNCLE_HOME_AGENT=0` or runner is not `claude`.

## 5. Observable behavior table
| ID | Class | Trigger | Current behavior | Expected behavior | Verification |
|---|---|---|---|---|---|
| SB-1 | ADD | UI starts, claude runner, `UNCLE_HOME_AGENT` != 0 | No home agent process | Home agent process alive shortly after start, before any message | unit test with fake session + manual `ps` |
| SB-2 | ADD | Preload runs | None | One application-sent turn with snapshot (branch/status, worktrees, open issues, key-file listing) marked not-from-operator, authorizing nothing, snapshot-time + re-check note | unit test of prompt text |
| SB-3 | MODIFY | First operator message | Lazy start + exploration | Reuses the preloaded session; queues behind an in-flight preload on the session lock | unit test |
| SB-4 | PRESERVE | `--noui`/`UNCLE_NOUI=1` | No UI | No home agent started | unit test (`run` guard) + manual `ps` |
| SB-5 | PRESERVE | `UNCLE_HOME_AGENT=0` or non-claude runner | Nothing / fallback note | Nothing started by preload; no new note from preload | unit test |
| SB-6 | PRESERVE | Build start (`_agent_quiesce`), quit | Agent closed | Preload cancelled and its process dead; no leaked process | unit test |
| SB-7 | PRESERVE | Project root changes | Restart with handoff on next message | Preload session discarded the same way; no preload re-run | unit test |
| SB-8 | PRESERVE | Preload fails (spawn error, gather error, timeout) | n/a | Silent; no history line; lazy start remains | unit test |
| SB-9 | PRESERVE | UI draw/input | Responsive | Preload does no work on the UI thread beyond starting a thread | code review + manual |

## 6. Invariant table
| ID | Status | Invariant | Scope | Enforcement point | Verification |
|---|---|---|---|---|---|
| SI-1 | EXISTING | One turn at a time on agent stdin | HomeAgentSession | `SupervisorSession.turn` lock | unit test: operator request waits for preload |
| SI-2 | EXISTING | No home agent process survives quiesce/exit | TUI | `_close_home_agent` | unit test |
| SI-3 | EXISTING | Only read-only base tools plus granted rules | agent command | `build_command` unchanged | existing; preload gathers data in-app so needs no tools |
| SI-4 | NEW | Preload turn is application-sent, authorizes nothing, and treats repo/issue text as data | preload prompt | `home_preload.preload_prompt` | unit test on prompt text and delimiters |
| SI-5 | NEW | Preload never runs under `--noui`, `UNCLE_HOME_AGENT=0`, non-claude runner | `run()` | guard in `_preload_home_agent` | unit test |
| SI-6 | NEW | A superseded preload (closed/generation changed) leaves no process | TUI thread | lock + cancel event + post-create check | unit test |
| SI-7 | NEW | Preload failure is silent | TUI | try/except in thread | unit test |

No RELAXED or REMOVED invariants.

## 7. Compatibility requirements
No change to `_agent_handoff_text`, system prompt, env var names, or log filenames.

## 8. Error and failure behavior
Any failure in gather/spawn/turn is swallowed; the next `_agent_turn` starts lazily as today.

## 9. Performance requirements
No UI-thread blocking beyond a short lock held for process spawn; snapshot gather subprocesses each time-limited (<=5s) and capped in size.

## 10. Security requirements
Preload text is bounded, sanitized, delimited as untrusted data; no new tool grants; no secrets sent beyond repo state the agent could read anyway.

## 12. Rollback expectations
Setting `UNCLE_HOME_AGENT=0` disables; reverting the `run()` call removes the feature.

## 14. Explicit non-goals
Handoff text, system prompt, re-preloading after root change/build, preload under `--noui`.

## 15. Assumptions
Preload content is chosen by the plan (in scope per request). Stale-state note is embedded in the preload turn.

## Acceptance criteria

| ID | Criterion | Verification |
|---|---|---|
| AC-1 | With the UI running, claude runner and UNCLE_HOME_AGENT unset, a home agent session is created and primed in a background thread before any operator message. | Unit test with patched persistent_session; manual ps check. |
| AC-2 | The preload turn is application-sent, states it is not from the operator and authorizes nothing, wraps repo/issue text as untrusted data, and notes the snapshot time and that state must be re-checked before acting. | Unit test on home_preload.preload_prompt output. |
| AC-3 | The snapshot contains git branch/status, worktrees, open issues (when gh works) and a key-file listing, each source time-limited and failures skipped; total size is capped. | Unit test with fake runner including timeout/failure cases. |
| AC-4 | No home agent is started or preloaded under UNCLE_NOUI=1, UNCLE_HOME_AGENT=0, or a non-claude runner, and preload adds no home-history note. | Unit tests of the guard. |
| AC-5 | An operator message sent while preload is running queues behind it on the session lock; turns never interleave. | Unit test with a blocking fake session turn. |
| AC-6 | _agent_quiesce, root change, and quit cancel an in-flight preload and leave no live process, including when the session is created after the close. | Unit tests for each path. |
| AC-7 | Any preload failure is silent and the lazy start path still works. | Unit test raising from gather and from session creation. |
| AC-8 | Startup does no preload work on the UI thread; existing shell and Python suites do not regress. | bash scripts/run-shell-tests.sh and bash scripts/run-python-tests.sh versus baseline; code inspection. |
| AC-9 | Time to first text for the first homepage message is no worse than for later ones and a question about branches/issues is answered without repeating the preloaded inspection. | Manual: launch uncle in a repo, wait, ask about branches, inspect home-agent-chat-1.jsonl for tool calls and timing. |

