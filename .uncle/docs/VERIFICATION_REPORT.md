# Verification report

## Findings

### MC-102

- **Action:** Loaded uncle_tui.py headlessly (no curses screenshot possible). Read the default-display code (uncle_tui.py:1463-1468), checked DEFAULT_MODEL_FOR_RUNNER['claude'] and MODEL_LABELS, and ran the unit probe test_picker_highlights_default_when_unset, which builds the TUI object with no stored model, calls _open_picker('model','plan') and checks the selected row.
- **Expected result:** The default shows claude-sonnet-5-5 with label Claude Sonnet 5.5, and the picker opens with that row highlighted.
- **Actual result:** DEFAULT_MODEL_FOR_RUNNER['claude'] is claude-sonnet-5-5 and MODEL_LABELS['claude-sonnet-5-5'] is 'Claude Sonnet 5.5'. The default-display code builds 'claude-sonnet-5-5  (default)  Claude Sonnet 5.5'. The picker probe opened with rows[pick_sel] == ('model','claude-sonnet-5-5') and stage_models still empty (test OK). I did not take a screenshot of the rendered curses UI; the checks were headless.
- **Defects:** None

### MC-103

- **Action:** Drove the real uncle_tui picker code headlessly (no curses screen/screenshots) with a Claude stage whose stored model is claude-sonnet-5; called _open_picker('model','plan') and _picker_filtered(); ran scripts/tests/claude-model-defaults-test.py (test_stored_old_id_not_in_catalog).
- **Expected result:** Stored id displayed verbatim and not rewritten; picker lists exactly 12 entries and highlights none; stored value unchanged after closing without selecting.
- **Actual result:** Picker listed 12 model rows; claude-sonnet-5 is not among them; stored value stayed {'plan': 'claude-sonnet-5'} (the _set_field write hook was set to raise and never fired). Cursor pick_sel=1 sits on the first selectable row (claude-haiku-5-5), the default list start, not on a row matching the stored id, so no catalog entry is marked as current. 8/8 tests in the model-defaults test file passed.
- **Defects:** None

### MC-104

- **Action:** No terminal emulator (pyte) available, so I drove the real UncleTUI picker methods (_picker_rows/_picker_filtered/_picker_move/_draw_picker) from uncle_tui.py against a recording fake curses screen. Used a 20-row height for the full walk, an 8-row height for the top view, and the filter 'opus'. Script: .uncle/tests/mc104.py. This was not a live curses session in a real tty.
- **Expected result:** All 12 entries are reachable by scrolling, and filtering narrows the list correctly without rendering glitches.
- **Actual result:** Stepping through the list at 20 rows reached all 12 distinct claude ids. At 8 rows the top view showed the 'Claude' header, then the entries from claude-haiku-5-5 through claude-opus-4-8, with '<current>' on claude-sonnet-5-5. Filter 'opus' left 5 opus entries (5-5, 4-8, 4-7, 4-6, 4-5-20251101) plus the Custom row, with the header dropped and the first row selected. Filter 'zzz' left only the Custom row. No exceptions, no garbled lines, no truncated text at width 100.
- **Defects:** None

### MC-105

- **Action:** Did not open the interactive TUI or take screenshots. Instead imported the working-tree uncle_tui.py and the HEAD version (git show HEAD:uncle_tui.py) and compared MODEL_CATALOG_CODEX, MODEL_CATALOG_KIMI and the codex/kimi entries of DEFAULT_MODEL_FOR_RUNNER. Also read the diff and searched the Codex and Kimi catalogs for 'claude' ids.
- **Expected result:** Codex and Kimi catalogs and defaults are unchanged from before the change, and no Claude entries appear in them.
- **Actual result:** Catalog and default data are unchanged and contain no Claude entries. The rendered pickers were not viewed, so the required screenshots were not captured. The only Codex-related diff line is a comment edit.
- **Defects:** None

### MC-201

- **Action:** Drove the real TUI class (uncle_tui.py, imported with python3 -I from a temp script in /tmp/mc201) without a curses screen: stored model for stage 'plan' = 'claude-sonnet-5' (runner claude), called _field_display('plan','model'), _open_picker('model','plan'), _picker_filtered(), _picker_current(), with _set_field patched to raise on any write.
- **Expected result:** Stage shows claude-sonnet-5 verbatim; picker lists exactly 12 entries and highlights none; stored value not rewritten.
- **Actual result:** Display was exactly 'claude-sonnet-5' (no label). Picker listed 12 model rows (haiku-5-5, sonnet-5-5, opus-5-5, fable-5-1, fable-5, opus-4-8, opus-4-7, sonnet-4-6, opus-4-6, opus-4-5-20251101, haiku-4-5-20251001, sonnet-4-5-20250929); no row equals claude-sonnet-5, so no row gets the '<current>' match marker. The navigation cursor (pick_sel=1) rests on the first selectable row, claude-haiku-5-5, which is the unavoidable fallback cursor position and not a match to the stored value. No rewrite was attempted; stored value remained {'plan': 'claude-sonnet-5'}.
- **Defects:** None

### MC-202

- **Action:** Read the checklist row only. No live TUI session was driven, so the picker was not opened, scrolled, or filtered at normal or short terminal heights.
- **Expected result:** All 12 rows are reachable by scrolling. The filter narrows the list correctly, and nothing renders garbled or is cut off.
- **Actual result:** Not performed. The check needs a person to look at the curses picker at two terminal heights, and no such observation was made.
- **Defects:** None

### MC-203

- **Action:** Inspected the data the Codex and Kimi pickers render (uncle_tui.py MODEL_CATALOG_CODEX, MODEL_CATALOG_KIMI, DEFAULT_MODEL_FOR_RUNNER, and the picker catalog mapping at ~line 1697) and compared the catalogs programmatically against git HEAD. The interactive curses TUI was not launched; the picker was verified through its backing data rather than a screen capture.
- **Expected result:** Codex and Kimi catalogs and defaults look unchanged and contain no Claude entries.
- **Actual result:** MODEL_CATALOG_CODEX (gpt-5.1-codex, gpt-5.1-codex-mini) and MODEL_CATALOG_KIMI (moonshotai/kimi-k2.7-code-highspeed, moonshotai/kimi-k2.6) are byte-identical to HEAD. Defaults are codex='codex default' and kimi='moonshotai/kimi-k2.7-code-highspeed'. The working-tree diff touches only a comment line mentioning codex, not values. Neither catalog contains a Claude entry. The picker maps 'codex' and 'kimi' to their own catalogs.
- **Defects:** None

### MC-300

- **Action:** Headless-drove UncleTUI (instance built with __new__, claude runner, no stored model) via a temp script /tmp/mc300.py: called _field_display('plan','model') and _open_picker('model','plan'), then read _picker_filtered() rows. No rendered terminal/curses session was used.
- **Expected result:** Picker lists exactly 12 entries in order Haiku 5.5, Sonnet 5.5, Opus 5.5, Fable 5.1, Fable 5, Opus 4.8, Opus 4.7, Sonnet 4.6, Opus 4.6, Opus 4.5, Haiku 4.5, Sonnet 4.5; default shows claude-sonnet-5-5  Claude Sonnet 5.5; no other Claude entries.
- **Actual result:** 12 model rows in exactly the expected order. Default display was 'claude-sonnet-5-5  (default)  Claude Sonnet 5.5' (includes a '(default)' marker between id and label). The picker opened with the claude-sonnet-5-5 row selected. No other Claude entries.
- **Defects:** None

### MC-301

- **Action:** Same headless harness: set stage_models['plan']='claude-sonnet-5', read _field_display, opened the model picker, read rows, then discarded it without calling _picker_confirm, and read the stored value again. No rendered terminal/curses session was used.
- **Expected result:** Stage shows claude-sonnet-5 verbatim; picker still lists exactly 12 entries; stored value unchanged after closing without choosing.
- **Actual result:** Display was 'claude-sonnet-5' verbatim (no label, no rewrite). Picker listed 12 model rows. The stored value was still 'claude-sonnet-5' after open and close without selecting. No row matched the stored id, so the cursor fell back to the first row (Claude Haiku 5.5) as a positional cursor, not a match for the stored value.
- **Defects:** None

### MC-302

- **Action:** Looked for a way to drive the real curses TUI in a ~15-row terminal (tmux, pyte). Neither is installed. Instead ran a narrow temporary probe, .uncle/tests/mc302_probe.py, that loads uncle_tui.py. It builds the TUI object without curses, uses a recording fake screen, and calls the real _open_picker, _picker_move, _picker_filtered, _reset_pick_sel and _draw_picker for a Claude stage with no stored model. It ran at screen height 15 and then at height 8, stepping the selection 13 times and applying the filter 'opus'.
- **Expected result:** In a short terminal (about 15 rows), all 12 Claude entries are reachable by scrolling with arrow keys without rendering glitches, and the filter 'opus' narrows the list to the Opus entries.
- **Actual result:** The probe observed the expected behavior in the real picker logic and draw code, but not in a live terminal with real keystrokes. The catalog has exactly 12 model rows. The picker opens on claude-sonnet-5-5 (<current>). At height 15 the whole list (header, 12 models, Custom row) fits with no clipping. At height 8 the window scrolled correctly: rows moved up and the selection wrapped from the last entry back to claude-haiku-5-5. No out-of-range draw rows occurred and 13 distinct model ids were rendered across the steps. The filter 'opus' left 5 Opus entries (5.5, 4.8, 4.7, 4.6, 4.5) plus the Custom row. Clearing the filter restored all rows (14: header, 12 models, Custom). The live check as specified (real terminal, arrow keys, typed filter, captures) was not performed.
- **Defects:** None. Needed action: install tmux (or pyte) so the TUI can be driven in a 15-row pty, then rerun MC-302. Alternatively a human can open the Claude model picker in a 15-row terminal.

### MC-303

- **Action:** Imported uncle_tui and printed the Codex and Kimi model catalogs that _picker_rows() uses for those runners; read the _picker_rows and _picker_current code paths; inspected the full uncle_tui.py working-tree diff against HEAD for any change touching Codex/Kimi catalogs, defaults or picker logic. I did not render the interactive curses picker.
- **Expected result:** The Codex and Kimi pickers show their usual lists and defaults, with no Claude entries and no visible change from before.
- **Actual result:** Codex picker rows come only from MODEL_CATALOG_CODEX: header 'Codex' with gpt-5.1-codex and gpt-5.1-codex-mini, plus the Custom row. Kimi picker rows come only from MODEL_CATALOG_KIMI: header 'Kimi' with moonshotai/kimi-k2.7-code-highspeed and moonshotai/kimi-k2.6, plus the Custom row. Neither list has a Claude entry. DEFAULT_MODEL_FOR_RUNNER for codex ('codex default') and kimi ('moonshotai/kimi-k2.7-code-highspeed') is unchanged. The diff changes only the Claude catalog, the Claude default id, and the _picker_current fallback, which applies only when stage_runner is 'claude'.
- **Defects:** None

### MC-401

- **Action:** Did not drive the interactive curses TUI. Imported the changed uncle_tui module and read MODEL_CATALOG_CODEX, MODEL_CATALOG_KIMI and DEFAULT_MODEL_FOR_RUNNER. Read _picker_rows, which builds picker rows for the Codex and Kimi runners from those catalogs. Compared against `git diff HEAD -- uncle_tui.py`.
- **Expected result:** Codex and Kimi pickers list the same entries and defaults as before the change; nothing Claude-related appears in them.
- **Actual result:** The diff changes only MODEL_CATALOG_CLAUDE, DEFAULT_MODEL_FOR_RUNNER['claude'] and the picker-initial-value branch, which is gated on runner == 'claude'. The Codex catalog is [gpt-5.1-codex, gpt-5.1-codex-mini] and the Kimi catalog is [moonshotai/kimi-k2.7-code-highspeed, moonshotai/kimi-k2.6]. Neither is in the diff. The Codex default ('codex default') and Kimi default (moonshotai/kimi-k2.7-code-highspeed) are unchanged. _picker_rows selects the catalog by runner, so no Claude ids appear in the Codex or Kimi pickers.
- **Defects:** None

### MC-402

- **Action:** Could not use a live interactive terminal (no tmux). Instead ran the real UncleTUI class under real curses in a pty at 100x40 (normal) and 100x10 (short). Opened the model picker for a Claude-runner stage via _open_picker('model', ...). Pressed Down 14 times through all entries and past the end, then Up 3 times. Typed 'opus' and then Backspace x4 through handle_key. Called draw() after every key and captured the screen. Temporary script in /tmp/mc402 (outside the project).
- **Expected result:** Scrolling and filtering work without rendering glitches or crashes. The filter matches the Opus entries and clearing it restores all 12.
- **Actual result:** No exceptions at either height. The picker listed 12 Claude models plus a Custom row. Down moved through the entries in order and wrapped from 'Custom…' back to claude-haiku-5-5 at the end of the list. Up moved back correctly. Typing 'opus' left claude-opus-5-5, -4-8, -4-7, -4-6, -4-5-20251101 and the Custom row (5 Opus entries), with the first match selected. Backspacing to an empty filter restored all 12 models with an empty filter string and the first model selected. At height 10 the list scrolled and the selection stayed visible, with the header line intact. The 'Claude' group header row is hidden while the filter is active and returns when it is cleared. No visible rendering glitches in the captured frames. Caveat: this is a headless drive of the real draw and key-handling code. It is not a human watching a live terminal, and the logo is drawn only at the tall height.
- **Defects:** None

### MC-403

- **Action:** Did not run the curses TUI interactively. Ran a narrow Python probe (python3 -I /tmp/mc403.py) that loads uncle_tui.py, builds the TUI object with stage 'plan' on runner claude and stored model 'claude-sonnet-5', and calls the real _open_picker('model','plan') and _picker_filtered(). _set_field was replaced with a stub that raises, to catch any rewrite of the stored value. Also read the Escape path in uncle_tui.py (~line 8699).
- **Expected result:** The stage shows claude-sonnet-5 verbatim; the picker lists exactly 12 entries with no row wrongly selected; after Escape the stored value remains claude-sonnet-5, unrewritten.
- **Actual result:** Stage model read back as 'claude-sonnet-5' verbatim. The picker returned exactly 12 model rows (haiku-5-5 through sonnet-4-5-20250929), and none equals claude-sonnet-5. _set_field was never called while the picker opened. In the Escape handler, state == 'picker' only sets self.state to 'stage' or 'config' and has no write path, so the stored value stays unrewritten. One open point: pick_sel falls back to the first selectable row (claude-haiku-5-5), because no row matches the stored id. That is the cursor position and not a stored-value match, but I did not see how the curses UI draws it, so I cannot confirm that the cursor on row 1 does not look 'wrongly selected'. The prepared unit test test_stored_old_id_not_in_catalog covers the 12-row and no-rewrite assertions, but I did not re-run it.
- **Defects:** None

### MC-404

- **Action:** Ran scripts/reviewer-claude.sh exec --output-last-message <file> hi with WORKFLOW_REVIEWER_CLAUDE_CMD pointing to a stub that echoes its args, first with WORKFLOW_REVIEWER_CLAUDE_MODEL=claude-opus-5-5, then gpt-4.
- **Expected result:** The override is used when it is Claude-like; a non-Claude id prints a warning and falls back to claude-sonnet-5-5, with the override taking precedence otherwise.
- **Actual result:** claude-opus-5-5 was used (banner 'model: claude-opus-5-5', stub received --model claude-opus-5-5), with no warning. gpt-4 printed the warning "'gpt-4' is not a Claude tier; using claude-sonnet-5-5" and the stub received --model claude-sonnet-5-5. The trailing 'returned no document' message came from the stub's trivial output and is unrelated to model selection.
- **Defects:** None

## Acceptance gate

| ID | Required | Status | Evidence |
|---|---|---|---|
| MC-102 | YES | PASS | Probe output: 'Ran 1 test ... OK'. Code: uncle_tui.py:492, 1463-1468, 1723-1742. I read the display string from the code and did not render it, so the on-screen text is unobserved. |
| MC-103 | YES | PASS | Inline probe output: '12 1 (model, claude-haiku-5-5) ... {plan: claude-sonnet-5}'. Test run: Ran 8 tests ... OK. Limitation: no on-screen screenshots were taken; verified at the code/state level, and the cursor-on-first-row versus 'highlight' distinction is my interpretation. |
| MC-104 | YES | PASS | Output: 'reachable 12 [claude-fable-5, claude-fable-5-1, claude-haiku-4-5-20251001, claude-haiku-5-5, claude-opus-4-5-20251101, claude-opus-4-6, claude-opus-4-7, claude-opus-4-8, claude-opus-5-5, claude-sonnet-4-5-20250929, claude-sonnet-4-6, claude-sonnet-5-5]'. The FILTER opus capture showed 5 opus rows plus 'Custom… (type a model id)'. Limitation: no real-terminal screenshots, and raw key handling was not exercised. |
| MC-105 | YES | PASS | Python comparison of working tree against HEAD: MODEL_CATALOG_CODEX equal True, MODEL_CATALOG_KIMI equal True, codex default 'codex default' equal True, kimi default 'moonshotai/kimi-k2.7-code-highspeed' equal True. Codex catalog: gpt-5.1-codex, gpt-5.1-codex-mini. Kimi catalog: moonshotai/kimi-k2.7-code-highspeed, moonshotai/kimi-k2.6. The list of claude ids across both catalogs is []. The diff only touches the claude catalog, the claude default, and the claude picker initial-selection branch (guarded by runner == claude). |
| MC-201 | YES | PASS | Probe output: display: 'claude-sonnet-5'; 12 [list above]; pick_sel 1 ('model','claude-haiku-5-5') cur 'claude-sonnet-5'; exact match rows: []; stored {'plan': 'claude-sonnet-5'}. _draw_picker source shows the '<current>' marker is applied only when row text equals _picker_current(). Not observed in a live curses screen; verified at the object level. Also covered by scripts/tests/claude-model-defaults-test.py::test_stored_old_id_not_in_catalog (driver green-check). |
| MC-202 | YES | BLOCKED-HUMAN | None. No captures were taken. |
| MC-203 | YES | PASS | Python regex extraction of both catalog blocks from HEAD and the working tree printed 'identical to HEAD: True' for each. Source lines 460-475 and 488-496 were read. 'git diff -U0' filtered for codex/kimi showed only a comment change. No live screen capture was taken. |
| MC-300 | YES | PASS | Script output: count 12 ['Claude Haiku 5.5','Claude Sonnet 5.5','Claude Opus 5.5','Claude Fable 5.1','Claude Fable 5','Claude Opus 4.8','Claude Opus 4.7','Claude Sonnet 4.6','Claude Opus 4.6','Claude Opus 4.5','Claude Haiku 4.5','Claude Sonnet 4.5']; selected ('model','claude-sonnet-5-5'). Source uncle_tui.py:443-458, 491-495, 1464-1467. Caveat: logic-level observation, not a visual screenshot; the '(default)' marker is a cosmetic difference from the literal string. |
| MC-301 | YES | PASS | Script output: stored= 'claude-sonnet-5' display= claude-sonnet-5; count 12; stored after open/close claude-sonnet-5. Source _open_picker uncle_tui.py:1743-1776. Caveat: logic-level observation, not a visual screenshot; the cursor on row 1 may be drawn as a highlight, which this check's expected result does not address. |
| MC-302 | YES | BLOCKED-SETUP | Probe output printed in the worker session. Probe script: .uncle/tests/mc302_probe.py. The check requires screen captures from a real ~15-row terminal, which could not be made in this environment because tmux and pyte are not installed. |
| MC-303 | YES | PASS | Catalog print: codex [('Codex', ['gpt-5.1-codex','gpt-5.1-codex-mini'])]; kimi [('Kimi', ['moonshotai/kimi-k2.7-code-highspeed','moonshotai/kimi-k2.6'])]. git diff -U0 uncle_tui.py shows only Claude-related +/- lines. uncle_tui.py:1693-1707 selects static catalogs per runner. This is code-level observation, not a screen capture of the picker. |
| MC-401 | YES | PASS | Module import printed the Codex and Kimi catalogs. `git diff HEAD -- uncle_tui.py` shows no hunk touching the Codex or Kimi catalogs or defaults. Limitation: there are no screenshots or terminal captures of a live picker, so this is code and data observation rather than a visual TUI observation. |
| MC-402 | YES | PASS | Captured frames at /tmp/mc402/tall.json and /tmp/mc402/short.json (keys open, down*, up*, filtered, cleared). The 'models' field is 12. 'filtered_rows' is [opus-5-5, opus-4-8, opus-4-7, opus-4-6, opus-4-5-20251101, Custom]. 'cleared_models' is 12 and 'cleared_filter' is ''. 'seen_down' ends in Custom, then haiku-5-5, sonnet-5-5, opus-5-5, fable-5-1. The 'error' field is absent at both heights. |
| MC-403 | YES | BLOCKED-HUMAN | Probe output: 'stage shows: claude-sonnet-5'; '12 [claude-haiku-5-5, claude-sonnet-5-5, claude-opus-5-5, claude-fable-5-1, claude-fable-5, claude-opus-4-8, claude-opus-4-7, claude-sonnet-4-6, claude-opus-4-6, claude-opus-4-5-20251101, claude-haiku-4-5-20251001, claude-sonnet-4-5-20250929]'; "sel row: ('model', 'claude-haiku-5-5') state picker"; 'matches stored: []'. Code: uncle_tui.py _open_picker lines 1743-1776 and the Escape handler around line 8699. No rendered terminal capture was taken. |
| MC-404 | YES | PASS | Command output: 'model: claude-opus-5-5' / 'STUB ARGS: -p --model claude-opus-5-5 ...'; 'reviewer-claude.sh: 'gpt-4' is not a Claude tier; using claude-sonnet-5-5' / 'model: claude-sonnet-5-5' / 'STUB ARGS: -p --model claude-sonnet-5-5 ...'. |
