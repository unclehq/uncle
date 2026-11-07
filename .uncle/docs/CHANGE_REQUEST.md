# Change Request

## Change Type
Behavior change (TUI runner selection)

## Summary
When no runners are available, the runner choices should show only the Self hosted runner.

## Motivation
Self hosted needs no local CLI from the user's side (it is configured with an endpoint), so it should always be selectable. An empty runner list gives the operator nothing to choose.

## Observed Current Behavior
`runners_for(side)` in uncle_tui.py scans PATH for claude, codex, kimi and opencode, and lists self-hosted only if opencode is found. With none installed the list is empty, and `stage_runner` returns an empty string.

## Desired Behavior
When no runner is detected, the runner options and the default runner consist of only `self-hosted` (displayed as "Self hosted"). When other runners are detected, behavior is unchanged.

## Reproduction
Run uncle with a PATH containing none of claude, codex, kimi or opencode, open Configure, and look at the runner choices for any stage.

## Constraints
Preserve existing behavior whenever at least one runner is installed. Keep the diff minimal. Do not weaken existing tests.

## Known Relevant Files
- uncle_tui.py: `runners_for` (about line 690), `stage_runner` (about line 1211), runner option lists (about lines 1441-1464)

## Out of Scope
Changes to the self-hosted configuration flow, other runners, or unrelated cleanup.

## Success Criteria
- With no runners installed, the runner choices list only Self hosted.
- With no runners installed, the default runner for a stage is self-hosted.
- With one or more runners installed, the lists are unchanged.
- Existing tests pass, and a test covers the no-runners case.