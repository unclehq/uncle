# Change Plan (Issue 188)

Seeded from [unclehq/uncle#188](https://github.com/unclehq/uncle/issues/188).

Omitted sections: Schema/persistence (none); Migration (none); Feature flag (existing UNCLE_HOME_AGENT=0 only)

Issue 188

## 1. Selected technical approach

New pure module `scripts/lib/home_preload.py` gathers a bounded snapshot in-app (git, worktrees, `gh issue list`, top-level listing; each subprocess time-limited, failures skipped) and builds the preload prompt. Secret-like names (`.env*`, `*key*`, `*.pem`, `credentials*`, case-insensitive) are filtered out of the top-level listing and the git status output before the prompt is built; the snapshot carries file names only, never file contents. `UncleTUI.run()` starts a daemon thread `_preload_home_agent` beside `_warm_supervisor`. The thread creates the session via `_home_agent_session()` under a new re-entrant `agent_lock`, then sends the prompt through `session.turn()` with a per-preload cancel Event, reply discarded. The deadline is a module constant `PRELOAD_TIMEOUT_S` (default 60, patchable by tests): a timer sets the cancel Event after `PRELOAD_TIMEOUT_S`; on expiry the preload thread closes the session it created and resets `agent_session` to None (only if `agent_session` is still that session), so the next `_agent_turn` lazily starts a fresh session. An operator turn arriving while the preload is in flight does not queue behind it for the full timeout: it sets the preload cancel Event, the preload turn is aborted, and the operator turn proceeds, waiting at most PRELOAD_CANCEL_WAIT_S (module constant, default 3s, patchable by tests) for the session lock to free. If that wait is exceeded, the preload session is closed, `agent_session` is reset to None (only if still that session), and the operator turn starts a fresh session lazily. The wait is therefore bounded by the preload finishing, PRELOAD_TIMEOUT_S, or PRELOAD_CANCEL_WAIT_S after the operator message arrives, whichever is first.

## 2. Alternatives considered
- Let the agent explore with tools during preload: rejected (cost, ungranted-tool denials, slower).
- Only spawn + `prime()`-style hello: rejected, fails requirement 2.
- Run preload on the UI thread: rejected (SB-9).

## 3. Why preferred

App-side gathering needs no tools and keeps data/instruction separation under our control. Preload yields to the operator: an operator turn cancels an in-flight preload (bounded wait), so preload can never delay the first message beyond later ones (AC-9).

## 4. Exact components to modify
See change-impact table.

## 5. Components not to modify
`_agent_handoff_text`, `prompts/home-agent.md`, `home_agent_session.py`, `supervisor_runner.py`, `uncle` launcher, `_warm_supervisor`.

## 6. Data-flow changes

Startup thread -> `home_preload.gather` -> prompt -> `session.turn` (log to `io.BytesIO`, discarded). The preload writes only to this in-memory buffer: it creates no `home-agent-chat-N.jsonl` file and increments no counter or log index used for operator turns (`chat_calls`, chat log numbering), and is not added to `home_history`. Exactly one preload turn is sent, asserted by tests (`turn` called exactly once; `home_history` and `chat_calls` unchanged). The first operator message therefore still logs to `home-agent-chat-1.jsonl`.

## 7. State-transition changes

Add `self.agent_preload_cancel` (Event or None, initially None) and `self.agent_lock` (RLock) in `_agent_state`. Session get-or-create is atomic under `agent_lock`: whichever caller (operator `_agent_turn` or preload thread) takes the lock first creates and assigns `agent_session`; the other reuses it and never spawns a second process or replaces an existing session. Each preload creates a fresh cancel Event (never reused), stores it in `agent_preload_cancel` under `agent_lock`, keeps a local reference to it, and passes that same Event to its `session.turn`. Preload runs at most once per process start: `run()` starts the thread once, and no build quiesce, root change, or `_close_home_agent` restarts it (later sessions start lazily on the operator's next message). `_close_home_agent` sets the current Event (if any) and then sets `agent_preload_cancel = None`, both under the lock, so a stale Event can never affect a later session. If the operator created the session first, the preload reuses it and skips its turn (no preload prompt is sent once an operator turn has started). After creating (or obtaining) the session and after the turn, the preload thread checks `agent_session is session and not its_event.is_set()`; otherwise it closes only a session it created itself, never one it did not create (SI-6). If the preload turn raises, fails or times out, the preload thread closes the session it created and, under `agent_lock`, sets `agent_session` to None only if `agent_session is session`, so the next `_agent_turn` lazily starts a fresh session and never reuses a half-primed one.

## 8. Interface changes
One new internal method and one new module; no public API.

## 10. Compatibility strategy

All preload guards live in ONE shared helper (e.g. `_home_agent_available()`) that checks the env opt-out (`UNCLE_HOME_AGENT == '0'`) and the runner (must be `claude`); `_home_agent_session` itself uses this helper, so the operator path and preload cannot drift. The `UNCLE_NOUI != '1'` check lives in `run()`, before the preload thread is started (not inside `_preload_home_agent`), and is tested with the thread start patched. `run()` starts the preload thread only when the NOUI check and the shared helper both allow it. `_preload_home_agent` also calls the shared helper first and returns silently before any session call (`_home_agent_session`, `_agent_note_unavailable`, spawn) when it is unavailable, so the preload path NEVER calls `_agent_note_unavailable` and adds no `home_history` note (SB-5). Only the operator path (`_agent_turn` -> `_home_agent_session`) may note unavailability. Decision D-1: preload pre-checks the shared helper and skips silently. Tests: with opt-out set and with a non-claude runner, assert `_agent_note_unavailable` is not called and `home_history` is unchanged; with `UNCLE_NOUI=1` and thread start patched, assert `run()` does not start the thread.

## 11. Concurrency implications

`agent_lock` (RLock) guards session get-or-create/close; held only for spawn/close, not the turn. `_home_agent_session` returns the existing `agent_session` if set; otherwise creation and assignment to `agent_session` are atomic under `agent_lock`, so whichever caller (operator `_agent_turn` or preload thread) takes the lock first creates the session and the other reuses it. Exactly one session is ever spawned, whether the operator message arrives before, during or after the preload's spawn. If the operator creates the session first, the preload thread reuses it and skips its turn (no preload turn is sent when an operator turn started first). Preload yields to the operator: `_agent_turn` first sets the active preload's cancel Event, then acquires `session.lock`, waiting at most PRELOAD_CANCEL_WAIT_S (default 3s, module constant patchable by tests). If the preload turn has not released the lock by then, the session is closed (killing the process) and the operator turn starts a fresh session lazily. Preload timeout (AR-004): the 60s deadline is measured from the start of the preload turn itself and excludes any lock wait before it. When it expires, or the preload is cancelled, the preload thread sets the cancel Event, closes the session it created and sets `agent_session` to None under `agent_lock`, silently and with no history note, so a partial preload turn is never kept. A queued operator turn then finds no live session and starts a fresh one lazily via `_home_agent_session` (AR-017), so the operator message is never lost and never sent into a half-primed or killed session. Operator turn otherwise queues on `session.lock` (SI-1); `_agent_turn` main-thread call takes the same lock via `_home_agent_session`. Test: patched `persistent_session` counts spawns (exactly one) for both orderings. Decision D-2: if the main thread closes while preload is mid-turn, `cancelled` is set and `close()` kills the process; `turn` returns.

Session-creation race (AR-003): whichever caller (preload thread or operator `_agent_turn`) acquires `agent_lock` first creates the session and assigns `agent_session` atomically; the other caller finds `agent_session` set and reuses it, never spawning a second process. The preload thread sends its priming turn only if no operator turn has started on that session (checked under `agent_lock` immediately before `session.turn`, via a flag set by `_agent_turn` when it begins); if the operator created the session first or has already started a turn, the preload skips its turn, leaves the session in place, and exits silently. A test covers both orderings (preload first, operator first).

## 12. Error and recovery behavior

Thread body wrapped in `except Exception: pass` after cleanup. On preload turn timeout (60s) or error, the preload thread closes the session it created and clears `agent_session` to None under `agent_lock` (only if `agent_session` is still that session), so the next `_agent_turn` starts a fresh session lazily and never reuses a half-primed one. Lazy start remains.

## 14. Rollback plan

Thread body wrapped in `except Exception: pass` after cleanup. On preload turn failure or timeout the thread first closes the session it created and resets `agent_session` to None (guarded by `agent_session is session` under `agent_lock`), then swallows the error silently. Lazy start remains.

## 15. Restrictions

| ID | source_kind | Source | Reqs | Property | Mechanism | Rationale | CAP | Phase |
|---|---|---|---|---|---|---|---|---|
| R-1 | USER | CHANGE_REQUEST Constraints | SB-4, SB-5, SI-5 | No preload under noui/opt-out/non-claude; skipped preload makes no session call and adds no history note | shared `_preload_allowed()` guard (noui, opt-out, non-claude runner) checked in `run()` before the thread starts, including the `UNCLE_NOUI` check, and again at the top of `_preload_home_agent`, before any session call | explicit requirement | CAP-PY | CODING |
| R-2 | USER | CHANGE_REQUEST Constraints | SB-2, SI-4 | App-sent, authorizes nothing, data not instruction | `preload_prompt` wording + sanitization + nonce delimiters. Sanitization: every gathered string has control characters (incl. newlines/ESC, except a single space) stripped and is truncated per item (200 chars). Delimiters: a per-run random nonce (`secrets.token_hex(8)`) forms the begin/end markers; the nonce string is removed from all gathered strings before embedding, and the prompt states the block is untrusted data, not instructions. | explicit | CAP-PY | CODING |
| R-3 | USER | CHANGE_REQUEST Constraints | SI-3 | No ungranted tools: preload session carries no operator-granted tool rules; any tool-use request during preload is denied and cancels the preload turn | app-side gather; `build_command` unchanged; preload session created without operator-granted rules; tool-use request or permission prompt during preload is denied and sets the preload cancel Event, then the session is closed per AR-019/AR-004 handling | feasible: `build_command` unchanged (home_agent_session.py:132); injected repo/issue text must not cause unattended tool calls | CAP-PY | CODING |
| R-4 | USER | CHANGE_REQUEST Constraints | SB-6, SB-7, SI-6 | Clean cancel on quiesce/root change/exit | cancel event + RLock + atomic get-or-create of `agent_session` under `agent_lock` + post-create check | `_close_home_agent` already on all paths (3634, 3657, 8866, 8885) | CAP-PY | CODING |
| R-5 | USER | CHANGE_REQUEST Constraints | SB-3, SI-1 | Operator turn cancels in-flight preload; queue, never interleave; wait bounded to at most 3s | `_agent_turn` sets the preload cancel Event, then waits on existing `session.lock` in `turn` (supervisor_runner.py ~447) for at most PRELOAD_CANCEL_WAIT_S (3s); if the lock is not released in that time, the preload session is closed and restarted lazily, so the operator turn never interleaves with the preload | queueing reuses the existing lock; cancelling the preload and bounding the wait at 3s keeps first-message latency small and within AC-9 without waiting out a full preload | CAP-PY | CODING |
| R-6 | USER | CHANGE_REQUEST Constraints | SB-2 | Staleness note | snapshot timestamp + re-check sentence in prompt | DESIGN | CAP-PY | CODING |
| R-7 | USER | CHANGE_REQUEST Constraints | SB-8, SI-7 | Silent failure, including timeout: no half-primed session left behind (session closed, agent_session None; next message restarts lazily) | broad except in thread; `PRELOAD_TIMEOUT_S` timer sets the cancel Event; on timeout or error the thread closes the session it created and clears `agent_session` to None under `agent_lock` | explicit | CAP-PY | CODING |
| R-8 | DESIGN | plan | SB-9 | UI thread not blocked | daemon thread; lock held only for spawn | revisable | CAP-PY | CODING |
| R-9 | PLATFORM | live claude binary | AC-9 | Live timing check | manual run | needs claude auth | CAP-CLAUDE | LIVE_VERIFICATION |

CAP-PY = python3 + unittest (present). CAP-CLAUDE = authenticated claude CLI, needed only for live verification, not for coding.

## 16. Automated-test strategy

New `scripts/tests/home-preload-test.py` (hyphenated name so the runner collects it): fake runner for gather (success, timeout, missing gh, size cap); prompt text assertions (SI-4, R-6); sanitization tests (control chars stripped, per-item truncation, a title/filename containing the closing delimiter or the nonce cannot terminate the data block, nonce differs between runs); `_preload_home_agent` with patched `persistent_session` for guards (noui, opt-out, non-claude), queueing behind a blocking turn, cancel via `_close_home_agent`, session created after close is closed, failure silence. Test fixtures use no git commits in real repos; any git fixture disables signing.

- Tool-use: a fake session emitting a tool-use event during preload causes the turn to be cancelled and denied, no grant rules are applied, and `build_command` output is unchanged.
- Concurrent creation: a barrier test calls `_home_agent_session` from two threads and asserts one `persistent_session` call and an identical session object; also operator-first ordering: `_agent_turn` creates the session first, `persistent_session` is called once and preload sends no turn.
- Cancel Event lifecycle: `_close_home_agent` sets then clears `agent_preload_cancel` to None; a later preload gets a distinct unset Event; closing and recreating the session after preload triggers no second preload thread or turn (at most once per process).
- Failure paths: fake `session.turn` raising, and timing out via patched `PRELOAD_TIMEOUT_S`, each assert `close()` called, `agent_session` is None and no exception escapes the thread; a queued operator turn behind a blocked preload that times out or is cancelled runs on a fresh session.
- Latency bound: a blocked fake preload turn plus an operator turn asserts the operator turn begins within the capped wait bound.
- Guard paths additionally assert `_agent_note_unavailable` is never called and `home_history` is unchanged; preload never alters `home_history`, `chat_calls` or the chat-N log index, writes nothing to disk, and the first operator turn writes chat-1.
- Gather: non-git directory and all-sources-failing cases skip preload with no session turn; total-cap tests at cap-1, cap, cap+1 assert total length and that git status survives; secret-like names (.env, *.pem, *key*, credentials*) are absent from the prompt; the fake runner records calls and asserts fixed argv lists, no shell, cwd equal to project root, `-c core.fsmonitor=false` on git, and bounded output; delimiter tests assert the nonce delimiter appears exactly once as open and once as close and control chars are stripped.

## 17. Regression-test strategy

Full driver commands from baseline: `bash scripts/run-shell-tests.sh` and `bash scripts/run-python-tests.sh` (parallel group). Existing suites set `UNCLE_HOME_AGENT=0` and never call `run()`.

`run()` is not called by existing suites, so the NOUI thread-start guard is tested in home-preload-test.py by patching the thread start and asserting it is not invoked when `UNCLE_NOUI=1` and is invoked otherwise.

## 18. Manual-verification strategy

Launch `uncle` with UI; `ps` shows `claude` child before typing; ask a branches/issues question and check `.uncle/workflow/logs/home-agent-chat-1.jsonl` (which must be the first operator message's log, unaffected by preload) for no repeated exploration and first-text latency; `uncle --noui ...` and `UNCLE_HOME_AGENT=0` show no process. Automated: new `scripts/tests/home-preload-test.py` (hyphenated name so the runner collects it) uses a fake runner for gather (success, timeout, missing gh, size cap); size-cap boundary tests (total <= 6000 chars at exactly-at-limit and over-limit inputs; truncation order issues, then worktrees, then listing; git status retained; all sources failing yields no snapshot and no preload); prompt text assertions (SI-4, R-6); `_preload_home_agent` with patched `persistent_session` for guards (noui, opt-out, non-claude), queueing behind a blocking turn, cancel via `_close_home_agent`, session created after close is closed, failure silence; and after a successful preload, assertions that the fake `session.turn` was called exactly once and that `home_history` and `chat_calls` are unchanged from their pre-preload values. Test fixtures use no git commits in real repos; any git fixture disables signing.

## 19. Observability
None added (silent by requirement).

## Change-impact table
| Component | Planned change | Reason | Regression risk | Test coverage |
|---|---|---|---|---|
| `uncle_tui.py` | `_agent_state` adds lock/cancel; `_home_agent_session` and `_close_home_agent` take lock/cancel; new `_preload_home_agent`; thread start in `run()` | wire preload | Medium (threading) | home-preload-test.py |
| `scripts/lib/home_preload.py` | new: `gather`, `preload_prompt` | bounded snapshot, data/instruction separation | Low | home-preload-test.py |
| `scripts/tests/home-preload-test.py` | new tests | verify SB/SI | Low | self |

## Traceability

| Requirement | Behavior | Invariant | Component | Automated test | Manual check |
|---|---|---|---|---|---|
| AC-1 | SB-1 | - | uncle_tui.py | home-preload-test.py | ps check |
| AC-2,AC-3 | SB-2 | SI-4 | home_preload.py | home-preload-test.py (prompt text, control-char stripping, per-item truncation, nonce delimiter escape attempts, total-cap truncation order and boundary tests) | log inspection |
| AC-4 | SB-4, SB-5 | SI-5 | uncle_tui.py | home-preload-test.py: shared guard helper `_preload_allowed()` for noui, opt-out, non-claude; `run()` with thread start patched asserts no thread is started under the NOUI guard; `_preload_home_agent` under each guard (noui, opt-out, non-claude) asserts `_home_agent_session` and `_agent_note_unavailable` are never called | noui / opt-out ps |
| An operator message sent while the preload is in flight cancels the preload and never interleaves with it. The operator turn starts within PRELOAD_CANCEL_WAIT_S (default 3s) of submission, rather than waiting for the preload's full 60s deadline. If the preload does not release the session lock within that bound, or has timed out or been cancelled, the preload session is closed and the queued operator message starts a fresh session lazily and is still answered, in order. | SB-3 | SI-1 | session lock | home-preload-test.py: blocking fake preload turn; operator turn sets cancel and starts within the PRELOAD_CANCEL_WAIT_S bound; on a stuck lock the preload session is closed and a fresh one is used; the operator message is still answered | send early message |
| AC-6 | SB-6, SB-7 | SI-2, SI-6 | uncle_tui.py | home-preload-test.py (incl. concurrent operator `_agent_turn` and preload creation: exactly one session spawned, both use it) | start build during preload |
| AC-7 | SB-8 | SI-7 | uncle_tui.py | home-preload-test.py: failure silence; timeout test with patched PRELOAD_TIMEOUT_S (preload timeout closes the session and agent_session is None) | claude missing |
| AC-8 | SB-9 | - | uncle_tui.py | full suites | keyboard feel |
| AC-9: first-message latency is no worse than later messages; the worst-case extra wait behind preload is bounded to 60s (preload finish or 60s, whichever is first). | SB-3 | - | all | - | timing in log |

## Implementation sequence

1. Create pure preload module (`gather` with injectable runner, per-command 5s timeout, `preload_prompt` with untrusted-data delimiters, timestamp and re-check note). Size rule: the TOTAL snapshot is at most 6000 chars (constant `SNAPSHOT_MAX_CHARS`), not per section. Truncation order when over cap: drop open issues (gh) first, then worktrees, then truncate the top-level file listing; git status is never dropped (truncated only as a last resort to fit). Non-git directory: git and worktree sections are omitted; listing and gh remain. If no source returns data, `gather` returns None and preload is skipped silently (no session, no turn). Subprocess hardening: every command is a fixed argv list (no shell, no user-derived argv), run with cwd=project root; git invocations are prefixed `git -c core.fsmonitor=false -c core.hooksPath=/dev/null --no-pager`, use `--no-ext-diff --no-textconv` where diffs are involved, with `GIT_OPTIONAL_LOCKS=0`; `gh` uses a fixed `gh issue list --json ... --limit N`. Env is minimal and explicit (PATH, HOME, LANG plus `GIT_TERMINAL_PROMPT=0`, `GH_PROMPT_DISABLED=1`, `NO_COLOR=1`); nothing else is inherited. Each command's stdout is read with a byte bound (excess truncated) and stderr is discarded. The runner interface receives argv, cwd, env and timeout so tests can assert all four. Boundary tests: exactly 6000, 6001, and each truncation stage.
   Owns: `scripts/lib/home_preload.py`
2. Write tests against the step-1 and step-3 interfaces (`_preload_allowed`, `_preload_home_agent`, `run()` thread-start seam); they patch `persistent_session` and call TUI methods, so they cannot be written against step 1 alone.
   Owns: `scripts/tests/home-preload-test.py`
   Depends on: 1, 3
3. Wire into TUI: lock/cancel state, `_preload_home_agent`, thread start in `run()` after `_warm_supervisor`; builds on step 1's API and edits functions already in this file only. This step owns the single shared guard helper (`_preload_allowed()`: UNCLE_NOUI=1, UNCLE_HOME_AGENT=0, runner != claude) called by BOTH `run()` (thread not started when False) and `_preload_home_agent` (returns before any session call), and fixes the `_preload_home_agent` signature and the thread-start seam (a small patchable function or `threading.Thread`) up front so step 2 can test them.
   Owns: `uncle_tui.py`
   Depends on: 1
4. Run new test file and then driver commands; fix only own code.
   
   Decisions: D-1 skip preload silently via the shared `_preload_allowed()` guard (noui, opt-out, non-claude) checked in both `run()` and `_preload_home_agent` before any session call; D-2 cancel Event passed to `session.turn`; D-3 gh missing or failing means issues section omitted; if all sources fail (or non-git with empty listing) preload is skipped; total snapshot capped at 6000 chars with truncation order issues, worktrees, listing (git status kept); D-4 each preload gets a fresh cancel Event and preload runs at most once per process start (no re-preload after build/root change; later sessions start lazily).
   Depends on: 2, 3

## Scope cuts under time pressure
Cut first: open-issues section (gh), then worktrees; keep git status + file listing + guards + cancel safety.

## Risks and unresolved questions
Thread races on `agent_*` state (mitigated by lock, test SI-6); prompt injection via issue titles (delimiters, instruction not to follow); live timing needs authenticated claude (R-9, LIVE_VERIFICATION only). No blocking questions.

## Adversarial review dispositions

| Finding | Disposition | Reason | Exact plan change |
|---|---|---|---|
| AR-001 | Accepted | A 60s queue would violate AC-9; an operator turn arriving during preload should cancel it instead of waiting. | Edit s1.1, s3.1, s10.1, R-5, AC-5: operator turn cancels in-flight preload and starts fresh; bounded wait of 3s at most. |
| AR-002 | Accepted | Guard placement was inconsistent between spec, R-1 and D-1; a single shared guard checked in both run() and the thread body removes drift. | Rewrote s9.1 and R-1 to define one shared guard helper used by run() and _preload_home_agent; AC-4 and step-4 D-1 aligned. |
| AR-003 | Accepted | Real gap: operator's first message could create the session before the preload thread; the plan only covered a preload already in flight. | s10.1 now states first-holder-of-agent_lock creates the session, the other reuses it, and the preload turn is skipped if an operator turn has started. |
| AR-004 | Accepted | Timeout behavior was unspecified; closing the session on timeout avoids reusing a partial turn and keeps lazy restart. | Section 11 (s10.1) states that on timeout the preload closes the session and clears agent_session; R-7 and AC-7 agree. |
| AR-005 | Accepted | Cap scope, truncation order, and empty/non-git behavior were unspecified and must be testable. | Step 1 and step 4 D-3 now state a total 6000-char cap, truncation order, git status kept, and preload skipped when no source returns data. |
| AR-006 | Accepted | Real gap: fresh-Event lifecycle and run-once semantics were unstated; stating them removes stale-cancel and re-preload ambiguity. | s7.1 now specifies a fresh cancel Event per preload and at-most-once preload per process start; D-4 in step-4 aligned. |
| AR-007 | Accepted | Guard logic must not be duplicated or drift, and preload must never add a history note via `_agent_note_unavailable`. | Section 10 (s9.1) now requires a shared guard helper used by `_home_agent_session` and preload, with preload never calling `_agent_note_unavailable`. |
| AR-008 | Accepted | Mid-spawn race is real; atomic get-or-create under agent_lock removes any chance of a second claude process. | s10.1 and s7.1 state get-or-create atomicity under agent_lock; AC-6 gains a test for it. |
| AR-009 | Accepted | A half-primed session must not be reused for the operator's first message; closing and clearing on timeout or error is simple and safe. | Edit s11.1 and R-7 to close and clear agent_session on preload timeout or error so the next _agent_turn starts fresh. |
| AR-010 | Accepted | The cancel Event lifecycle was unspecified; a fresh per-preload Event cleared on close prevents a stale event cancelling a later session. | s7.1 now specifies a fresh Event per preload, set then cleared to None by `_close_home_agent` under the lock; preload runs once per process start. |
| AR-011 | Accepted | Plan was silent on counters and log numbering; operator logs must stay home-agent-chat-1 for the first operator message. | Section 6 data-flow states preload uses an in-memory buffer and advances no operator counter or log index; manual check in section 18 reads chat-1 as the first operator turn. |
| AR-012 | Accepted | The UNCLE_NOUI guard was split between run() and _preload_home_agent; placing it in run() (testable with thread start patched) removes the inconsistency. | Edit s9.1, R-1, s15.1 and AC-4 so the UNCLE_NOUI check lives in run() before the thread starts, with a test that patches thread start. |
| AR-013 | Accepted | Sanitization and delimiting were undefined, so gathered text containing the closing delimiter could escape the data block. | Edit R-2 mechanism, s14.1 test strategy and s19.1.r2 tests to define control-char stripping, per-item truncation and a per-run random-nonce delimiter. |
| AR-014 | Accepted | The plan was silent on tool rules and mid-preload tool requests; unattended injected text must not trigger tools. | Revised R-3 (section 15) so preload runs with no granted rules and any tool-use request is denied and cancels the turn. |
| AR-015 | Accepted | Sending secret-named files to the model unprompted at startup is an avoidable exposure; filtering names and sending names only is cheap. | s1.1 now says the gather filters secret-like names from listing and git status and sends names only, never contents; s7.1 notes filtering happens before the prompt is built. |
| AR-016 | Accepted | Real gap: unspecified argv, cwd and env let repo-configured git helpers run unattended at startup. | Step 1 now fixes argv lists, no shell, cwd=project root, git -c core.fsmonitor=false, minimal env and size-bounded output; test added in step 2 scope note. |
| AR-017 | Accepted | Behavior when a queued operator turn meets a preload that times out or is cancelled was unspecified; closing the session and restarting lazily is the safe rule. | Section 11 (s10.1) states the 60s excludes lock wait, and the queued operator turn starts a fresh session lazily after preload timeout/cancel; AC-5 updated to match. |
| AR-018 | Accepted | The 60s deadline needs a named, patchable mechanism and a defined expiry outcome to be testable. | s1.1 now defines PRELOAD_TIMEOUT_S via the cancel Event with close and agent_session=None on expiry; R-7 and AC-7 updated to match. |
| AR-019 | Accepted | The plan was silent on session fate after a failed or timed-out preload turn; closing and clearing it prevents a half-primed session being reused. | Edited s7.1 (state transitions) and s12.1 (error and recovery) to close the preload's session and set agent_session to None on turn failure or timeout. |
| AR-020 | Accepted | Unbounded queueing behind preload conflicts with AC-9; a wait cap of min(preload finish, 60s) reconciles AC-5 and AC-9. | Edit s1.1, R-5, AC-5 and AC-9 to bound an operator message's wait behind preload at the preload finishing or 60s, whichever is first. |
| AR-021 | Accepted | The plan did not say what happens when the operator creates the session before the preload thread does; whoever holds agent_lock first creates it and the other reuses it. | Edited s7.1 and s10.1: atomic get-or-create under agent_lock; preload skips its turn if an operator turn already started; added a race test. |
| AR-022 | Accepted | The cap was ambiguous; a total cap with a fixed truncation order and boundary tests makes it testable. | Step 1 states the total 6000-char cap and truncation order; s16.1 and AC-3 traceability add boundary tests. |
| AR-023 | Accepted | Real gap: the no-history/no-counter claim and single-turn behavior had no planned assertions. | s16.1 adds assertions (turn called exactly once; home_history and chat_calls unchanged); s6.1 and step-4 note it. |
