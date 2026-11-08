# Change Request

Issue 188

Seeded from [unclehq/uncle#188](https://github.com/unclehq/uncle/issues/188).

## Change Type

Feature | Bug Fix | Prototype | Refactor | Performance | Security | Upgrade

## Summary

Preload the home agent in the background when the UI starts (not under --noui)

## Motivation

## Summary
Start and warm the home agent in the background when the full-screen UI starts, so the operator's first homepage message does not pay for process start, the lazy connection, and first-time project exploration.

## Observed current behavior
- `uncle_tui.py:8848` starts `_warm_supervisor` on a thread at startup. That warms the old supervisor chat session (`_supervisor_session()` then `prime()`), not the home agent.
- The home agent is created lazily by `_home_agent_session()` (`uncle_tui.py:3604`), first called from `_agent_turn` (`uncle_tui.py:3679`) when the operator sends a message. The first message pays process start plus the lazy connection (documented in `SupervisorSession.prime()` as roughly 2s cold against 1.4s primed).
- In a recent session log (`home-agent-chat-1.jsonl`), the first question took about 25s: six model turns of Grep/Read exploration. The follow-up took about 6.6s with no tool calls, because context carried over.

## Desired behavior
1. When the UI is displayed, start the home agent in a background thread at startup and `prime()` it, so it is ready before the operator types.
2. Preload useful project context in the same background step so the first real question does not re-explore the project. Candidate content: git branch/status, worktrees, open issues, and a listing of key files. Exact content is for the plan to decide.
3. The preload must not block or visibly slow UI start-up, redraw, or input. The operator should not notice it.
4. Preload only when the UI is displayed. Under `--noui` / `UNCLE_NOUI=1` there is no interactive prompt, so do not start or preload a home agent.

## Constraints
- Respect the existing `UNCLE_HOME_AGENT=0` opt-out and the non-`claude` runner fallback in `_home_agent_session()`.
- Preload turns must be marked as application-sent, not from the operator, and must authorize nothing (as `prime()` already does). Repository and issue text read during preload is data, not instruction.
- Preload must not use ungranted tools. Only the read-only base tools plus existing session grants.
- Preload must be discarded or cancelled cleanly when a build starts (`_agent_quiesce`), when the project root changes, and on exit. No leaked process.
- If the operator sends a message while preload is still running, the message must queue behind it (one turn at a time) or cancel it, never interleave on the agent's stdin.
- Preloaded state can go stale. Decide how the agent is told to re-check before acting on it (for example a short note in the preload turn).
- Warm-up failure must be silent and fall back to the current lazy start.

## Out of scope
- Changing the restart handoff (`_agent_handoff_text`).
- Changing the system prompt's "inspect first" rule, unless the plan finds it is needed.

## Success criteria
- With the UI shown, `ps` shows the home agent process shortly after start, before any message is sent.
- Time to first text for the first homepage message is no worse than for later messages.
- A first question about branches or issues is answered without repeating inspection that the preload already did.
- `uncle --noui ...` never starts a home agent.
- Startup frame time and keyboard responsiveness are unchanged.
- `UNCLE_HOME_AGENT=0` starts nothing.

## Observed Current Behavior

Describe what the system currently does.

## Desired Behavior

Describe what the system should do after the change.

## Reproduction

For a bug, provide exact steps to reproduce it.

For other change types, write "Not applicable."

## Constraints

List compatibility, security, performance, timing, or scope constraints.

## Known Relevant Files

List files or components if known.

## Out of Scope

List behavior or components that must not be changed.

## Success Criteria

Describe the observable evidence that proves the change works.
