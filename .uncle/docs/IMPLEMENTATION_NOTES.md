# Implementation notes

### Files changed

- `uncle_tui.py` — Home page bottom anchoring: new _home_anchor helper; _draw_chat_composer(anchor_bottom=True) pins status to row h-1 and bottom rule to h-2; _draw_homepage sizes history above the anchored block; feedback moved above the status. Composer rows capped at min(count, 6, h-3).; 2; S-1..S-5, S-8, V-1, V-2, V-4
- `scripts/tests/home-layout-test.py` — New fake-screen test (19 tests) for AC-1..AC-5; fixed body-rows-zero case to h=6, where the anchored block starts at row 0.; 1; V-1, V-2, V-3, V-4

### Unresolved concerns

- No live-terminal run of the TUI was performed; layout is verified with a fake curses screen only.

## Acceptance delivery

| ID | Status | Changed code | Observed targeted verification |
|---|---|---|---|
| AC-1 | IMPLEMENTED | uncle_tui.py _draw_chat_composer: status_row = h-1 when anchored | python3 scripts/tests/home-layout-test.py: Ran 19 tests OK (test_AC1_status_on_last_row_at_24_and_50) |
| AC-2 | IMPLEMENTED | uncle_tui.py _home_anchor/_draw_chat_composer: bottom rule at h-2 directly above status, composer capped at 6 rows | home-layout-test OK (test_AC2_no_gap_between_bottom_rule_and_status, test_AC2_non_compact_block_offsets) |
| AC-3 | IMPLEMENTED | uncle_tui.py _draw_chat_composer: feedback_row = composer_row-2 when anchored; hint suppressed in compact when feedback active | home-layout-test OK (test_AC3_* four tests) |
| AC-4 | IMPLEMENTED | uncle_tui.py: anchor_bottom defaults False, so build page and chat panel offsets are unchanged | home-layout-test OK (test_AC4_* five tests, hard-coded baseline offsets) |
| AC-5 | IMPLEMENTED | uncle_tui.py _draw_homepage: body_rows = block_start - top; empty _text_view at 0 rows; tiny heights guarded | home-layout-test OK (test_AC5_* six tests); scripts/tests/home-actions-test.py Ran 39 tests OK |
| AC-6 | IMPLEMENTED | No change; driver owns the full suites | Full suites not run here (driver pending). home-actions-test.py OK as a related check. |
