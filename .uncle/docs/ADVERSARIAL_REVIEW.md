## AR-001: Plan is silent on a pending D-1 approval or in-flight agent turn when a build starts.

- Severity: HIGH
- References: CHANGE_PLAN D-1, D-7, s10: home_request guards one turn only; no row covers a build starting mid-turn.
- Failure: Plan is silent on a pending D-1 approval or in-flight agent turn when a build starts. Add: 'Build start or recovery cancels the in-flight turn, discards pending approvals, posts one note; later approvals are ignored.'
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-002: Busy/idle boundary undefined while the session is closing or re-created.

- Severity: HIGH
- References: CHANGE_PLAN s7 idle predicate, D-7; CHANGE_SPEC I-3. AC-7 only tests argv during a running build.
- Failure: Busy/idle boundary undefined while the session is closing or re-created. Add: 'Idle is evaluated at send time; the session is confirmed dead before a build spawns; messages in that window go to the tool-free supervisor.'
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-003: D-1 approval semantics unspecified: grant scope, decline behavior, persistence across respawn, multiple denials.

- Severity: HIGH
- References: CHANGE_PLAN D-1, D-6, D-7; CHANGE_SPEC S-11. No reset or decline behavior described.
- Failure: D-1 approval semantics unspecified: grant scope, decline behavior, persistence across respawn, multiple denials. Add: 'Approval grants the exact denied tool+input for this session only, cleared on build start; decline sends the agent a refusal; denials are shown one at a time.'
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-004: Replies with duplicate or combined uncle_action/uncle_cwd blocks are unspecified.

- Severity: MEDIUM
- References: CHANGE_PLAN D-5 ('one' block) vs D-6 ('a' block); S-3 mismatch refusal; no ordering rule.
- Failure: Replies with duplicate or combined uncle_action/uncle_cwd blocks are unspecified. Add: 'More than one block of a kind executes none of that kind; uncle_cwd applies before uncle_action; an invalid cwd cancels the action.'
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-005: I-2 enforcement via name-pattern --disallowedTools is bypassable (bash -c, other names, paths), yet AC-6 says builds sta

- Severity: MEDIUM
- References: CHANGE_PLAN D-5; CHANGE_SPEC I-2 and AC-6 (argv test only).
- Failure: I-2 enforcement via name-pattern --disallowedTools is bypassable (bash -c, other names, paths), yet AC-6 says builds start only via the action path. Add: 'Deny patterns are best-effort; I-2 is verified only for listed entry points; residual risk recorded in IMPLEMENTATION_NOTES.'
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-006: AC-3 allows housekeeping mentions only in the migration note and removal tests, but AC-9 needs legacy housekeeping.* con

- Severity: MEDIUM
- References: CHANGE_SPEC AC-3 vs AC-9/S-10; CHANGE_PLAN step 6 names no legacy-config test file.
- Failure: AC-3 allows housekeeping mentions only in the migration note and removal tests, but AC-9 needs legacy housekeeping.* config fixtures. Add: 'The allowlist is exactly the migration doc, no-housekeeping-test.py, launcher-removed-flag-test.sh and the legacy-config test file.'
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-007: Plan says a pending proposal keeps the tool-free supervisor, but a denied-tool approval prompt (D-1) is also a pending s

- Severity: HIGH
- References: CHANGE_PLAN s7.1 idle predicate lists only build, recovery, pending proposal; D-1 introduces a pending approval.
- Failure: Plan says a pending proposal keeps the tool-free supervisor, but a denied-tool approval prompt (D-1) is also a pending state. The plan never says whether the idle predicate counts it, or what a new user message does while an approval is pending. Settle with: while a tool approval is pending, any non-approve/decline message is treated as a decline and the denial prompt is cleared before routing.
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-008: D-7 closes the session when a build starts, but the plan does not say what happens to an in-flight agent turn, to a pend

- Severity: HIGH
- References: CHANGE_PLAN D-7 and s10.1 (only 'one in-flight turn guarded by home_request') versus D-5 trailing uncle_action execution.
- Failure: D-7 closes the session when a build starts, but the plan does not say what happens to an in-flight agent turn, to a pending approval, or to an uncle_action block parsed from a reply that arrives after the close. Settle with: starting a build cancels any in-flight agent turn and discards its output and pending approval, and trailing blocks from a closed session are never executed.
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-009: A single reply may contain both uncle_cwd and uncle_action blocks (for example clone then build issue 34).

- Severity: MEDIUM
- References: CHANGE_PLAN D-5 and D-6 each describe one trailing block; S-3 requires the build to target the clone.
- Failure: A single reply may contain both uncle_cwd and uncle_action blocks (for example clone then build issue 34). The order of application, and whether the action runs against the old or new root, is unspecified. This is the S-3 regression risk. Settle with: uncle_cwd is validated and applied first, then uncle_action executes against the new root, and an invalid cwd cancels the action.
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-010: D-1 restarts the session on approval and re-sends the message, but the plan does not say what happens if the re-sent tur

- Severity: MEDIUM
- References: CHANGE_PLAN D-1 'restarts the session (history handoff), then re-sends the message'; no retry bound.
- Failure: D-1 restarts the session on approval and re-sends the message, but the plan does not say what happens if the re-sent turn side-effects twice. Commands that partly ran before the denial may run again, and a second denial may loop. Settle with: re-send happens at most once per user message, and a second denial shows a new prompt rather than auto-retrying.
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-011: D-10 renames the stdin helper, but the golden-transcript step 1 only covers home actions.

- Severity: MEDIUM
- References: CHANGE_PLAN steps 2 and 6; step 6 deletes housekeeping-input-test.py and adds startup-text-input-test.py.
- Failure: D-10 renames the stdin helper, but the golden-transcript step 1 only covers home actions. The preserved --application stdin path has no baseline-equivalent regression test until step 6. Settle with: the old housekeeping-input-test.py is run against the renamed module, with only the import renamed, before it is deleted.
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-012: AC-3 forbids any housekeeping mention outside the migration note and removal tests, but AC-9 legacy-key tests must name

- Severity: LOW
- References: CHANGE_SPEC AC-3 versus AC-9; CHANGE_PLAN s15 new tests.
- Failure: AC-3 forbids any housekeeping mention outside the migration note and removal tests, but AC-9 legacy-key tests must name housekeeping.* keys. The allowed-file list is not specified. Settle with: the allowlist is exactly the migration doc, no-housekeeping-test.py, launcher-removed-flag-test.sh and tui-home-agent-test.py.
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-013: D-1 grants an 'exact tool/command' via --allowedTools but never defines exact or the grant's lifetime.

- Severity: HIGH
- References: CHANGE_PLAN D-1, I-5; CHANGE_SPEC S-11 do not define 'exact', lifetime across respawn, or prompt contents.
- Failure: D-1 grants an 'exact tool/command' via --allowedTools but never defines exact or the grant's lifetime. Plan should say: 'An approval adds only the verbatim denied command as an exact-match Bash(<cmd>) rule, never a wildcard or bare tool name, for that session only; the prompt shows the full command.'
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-014: The D-5 prefix deny rules cannot stop an agent with Bash from starting a build (bash -c, absolute path, wrapper script,

- Severity: HIGH
- References: CHANGE_PLAN D-5 calls Bash(uncle:*) etc. an 'I-2 guard'; CHANGE_SPEC I-2 enforcement point.
- Failure: The D-5 prefix deny rules cannot stop an agent with Bash from starting a build (bash -c, absolute path, wrapper script, python subprocess), bypassing I-2. Plan should say: 'I-2 is enforced by the drivers refusing to start unless launched through the app action path (app-issued marker); argv deny rules are only advisory.'
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-015: A trailing uncle_action block is parsed from free-form agent text, so injected repo, issue or web content could forge on

- Severity: MEDIUM
- References: CHANGE_PLAN D-4, D-5; the risks table covers a missing block but not a forged or injected one.
- Failure: A trailing uncle_action block is parsed from free-form agent text, so injected repo, issue or web content could forge one. Plan should say: 'Every agent-emitted uncle_action needs explicit user confirmation, and only the last fenced block of the agent's own final text is parsed, never tool output.'
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-016: uncle_cwd validation is only isdir on an absolute path; symlinks, '/', $HOME and arbitrary directories are unspecified.

- Severity: MEDIUM
- References: CHANGE_PLAN D-6; CHANGE_SPEC I-6.
- Failure: uncle_cwd validation is only isdir on an absolute path; symlinks, '/', $HOME and arbitrary directories are unspecified. Plan should say: 'Paths are realpath-resolved, must not be / or $HOME, and a path not created or cloned this session needs user confirmation.'
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-017: The plan does not say what environment the agent's Bash inherits, yet the deny list that protected secrets is removed.

- Severity: MEDIUM
- References: CHANGE_SPEC section 10 says only 'existing STRIP_ENV treatment'; CHANGE_PLAN D-4 relies on permissions alone.
- Failure: The plan does not say what environment the agent's Bash inherits, yet the deny list that protected secrets is removed. Plan should say: 'The agent subprocess gets an allowlisted environment with STRIP_ENV secrets removed; gh uses only its own stored auth.'
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-018: The interaction between a pending approval, a new user message, a build start, and a session restart is unspecified.

- Severity: LOW
- References: CHANGE_PLAN D-1 (restart and re-send) and D-7 (close on build start) do not define their interaction.
- Failure: The interaction between a pending approval, a new user message, a build start, and a session restart is unspecified. Plan should say: 'A pending approval is discarded with a note on a new message, build start, or restart; approval never re-sends a message from a prior session state.'
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-019: D-1 approval flow leaves decline, repeat denial, and typing while a prompt is pending unspecified.

- Severity: HIGH
- References: CHANGE_PLAN D-1 and S-11 describe only the approve path.
- Failure: D-1 approval flow leaves decline, repeat denial, and typing while a prompt is pending unspecified. Say: 'Decline discards the tool and posts a note without re-send; messages typed during a pending approval are queued; a repeat denial after approval ends the turn with an error note.'
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-020: The denial-format fixture is an assumption, so the session test could pass against an invented format.

- Severity: HIGH
- References: CHANGE_PLAN Risks row 1; Automated-test strategy uses a fake runner only.
- Failure: The denial-format fixture is an assumption, so the session test could pass against an invented format. Say: 'The permission_denials fixture is copied from a recorded real claude -p stream-json result, and the session test parses that file.'
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-021: D-1 adds approved commands to --allowedTools while D-5 disallows driver entry points; precedence and wildcard grants are

- Severity: MEDIUM
- References: CHANGE_PLAN D-1 vs D-5; I-5 test only rejects bypass flags.
- Failure: D-1 adds approved commands to --allowedTools while D-5 disallows driver entry points; precedence and wildcard grants are unstated. Say: 'Approval grants only the exact denied command string, never a wildcard, and --disallowedTools always wins; a test asserts it.'
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-022: Trailing-block parsing is unspecified for multiple blocks, both block types in one reply, malformed JSON, and relative o

- Severity: MEDIUM
- References: CHANGE_PLAN D-5, D-6 and Error section cover only a single block.
- Failure: Trailing-block parsing is unspecified for multiple blocks, both block types in one reply, malformed JSON, and relative or symlink paths. Say: 'Only the last block of each type at the end of the reply is honored; cwd applies before the action; malformed or duplicate blocks are ignored with a note; the path is realpath-resolved before isdir.'
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-023: Lifecycle races are unspecified: a build starting during an in-flight agent turn, or a turn finishing after the session

- Severity: MEDIUM
- References: CHANGE_PLAN s7 idle predicate, D-7, and s10 guard only via home_request.
- Failure: Lifecycle races are unspecified: a build starting during an in-flight agent turn, or a turn finishing after the session closed. Say: 'Build start cancels any in-flight agent turn and closes the session before spawning; late results are discarded; the idle predicate is evaluated once at send time.'
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-024: The AC-3 allowlist of files that may mention housekeeping is unstated, and D-9 conflicts with AC-9.

- Severity: LOW
- References: CHANGE_SPEC AC-3, AC-9; CHANGE_PLAN step 6 and D-9.
- Failure: The AC-3 allowlist of files that may mention housekeeping is unstated, and D-9 conflicts with AC-9. Say: 'no-housekeeping-test.py allowlists exactly the migration doc, itself, launcher-removed-flag-test.sh and tui-home-agent-test.py.'
- Fix: Address in the plan.
- Verify: Re-run the check.

## Overall assessment

Review findings require disposition.
