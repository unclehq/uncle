# Verification report

## Findings

### MC-100

- **Action:** Launched ./uncle in a pseudo-terminal with the window size set before exec (24 rows x 100 cols, then 50 rows x 100 cols). Waited 8s on the home page with an empty composer, rendered the output through the pyte terminal emulator and printed every non-blank screen row. This was an emulated terminal, not a human looking at a physical terminal.
- **Expected result:** The status line (model/project/branch) is on the very last terminal row, and the composer's bottom rule sits directly above it with no blank row between them.
- **Actual result:** The bottom rule is directly above the status line (no blank row between them), but the status is NOT on the last terminal row. At 24 rows the rule is on row 21 and the status on row 22, leaving rows 23-24 blank. At 50 rows the rule is on row 46 and the status on row 48, with row 47 blank and rows 49-50 blank. An earlier run that set the size after fork showed the same 24-row layout with status on row 22. In both heights the status is 2 rows short of the bottom.
- **Defects:** None recorded yet: status line renders 2 rows above the last terminal row at 24 and 50 rows (expected the last row). Needs a DEFECTS.md entry from the driver.

### MC-101

- **Action:** Checked whether a real terminal could be driven and captured for the home page: looked for tmux and for the Python 'pyte' terminal emulator. Did not launch the app or observe the screen.
- **Expected result:** The status stays on the last row and the bottom rule stays directly above it while the composer wraps to 2, 4 and 6+ rows. The composer grows upward, the cursor stays on the last visible composer row, and the greeting, hint and logo text are unchanged.
- **Actual result:** Not observed. This environment has no tmux and no pyte, so there is no way to capture the screen of a curses TUI at a controlled size. The live observation was not performed.
- **Defects:** None

### MC-102

- **Action:** Rendered the real _draw_homepage (uncle_tui.py) via a narrow temporary probe (/tmp/mc102/p.py, reusing the fake-screen helper from scripts/tests/home-layout-test.py) at 40 rows (non-compact) and 14 rows (compact, LOGO=22 so threshold 34), width 80, for states: idle, slash ('/' composer), chat_error, and slash+chat_error together. A real interactive TUI/model was not driven; the chat error was injected by setting chat_error state.
- **Expected result:** One feedback line stays visible on a row other than the last row and never overlaps the status. In compact mode it replaces the hint and the hint returns when cleared. With several conditions, chat_error shows first.
- **Actual result:** h=40: feedback on row 35 (slash list or 'boom happened'), hint stays on row 34, rules at 36/38, status on row 39 (last). h=14: idle hint on row 9; with slash or error the feedback occupies row 9 and the hint is absent; idle again shows the hint on row 9. With both active, 'boom happened' is shown (chat_error first) at both heights. Status stays on the last row (39 / 13) in all cases with no overlap.
- **Defects:** None

### MC-103

- **Action:** Rendered the home page through the project's FakeScreen harness (scripts/tests/home-layout-test.py helpers) with 30 history entries at 12 rows and at 5 rows, and printed the draw calls and the _text_view mouse-selection mapping. Ran the 24-test home-layout suite, which passed. I did not run the app in a real terminal: no pty screen emulator (pyte) is installed, and no real resize, scroll or mouse drag was performed.
- **Expected result:** History renders above the greeting and composer block and is scrollable. Mouse selection hits the correct history rows. Nothing crashes at small sizes. At 5 rows the status is on the last row and the bottom rule is directly above it.
- **Actual result:** At 12 rows, history 'msg 24'..'msg 29' is on rows 0-5, the greeting on row 6, the hint on row 7, the rule on row 8, the composer on row 9, the bottom rule on row 10 and the status on row 11. The _text_view is top=0, rows=6, start=24, and its lines list holds all 30 entries, so the visible history rows map to the right lines. At 5 rows the history is dropped (rows=0) and the hint is on row 0, the rule on row 1, the composer on row 2, the bottom rule on row 3 and the status on row 4 (the last row). Nothing raised at either size. Not observed in a real terminal: live scrolling, a real mouse drag selecting a history line, and a live resize.
- **Defects:** None

### MC-200

- **Action:** Launched uncle_tui.py in a real pseudo-terminal (pty, TERM=xterm-256color) sized 24 rows x 100 cols, rendered the output through the pyte terminal emulator, and dumped the screen with an empty composer and after typing text that wrapped to 2, 3 and 6 composer rows.
- **Expected result:** Status text on the very last screen row; composer bottom rule directly above it with no blank row, at every wrap count.
- **Actual result:** Empty composer: rule on row 22, status on row 23 (last). 2 rows wrapped: rows 20-21 text, rule row 22, status row 23. 3 rows wrapped: text rows 19-21, rule row 22, status row 23. 6 rows wrapped: text rows 16-21, rule row 22, status row 23. The composer grew upward each time; there was never a blank row between the rule and the status. Note: the second step produced 3 wrapped rows rather than 4. The 2-6 range is still covered.
- **Defects:** None

### MC-202

- **Action:** Ran the prepared narrow probe subset (python3 scripts/tests/home-layout-test.py -v -k AC3) which renders the home page draw model and triggers chat error, file choice, and slash hint individually, in combination, and cleared, including compact height. No live interactive TUI session was driven.
- **Expected result:** One feedback line visible, never overlapping the status row; precedence chat error > file choice > slash hint; in compact height the hint is hidden only while feedback shows and returns when it clears.
- **Actual result:** All 7 AC3 tests passed: each condition visible on home; chat error beats choices and slash; choices beat slash; compact feedback replaces the hint at crow-2 and the hint returns when cleared; non-compact keeps the hint at crow-3; feedback never lands on pinned rows (h-1..h-3), including with no free row.
- **Defects:** None

### MC-204

- **Action:** Launched the real app (python3 uncle_tui.py) under a pty and resized it 24->5->3->24->5->3->24 rows (80 cols) with SIGWINCH, typing 150 chars (wrapped composer) and sending Up/PageUp/Down keys at each size. Also ran the fake-curses layout probe scripts/tests/home-layout-test.py (read-only). No terminal emulator (tmux/pyte) is installed, so the rendered screen was not read back.
- **Expected result:** No crash or garbled screen; status on last row, bottom rule on row above; history only above composer and scrollable; cursor on last visible composer row.
- **Actual result:** Observed: process stayed alive after every resize and input, with no 'Traceback' in the output stream (61 KB). The layout probe (24 tests) passed; it includes the tiny-height cases (h=3 and h=2), status-last, rule at h-2, history above the composer and cursor on the last composer row. NOT observed: the real rendered screen, i.e. actual status/rule row positions and cursor placement on a live terminal at 5 and 3 rows, or visual garbling.
- **Defects:** None. Setup needed: install a terminal emulator (tmux or the pyte Python package) so the screen grid and cursor can be read back at 5 and 3 rows, or have a human eyeball it.

### MC-301

- **Action:** Launched ./uncle under a pty (TERM=xterm, 100 cols) sized 24 and 50 rows and captured raw output for 6s; crudely replayed cursor-position escapes (no terminal emulator such as pyte available) to find the last painted rows. No real terminal or screenshot was available.
- **Expected result:** Status bar is on the very last terminal row, and no blank row separates the composer's bottom rule from the status line.
- **Actual result:** Inconclusive. The naive replay put the status line at CUP row 22 of 24 and row 48 of 50, which would leave one or two rows below it. But the replay is lossy: it did not render the composer rules fully, and it ignored incremental repaints, scroll and clear sequences. I therefore cannot confirm or refute the expected placement. The automated home-layout test (scripts/tests/home-layout-test.py) is the driver's concern and was not re-run here.
- **Defects:** None (the 24/50 vs 22/48 discrepancy is unconfirmed; a human should check it visually in a real terminal)

### MC-302

- **Action:** No real terminal was available (tmux and pyte are not installed). I rendered the real UncleTUI._draw_homepage from uncle_tui.py through the FakeScreen draw harness in scripts/tests/home-layout-test.py. The composer held text wrapping to 1, 3 and 7 rows at width 80, at heights 12, 24 and 40 (resize taller and shorter). I recorded the composer rows, the rule rows, the last-row content and the app-drawn cursor cell (A_REVERSE).
- **Expected result:** As the composer grows, the block moves up. The status stays on the last row, directly under the bottom rule, and the cursor sits on the last visible composer row.
- **Actual result:** The composer block moved up as rows grew. At h=24, the composer's first row was 21 with 1 row, 19 with 3 rows and 16 with 7 rows (display capped at 5 text rows). The bottom rule was always at h-2 (22 at h=24; 10 at h=12; 38 at h=40). Status text was drawn on row h-1 in every case, with no blank row between the rule and the status. The cursor cell was always on row h-3, the last composer text row (9 at h=12, 21 at h=24, 37 at h=40). The same held after changing height.
- **Defects:** None

### MC-303

- **Action:** The home page is a curses TUI, not a browser page. Drove UncleTUI._draw_homepage through the repo's FakeScreen harness (temporary probe /tmp/mc303/p.py) at h=24 (compact) and h=60. Set composer '/', then added chat_choices ['x.py'], then chat_error 'boom happened', and finally returned to the slash-only state. Recorded the rows drawn near the bottom. This is an emulated draw, not a real terminal session or a real chat error or file pick.
- **Expected result:** One feedback line is visible and does not overlap the status row. Precedence is chat_error, then file choice, then slash hint. The hint text returns when the feedback clears.
- **Actual result:** At h=24 the status row is 23 and the feedback line is on row 19, with the composer on row 21 and rules on rows 20 and 22. Slash only: '/configure /settings /file /quit /issue # /require...' replaced the idle '/ commands' hint. Slash plus choices: 'File: x.py'. Error plus choices plus slash: 'boom happened'. Back to slash only: the slash hint returned on the same row. At h=60 the feedback is on row 55, the idle hint on row 54 and the status on row 59. Exactly one feedback line appeared per state, and none landed on the status row. The idle state restored the '/ commands @ files # issues' hint at h=24.
- **Defects:** None

### MC-304

- **Action:** Launched the real uncle_tui.py in a pty (isolated empty HOME) at 24x80, sent mouse-wheel escape sequences, resized the pty to 5 rows (SIGWINCH), sent another wheel event, and inspected the raw output and process liveness. Also re-ran scripts/tests/home-layout-test.py (24 tests, OK).
- **Expected result:** History renders above the composer and scrolls. Mouse selection hits the correct rows. The status stays on the last row with the bottom rule above it, with no crash at the small size.
- **Actual result:** Process stayed alive after the resize to 5 rows and after wheel events. The last frame emitted at 5 rows ended with a horizontal rule followed by the status line ('claude-sonnet-5-5 (low) · Chat ready  uncle-issue-187 · mode(auto)') as the final row. Not observed live: the isolated HOME had no chat history, so history rendering and scrolling were not seen, and terminal mouse text selection is done by the terminal emulator and cannot be observed from a raw pty without a screen emulator (pyte not installed) or a human. Those parts are covered only by the unit tests (AC5 history newest shown, h3/h2 no raise and status last, tiny-height pinned rows), which pass.
- **Defects:** None

### MC-401

- **Action:** Could not start a real build run in a live terminal. Instead I loaded uncle_tui.py's real _draw_chat_composer with state='running' on a fake 30-row screen, using the make() helper from scripts/tests/home-layout-test.py, and printed every draw call. I did this in both non-compact and compact modes. I called it the way the build page's _draw_chat_panel does, without anchor_bottom.
- **Expected result:** Build page layout unchanged: status row sits two rows below the composer row (directly after the bottom rule, no blank row), is not forced to the last screen row, and greeting/hint/status text is unchanged.
- **Actual result:** Non-compact, 30 rows, first row 14: greeting on 15, hint on 17, top rule on 19, composer on 20, bottom rule on 21, status on 22. The status is at composer+2, with no blank row after the rule, and is not on the last row (29). Compact: hint on 14, top rule on 15, composer on 16, bottom rule on 17, status on 18, again at composer+2 and not pinned to the last row. Text is unchanged: 'What can uncle do for you?', '/homepage to leave   / commands   @ files   # issues   Tab t...', 'Talk to uncle while he builds', 'Configure a model  ·  Chat ready'. The driver green-check's BuildAndPanelUnchanged tests (literal baseline offsets) cover the same layout. I did not look at a real terminal screen.
- **Defects:** None

### MC-402

- **Action:** Tried to open the chat panel in a real terminal. tmux is not installed and I did not get a pty-driven TUI session. Instead I imported uncle_tui.py through the home-layout-test harness (FakeScreen, state 'menu') and called _draw_chat_composer(10, 40, 80, 2, 76) with three composers: empty, a three-line message with newlines, and a 3-row wrapped message.
- **Expected result:** Chat panel composer and status placement behave as before the change (not bottom-anchored), with no layout corruption or exceptions, observed in a real terminal.
- **Actual result:** The simulated draw raised no exceptions. Empty composer: rules at rows 12 and 14, status on row 15, which is not the last row (39). Newline composer: same rows as the empty one, so embedded newlines did not add rows in this draw path. Wrapped composer: the bottom rule moved to row 16 and the status to row 17, so the block grows downward and the status is not pinned. This matches the hard-coded baseline offsets in the AC4 probe. The real-terminal observation with typed multi-line input was not performed.
- **Defects:** None. The blocker is setup: a pty or tmux-driven real terminal session, or a human, is needed to type into the chat panel and capture it.

### MC-403

- **Action:** Read the MC-403 row from the canonical checklist JSON. No live action was performed.
- **Expected result:** History renders above the composer, scrolls, and mouse selection highlights the text under the pointer (no row offset); the status stays on the last row with no gap below the composer rule after each resize.
- **Actual result:** Not executed. The check needs a person to drag the mouse across history text in a real terminal and to resize the terminal window, then compare the selection with the pointer position. This worker has no pointer input or window-resize control. I did not infer a result from the driver green-check or from scripts/tests/home-layout-test.py.
- **Defects:** None

### MC-404

- **Action:** Ran the prepared headless draw-level probe scripts/tests/home-layout-test.py (python3 -I) to inspect composer growth, feedback precedence/clipping, hint return and cursor row. Did not drive a live interactive terminal session: typing a 6+ row message, '/', and triggering a chat error or file choice in a real TUI were not performed.
- **Expected result:** Composer growth moves the block up while status stays on the last row; feedback remains visible on one line not overlapping the status; hint text returns once feedback clears; cursor stays on the last visible composer row and the terminal shows no crash.
- **Actual result:** Probe: 24 tests ran, OK. Its tests cover status on last row across heights and composer rows, feedback precedence, one-line clip and no-free-row cases, compact feedback replacing the hint, and cursor on the last visible composer row. These are simulated draw calls only. No human-visible observation of a real terminal (screenshots at each state, cursor location, no crash) was made, and the checklist requires that evidence.
- **Defects:** None

## Acceptance gate

| ID | Required | Status | Evidence |
|---|---|---|---|
| MC-100 | YES | FAIL | 24-row capture: 17 'What can uncle do for you?', 18 hint, 19 rule, 20 '› Describe an app or a change…', 21 rule, 22 'claude-sonnet-5-5 (low) · Chat ready ... uncle-issue-187 · mode(auto)', rows 23-24 blank. 50-row capture: 40 greeting, 42 hint, 44 rule, 45 composer, 46 rule, 48 status, rows 47, 49, 50 blank. Emulation caveat: results come from pyte rendering of the pty stream; a real-terminal visual confirmation was not performed. Other rows were not independently re-examined. |
| MC-101 | YES | BLOCKED-SETUP | 'which tmux' returned exit 1 (not found). 'import pyte' raised ModuleNotFoundError. scripts/tests/home-layout-test.py drives a FakeScreen, not a real terminal, so it is not live evidence. It is covered by the driver green-check, which this worker did not rerun or cite as a pass for this row. Action to unblock: install tmux (or pyte), or have a human run ./uncle in a real terminal and type text that wraps to 2, 4 and 6+ rows. |
| MC-102 | YES | PASS | Probe output: 40 error -> row35 'boom happened', row34 hint, row39 status; 40 both -> row35 'boom happened'; 14 slash -> row9 '/configure /settings /file /quit...'; 14 error -> row9 'boom happened' (hint gone); 14 idle -> row9 hint; 14 both -> row9 'boom happened'; status row 13 'Configure a model · Chat ready'. |
| MC-103 | YES | BLOCKED-HUMAN | Output of /tmp/mc103.py (draw coordinates and _text_view as above). `python3 -m unittest scripts/tests/home-layout-test.py` ran 24 tests, OK. Layout and selection-mapping logic is verified. The interactive scroll and mouse-selection parts need a human in a real terminal. |
| MC-200 | YES | PASS | Pyte screen dumps from the temporary harness /tmp/mc200/run.py. Last two rows in every state: row 22 = '────…' rule, row 23 = 'claude-sonnet-5-5 (low)  ·  Chat ready   uncle-issue-187  ·  mode(auto)'. The greeting block moved from rows 18-19 to 17-18, 16-17 and 13-14 as the composer grew. |
| MC-202 | YES | PASS | Ran 7 tests in 0.002s, OK (test_AC3_each_condition_visible_on_home, test_AC3_chat_error_wins_over_choices_and_slash, test_AC3_choices_win_over_slash, test_AC3_compact_feedback_replaces_hint_at_crow_minus_2, test_AC3_non_compact_feedback_at_crow_minus_2_hint_stays, test_AC3_no_free_row_feedback_never_lands_on_pinned_rows, test_AC3_feedback_precedence_clip_and_no_free_row). This is a render-model probe, not a human-visible terminal observation. |
| MC-204 | YES | BLOCKED-SETUP | pty run script /tmp/mc204.py output: all 7 sizes 'alive True', 'traceback False'. python3 scripts/tests/home-layout-test.py: Ran 24 tests, OK. The probe is a fake-curses harness, not a live screen. |
| MC-301 | YES | BLOCKED-HUMAN | Replay output at 24 rows: row 17 'What can uncle do for you?', row 18 hint line, row 22 'uncle-issue-187 · mode(auto)'. At 50 rows: row 40 prompt text, row 42 hint line, row 48 status line. Script at /tmp/pt.py. This is not a valid visual observation. |
| MC-302 | YES | PASS | Probe output (/tmp/mc302.py). Rows: 'rows h composerfirst rules cursor': 1 24 [21] rules [20,22] cursor (21,75); 3 24 [19] rules [18,22] cursor (21,75); 7 24 [16] rules [15,22] cursor (21,75); 3 12 [7] rules [6,10] cursor (9,75); 7 40 [32] rules [31,38] cursor (37,75). The status row was h-1 in all 9 cases. Limitation: this is a render-level observation of the real draw code, not a visual capture in a real terminal. |
| MC-303 | YES | PASS | Probe output: h=24 error+choices+slash -> (19,'boom happened'), status at (23,...); choices+slash -> (19,'File: x.py'); cleared->slash -> (19,'/configure /settings ...'). h=60 error -> (55,'boom happened'), status (59). The driver green-check also covers FeedbackRows and FeedbackVisible in scripts/tests/home-layout-test.py. The live-terminal part of the action (a real chat error and a real file choice) was not exercised. |
| MC-304 | YES | BLOCKED-HUMAN | Pty script /tmp/mc304.py: alive=True after the 5-row resize; output tail shows the rule then the status text. home-layout-test.py: Ran 24 tests, OK. Driver checks log is the authority for the full suite and was not re-run. |
| MC-401 | YES | PASS | Draw list printed from /tmp/mc401/p.py (rows as above). Source: uncle_tui.py:7337 (anchored = anchor_bottom and not build) and uncle_tui.py:7445 (status_row = composer_row + extra + 2 when build). |
| MC-402 | YES | BLOCKED-SETUP | Output of the ad-hoc probe: '' -> rules [12,14] status [15]; 'line one\nline two\n...' -> rules [12,14] status [15]; wrapped text -> rules [12,16] status [17]. The driver green-check covers test_AC4_chat_panel_default_not_anchored. A real-terminal capture was not obtained. |
| MC-403 | YES | BLOCKED-HUMAN | None. No screenshots or pointer-versus-selection observations were captured. |
| MC-404 | YES | BLOCKED-HUMAN | python3 -I scripts/tests/home-layout-test.py -> 'Ran 24 tests in 0.061s OK'. Relevant tests: test_AC1_AC2_AC5_matrix_widths_heights_composer_rows, test_AC3_each_condition_visible_on_home, test_AC3_chat_error_wins_over_choices_and_slash, test_AC3_feedback_precedence_clip_and_no_free_row, test_AC5_cursor_on_last_visible_composer_row. No screenshots captured. |
