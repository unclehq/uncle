## AR-001: Operator's early message queues behind preload on session.lock, but preload has a 60s deadline, so the first message cou

- Severity: HIGH
- References: CHANGE_PLAN s1 (60s deadline) and R-5/SI-1 'Queue, never interleave' versus CHANGE_SPEC AC-5 and AC-9.
- Failure: Operator's early message queues behind preload on session.lock, but preload has a 60s deadline, so the first message could wait up to 60s, contradicting AC-9. Plan should say: an operator turn arriving during preload cancels the preload (or the wait is capped at N seconds) rather than queueing.
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-002: Guard placement conflicts: spec puts the SB-4 guard in run() and in _preload_home_agent, and D-1 covers only opt-out/run

- Severity: HIGH
- References: CHANGE_SPEC SB-4 'run guard' and SI-5 'guard in _preload_home_agent'; CHANGE_PLAN s9 D-1.
- Failure: Guard placement conflicts: spec puts the SB-4 guard in run() and in _preload_home_agent, and D-1 covers only opt-out/runner. Plan should say: _preload_home_agent returns before any session call if UNCLE_NOUI=='1', UNCLE_HOME_AGENT=='0' or runner != 'claude', and run() starts the thread only when the same checks pass.
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-003: Unspecified: the operator's first message creating the session lazily before the preload thread does.

- Severity: MEDIUM
- References: CHANGE_PLAN s10 'agent_lock guards session creation'; SB-3 only covers preload already in flight.
- Failure: Unspecified: the operator's first message creating the session lazily before the preload thread does. Plan should say: whichever caller holds agent_lock first creates the session, the other reuses it, and the preload turn is sent only if no operator turn has started.
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-004: Behavior on preload timeout is unspecified: after 60s the session may hold a partial turn, and no rule says keep or clos

- Severity: MEDIUM
- References: CHANGE_PLAN s1 '60s deadline', s10 D-2, SB-8 'timeout' silent with 'lazy start remains'.
- Failure: Behavior on preload timeout is unspecified: after 60s the session may hold a partial turn, and no rule says keep or close. Plan should say: on timeout the session is closed and agent_session cleared so the next message restarts it lazily.
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-005: Snapshot rules unspecified: whether the 6000-char cap is total or per-section, which section is truncated first, and wha

- Severity: MEDIUM
- References: CHANGE_PLAN step 1 '6000-char cap'; CHANGE_SPEC AC-3 'total size is capped', s10 'sanitized'; D-3.
- Failure: Snapshot rules unspecified: whether the 6000-char cap is total or per-section, which section is truncated first, and what happens in a non-git directory or when every source fails. Plan should say: the cap is total, truncating gh, then worktrees, then listing; if no source returns data, preload is skipped.
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-006: After root change or build quiesce the cancel event is set, but whether a fresh Event is created and whether preload may

- Severity: LOW
- References: CHANGE_PLAN s7 agent_preload_cancel and D-4; CHANGE_SPEC SB-7 'no preload re-run'.
- Failure: After root change or build quiesce the cancel event is set, but whether a fresh Event is created and whether preload may run again is unspecified. Plan should say: each preload gets a fresh Event and preload runs at most once per process start.
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-007: D-1 skips preload on opt-out or non-claude runner, but the plan never says how without calling `_home_agent_session`, wh

- Severity: HIGH
- References: CHANGE_PLAN s9 and D-1; SB-5 'no new note from preload'.
- Failure: D-1 skips preload on opt-out or non-claude runner, but the plan never says how without calling `_home_agent_session`, which can call `_agent_note_unavailable`. Duplicated guard logic can drift and add a history note (SB-5). Plan should say: 'The preload guard reuses the helper `_home_agent_session` uses and never calls `_agent_note_unavailable`.'
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-008: Mid-spawn races are unspecified: if the main thread calls `_agent_turn` while the preload holds `agent_lock`, it is uncl

- Severity: HIGH
- References: CHANGE_PLAN s10 'agent_lock guards session creation/close'; SI-6 covers only close before the post-create check.
- Failure: Mid-spawn races are unspecified: if the main thread calls `_agent_turn` while the preload holds `agent_lock`, it is unclear whether the operator path waits for the preload session or spawns a second process. Plan should say: '`_home_agent_session` returns the existing `agent_session` if set; creation and assignment are atomic under `agent_lock`.'
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-009: The plan does not say what happens to the session on preload timeout (60s) or turn error.

- Severity: MEDIUM
- References: CHANGE_PLAN s1 '60s deadline', s11 'except Exception: pass', SB-8.
- Failure: The plan does not say what happens to the session on preload timeout (60s) or turn error. A half-primed session could be reused for the operator's first message. Plan should say: 'On timeout or error the preload closes and clears `agent_session`, so the next `_agent_turn` starts fresh.'
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-010: Lifecycle of `agent_preload_cancel` is unspecified, so a stale cancel event could cancel a later session or preload afte

- Severity: MEDIUM
- References: CHANGE_PLAN s7 'agent_preload_cancel (Event or None)'; D-4 no re-preload.
- Failure: Lifecycle of `agent_preload_cancel` is unspecified, so a stale cancel event could cancel a later session or preload after root change or close. Plan should say: 'Each preload creates a fresh cancel Event; `_close_home_agent` sets it and then sets it to None under the lock.'
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-011: Plan does not say whether the preload turn advances counters or log numbering that operator turns use.

- Severity: MEDIUM
- References: CHANGE_PLAN s6 'log to io.BytesIO', s16 manual check, AC-9.
- Failure: Plan does not say whether the preload turn advances counters or log numbering that operator turns use. The manual check reads home-agent-chat-1.jsonl and existing tests may assume chat-1 is the first operator message. Plan should say: 'The preload writes to an in-memory buffer and increments no counter or log index used for operator turns.'
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-012: The UNCLE_NOUI guard location is inconsistent: R-1 says guards live in `_preload_home_agent`, while SB-4 says unit test

- Severity: LOW
- References: CHANGE_PLAN s9, R-1, s15; CHANGE_SPEC SB-4.
- Failure: The UNCLE_NOUI guard location is inconsistent: R-1 says guards live in `_preload_home_agent`, while SB-4 says unit test of the `run` guard. Existing suites never call `run()`, so the thread-start path is untested. Plan should say: 'The `UNCLE_NOUI` check is in `run()` before the thread starts, tested with thread start patched.'
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-013: Plan says repo/issue text is 'sanitized' and delimited but never defines either.

- Severity: HIGH
- References: CHANGE_SPEC §10 'sanitized, delimited'; CHANGE_PLAN Risks 'delimiters'; SI-4 test checks only 'prompt text and delimiters'.
- Failure: Plan says repo/issue text is 'sanitized' and delimited but never defines either. A title or filename containing the closing delimiter can escape the data block. Say: strip control chars, truncate each item, use a per-run random-nonce delimiter removed from all gathered strings.
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-014: Plan does not say whether the preload session has operator-granted tool rules or what happens on a tool request mid-prel

- Severity: HIGH
- References: CHANGE_SPEC SI-3 'read-only base tools plus granted rules'; CHANGE_PLAN R-3 only says build_command is unchanged.
- Failure: Plan does not say whether the preload session has operator-granted tool rules or what happens on a tool request mid-preload. Injected issue text could trigger tool calls unattended. Say: preload runs with no granted rules, and any tool-use request during preload is denied and cancels the turn.
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-015: Snapshot may expose secret-named files via the top-level listing or git status, sent to the model unprompted at startup.

- Severity: MEDIUM
- References: CHANGE_SPEC §10 'no secrets beyond repo state the agent could read anyway'; CHANGE_PLAN §1 gather list.
- Failure: Snapshot may expose secret-named files via the top-level listing or git status, sent to the model unprompted at startup. Say: filter secret-like names (.env*, *key*, *.pem, credentials*) from the listing and send names only, never contents.
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-016: Gather subprocess argv, cwd and env are unspecified; git/gh run in an untrusted repo can execute repo-configured helpers

- Severity: MEDIUM
- References: CHANGE_PLAN §1 and step 1 give only 'injectable runner, per-command 5s timeout'.
- Failure: Gather subprocess argv, cwd and env are unspecified; git/gh run in an untrusted repo can execute repo-configured helpers (fsmonitor, diff drivers). Say: fixed argv lists, no shell, cwd=project root, git with -c core.fsmonitor=false, minimal env, size-bounded output.
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-017: Unspecified: operator message queued when the 60s preload times out or is cancelled, and whether 60s includes lock wait.

- Severity: MEDIUM
- References: CHANGE_PLAN §1 '60s deadline'; §11 D-2 'close() kills the process; turn returns'; SB-3/SB-8 silent on this combination.
- Failure: Unspecified: operator message queued when the 60s preload times out or is cancelled, and whether 60s includes lock wait. Say: on preload timeout the session is closed and the queued operator turn starts a fresh session lazily.
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-018: The '60s deadline' is not tied to a testable mechanism or an expiry outcome.

- Severity: HIGH
- References: CHANGE_PLAN s1 says '60s deadline' with no mechanism or test hook. SB-8 lists timeout as a failure without saying what state results.
- Failure: The '60s deadline' is not tied to a testable mechanism or an expiry outcome. Settle it: 'The preload turn is cancelled via the cancel Event after PRELOAD_TIMEOUT_S (default 60, module constant patchable by tests); on expiry the session is closed and agent_session reset to None.'
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-019: The plan doesn't say whether the session is kept after the preload turn fails or times out.

- Severity: HIGH
- References: CHANGE_PLAN s7 covers cleanup only for superseded sessions. s12 says only 'except Exception: pass after cleanup'.
- Failure: The plan doesn't say whether the session is kept after the preload turn fails or times out. Settle it: 'If the preload turn fails or times out, the preload thread closes the session it created and sets agent_session to None.'
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-020: AC-5 queues an operator message behind the preload, but AC-9 wants first-message latency no worse than later ones, and n

- Severity: MEDIUM
- References: SB-3 and AC-5 say 'queues behind an in-flight preload'. s1 sets a 60s deadline. AC-9 requires first-message latency no worse than later ones.
- Failure: AC-5 queues an operator message behind the preload, but AC-9 wants first-message latency no worse than later ones, and no bound on the wait is given. Settle it: 'An operator message queued behind the preload waits at most until the preload finishes or 60s, whichever is first.'
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-021: The plan doesn't say what happens when the operator message arrives before the preload thread has created the session.

- Severity: MEDIUM
- References: CHANGE_PLAN s10 says agent_lock guards creation, but s7's post-create check only compares agent_session to the thread's own session. No test covers this race.
- Failure: The plan doesn't say what happens when the operator message arrives before the preload thread has created the session. Settle it: 'If the operator creates the session first, the preload reuses that session and skips its turn.'
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-022: The size cap is ambiguous: per section or total, and which section is truncated first.

- Severity: MEDIUM
- References: Implementation step 1 says '6000-char cap'. AC-3 and s16 give no truncation order or boundary tests.
- Failure: The size cap is ambiguous: per section or total, and which section is truncated first. Settle it: 'Total snapshot is at most 6000 chars; drop issues, then worktrees, then truncate the file listing; git status is never dropped.'
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-023: No assertion is planned for 'exactly one preload turn' or for home_history and chat_calls being unchanged.

- Severity: LOW
- References: CHANGE_PLAN s6 says 'Not added to home_history; not counted in chat_calls'. s16 lists no such assertion.
- Failure: No assertion is planned for 'exactly one preload turn' or for home_history and chat_calls being unchanged. Settle it: 'Tests assert fake session.turn is called exactly once and home_history and chat_calls are unchanged after preload.'
- Fix: Address in the plan.
- Verify: Re-run the check.

## Overall assessment

Review findings require disposition.
