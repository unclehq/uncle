# Change Request

Issue 81

Seeded from [unclehq/uncle#81](https://github.com/unclehq/uncle/issues/81).

## Change Type

Feature | Bug Fix | Prototype | Refactor | Performance | Security | Upgrade

## Summary

Add tooltips to each option in the Supervision configuration menu

## Motivation

## Summary

Add tooltips to each option in the Supervision configuration menu (Configure → Supervision in `uncle_tui.py`) so every setting explains what it does without requiring the user to consult `.uncle/config.example` or the README.

## Current state

- The menu lists the 12 typed controls from `supervision_lib.CONTROLS` (`scripts/lib/supervisor.py:44`): `enabled`, `runner`, `model`, `effort`, `max_interventions`, `steering_timeout_seconds`, `stage_time_seconds`, `stage_tokens`, `call_timeout_seconds`, `max_calls_per_run`, `call_max_cost_usd`, `delegate_gates`.
- Rows are rendered by `_supervision_items()` (`uncle_tui.py:3477`) as plain `key  value` text with no inline hint.
- Per-option descriptions already exist in `SUPERVISION_DESC` (`uncle_tui.py:670`), but they are shown only for the **highlighted** option, in the side panel / bottom strip drawn by `_draw_config_desc()` (`uncle_tui.py:5450`).
- The value pickers opened when editing an option (effort → low/medium/high/custom, runner, model, delegate_gates → none/routine) present bare choices with no explanation of what each choice implies (see `_picker_rows()`, `uncle_tui.py:1231`).

## Proposal

- Show a tooltip/hint for every option in the Supervision menu, not just the highlighted row — e.g. a short inline hint per row, or an expanded panel — so users can compare settings at a glance.
- Extend tooltips into the value pickers so each choice (e.g. `delegate_gates` none vs routine, effort low/medium/high) explains its effect before it is selected.
- Reuse/extend `SUPERVISION_DESC` as the single source of tooltip text so menu rows and picker choices stay consistent; keep text in sync with `.uncle/config.example` and README (AT-9 already checks the control key list against `CONTROLS`).

## Acceptance criteria

- [ ] Every option in the Supervision configuration menu has a visible tooltip/hint without needing to read external docs.
- [ ] Each choice in the option value pickers carries a short explanation.
- [ ] Tooltip text covers all keys in `supervision_lib.CONTROLS` and degrades gracefully on narrow terminals (existing `_draw_config_desc` fallback behavior).

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
