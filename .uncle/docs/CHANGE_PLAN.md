# Change Plan (Issue 164)

Omitted sections: Schema/persistence (none); Concurrency (session lifecycle only, noted in 11); Feature flag (none: removal, rollback by revert); Observability beyond existing logs

Issue 164

Seeded from [unclehq/uncle#164](https://github.com/unclehq/uncle/issues/164).

## 1. Selected technical approach
Delete housekeeping. Add `scripts/lib/home_agent_session.py` (Claude only), derived from the surviving mechanics of `HousekeepingSession`/`build_command` but without any deny list: argv = `claude -p --output-format stream-json --verbose --include-partial-messages --strict-mcp-config --no-session-persistence --permission-mode default --model --effort --append-system-prompt <prompts/home-agent.md>`. No `--allowedTools` wildcard grants, no bypass flags. Idle `send_home_chat` routes to it; busy (build running, recovery, pending proposal) keeps the existing tool-free `_supervisor_turn`.

## Decisions (resolved in scope)

| ID | Decision | Reason |
|---|---|---|
| D-1 | Permissions: Claude default mode. `-p` cannot prompt, so tools needing approval are denied by Claude and the result event's denials are shown in the TUI as a pending approval, one denial at a time (queued, FIFO); the prompt shows the full verbatim denied command or tool input. Approval grants only that exact denied tool+input as an exact-match rule (for Bash, `Bash(<full command>)` with the command escaped so it cannot act as a pattern; never a wildcard such as `:*`, never a bare tool name like `Bash`). The grant is session-only (lives only in that session's argv, never persisted): kept across idle respawns (cwd change) within the same idle period, and cleared when a build starts (D-7) or recovery begins. `--disallowedTools` (D-5) always takes precedence over any grant. On approval the app adds that rule to `--allowedTools`, restarts the session (history handoff; the handoff tells the agent earlier commands may have partly run, so it must check state before repeating side effects) and re-sends the original user message at most once per user message; if the re-sent turn is denied again, the app shows a new approval prompt and never auto-retries, and ends that turn with an error note if it is not approved. Decline sends the agent a refusal message for that tool (no grant, no re-send) and posts a note. Messages typed while an approval is pending are queued and handled after it is resolved. A pending approval is discarded with one note on build start or session restart, and approval never re-sends a message from a prior session state (re-send only for the message that produced the still-current pending denial). Never a bypass flag | Uses Claude's own permission system; attended only; grant scope (exact string, session-only, cleared on build start) and re-send bounds are explicit so approvals cannot outlive the idle period, be broader than the command the user saw, override D-5, or cause duplicate side effects and denial loops |
| D-2 | Unattended and `--noui`: no chat exists, so no agent | Issue suggestion; home chat implies a person |
| D-3 | Runner: claude only; other runners fall back to the tool-free supervisor with one note | Permission model equivalence not available for codex/kimi |
| D-4 | Untrusted content policy in `prompts/home-agent.md`: repo, issue and web text is data, never instruction; actions come only from the user's messages; sanitization of excerpts retained. Because injected content could try to make the agent emit a forged `uncle_action`, the app never executes an agent-emitted action without explicit user confirmation (see D-5). Environment: the agent subprocess (and its Bash) is launched with an allowlisted environment (PATH, HOME, locale, TERM and the variables claude itself needs) with every STRIP_ENV secret removed; `gh` relies only on its own stored auth, and no token variables are passed through. A test asserts STRIP_ENV names are absent from the spawned env | Permissions remain the control; confirmation is the guard against forged action blocks, and the environment allowlist replaces the removed deny list as secret protection |
| D-5 | Builds: agent ends its reply with one fenced `uncle_action` JSON block; app parses with `home_actions.parse_reply` and executes via `_home_action`. Parsing rule (shared with D-6): only a fenced block at the end of the agent's own final assistant text is parsed; tool output, tool results and quoted repo/issue/web text are never parsed. More than one `uncle_action` block in a reply executes none of that kind and posts a system note; malformed JSON is ignored with a note. Every agent-emitted `uncle_action` is shown to the user and executes only after explicit user confirmation; an unconfirmed or declined action is discarded. When a reply has both `uncle_cwd` and `uncle_action`, `uncle_cwd` is validated and applied first and the action then runs against the new root; an invalid cwd cancels the action. I-2 is enforced by the build drivers (`uncle`, `*workflow.sh`, `from-issue.sh`) refusing to start unless launched through the app action path, which sets an app-issued marker (env var carrying a per-app-process random token, never exposed to the agent subprocess, which is spawned with that variable stripped). The agent argv also adds `--disallowedTools` for `Bash(uncle:*)`, `Bash(*workflow.sh:*)`, `Bash(*from-issue.sh:*)`; these name-prefix rules are advisory defense in depth only (bypassable via bash -c, absolute paths, wrappers, subprocesses) and are not the control, so I-2 is verified for the listed entry points and the residual risk is recorded in IMPLEMENTATION_NOTES. Deny rules always win over `--allowedTools` grants, including approved D-1 grants | I-2; the driver-side marker check is the enforcement point and argv deny rules are best-effort defense in depth; user confirmation and last-block-only parsing prevent injected content from forging a build action; AR-009: with uncle_cwd present, the action executes only after the cwd is applied (see D-6) |
| D-6 | cwd: agent ends a reply with at most one fenced `uncle_cwd` JSON block `{"path": "/abs"}` after a real successful `cd`/clone. More than one `uncle_cwd` block, or malformed JSON, executes none of that kind and posts a system note. The app requires an absolute path, resolves it with `os.path.realpath` (symlinks resolved), and requires `os.path.isdir` on the resolved path. The resolved path must not be `/` or the user's `$HOME`. A resolved path that was not created or cloned during this session needs explicit user confirmation before it is applied. Only after validation does the app set `UNCLE_PROJECT_ROOT` via the existing `_follow_project_root` logic and respawn the session with that cwd plus a short handoff of recent turns. A rejected path is ignored with a system note. Ordering with `uncle_action` follows the D-5 block rule: if a reply contains both blocks, `uncle_cwd` is validated and applied first, then `uncle_action` executes against the new root; an invalid or rejected `uncle_cwd` cancels the `uncle_action` in the same reply. | Session cwd fixed at spawn; I-6. Realpath resolution defeats symlink escapes; the / and $HOME exclusions and confirmation limit the blast radius of an injected or mistaken path. AR-009 ordering: cwd is applied before the action, and an invalid or rejected cwd cancels the action and posts one system note, so a build never runs against the old root. |
| D-7 | Lifecycle: one persistent session while idle; re-created lazily (cwd = current root) when a build ends. Build or recovery start first cancels any in-flight agent turn, discards its output and any pending D-1 approval with one system note, and confirms the session process is dead before the build process spawns (build start is deferred until that confirmation). Each session carries a generation id; any reply, `uncle_action`/`uncle_cwd` block or approval arriving from a closed, cancelled or superseded session is discarded and never executed, and later approvals for the discarded prompt are ignored. Messages arriving during the close or re-create window go to the tool-free supervisor. | I-3; AR-008, AR-023: no late output from a closed session may act |
| D-8 | Cost: per-turn deadline kept (env renamed `UNCLE_HOME_AGENT_TIMEOUT`, default 900); existing supervision cost settings untouched | Minimal |
| D-9 | Legacy keys/env: no code reads them; deprecated no-op env vars `UNCLE_HOUSEKEEPING_UNATTENDED` handling dropped from mode.sh/launcher; the migration doc keeps one note. The only files allowed to mention housekeeping are exactly: `docs/UNATTENDED_DEFAULT_MIGRATION.md`, `scripts/tests/no-housekeeping-test.py` (which allowlists exactly these four files), `scripts/tests/launcher-removed-flag-test.sh` and `scripts/tests/tui-home-agent-test.py` (legacy `housekeeping.*` config fixtures for AC-9) | I-1 |
| D-10 | `housekeeping_input.py` stdin helper, used by `--application` (uncle:210), is renamed `startup_text_input.py` (same behavior); its test renamed `startup-text-input-test.py`. Before the old `housekeeping-input-test.py` is deleted, it is run once against the renamed module with only its import renamed, and must pass unchanged otherwise (baseline-equivalent regression evidence, recorded in IMPLEMENTATION_NOTES) | Preserve `--application` stdin |

## 2. Alternatives considered
| Alt | Rejected because |
|---|---|
| Keep tool-free supervisor and add more actions (clone, mkdir) | Cannot cover arbitrary requests |
| `bypassPermissions` or broad `--allowedTools Bash` | Violates I-5 |
| MCP `--permission-prompt-tool` | New server surface; D-1 meets need |

## 3. Why preferred
Smallest change reusing the existing persistent-session class, action path and root-following.

## 4. Exact components to modify
See change-impact table.

## 5. Not to modify

Build driver behavior, gates, `home_actions.py` schema, `supervisor_runner.py`, `supervise-chat.md`, FINAL_AUDIT.md and other reviewer artifacts. The sole exception is the I-2 app-issued marker refusal check (D-5, step 2), which may touch only the driver entry-point preamble needed to refuse a start without the marker; it changes no other driver behavior.

## 6-7. Data flow and state

Idle message -> agent session -> stream reply -> TUI parses trailing `uncle_action`/`uncle_cwd` blocks -> app validates and executes. State `home_mode` removed; idle predicate becomes: no running build, no recovery, no pending proposal, no pending tool approval (D-1), runner claude, and no session close/re-create in progress. Idle is evaluated exactly once, at send time. A message sent while the session is closing or being re-created, or after a build start has begun, is routed to the tool-free `_supervisor_turn`, never to the agent. While a D-1 tool approval is pending, only the explicit approve/decline responses are handled as approve or decline; any other user message is treated as a decline: the denial prompt is cleared with a note, the denied tool is not granted and nothing is re-sent, and then that message is routed under the idle predicate as usual. Cancel-then-close happens before any spawn. Each agent turn carries a session generation token; a result whose generation is not the current live session is discarded.

## 8. Interfaces
Removed: `--housekeeping`, `/housekeeping`, `/mode`, `UNCLE_STARTUP_ACTION=housekeeping`. Added: none public.

## 10. Compatibility

Old config keys and env ignored (D-9). The agent subprocess environment is allowlisted with STRIP_ENV secrets removed (D-4), so legacy env vars carrying secrets are not inherited.

## 11. Concurrency

Build or recovery start cancels any in-flight agent turn, discards its output and pending approvals, posts one note, and closes the session and confirms it dead before spawning the build process (D-7). Results, trailing action/cwd blocks or approvals from a closed session (stale generation id) are discarded and never parsed or executed; later approvals are ignored. Idle is evaluated once at send time; messages arriving in the closing/re-creating window go to the tool-free supervisor. One in-flight turn is also guarded by the existing `home_request` check.

## 12. Error and recovery

Session death: restart on next message. Denied tool: pending approval prompt (D-1); decline posts a note with no re-send; messages typed during a pending approval are queued; a repeat denial after approval ends the turn with an error note. Bad cwd block: ignored with a system note. Missing claude: fallback note (D-3).

Pending-approval interaction: a pending approval is discarded with a note when a new user message arrives, a build starts, or the session restarts; an approval is honored only while its originating session state is current, and never re-sends a message from a prior session state.

## 14. Rollback plan
Revert the change set; no persisted formats change; `.uncle/config` is untouched.

## Change-impact table
| Component | Planned change | Reason | Regression risk | Test coverage |
|---|---|---|---|---|
| `scripts/housekeeping-workflow.sh`, `scripts/lib/housekeeping_config.py`, `housekeeping_policy.py`, `housekeeping_session.py`, `prompts/housekeeping-plan.md` | Delete | Remove feature | Low | no-housekeeping-test |
| `scripts/lib/housekeeping_input.py` | Rename to `startup_text_input.py` | Shared with `--application` | Medium | startup-text-input-test |
| `uncle` | Remove flag, usage, exclusivity entries, did-you-mean entry, Configure item, menu function; use renamed helper | S-7, S-9 | Medium | launcher tests |
| `scripts/lib/mode.sh`, `run_duties.py`, `uncle_headless.py` | Drop housekeeping entries | I-1 | Low | mode-resolution, run-duties, headless tests |
| `scripts/lib/home_agent_session.py` (new), `prompts/home-agent.md` (new) | Tool agent session and prompt | S-1..S-3, S-11 | Medium | home-agent-session-test |
| `uncle_tui.py` | Remove housekeeping code, `/mode`, config section; route idle chat to agent; action/cwd parsing; lifecycle | Core | High | tui-home-agent-test, existing TUI tests |
| `README.md`, `docs/quickstart.md`, `docs/UNATTENDED_DEFAULT_MIGRATION.md` | Remove housekeeping text; add home-chat agent section; one legacy-key migration note | I-1 | Low | no-housekeeping-test |
| Tests with housekeeping mentions (nine files) | Remove or rewrite those assertions | Requirement-mandated | Low | self |
| 5 housekeeping test files and `tui-housekeeping-test.py` | Delete | Feature removed | Low | n/a |

## Traceability

| Requirement | Behavior | Invariant | Component | Automated test | Manual check |
|---|---|---|---|---|---|
| AC-1 | S-7 | I-1 | uncle | launcher-removed-flag-test.sh | M-1 |
| AC-2 | S-8, S-9 | I-1 | uncle_tui.py | tui-home-agent-test.py | M-1 |
| AC-3: no housekeeping mention anywhere in the repo except an allowlist of exactly four files: docs/UNATTENDED_DEFAULT_MIGRATION.md, scripts/tests/no-housekeeping-test.py, scripts/tests/launcher-removed-flag-test.sh and scripts/tests/tui-home-agent-test.py (the legacy-config test file). | all removals | I-1 | repo | no-housekeeping-test.py (allowlists exactly the four files, itself included: docs/UNATTENDED_DEFAULT_MIGRATION.md, no-housekeeping-test.py, launcher-removed-flag-test.sh, tui-home-agent-test.py only) | none |
| AC-4 | S-1, S-11 | I-4, I-5 | home_agent_session.py | home-agent-session-test.py | M-2 |
| AC-5 | S-2, S-3 | I-6 | uncle_tui.py | tui-home-agent-test.py (incl. duplicate blocks execute none, cwd-before-action ordering, reply with both uncle_cwd and uncle_action: action runs against the new root, invalid cwd cancels the action, malformed block ignored, cwd validation: relative path rejected, symlink resolved via realpath, `/` rejected, `$HOME` rejected, unconfirmed pre-existing path rejected) | M-2 |
| AC-6: builds started by the app come only via the validated action path; the agent argv denies the listed driver entry points (best-effort, verified only for those entry points); residual bypass risk is recorded in IMPLEMENTATION_NOTES. | S-4, S-5, S-13 | I-2 | uncle_tui.py, uncle, scripts/*workflow.sh, scripts/from-issue.sh | home-actions-test.py, launcher-removed-flag-test.sh, driver-marker-test.sh (drivers refuse to start without the app-issued marker, including via bash -c, absolute path and wrapper invocation; accept with it) | M-3 |
| AC-7 | S-6 | I-3 | uncle_tui.py | tui-home-agent-test.py (+ defect injection): send during close/re-create window routes to tool-free supervisor; no agent process alive when build spawns | none |
| AC-8 | S-11, S-12 | I-5 | home_agent_session.py | home-agent-session-test.py (argv has no bypass flag; an approved grant is the exact denied string verbatim: no wildcard, no bare tool name, glob/pattern characters escaped, absent after session close; every --disallowedTools entry remains present after any approval and a grant matching a deny pattern is refused), headless tests | M-2 |
| AC-9: legacy housekeeping.* config keys and env are ignored; their fixtures live only in tui-home-agent-test.py, an allowlisted file under AC-3 (allowlist: migration doc, no-housekeeping-test.py, launcher-removed-flag-test.sh, tui-home-agent-test.py). | S-10 | none | config | tui-home-agent-test.py (legacy housekeeping.* fixtures; file is on the AC-3 allowlist) | none |

## Automated-test strategy

Commands: the two baseline commands only. New tests: `launcher-removed-flag-test.sh`, `home-agent-session-test.py` (argv has no bypass, driver denies, denial surfaced), `tui-home-agent-test.py` (idle routing, cwd, I-3, S-8/S-9/S-10, legacy housekeeping.* config keys ignored), `no-housekeeping-test.py`. The housekeeping-mention allowlist is exactly: `docs/UNATTENDED_DEFAULT_MIGRATION.md`, `no-housekeeping-test.py`, `launcher-removed-flag-test.sh` and `tui-home-agent-test.py`; `no-housekeeping-test.py` enforces it and no other file may mention housekeeping. Fake runner via `WORKFLOW_CLAUDE_CMD` for turn flow only. The `permission_denials` fixture is never hand-written: it is copied verbatim from a recorded real `claude -p --output-format stream-json` result event (captured with a logged-in Claude on a command that default mode denies), stored as `scripts/tests/fixtures/claude-permission-denial.jsonl` with the capture date and claude version in a header comment file, and `home-agent-session-test.py` parses that file through the production denial parser. If a real recording cannot be captured, the denial-parsing test is reported NOT RUN and the plan's raw-denial-text fallback is used, never a synthetic format. Defect injection for I-3 and I-5 recorded in test docstrings and run once. Python tests named `<name>-test.py`.

- tui-home-agent-test.py: build starts mid-turn with a pending approval -> turn cancelled, approval discarded, session closed (confirmed dead), late approval ignored; a reply with an uncle_action arriving after session close never calls _home_action (included in I-3 defect injection)
- tui-home-agent-test.py: message sent during session close/re-create window routes to the tool-free _supervisor_turn
- tui-home-agent-test.py: approval flow: decline posts a note with no re-send and (per D-1) no grant; a non-approve message during a pending approval clears the prompt as a decline before routing; pending approval discarded on new message, build start or restart and never re-sends a prior-state message; always-deny runner yields exactly one re-send per user message and a new prompt or error note on the second denial; grant cleared on build start
- tui-home-agent-test.py / home-actions-test.py parse tests: duplicate blocks of one kind execute none of that kind; both block types in one reply apply cwd first and the action targets the new root; invalid cwd cancels the action; malformed JSON ignored with a note; an uncle_action inside tool_result output or non-final text is not parsed; agent-emitted action needs explicit user confirmation and is discarded if declined
- tui-home-agent-test.py: uncle_cwd validation rejects relative paths, `/`, `$HOME` and symlinks resolving to them (realpath first), requires confirmation for a path not created or cloned this session
- home-agent-session-test.py: argv after approval contains exactly Bash(<verbatim cmd>) with no wildcard or bare Bash and still contains every --disallowedTools entry; spawned env contains no STRIP_ENV name
- Step 8 closing check: IMPLEMENTATION_NOTES.md records the residual I-2 risk (deny patterns bypassable; I-2 verified only for the listed entry points and the driver marker check)

## Regression-test strategy
Golden transcripts for 'build issue 34' and hello-world captured from current behavior before deleting code (step 3 records them into `home-actions-test.py`). Test edits to existing files only remove housekeeping assertions: protected-path changes are mandated by the request; reviewers should check no non-housekeeping assertion is weakened.

## Manual-verification strategy
M-1 launcher rejects flag, menus clean. M-2 from an empty dir ask: fork a repo, clone it, build an issue; approval prompt appears for a command. M-3 hello-world C program request. Live checks need a logged-in Claude and `gh`; absence does not block coding.

## Restrictions

| ID | Source | Reqs | Property | Mechanism | CAP | Feasibility evidence | Phase |
|---|---|---|---|---|---|---|---|
| R-1 | USER (CHANGE_REQUEST I-5) | AC-8 | No bypass flags | argv builder plus test | CAP-CLAUDE-CLI | build_command pattern at housekeeping_session.py:58 | CODING |
| R-2 | USER (I-3) | AC-7 | Tool-free during build | existing supervisor_command path | CAP-FAKE-RUNNER | uncle_tui.py:3467 | CODING |
| R-3 | USER (I-2) | AC-6 | Builds start only via the app action path (enforced in drivers); deny patterns best-effort, verified only for listed entry points, residual risk recorded in IMPLEMENTATION_NOTES | parse_home_action plus driver-side refusal to start a build without the app-issued marker; argv deny rules advisory only (best-effort, verified only for listed entry points) | CAP-FAKE-RUNNER | uncle_tui.py:4034 | CODING |
| R-4 | REPOSITORY | AC-1 | Mutual exclusion and stdin rules | keep launcher logic | none | uncle:172-283 | CODING |

## Implementation sequence

1. Record golden transcripts: extend `scripts/tests/home-actions-test.py` with current 'build issue 34' and hello-world mappings (before any deletion).
   Owns: `scripts/tests/home-actions-test.py`
2. Rename stdin helper and update launcher: `git mv` `scripts/lib/housekeeping_input.py` to `scripts/lib/startup_text_input.py`; edit `uncle` (flag, usage, exclusivity, did-you-mean, Configure menu, noui message, env). Add the I-2 app-issued marker check to the launcher/driver entry points (refuse to start a build when the marker is absent or invalid, unless started by a human via the normal CLI path) and add `driver-marker-test.sh`; record the residual risk in IMPLEMENTATION_NOTES. Then, before step 6 deletes it, run the old `scripts/tests/housekeeping-input-test.py` against the renamed module with only its import renamed (temporary, not committed as a change to its assertions) and record the passing result in IMPLEMENTATION_NOTES.
   Owns: `uncle`, `scripts/lib/startup_text_input.py`, `scripts/lib/housekeeping_input.py`, `scripts/tests/housekeeping-input-test.py`, `scripts/tests/driver-marker-test.sh`
   Depends on: 1
3. Remove housekeeping from libs: delete `scripts/housekeeping-workflow.sh`, `scripts/lib/housekeeping_config.py`, `scripts/lib/housekeeping_policy.py`; edit `mode.sh`, `run_duties.py`, `uncle_headless.py`.
   Owns: `scripts/housekeeping-workflow.sh`, `scripts/lib/housekeeping_config.py`, `scripts/lib/housekeeping_policy.py`, `scripts/lib/mode.sh`, `scripts/lib/run_duties.py`, `scripts/lib/uncle_headless.py`
   Depends on: 1
4. New agent session and prompt (independent of steps 2-3): `scripts/lib/home_agent_session.py`, `prompts/home-agent.md`, `scripts/tests/home-agent-session-test.py`.
   Owns: `scripts/lib/home_agent_session.py`, `prompts/home-agent.md`, `scripts/tests/home-agent-session-test.py`
5. TUI rewrite: remove housekeeping code and `/mode`, config section, startup action; route idle chat to the agent; trailing-block parsing; cwd validation and respawn; lifecycle. Also delete `scripts/lib/housekeeping_session.py` and `prompts/housekeeping-plan.md` (imports go away here).
   Owns: `uncle_tui.py`, `scripts/lib/housekeeping_session.py`, `prompts/housekeeping-plan.md`, `scripts/tests/tui-home-agent-test.py`
   Depends on: 3, 4
6. Tests cleanup: delete `scripts/tests/housekeeping-input-test.py`, `housekeeping-launcher-test.sh`, `housekeeping-policy-test.py`, `housekeeping-session-test.py`, `housekeeping-workflow-test.sh`, `tui-housekeeping-test.py`; add `startup-text-input-test.py`, `launcher-removed-flag-test.sh`, `no-housekeeping-test.py`; strip housekeeping from `run-duties-test.py`, `mode-resolution-test.sh`, `launcher-stdin-text-test.sh`, `supervisor-chat-test.py`, `headless-run-test.py`, `home-chat-test.py`, `launcher-noui-test.sh`, `chat-test.py`. The only files that may still mention housekeeping are exactly: docs/UNATTENDED_DEFAULT_MIGRATION.md, `no-housekeeping-test.py`, `launcher-removed-flag-test.sh` and `tui-home-agent-test.py`; `no-housekeeping-test.py` enforces this allowlist. Legacy `housekeeping.*` config fixtures go only in `tui-home-agent-test.py`.
   Owns: `scripts/tests/housekeeping-input-test.py`, `scripts/tests/housekeeping-launcher-test.sh`, `scripts/tests/housekeeping-policy-test.py`, `scripts/tests/housekeeping-session-test.py`, `scripts/tests/housekeeping-workflow-test.sh`, `scripts/tests/tui-housekeeping-test.py`, `scripts/tests/startup-text-input-test.py`, `scripts/tests/launcher-removed-flag-test.sh`, `scripts/tests/no-housekeeping-test.py`, `scripts/tests/run-duties-test.py`, `scripts/tests/mode-resolution-test.sh`, `scripts/tests/launcher-stdin-text-test.sh`, `scripts/tests/supervisor-chat-test.py`, `scripts/tests/headless-run-test.py`, `scripts/tests/home-chat-test.py`, `scripts/tests/launcher-noui-test.sh`, `scripts/tests/chat-test.py`, `scripts/tests/tui-home-agent-test.py`
   Depends on: 2, 3, 5
7. Docs: remove housekeeping from `README.md`, `docs/quickstart.md`; keep one migration note in `docs/UNATTENDED_DEFAULT_MIGRATION.md`; document home-chat agent in README.
   Owns: `README.md`, `docs/quickstart.md`, `docs/UNATTENDED_DEFAULT_MIGRATION.md`
   Depends on: 5
8. Final grep for housekeeping (allowlist per AC-3), reconcile; record deviations in `.uncle/docs/IMPLEMENTATION_NOTES.md`, including the residual I-2 risk (argv deny patterns are bypassable; I-2 verified only for listed entry points and the marker check) and the old housekeeping-input-test result against the renamed module.
   
   Steps 2, 3, 4 are independent (no shared files) and can run in parallel.
   Owns: `.uncle/docs/IMPLEMENTATION_NOTES.md`
   Depends on: 6, 7

## Scope cuts under time pressure

Cut first: D-6 session respawn handoff (just respawn without history), then README agent section, then D-1 auto-resend after approval (user re-types). Never cut: removal, I-1, I-2 (including the driver-side marker check), I-3, I-5.

## Risks and unresolved questions
| Risk | Mitigation |
|---|---|
| Claude `-p` denial format differs from assumption | Fixture-based session test; live manual check M-2; fall back to showing raw denial text |
| TUI edit breaks unrelated paths | Run Python suite after step 5; touch only housekeeping and idle routing |
| Agent forgets trailing blocks | Prompt plus app never assumes success without a validated block |
| Existing test with non-housekeeping meaning edited | Reviewer inspects step 6 diff |

No blocking planning decisions.

## Adversarial review dispositions

| Finding | Disposition | Reason | Exact plan change |
|---|---|---|---|
| AR-001 | Accepted | Plan was silent on a build or recovery starting while an agent turn or approval is pending; I-3 needs it defined. | Extended D-7 and Concurrency (s10.1): build/recovery start cancels the in-flight turn, discards pending approvals, posts one note, ignores later approvals. |
| AR-002 | Accepted | The busy/idle boundary during session close and re-creation was undefined; evaluating idle once at send time and confirming session death before build spawn closes it. | Edit s7.1, D-7, s10.1 and AC-7 to define send-time idle evaluation, session-dead-before-spawn, and tool-free routing in the window. |
| AR-003 | Accepted | D-1 left grant scope, decline, respawn persistence and multiple denials undefined; these are real gaps in the approval flow. | D-1 now defines exact-input grant, session-only lifetime cleared on build start, decline refusal, and one denial prompt at a time. |
| AR-004 | Accepted | D-5 says 'one' block and D-6 'a' block with no rule for duplicates, combined replies, or ordering; this is a real gap that threatens S-3. | D-5 and D-6 gain a shared block-parsing rule (duplicates execute none, cwd before action, invalid cwd cancels action); AC-5 tests it. |
| AR-005 | Accepted | Name-pattern deny rules are bypassable, so the plan must not claim they enforce I-2 beyond the listed entry points. | D-5 reworded as best-effort; AC-6 and R-3 scoped to listed entry points; residual risk recorded in IMPLEMENTATION_NOTES. |
| AR-006 | Accepted | AC-3 forbids housekeeping mentions but AC-9 needs legacy housekeeping.* config fixtures, so the allowlist must be explicit and include the legacy-config test file. | Add an exact allowlist to s15.1 and AC-3/AC-9, and name tui-home-agent-test.py as the legacy-config test file in step-6. |
| AR-007 | Accepted | A pending tool approval is a real pending state the idle predicate and message handling did not cover. | Section 6-7 idle predicate now includes pending approval; new text sets non-approve/decline messages as decline before routing. |
| AR-008 | Accepted | D-7 and s10.1 did not define in-flight turns, pending approvals, or late trailing blocks at build start; this is a real gap. | Extend D-7 and s10.1 so build start cancels the in-flight turn, discards output and approvals, and never executes blocks from a closed session. |
| AR-009 | Accepted | A reply with both blocks (clone then build) is the S-3 regression risk and ordering was unspecified. | D-5 and D-6 state cwd-first ordering and cancel-on-invalid-cwd; AC-5 test and s2 rule added. |
| AR-010 | Accepted | Unbounded restart-and-resend could double side effects or loop on repeated denials; a once-per-message bound is cheap and safe. | D-1 now bounds re-send to once per user message, with a second denial shown as a new prompt and no auto-retry. |
| AR-011 | Accepted | The preserved --application stdin path needs baseline-equivalent evidence before the old test is deleted. | Step 2 runs the old housekeeping-input-test.py against the renamed module (import-only edit) before step 6 deletes it; D-10 states this. |
| AR-012 | Accepted | AC-3 and AC-9 conflict unless the files allowed to mention housekeeping are fixed; the finding's allowlist is adopted. | AC-3 and AC-9 rows, s15.1 and step 6 name the exact allowlist: migration doc, no-housekeeping-test.py, launcher-removed-flag-test.sh, tui-home-agent-test.py. |
| AR-013 | Accepted | D-1 left 'exact' undefined; defining the grant as a verbatim exact-match rule scoped to the session closes the wildcard gap. | D-1 now defines the grant (verbatim Bash(<cmd>), no wildcard, session-only, full command shown); AC-8 and s15.1 add a test for it. |
| AR-014 | Accepted | Prefix deny rules are bypassable (bash -c, absolute paths, wrappers), so I-2 needs enforcement in the drivers; argv rules become advisory. | Rewrote D-5, R-3 and AC-6 so drivers refuse to start without an app-issued marker; argv deny rules advisory; added step-2 launcher work and tests. |
| AR-015 | Accepted | Parsing free-form agent text lets injected content forge a build action, so confirmation and last-block-only parsing of the agent's own final text are needed. | Edited D-4 and D-5 to require user confirmation of every agent-emitted uncle_action and to parse only the last fenced block of the final assistant text, never tool output. |
| AR-016 | Accepted | isdir on a raw absolute path allows symlinks, '/', $HOME and arbitrary directories as the session root; tighter validation is cheap and protects I-6. | D-6 now requires realpath resolution, rejection of / and $HOME, and user confirmation for paths not created/cloned this session; AC-5 requirement updated. |
| AR-017 | Accepted | Removing the deny list leaves the agent's Bash environment undefined, so an explicit allowlisted environment with STRIP_ENV secrets removed is needed. | D-4 now specifies the agent subprocess environment (allowlist, STRIP_ENV removed, gh uses stored auth); s9.1 notes the environment on compatibility. |
| AR-018 | Accepted | Interaction of pending approval, new message, build start and restart was unspecified; a single discard rule resolves it. | D-1 and D-7 extended; s11 error section gains a block stating discard-with-note and no cross-session re-send. |
| AR-019 | Accepted | D-1 only described the approve path; decline, repeat denial and typing during a pending approval were unspecified. | Added decline/queue/repeat-denial rules to D-1 and the s11 error section. |
| AR-020 | Accepted | A fixture invented by us could make the session test pass against a nonexistent denial format. | Automated-test strategy (s15.1): denial fixture is a recorded real claude -p stream-json result that the session test parses. |
| AR-021 | Accepted | Grant scope and allow/deny precedence were unstated; D-1 and D-5 can conflict without a rule. | D-1 states exact-string grants only; D-5 states --disallowedTools always wins; AC-8 adds a test asserting both. |
| AR-022 | Accepted | Multi-block, mixed-block, malformed JSON and path-resolution behavior was unspecified and is a real gap. | D-5 and D-6 now state last-block-wins parsing, cwd-before-action ordering, ignore-with-note on malformed/duplicate blocks, and realpath before isdir. |
| AR-023 | Accepted | Lifecycle races between build start and in-flight agent turns were unspecified; I-3 requires the session be gone before a build runs. | Edited D-7, s7.1 and s10.1 to define cancel-then-close before spawn, discard of late results, and idle evaluated once at send time. |
| AR-024 | Accepted | AC-3 forbids housekeeping mentions yet D-9/AC-9 need legacy-key fixtures; an explicit allowlist resolves the conflict. | Edit D-9, AC-3, AC-9 and step-6 to state the exact allowlist: migration doc, no-housekeeping-test.py, launcher-removed-flag-test.sh, tui-home-agent-test.py. |
