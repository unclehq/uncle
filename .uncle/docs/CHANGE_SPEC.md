# Change spec: Supervision tooltips (Issue 81)

Omitted sections: Performance (negligible); Security (no new input/IO); Migration (none); Prototype isolation (not a prototype)

## 1. Change type
Feature (TUI usability).

## 2. Problem statement
Only the highlighted Supervision option explains itself; pickers show bare choices.

## 4. Desired behavior
Every Supervision row carries a short visible hint; every picker choice for supervision options (effort, delegate_gates, runner) carries a short explanation; text lives in uncle_tui.py beside `SUPERVISION_DESC` and covers every `supervision_lib.CONTROLS` key.

## 5. Observable behavior table
| ID | Class | Trigger | Current behavior | Expected behavior | Verification |
|---|---|---|---|---|---|
| SB-1 | ADD | Render Supervision menu on a wide terminal | Rows are `key value` only | Each row shows a short hint (<=40 chars) after the value, from a per-key hint source; rows still start with the key | AC-1, unit test on `_supervision_items` |
| SB-2 | PRESERVE | Highlight a row | Full description in side panel/strip | Unchanged, incl. narrow-terminal strip fallback | AC-3 |
| SB-3 | MODIFY | Open effort picker for supervision | Bare none/low/medium/high + Custom | Each value row is followed by a short explanation | AC-2 |
| SB-4 | MODIFY | Enter on `delegate_gates` | Free-text Custom row only | Picker lists `none` and `routine` each with explanation; selecting stores the same value `_set_field` stored before | AC-2 |
| SB-5 | MODIFY | Open runner picker for supervision | Bare runner names | Each runner row has a short explanation (generic text for any supported runner) | AC-2 |
| SB-6 | PRESERVE | Model picker, stage-config pickers, bool toggle, numeric edit, filter typing, Custom entry | As today | Unchanged | AC-4 |
| SB-7 | ADD | Narrow terminal | n/a | Inline hints omitted rather than truncating keys/values; draws never raise | AC-3 |

## 6. Invariant table
| ID | Status | Invariant | Scope | Enforcement point | Verification |
|---|---|---|---|---|---|
| SI-1 | NEW | Every key in `supervision_lib.CONTROLS` has non-empty hint text and description | uncle_tui.py | test comparing key sets | AC-5 |
| SI-2 | EXISTING | Value stored for a picker choice is identical to that of the typed value (validated by supervision_lib) | supervision config | existing `_set_field` path | AC-4 |
| SI-3 | EXISTING | Drawing swallows curses.error | draw funcs | try/except | AC-3 |
| SI-4 | EXISTING | AT-9 doc key list equals CONTROLS | docs | DocsTests | AC-5 |
No RELAXED or REMOVED invariants.

## 7. Compatibility
`.uncle/config` keys/values unchanged. Rows keep `key` prefix (supervisor-test.py:1214). Non-supervision pickers render unchanged.

## 8. Error behavior
Missing hint for a key renders no hint (no exception). Invalid config row `! reason` unchanged.

## 11-12. Migration/rollback
None / revert the commit; no persisted state.

## 14. Non-goals
Stage config menus, Configure other pages, model catalog descriptions, changing defaults or CONTROLS, mouse hover.

## 15. Assumptions
- 'Tooltip' means inline text, since curses has no hover.
- Hint text must stay consistent with `.uncle/config.example`/README; no doc edit unless drift is found.

## Acceptance criteria

| ID | Criterion | Verification |
|---|---|---|
| AC-1 | At a width of 120 columns, every row from `_supervision_items()` for all CONTROLS keys contains a non-empty hint after the value and still begins with its key. | New unit test iterating CONTROLS asserting hint presence and key prefix; existing :1214 assertion still passes. |
| AC-2 | The supervision effort, delegate_gates (none/routine) and runner pickers each show a non-empty explanation for every choice; selecting a delegate_gates choice stores 'none' or 'routine' via the existing set-field path. | Unit test on `_picker_rows`/draw output for each picker kind with a fake screen; test of selection result. |
| AC-3 | On narrow terminals the inline hints are dropped, the highlighted-option description still appears via the existing side-panel/strip logic, and drawing raises no exception at small sizes. | Unit test drawing with fake stdscr at widths 30, 60, 120; asserts no exception and description present. |
| AC-4 | Model pickers, stage-config pickers (effort/runner/network), bool toggle, custom entry and picker filtering behave as before. | Existing suites supervisor, supervisor-default-runner and shell suites pass; new test asserts non-supervision `_picker_rows` output equals prior values. |
| AC-5 | Hint and description text exist for every key in `supervision_lib.CONTROLS`, and AT-9 still passes. | New test comparing key sets; DocsTests in supervisor suite. |

