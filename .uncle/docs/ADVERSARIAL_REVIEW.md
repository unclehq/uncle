## AR-001: Feedback placement contradicts the unchanged-hint rule in compact mode.

- Severity: HIGH
- References: CHANGE_PLAN D-2 vs CHANGE_SPEC S-7 and AC-3.
- Failure: Feedback placement contradicts the unchanged-hint rule in compact mode. D-2 replaces the hint row with feedback, but S-7/AC-4 say hints are unchanged. Plan should say: 'In compact anchored mode the feedback line replaces the hint row only while feedback is active; the hint is redrawn when it clears.'
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-002: AC-1 covers only h>=12, but V-1 and AC-2 demand adjacency everywhere.

- Severity: HIGH
- References: CHANGE_SPEC AC-1 (h>=12) vs V-1/AC-5 (5x20, 1x10); CHANGE_PLAN s12.
- Failure: AC-1 covers only h>=12, but V-1 and AC-2 demand adjacency everywhere. Behavior for h<12, or a composer taller than the screen, is unspecified. Plan should say: 'Status stays at h-1 and the bottom rule at h-2 whenever h>=2; upper rows are clipped from the top.'
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-003: Clamping row to >=0 conflicts with keeping the status at h-1 with adjacency.

- Severity: MEDIUM
- References: CHANGE_PLAN s12 and Risk row 3 ('clamp row >= 0') vs s1 (status_row == h-1).
- Failure: Clamping row to >=0 conflicts with keeping the status at h-1 with adjacency. A raised row would move the composer or bottom rule. Plan should say: 'The clamp applies only to upper rows (greeting, hint, top rule); composer, bottom rule and status positions derive from h-1 and are never raised.'
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-004: History area size is unspecified when the shifted block leaves no space, e.g.

- Severity: MEDIUM
- References: CHANGE_PLAN s1 (body_rows/top) and AC-5.
- Failure: History area size is unspecified when the shifted block leaves no space, e.g. a 6+ row composer. It is unclear whether body_rows goes to 0 or negative, and what _text_view holds. Plan should say: 'body_rows = max(0, greeting_block_start - top); with 0 rows no history is drawn and _text_view is empty.'
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-005: Cursor placement when anchored is unspecified.

- Severity: MEDIUM
- References: CHANGE_SPEC V-4 vs CHANGE_PLAN s1.
- Failure: Cursor placement when anchored is unspecified. V-4 says the cursor stays on the composer row, but the composer now moves as it wraps and may be clipped. Plan should say: 'The cursor goes on the last wrapped composer row at the computed column, clamped to the screen.'
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-006: D-2 provides one feedback row, but three feedback conditions (chat_error, file choice, slash hint) can be active togethe

- Severity: LOW
- References: CHANGE_PLAN D-2 (single row at row+4) vs CHANGE_SPEC AC-3.
- Failure: D-2 provides one feedback row, but three feedback conditions (chat_error, file choice, slash hint) can be active together. Priority is unspecified. Plan should say: 'When several are active, show chat_error first, then file choice, then slash hint; only one is drawn.'
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-007: AC-1/AC-2 hold for h>=12, but the plan clamps row>=0 and keeps status at h-1 on tiny terminals, so V-1 adjacency can't h

- Severity: HIGH
- References: CHANGE_SPEC AC-1 says h>=12, AC-2 has no height bound; CHANGE_PLAN section 12 and risk row 3 clamp row>=0.
- Failure: AC-1/AC-2 hold for h>=12, but the plan clamps row>=0 and keeps status at h-1 on tiny terminals, so V-1 adjacency can't hold there. Plan should say: below the height that fits all rows, only status==h-1 and no exception are required, and upper rows drop in order greeting, hint, top rule.
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-008: The plan doesn't say what happens when the wrapped composer rows exceed the available space.

- Severity: HIGH
- References: CHANGE_PLAN section 1 pre-computes extra with no cap; the test strategy says '6+' rows.
- Failure: The plan doesn't say what happens when the wrapped composer rows exceed the available space. Anchoring derives row from extra, so a 6+ row composer can cover history or go negative. Plan should say: composer rows are capped at min(extra, h-4), with the cursor on the last visible composer row (V-4).
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-009: D-2 hides the compact hint while feedback is active, which conflicts with S-5/S-7 (hint text unchanged).

- Severity: MEDIUM
- References: CHANGE_PLAN D-2 vs CHANGE_SPEC S-5, S-7 and AC-3.
- Failure: D-2 hides the compact hint while feedback is active, which conflicts with S-5/S-7 (hint text unchanged). Behavior is also unspecified when the greeting is hidden or the feedback text is wider than the terminal. Plan should say: the hint is intentionally hidden during feedback in compact mode, and S-7 carves out this exception.
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-010: The history area (body_rows/top) is undefined when the shifted block leaves zero or negative rows above it, so the _text

- Severity: MEDIUM
- References: CHANGE_PLAN section 1 and risk row 1 say top equals the first history row, with no rule for body_rows<=0.
- Failure: The history area (body_rows/top) is undefined when the shifted block leaves zero or negative rows above it, so the _text_view mouse mapping is unspecified. Plan should say: when body_rows<=0, no history is drawn and _text_view is an empty region.
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-011: The AC-4 baseline offsets are cited but never given as values, so the regression test has no recorded oracle.

- Severity: MEDIUM
- References: CHANGE_SPEC AC-4 'status = composer_row + extra + 2'; CHANGE_PLAN section 10 gives no numbers.
- Failure: The AC-4 baseline offsets are cited but never given as values, so the regression test has no recorded oracle. Plan should say: baseline offsets are captured as literal constants in the test, taken from the unmodified code before the change.
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-012: Compact mode with feedback active is ambiguous: D-2 says feedback replaces the hint row, but the plan never says how lon

- Severity: MEDIUM
- References: CHANGE_PLAN D-2 and CHANGE_SPEC AC-3; the plan never states clipping or hint suppression.
- Failure: Compact mode with feedback active is ambiguous: D-2 says feedback replaces the hint row, but the plan never says how long text is clipped or whether the hint is hidden. Add: 'In compact anchored mode, feedback is clipped to the screen width at row+1 and the hint is not drawn while feedback is active.'
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-013: Feedback text carries user-controlled content (a file choice, or a chat_error that may embed a path or typed text).

- Severity: LOW
- References: CHANGE_PLAN D-2 relocates feedback drawing and says nothing about sanitization; S-7 only requires that the text be unchanged.
- Failure: Feedback text carries user-controlled content (a file choice, or a chat_error that may embed a path or typed text). The plan does not say it is stripped of control characters before addnstr. Add: 'Feedback and composer text is drawn through put with non-printable characters replaced, unchanged from the current behavior.'
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-014: AC-1 requires status on h-1 only for h>=12, while AC-5 and plan section 12 cover h<12 (5x20, 1x10).

- Severity: HIGH
- References: CHANGE_SPEC AC-1 ('at least 12 rows') vs AC-5 and CHANGE_PLAN section 12; the plan's own test heights include 5.
- Failure: AC-1 requires status on h-1 only for h>=12, while AC-5 and plan section 12 cover h<12 (5x20, 1x10). The plan doesn't say whether status must be on h-1 at tiny heights. Settle it: 'For h<12 only no-exception, in-bounds writes and history above the composer are asserted; status is on h-1 whenever h>=2.'
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-015: The plan never says which rows win when the composer's 1 to 6+ wrapped rows plus greeting, hint and rules exceed the hei

- Severity: HIGH
- References: CHANGE_PLAN section 12 ('upper rows clip via put') vs section 16 ('1..6+ wrapped rows' at height 5) and V-4.
- Failure: The plan never says which rows win when the composer's 1 to 6+ wrapped rows plus greeting, hint and rules exceed the height. Settle it: 'Priority from h-1 upward: status, bottom rule, composer rows (newest kept, cursor row visible), top rule, hint, greeting; lower-priority rows are dropped, never overlapped.'
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-016: D-2 places feedback on row+4 (or over the hint in compact mode) but doesn't cover clipping, several feedbacks active at

- Severity: HIGH
- References: CHANGE_PLAN D-2 and AC-3 ('each feedback condition').
- Failure: D-2 places feedback on row+4 (or over the hint in compact mode) but doesn't cover clipping, several feedbacks active at once, or multi-row file choices. Settle it: 'At most one feedback line is drawn (error, then file choice, then slash hint); with no free row it replaces the hint row, then the greeting.'
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-017: The plan has no definition of 'compact', yet tests parametrize compact and non-compact heights.

- Severity: MEDIUM
- References: CHANGE_SPEC AC-2; CHANGE_PLAN D-1 and risk row 3 cite line 7323 with no threshold.
- Failure: The plan has no definition of 'compact', yet tests parametrize compact and non-compact heights. Settle it: 'Compact is the existing condition at line 7323, stated as a height threshold, and each test height {5,12,20,30,50} is labeled compact or non-compact.'
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-018: The plan doesn't say how long history is cut or what _text_view['top'] is with empty history.

- Severity: MEDIUM
- References: CHANGE_PLAN section 1 (body_rows/top) and risk row 1; AC-5.
- Failure: The plan doesn't say how long history is cut or what _text_view['top'] is with empty history. Settle it: 'History shows the newest entries that fit above the greeting block; with no history rows, _text_view[top] is the greeting row.'
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-019: AC-4 says build status = composer_row + extra + 2, but the plan's alternative A calls the old offset '+3'.

- Severity: MEDIUM
- References: CHANGE_SPEC AC-4 vs CHANGE_PLAN section 2 alternative A ('+3').
- Failure: AC-4 says build status = composer_row + extra + 2, but the plan's alternative A calls the old offset '+3'. The offsets conflict and no fixed oracle is named. Settle it: 'The test hard-codes the baseline build offsets from BASELINE_REPORT B-3 rather than computing them from the code under test.'
- Fix: Address in the plan.
- Verify: Re-run the check.

## Overall assessment

Review findings require disposition.
