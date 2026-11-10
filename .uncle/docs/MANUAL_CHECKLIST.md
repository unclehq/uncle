# Manual checklist

## Coverage

### MC-102
- Required for acceptance: YES
- Exclusive resources: none
- Depends on: none
- Exact action: Resize the terminal to 99, 100, 60 and 30 columns in turn while viewing Configure -> Supervision, moving the highlight between rows.
- Expected result: Inline hints are absent at 99 columns and below, present at 100; at 60 and 30 columns the highlighted row's description still appears (strip fallback) and nothing crashes or truncates keys or values.
- Evidence to capture: Captures at each width plus a note of any exception or garbled output.
- Actual result: 
- Status: NOT RUN

### MC-103
- Required for acceptance: YES
- Exclusive resources: none
- Depends on: none
- Exact action: At ~120 columns, press Enter on `effort`, then Esc; press Enter on `runner`, then Esc.
- Expected result: Each option row (none/low/medium/high; each runner) shows a '  - explanation'. The Custom and filter rows have no explanation, and Esc backs out leaving the stored value unchanged.
- Evidence to capture: Captures of the effort and runner pickers and the value before and after Esc.
- Actual result: 
- Status: NOT RUN

### MC-104
- Required for acceptance: YES
- Exclusive resources: none
- Depends on: none
- Exact action: Press Enter on `delegate_gates`, observe the picker, select `routine`, then reopen it and select `none`.
- Expected result: The picker lists only `none` and `routine`, each with an explanation, and has no Custom free-text row. The current value is marked, and each selection is stored and shown in the menu row.
- Evidence to capture: Picker capture and menu row value after each selection.
- Actual result: 
- Status: NOT RUN

### MC-105
- Required for acceptance: YES
- Exclusive resources: file:.uncle/config
- Depends on: none
- Exact action: Set `delegate_gates` in the `.uncle/config` file to an out-of-set value such as `bogus`, open Configure -> Supervision, press Enter on `delegate_gates`, then Esc.
- Expected result: The picker opens with only none/routine selectable and no row marked current; the stored value is shown unchanged as current without an explanation. Esc leaves the config value unchanged.
- Evidence to capture: Picker capture and the config value after Esc.
- Actual result: 
- Status: NOT RUN

### MC-106
- Required for acceptance: YES
- Exclusive resources: file:.uncle/config
- Depends on: none
- Exact action: On the Supervision menu, press Enter on the `enabled` boolean row and on a numeric row, then open a stage-config effort/runner/network picker and a model picker.
- Expected result: The bool toggles true/false without a picker and the numeric edit works. Stage-config and model pickers show bare choices with no explanations, and filter typing and Custom entry work as before.
- Evidence to capture: Captures of the toggle result, the numeric edit and the stage pickers.
- Actual result: 
- Status: NOT RUN

## Invariants

### MC-200
- Required for acceptance: YES
- Exclusive resources: none
- Depends on: none
- Exact action: In the real TUI at 120 columns, open Configure -> Supervision, then move the highlight through every row and press Enter on `enabled` (bool), then Enter on a hinted numeric row and Esc.
- Expected result: Every control row starts with its key, followed by its value and a short `  - hint` (<=40 chars, not truncated); Enter on each row acts on that row's own key (bool toggles without a picker, numeric opens edit), and the highlighted row's full description still appears in the side panel or strip.
- Evidence to capture: Terminal screenshot or captured screen text of the menu at 120 cols plus a note of the behavior of each Enter tried.
- Actual result: 
- Status: NOT RUN

### MC-201
- Required for acceptance: YES
- Exclusive resources: none
- Depends on: none
- Exact action: Open Configure -> Supervision at terminal widths 99, 100, 60 and 30 columns (resize between observations) and look at the rows and the highlighted-row description.
- Expected result: Inline hints are absent at 99 and below and present at 100; keys and values are never truncated by the hint logic; the highlighted description still shows (side panel or bottom strip); resizing to tiny sizes never crashes the TUI.
- Evidence to capture: Screen captures at each width and a note that the TUI stayed running.
- Actual result: 
- Status: NOT RUN

### MC-202
- Required for acceptance: YES
- Exclusive resources: none
- Depends on: none
- Exact action: At width >=120 in Configure -> Supervision, press Enter on `effort`, then `runner`, then `delegate_gates`, reading each picker and pressing Esc between them.
- Expected result: Each option row in the effort (none/low/medium/high), runner (every listed runner) and delegate_gates (none/routine only) pickers shows a non-empty `  - explanation`; Custom, filter and model rows carry no explanation; delegate_gates has no Custom row.
- Evidence to capture: Screen captures of each of the three pickers.
- Actual result: 
- Status: NOT RUN

### MC-203
- Required for acceptance: YES
- Exclusive resources: file:.uncle/config
- Depends on: none
- Exact action: Open the delegate_gates picker, select `routine`, then reopen and select `none`; afterwards re-view the Supervision menu row and press Esc from a freshly opened picker.
- Expected result: The current value is marked on the matching row; selecting stores exactly `routine` or `none` as shown in the menu row; Esc leaves the stored value unchanged.
- Evidence to capture: Screen captures of the menu row after each selection and after Esc.
- Actual result: 
- Status: NOT RUN

### MC-204
- Required for acceptance: YES
- Exclusive resources: file:.uncle/config
- Depends on: none
- Exact action: Set `delegate_gates` to an out-of-set value in the project config by hand-editing the config file, launch the TUI, open Configure -> Supervision, press Enter on `delegate_gates`, observe, then press Esc.
- Expected result: The picker opens listing only none/routine with no row highlighted as current (stored value shown as an unannotated current row), and Esc leaves the stored value unchanged; selecting routine stores routine.
- Evidence to capture: Screen capture of the picker and the config file value before and after Esc.
- Actual result: 
- Status: NOT RUN

## resources

### MC-301
- Required for acceptance: YES
- Exclusive resources: none
- Depends on: none
- Exact action: Resize the terminal to 99, 100, 60 and 30 columns in turn while viewing Configure -> Supervision.
- Expected result: Inline hints are absent at 99 columns and below and present at 100. At 60 and 30 columns the highlighted-option description still shows through the strip fallback. No crash or garbled screen appears, and keys and values are not truncated by the hint logic.
- Evidence to capture: Captures at each width, plus a note of whether hints appeared.
- Actual result: 
- Status: NOT RUN

### MC-302
- Required for acceptance: YES
- Exclusive resources: none
- Depends on: none
- Exact action: At about 120 columns, press Enter on the effort, delegate_gates and runner rows in turn to open each picker. Read each choice, then press Esc.
- Expected result: Each option row (effort none/low/medium/high; delegate_gates none/routine; each runner) shows a short non-empty explanation. Custom rows get none. The delegate_gates picker lists only none and routine.
- Evidence to capture: A capture of each of the three pickers.
- Actual result: 
- Status: NOT RUN

### MC-303
- Required for acceptance: YES
- Exclusive resources: file:.uncle/config
- Depends on: none
- Exact action: Open the delegate_gates picker, select routine, and re-open Configure -> Supervision. Then open it again and press Esc without selecting. Finally select none.
- Expected result: Selecting routine stores routine and the row shows routine. Esc leaves the value unchanged. Selecting none stores none. The current value is marked in the picker each time.
- Evidence to capture: Row text after each step, and the `delegate_gates` line in `.uncle/config` if it is visible.
- Actual result: 
- Status: NOT RUN

### MC-304
- Required for acceptance: YES
- Exclusive resources: file:.uncle/config
- Depends on: none
- Exact action: Open a stage-config picker (effort, runner, network, or model) from outside Supervision at about 120 columns. Also press Enter on the `enabled` row in Supervision, and in a picker type a filter and use Custom entry.
- Expected result: Non-supervision pickers show no explanations and look as before. The bool row toggles without opening a picker. Filtering and Custom entry work as before.
- Evidence to capture: A capture of a stage-config picker, and notes on the toggle, filter and Custom entry behavior.
- Actual result: 
- Status: NOT RUN

### MC-401
- Exclusive resources: file:.uncle/config
- Depends on: none
- Exact action: In the TUI at ~120 columns open Configure -> Supervision, highlight the 'enabled' row and press Enter; then highlight a numeric row and press Enter, type an invalid value, then a valid value, and confirm.
- Expected result: Enter on the bool row toggles true/false with no picker. Numeric edit still opens free-text entry, rejects invalid values as before and stores valid ones. Hinted rows act on the correct key.
- Evidence to capture: Screen captures before and after the toggle and numeric edit, plus the resulting config values.
- Actual result: 
- Status: NOT RUN

### MC-402
- Exclusive resources: none
- Depends on: none
- Exact action: At ~60 columns open Configure -> Supervision and move the highlight through several rows. Then resize to 99 columns and to 100 columns and look at the rows again.
- Expected result: At 60 and 99 columns there are no inline hints, rows are not garbled, and the highlighted row's description still shows in the strip or side panel. At 100 columns hints appear and the description still shows. Nothing crashes at any width.
- Evidence to capture: Screen captures at 60, 99 and 100 columns.
- Actual result: 
- Status: NOT RUN

### MC-403
- Exclusive resources: none
- Depends on: none
- Exact action: Open a stage-config picker (model, effort, runner or network) outside Supervision. Type to filter, choose Custom..., then press Esc.
- Expected result: The picker rows, labels, ordering, filtering and Custom entry behave as before, and no explanation text appears next to any row.
- Evidence to capture: Screen captures of each stage-config picker and the filter and Custom entry flow.
- Actual result: 
- Status: NOT RUN

### MC-404
- Exclusive resources: file:.uncle/config
- Depends on: none
- Exact action: In Supervision, open the model picker, then type to filter and choose Custom... Separately, open the effort picker, select a value and confirm. Set the value back afterwards.
- Expected result: Model rows show no explanations. Filtering and Custom entry work as before. The effort selection stores the chosen value.
- Evidence to capture: Screen captures of the model and effort pickers and the stored config values.
- Actual result: 
- Status: NOT RUN

### MC-405
- Exclusive resources: file:.uncle/config
- Depends on: none
- Exact action: In Supervision, press Enter on delegate_gates, select 'routine', then reopen it and press Esc. If a stored value outside none/routine can be set in .uncle/config, reopen the picker with that value, press Esc, and check the config.
- Expected result: The picker lists only none and routine, each with an explanation. Selecting routine stores 'routine'. Esc leaves the value unchanged, including an out-of-set stored value, which has no row highlighted.
- Evidence to capture: Screen captures of the picker and the config value after each step.
- Actual result: 
- Status: NOT RUN

### MC-406
- Exclusive resources: file:.uncle/config
- Depends on: none
- Exact action: Use an invalid supervision config, for example a bad numeric value in .uncle/config, and open Configure -> Supervision at ~120 columns. Then restore the config.
- Expected result: The '! reason' row appears unchanged and has no hint. All other rows still start with their key, and nothing crashes.
- Evidence to capture: Screen capture of the menu with the invalid-config row.
- Actual result: 
- Status: NOT RUN
