# Change Request

Issue 185

Seeded from [unclehq/uncle#185](https://github.com/unclehq/uncle/issues/185).

## Change Type

Feature | Bug Fix | Prototype | Refactor | Performance | Security | Upgrade

## Summary

Set the default model list for the Claude runner to the Claude models Uncle currently sees

## Motivation

## Summary
Make the default models available to the Claude runner the Claude models from the current Claude model list, so the picker and the runner defaults agree.

## Current state
`uncle_tui.py` `MODEL_CATALOG_CLAUDE` (line ~443) offers:
- Claude Opus 5 (`claude-opus-5`)
- Claude Sonnet 5 (`claude-sonnet-5`)
- Claude Haiku 4.5 (`claude-haiku-4-5`)

Related defaults:
- `DEFAULT_MODEL_FOR_RUNNER["claude"]` = `claude-sonnet-5` (`uncle_tui.py`)
- `scripts/stagegate.sh` `DEFAULT_MODEL="claude-sonnet-5"`
- `scripts/reviewer-claude.sh` `DEFAULT_MODEL` = `claude-sonnet-5`
- The comment above `DEFAULT_MODEL_FOR_RUNNER` still says the default is the "opus" tier alias, which no longer matches the code.

## Desired behavior
The default model list for the Claude runner is exactly these models (id, label), in this order:

| id | label |
|---|---|
| `claude-haiku-5-5` | Claude Haiku 5.5 |
| `claude-sonnet-5-5` | Claude Sonnet 5.5 |
| `claude-opus-5-5` | Claude Opus 5.5 |
| `claude-fable-5-1` | Claude Fable 5.1 |
| `claude-fable-5` | Claude Fable 5 |
| `claude-opus-4-8` | Claude Opus 4.8 |
| `claude-opus-4-7` | Claude Opus 4.7 |
| `claude-sonnet-4-6` | Claude Sonnet 4.6 |
| `claude-opus-4-6` | Claude Opus 4.6 |
| `claude-opus-4-5-20251101` | Claude Opus 4.5 |
| `claude-haiku-4-5-20251001` | Claude Haiku 4.5 |
| `claude-sonnet-4-5-20250929` | Claude Sonnet 4.5 |

- The default model shown by the picker, `stagegate.sh`, and `reviewer-claude.sh` is the same single value: `claude-sonnet-5-5` (replaces `claude-sonnet-5`).
- Every id in the list passes `reviewer-claude.sh`'s allowlist (`claude*|opus*|sonnet*|haiku*`).

## Acceptance criteria
- Picker for the Claude runner lists exactly the models in the table above and no others by default.
- The default for a stage with no stored model is identical in the TUI and the shell drivers (`claude-sonnet-5-5`).
- The stale "opus" comment is corrected.
- Existing tests pass; add a test that the shell and TUI defaults agree, and that every catalog id passes the `reviewer-claude.sh` allowlist.

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
