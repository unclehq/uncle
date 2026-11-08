# Manual checklist

## Coverage

### MC-102
- Required for acceptance: YES
- Exclusive resources: none
- Depends on: none
- Exact action: For a Claude stage with no stored model, view the default model display and open the picker.
- Expected result: The default shows claude-sonnet-5-5 with label Claude Sonnet 5.5, and the picker opens with that row highlighted.
- Evidence to capture: Screenshot of the default display and the highlighted picker row.
- Actual result: 
- Status: NOT RUN

### MC-103
- Required for acceptance: YES
- Exclusive resources: none
- Depends on: none
- Exact action: Set a Claude stage's stored model to the old id claude-sonnet-5 (not in the new catalog), then reopen the TUI and its picker.
- Expected result: The stored id is displayed verbatim and not rewritten. The picker lists exactly 12 entries and highlights none, and the stored value is unchanged after closing the picker without selecting.
- Evidence to capture: Screenshots of the display and picker, plus the stored config value before and after.
- Actual result: 
- Status: NOT RUN

### MC-104
- Required for acceptance: YES
- Exclusive resources: none
- Depends on: none
- Exact action: Open the Claude picker in a short terminal (e.g. 20 rows), scroll through all entries, and use the filter if available (e.g. 'opus').
- Expected result: All 12 entries are reachable by scrolling, and filtering narrows the list correctly without rendering glitches.
- Evidence to capture: Captures of the picker at top, bottom and filtered.
- Actual result: 
- Status: NOT RUN

### MC-105
- Required for acceptance: YES
- Exclusive resources: none
- Depends on: none
- Exact action: Open the Codex and Kimi pickers and view their defaults in the TUI.
- Expected result: Their catalogs and defaults are unchanged from before the change, and no Claude entries appear in them.
- Evidence to capture: Screenshots of both pickers and their default displays.
- Actual result: 
- Status: NOT RUN

## Invariants

### MC-201
- Required for acceptance: YES
- Exclusive resources: none
- Depends on: none
- Exact action: In the TUI, set a Claude stage's stored model to the old id `claude-sonnet-5`, then open the picker and view the stage's model display.
- Expected result: The stage shows `claude-sonnet-5` verbatim. The picker lists exactly 12 entries and highlights none of them. The stored value is not rewritten.
- Evidence to capture: Capture of the stage model display and the picker list, plus the stored model value after closing the picker.
- Actual result: 
- Status: NOT RUN

### MC-202
- Required for acceptance: YES
- Exclusive resources: none
- Depends on: none
- Exact action: With the 12-entry Claude picker open, scroll through the full list (down and up) and use the filter to narrow it, for example by typing `opus`, at a normal terminal height and at a short one.
- Expected result: All 12 rows are reachable by scrolling. The filter narrows the list correctly, and nothing renders garbled or is cut off.
- Evidence to capture: Captures of the picker at both terminal heights, scrolled to the end and with the filter applied.
- Actual result: 
- Status: NOT RUN

### MC-203
- Required for acceptance: YES
- Exclusive resources: none
- Depends on: none
- Exact action: Open the Codex and Kimi pickers in the TUI and read their entries and default rows.
- Expected result: Codex and Kimi catalogs and defaults look unchanged and contain no Claude entries.
- Evidence to capture: Captures of the Codex and Kimi pickers showing their lists and highlighted defaults.
- Actual result: 
- Status: NOT RUN

## Resources: Claude picker

### MC-300
- Required for acceptance: YES
- Exclusive resources: file:tui-stage-config
- Depends on: none
- Exact action: Launch the TUI in a fresh config state, select a stage whose runner is Claude with no stored model, and open the model picker.
- Expected result: The picker lists exactly 12 entries in this order: Claude Haiku 5.5, Sonnet 5.5, Opus 5.5, Fable 5.1, Fable 5, Opus 4.8, Opus 4.7, Sonnet 4.6, Opus 4.6, Opus 4.5, Haiku 4.5, Sonnet 4.5. The default shows `claude-sonnet-5-5  Claude Sonnet 5.5` and no other Claude entries appear.
- Evidence to capture: Terminal screenshot or text capture of the picker and the stage's default model display.
- Actual result: 
- Status: NOT RUN

## Resources: stored model id

### MC-301
- Required for acceptance: YES
- Exclusive resources: file:tui-stage-config
- Depends on: none
- Exact action: Set a Claude stage's stored model to the old id `claude-sonnet-5`, reopen the TUI, view the stage, open the picker, then close it without choosing anything.
- Expected result: The stage shows `claude-sonnet-5` verbatim and the picker still lists exactly 12 entries. The stored value is unchanged after closing the picker.
- Evidence to capture: Captures of the stage display and picker, plus the stored value before and after.
- Actual result: 
- Status: NOT RUN

## Resources: picker usability

### MC-302
- Required for acceptance: YES
- Exclusive resources: none
- Depends on: none
- Exact action: In a short terminal window (about 15 rows), open the Claude picker, scroll through all 12 entries with the arrow keys, and use the picker's filter (if offered) to type `opus`.
- Expected result: All 12 entries are reachable by scrolling without rendering glitches. The filter narrows the list to the Opus entries.
- Evidence to capture: Captures of the top and bottom of the scrolled list and of the filtered list.
- Actual result: 
- Status: NOT RUN

## Resources: other runners

### MC-303
- Required for acceptance: YES
- Exclusive resources: none
- Depends on: none
- Exact action: Open the model picker for a Codex stage and for a Kimi stage and note the entries and default of each.
- Expected result: The Codex and Kimi pickers show their usual lists and defaults, with no Claude entries and no visible change from before.
- Evidence to capture: Captures of the Codex and Kimi pickers with their default rows.
- Actual result: 
- Status: NOT RUN

## Regressions

### MC-401
- Required for acceptance: YES
- Exclusive resources: none
- Depends on: none
- Exact action: In the TUI, open the model picker for a Codex stage and then a Kimi stage, and note the listed entries and the default row of each.
- Expected result: Codex and Kimi pickers list the same entries and defaults as before the change; nothing Claude-related appears in them.
- Evidence to capture: Screenshots or terminal captures of both pickers showing entries and the default row.
- Actual result: 
- Status: NOT RUN

### MC-402
- Required for acceptance: YES
- Exclusive resources: none
- Depends on: none
- Exact action: In the TUI, open the Claude picker, scroll through all 12 entries with arrow keys (including wrap or end of list), type a filter such as 'opus' and then clear it, at a normal and a short terminal height.
- Expected result: Scrolling and filtering work without rendering glitches or crashes; the filter matches the Opus entries and clearing it restores all 12.
- Evidence to capture: Terminal captures at top, bottom, filtered and cleared states, for both terminal heights.
- Actual result: 
- Status: NOT RUN

### MC-403
- Required for acceptance: YES
- Exclusive resources: none
- Depends on: none
- Exact action: Configure a stage with a stored model id absent from the new catalog (claude-sonnet-5), restart the TUI, view that stage's model, then open the Claude picker and close it with Escape.
- Expected result: The stage shows claude-sonnet-5 verbatim; the picker lists exactly 12 entries with no row wrongly selected; after Escape the stored value remains claude-sonnet-5, unrewritten.
- Evidence to capture: Captures of the stage display and picker, plus the stored config value after cancelling.
- Actual result: 
- Status: NOT RUN

### MC-404
- Required for acceptance: YES
- Exclusive resources: none
- Depends on: none
- Exact action: Run reviewer-claude.sh with WORKFLOW_REVIEWER_CLAUDE_MODEL set to a valid override id, then to a non-Claude id such as gpt-4, and observe the model used and any warning.
- Expected result: The override is used when it is Claude-like; a non-Claude id prints a warning and falls back to claude-sonnet-5-5, with the override taking precedence otherwise.
- Evidence to capture: Command output showing the chosen model and the fallback warning.
- Actual result: 
- Status: NOT RUN
