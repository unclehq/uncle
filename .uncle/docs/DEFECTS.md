# Defects

## None

- **Status:** BLOCKED-HUMAN
- **Evidence:** None. No captures were taken.
- **Expected result:** All 12 rows are reachable by scrolling. The filter narrows the list correctly, and nothing renders garbled or is cut off.
- **Actual result:** Not performed. The check needs a person to look at the curses picker at two terminal heights, and no such observation was made.

## None. Needed action: install tmux (or pyte) so the TUI can be driven in a 15-row pty, then rerun MC-302. Alternatively a human can open the Claude model picker in a 15-row terminal.

- **Status:** BLOCKED-SETUP
- **Evidence:** Probe output printed in the worker session. Probe script: .uncle/tests/mc302_probe.py. The check requires screen captures from a real ~15-row terminal, which could not be made in this environment because tmux and pyte are not installed.
- **Expected result:** In a short terminal (about 15 rows), all 12 Claude entries are reachable by scrolling with arrow keys without rendering glitches, and the filter 'opus' narrows the list to the Opus entries.
- **Actual result:** The probe observed the expected behavior in the real picker logic and draw code, but not in a live terminal with real keystrokes. The catalog has exactly 12 model rows. The picker opens on claude-sonnet-5-5 (<current>). At height 15 the whole list (header, 12 models, Custom row) fits with no clipping. At height 8 the window scrolled correctly: rows moved up and the selection wrapped from the last entry back to claude-haiku-5-5. No out-of-range draw rows occurred and 13 distinct model ids were rendered across the steps. The filter 'opus' left 5 Opus entries (5.5, 4.8, 4.7, 4.6, 4.5) plus the Custom row. Clearing the filter restored all rows (14: header, 12 models, Custom). The live check as specified (real terminal, arrow keys, typed filter, captures) was not performed.

## None

- **Status:** BLOCKED-HUMAN
- **Evidence:** Probe output: 'stage shows: claude-sonnet-5'; '12 [claude-haiku-5-5, claude-sonnet-5-5, claude-opus-5-5, claude-fable-5-1, claude-fable-5, claude-opus-4-8, claude-opus-4-7, claude-sonnet-4-6, claude-opus-4-6, claude-opus-4-5-20251101, claude-haiku-4-5-20251001, claude-sonnet-4-5-20250929]'; "sel row: ('model', 'claude-haiku-5-5') state picker"; 'matches stored: []'. Code: uncle_tui.py _open_picker lines 1743-1776 and the Escape handler around line 8699. No rendered terminal capture was taken.
- **Expected result:** The stage shows claude-sonnet-5 verbatim; the picker lists exactly 12 entries with no row wrongly selected; after Escape the stored value remains claude-sonnet-5, unrewritten.
- **Actual result:** Stage model read back as 'claude-sonnet-5' verbatim. The picker returned exactly 12 model rows (haiku-5-5 through sonnet-4-5-20250929), and none equals claude-sonnet-5. _set_field was never called while the picker opened. In the Escape handler, state == 'picker' only sets self.state to 'stage' or 'config' and has no write path, so the stored value stays unrewritten. One open point: pick_sel falls back to the first selectable row (claude-haiku-5-5), because no row matches the stored id. That is the cursor position and not a stored-value match, but I did not see how the curses UI draws it, so I cannot confirm that the cursor on row 1 does not look 'wrongly selected'. The prepared unit test test_stored_old_id_not_in_catalog covers the 12-row and no-rewrite assertions, but I did not re-run it.
