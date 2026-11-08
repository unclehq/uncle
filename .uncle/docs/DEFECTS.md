# Defects

## None recorded yet: status line renders 2 rows above the last terminal row at 24 and 50 rows (expected the last row). Needs a DEFECTS.md entry from the driver.

- **Status:** FAIL
- **Evidence:** 24-row capture: 17 'What can uncle do for you?', 18 hint, 19 rule, 20 '› Describe an app or a change…', 21 rule, 22 'claude-sonnet-5-5 (low) · Chat ready ... uncle-issue-187 · mode(auto)', rows 23-24 blank. 50-row capture: 40 greeting, 42 hint, 44 rule, 45 composer, 46 rule, 48 status, rows 47, 49, 50 blank. Emulation caveat: results come from pyte rendering of the pty stream; a real-terminal visual confirmation was not performed. Other rows were not independently re-examined.
- **Expected result:** The status line (model/project/branch) is on the very last terminal row, and the composer's bottom rule sits directly above it with no blank row between them.
- **Actual result:** The bottom rule is directly above the status line (no blank row between them), but the status is NOT on the last terminal row. At 24 rows the rule is on row 21 and the status on row 22, leaving rows 23-24 blank. At 50 rows the rule is on row 46 and the status on row 48, with row 47 blank and rows 49-50 blank. An earlier run that set the size after fork showed the same 24-row layout with status on row 22. In both heights the status is 2 rows short of the bottom.

## None

- **Status:** BLOCKED-SETUP
- **Evidence:** 'which tmux' returned exit 1 (not found). 'import pyte' raised ModuleNotFoundError. scripts/tests/home-layout-test.py drives a FakeScreen, not a real terminal, so it is not live evidence. It is covered by the driver green-check, which this worker did not rerun or cite as a pass for this row. Action to unblock: install tmux (or pyte), or have a human run ./uncle in a real terminal and type text that wraps to 2, 4 and 6+ rows.
- **Expected result:** The status stays on the last row and the bottom rule stays directly above it while the composer wraps to 2, 4 and 6+ rows. The composer grows upward, the cursor stays on the last visible composer row, and the greeting, hint and logo text are unchanged.
- **Actual result:** Not observed. This environment has no tmux and no pyte, so there is no way to capture the screen of a curses TUI at a controlled size. The live observation was not performed.

## None

- **Status:** BLOCKED-HUMAN
- **Evidence:** Output of /tmp/mc103.py (draw coordinates and _text_view as above). `python3 -m unittest scripts/tests/home-layout-test.py` ran 24 tests, OK. Layout and selection-mapping logic is verified. The interactive scroll and mouse-selection parts need a human in a real terminal.
- **Expected result:** History renders above the greeting and composer block and is scrollable. Mouse selection hits the correct history rows. Nothing crashes at small sizes. At 5 rows the status is on the last row and the bottom rule is directly above it.
- **Actual result:** At 12 rows, history 'msg 24'..'msg 29' is on rows 0-5, the greeting on row 6, the hint on row 7, the rule on row 8, the composer on row 9, the bottom rule on row 10 and the status on row 11. The _text_view is top=0, rows=6, start=24, and its lines list holds all 30 entries, so the visible history rows map to the right lines. At 5 rows the history is dropped (rows=0) and the hint is on row 0, the rule on row 1, the composer on row 2, the bottom rule on row 3 and the status on row 4 (the last row). Nothing raised at either size. Not observed in a real terminal: live scrolling, a real mouse drag selecting a history line, and a live resize.

## None. Setup needed: install a terminal emulator (tmux or the pyte Python package) so the screen grid and cursor can be read back at 5 and 3 rows, or have a human eyeball it.

- **Status:** BLOCKED-SETUP
- **Evidence:** pty run script /tmp/mc204.py output: all 7 sizes 'alive True', 'traceback False'. python3 scripts/tests/home-layout-test.py: Ran 24 tests, OK. The probe is a fake-curses harness, not a live screen.
- **Expected result:** No crash or garbled screen; status on last row, bottom rule on row above; history only above composer and scrollable; cursor on last visible composer row.
- **Actual result:** Observed: process stayed alive after every resize and input, with no 'Traceback' in the output stream (61 KB). The layout probe (24 tests) passed; it includes the tiny-height cases (h=3 and h=2), status-last, rule at h-2, history above the composer and cursor on the last composer row. NOT observed: the real rendered screen, i.e. actual status/rule row positions and cursor placement on a live terminal at 5 and 3 rows, or visual garbling.

## None (the 24/50 vs 22/48 discrepancy is unconfirmed; a human should check it visually in a real terminal)

- **Status:** BLOCKED-HUMAN
- **Evidence:** Replay output at 24 rows: row 17 'What can uncle do for you?', row 18 hint line, row 22 'uncle-issue-187 · mode(auto)'. At 50 rows: row 40 prompt text, row 42 hint line, row 48 status line. Script at /tmp/pt.py. This is not a valid visual observation.
- **Expected result:** Status bar is on the very last terminal row, and no blank row separates the composer's bottom rule from the status line.
- **Actual result:** Inconclusive. The naive replay put the status line at CUP row 22 of 24 and row 48 of 50, which would leave one or two rows below it. But the replay is lossy: it did not render the composer rules fully, and it ignored incremental repaints, scroll and clear sequences. I therefore cannot confirm or refute the expected placement. The automated home-layout test (scripts/tests/home-layout-test.py) is the driver's concern and was not re-run here.

## None

- **Status:** BLOCKED-HUMAN
- **Evidence:** Pty script /tmp/mc304.py: alive=True after the 5-row resize; output tail shows the rule then the status text. home-layout-test.py: Ran 24 tests, OK. Driver checks log is the authority for the full suite and was not re-run.
- **Expected result:** History renders above the composer and scrolls. Mouse selection hits the correct rows. The status stays on the last row with the bottom rule above it, with no crash at the small size.
- **Actual result:** Process stayed alive after the resize to 5 rows and after wheel events. The last frame emitted at 5 rows ended with a horizontal rule followed by the status line ('claude-sonnet-5-5 (low) · Chat ready  uncle-issue-187 · mode(auto)') as the final row. Not observed live: the isolated HOME had no chat history, so history rendering and scrolling were not seen, and terminal mouse text selection is done by the terminal emulator and cannot be observed from a raw pty without a screen emulator (pyte not installed) or a human. Those parts are covered only by the unit tests (AC5 history newest shown, h3/h2 no raise and status last, tiny-height pinned rows), which pass.

## None. The blocker is setup: a pty or tmux-driven real terminal session, or a human, is needed to type into the chat panel and capture it.

- **Status:** BLOCKED-SETUP
- **Evidence:** Output of the ad-hoc probe: '' -> rules [12,14] status [15]; 'line one\nline two\n...' -> rules [12,14] status [15]; wrapped text -> rules [12,16] status [17]. The driver green-check covers test_AC4_chat_panel_default_not_anchored. A real-terminal capture was not obtained.
- **Expected result:** Chat panel composer and status placement behave as before the change (not bottom-anchored), with no layout corruption or exceptions, observed in a real terminal.
- **Actual result:** The simulated draw raised no exceptions. Empty composer: rules at rows 12 and 14, status on row 15, which is not the last row (39). Newline composer: same rows as the empty one, so embedded newlines did not add rows in this draw path. Wrapped composer: the bottom rule moved to row 16 and the status to row 17, so the block grows downward and the status is not pinned. This matches the hard-coded baseline offsets in the AC4 probe. The real-terminal observation with typed multi-line input was not performed.

## None

- **Status:** BLOCKED-HUMAN
- **Evidence:** None. No screenshots or pointer-versus-selection observations were captured.
- **Expected result:** History renders above the composer, scrolls, and mouse selection highlights the text under the pointer (no row offset); the status stays on the last row with no gap below the composer rule after each resize.
- **Actual result:** Not executed. The check needs a person to drag the mouse across history text in a real terminal and to resize the terminal window, then compare the selection with the pointer position. This worker has no pointer input or window-resize control. I did not infer a result from the driver green-check or from scripts/tests/home-layout-test.py.

## None

- **Status:** BLOCKED-HUMAN
- **Evidence:** python3 -I scripts/tests/home-layout-test.py -> 'Ran 24 tests in 0.061s OK'. Relevant tests: test_AC1_AC2_AC5_matrix_widths_heights_composer_rows, test_AC3_each_condition_visible_on_home, test_AC3_chat_error_wins_over_choices_and_slash, test_AC3_feedback_precedence_clip_and_no_free_row, test_AC5_cursor_on_last_visible_composer_row. No screenshots captured.
- **Expected result:** Composer growth moves the block up while status stays on the last row; feedback remains visible on one line not overlapping the status; hint text returns once feedback clears; cursor stays on the last visible composer row and the terminal shows no crash.
- **Actual result:** Probe: 24 tests ran, OK. Its tests cover status on last row across heights and composer rows, feedback precedence, one-line clip and no-free-row cases, compact feedback replacing the hint, and cursor on the last visible composer row. These are simulated draw calls only. No human-visible observation of a real terminal (screenshots at each state, cursor location, no crash) was made, and the checklist requires that evidence.
