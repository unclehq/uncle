# Change Plan — Issue 187

Seeded from [unclehq/uncle#187](https://github.com/unclehq/uncle/issues/187).

Issue 187

Omitted sections: Schema/persistence (none); Concurrency (single-threaded draw); Migration (none); Feature flag (none, pure layout); Observability (none)

## 1. Selected technical approach

Home-page-only bottom anchoring. `_draw_chat_composer` gains a keyword `anchor_bottom=False`. `_draw_homepage` passes `anchor_bottom=True`; `_draw_chat_panel` and the build page keep the default, so their layout is untouched.
When anchored (and not build), `_draw_chat_composer` pre-computes the composer's wrapped row count `extra` using the same wrapping, then caps the drawn composer rows at `min(extra, h-4)` (newest rows kept, cursor on the last visible composer row, per V-4). It derives `row` so that `status_row == h-1` with the status directly after the bottom rule (offset 2, no blank row; compact and non-compact both use offset 2). Rows above (greeting, hint, top rule) are placed at their existing relative offsets from the shifted `row`. The pre-existing relative offsets between greeting/hint/top rule/composer are kept so only the distance below the composer changes.
Priority when height is insufficient, from h-1 upward: status, bottom rule, composer rows, top rule, hint, greeting; lower-priority rows are dropped, never overlapped. Status stays at h-1 and the bottom rule at h-2 whenever h>=2. Full adjacency and the exact layout (AC-1/AC-2) are guaranteed only at heights that fit all rows; below that, only status==h-1 and no exception are required.
`_draw_homepage` sets `body_rows`/`top` so history fills the space above the shifted block (history area ends where the greeting block begins): `body_rows = max(0, greeting_block_start - top)`, where greeting_block_start is the first row of the shifted block that is actually drawn. `body_rows` is never negative. When `body_rows` is 0, no history is drawn and `_text_view` is an empty region (zero rows, no mouse-selectable rows). Otherwise `_text_view` coordinates are derived from `top` as before and match the first drawn history row, and the newest entries that fit are shown.

History cutting rule: history shows the newest entries that fit above the greeting block, i.e. `body_rows = max(0, greeting_block_start - top)` rows, oldest rows cut first. When there are no history rows to draw (empty history or body_rows == 0), `_text_view['top']` equals the greeting row (the first row of the shifted block); otherwise `_text_view['top']` equals the first drawn history row.

## 2. Alternatives considered

| Alt | Result |
|---|---|
| A. Just change `+3` to `+2` | Removes gap but status not at bottom; rejected |
| B. Draw status in a separate function at h-1 and leave composer where it is | Leaves gap between rule and status when slack exists; fails AC-2; rejected |
| C. Anchor whole composer block to bottom (selected) | Satisfies both |

Offset note: the `+3` in alternative A is the home-page composer-to-status distance (a blank row between the bottom rule and status) before the change. The build page's baseline distance is a separate value, status = composer_row + extra + 2 (BASELINE_REPORT B-3), and stays unchanged. The two are not in conflict.

## 3. Why preferred
Only C meets both "very bottom" and "no gap" simultaneously with a small change surface.

## 4. Exact components to modify
`uncle_tui.py`: `_draw_homepage` (7168-7257), `_draw_chat_composer` (7313-7430). New test `scripts/tests/home-layout-test.py`.

## 5. Components not to modify
`_draw_running`, `_draw_chat_panel` body, status text construction (7386-7410), logo, hints, workflow scripts, existing tests.

## 6. Data-flow / 7. State-transition / 8. Interface changes
No data-flow or state changes. Interface: one optional keyword argument `anchor_bottom` on private `_draw_chat_composer`; default preserves all existing callers.

## 10. Compatibility strategy

Default `anchor_bottom=False` retains current offsets exactly for build page and chat panel (AC-4). The baseline offsets are captured as literal integer constants in `home-layout-test.py`, taken by running the unmodified code (and recorded from BASELINE_REPORT) before the change; the test never derives them from the code under test.

## 12. Error and recovery behavior

All draws stay guarded by `put`/`curses.error`. Row priority when the screen is too short, from h-1 upward: status, bottom rule, composer rows, top rule, feedback/hint, greeting. Status stays at h-1 whenever h>=2 and the bottom rule at h-2. Composer rows are capped at `min(extra, h-4)`, newest kept, with the cursor on the last visible composer row. Remaining upper rows are dropped in the order greeting, hint, top rule, never overlapped. The clamp applies only to upper rows; composer, bottom rule and status positions derive from h-1 and are never raised. No negative-row writes occur and no exception is raised at any height. Tiny-height contract: for h<12 only no-exception, in-bounds writes and history drawn above the composer are asserted (AC-1's h>=12 bound is the guarantee for full adjacency/layout). Feedback and composer text is drawn through `put` with non-printable characters replaced, unchanged from the current behavior.

## Decisions

| ID | Decision | Reason |
|---|---|---|
| D-1 | Bottom anchoring applies to both compact and non-compact home layouts. 'Compact' is exactly the existing condition in `_draw_chat_composer` (the greeting-hide check near uncle_tui.py:7323), which the implementer must restate as a literal height threshold `h < H_COMPACT` in the test, read from the unmodified code before the change. Test heights are labeled in the test: 5 = compact, and each of 12, 20, 30, 50 is labeled compact or non-compact by evaluating that same threshold. | Issue says pinned to very bottom; compact had no gap already. A concrete, recorded threshold lets tests label each height unambiguously. |
| D-2 | At most one feedback line is drawn, chosen by fixed precedence: chat_error, then file choice, then slash hint. Text is clipped to the screen width and drawn through `put` as today. Non-compact: row+4 (the former blank row between hint and top rule). Compact anchored mode: the feedback line is drawn at row+1 and replaces the hint row only while feedback is active; the hint is redrawn when feedback clears. If no free row exists it replaces the hint row, then the greeting row. This is the sole intentional exception to the unchanged-hint rule (S-7/S-5). | Status owns h-1 so status_row+1 is off-screen; feedback must stay visible (AC-3) without adding a gap below the composer. A single row requires a fixed precedence; compact has no spare row, so the hint yields to feedback only transiently and is never permanently altered. AC-3 and s11.1 test each precedence, clipping and fallback case. |
| D-4 | When anchored, the cursor is placed on the last visible wrapped composer row at the computed column, clamped to the screen bounds. | The composer moves as it wraps and may be clipped, so the cursor must follow the last visible composer row (V-4). |
| D-3 | Test uses a fake `stdscr` recording `addnstr(y,x,text,...)` calls; TUI instance built via `object.__new__` with the minimal attributes `_draw_homepage` reads, stubbing helpers like `menu_items`, `chat_entries`, `_background_status`, `_next_run_unattended`, `test_execution_status` | No existing harness; avoids a real terminal |

## 14. Rollback plan
Revert `uncle_tui.py` and delete `scripts/tests/home-layout-test.py` (`git checkout -- uncle_tui.py`). No persisted state or migration.

## 16. Automated-test strategy

Added cases: (a) overflow priority: with composer rows exceeding available space, assert status at h-1, bottom rule at h-2, newest composer rows kept, and lower-priority rows dropped with no two draws sharing a row; (b) feedback: with chat_error, file choice and slash hint active together only the chat_error line is drawn, each alone is drawn, long text is clipped to width, and with no free row it replaces the hint row, then the greeting.

New `scripts/tests/home-layout-test.py` (hyphenated name so `run-python-tests.sh` collects it) covering AC-1..AC-5 over heights {5,12,20,30,50} and widths {20,40,80,120}, composer text lengths giving 1..6+ wrapped rows (including counts exceeding h-4, which must be capped at min(extra, h-4) with the cursor on the last visible composer row), with and without history, and each feedback condition. For heights that fit all rows (h>=12), assert the exact AC-1/AC-2 layout (including adjacency). For smaller heights (h<12), assert only: no exception, all writes in bounds, history above the composer, and status on h-1 whenever h>=2. Feedback/composer text sanitization (non-printable characters replaced via `put`) is unchanged and asserted by checking a control character in feedback is not written raw. Uses Python unittest; no new dependencies. It must fail on the pre-change code for AC-1 and AC-2 (run once against the unmodified `uncle_tui.py` via `git stash`-free means: write test first, run it, confirm failure, then implement).

Small-height rule (AR-002): whenever h>=2 the status is on row h-1 and the bottom rule on row h-2, with upper rows (composer, top rule, hint, greeting) clipped from the top; this holds for every tested height including h<12 (e.g. 5x20). For h<12 the tests assert status on h-1, bottom rule on h-2, no exception, all writes in bounds, and history (if any) above the composer.

## 17. Regression-test strategy

Build-state assertions (AC-4) plus the driver's full shell/Python suite comparison (AC-6). The AC-4 test hard-codes the baseline build-page offsets as literal constants taken from BASELINE_REPORT B-3 (status = composer_row + extra + 2, measured on the unmodified code). It never computes them from the code under test, so the oracle is independent of the change. All draws stay guarded by `put`/`curses.error`. If `h` is too small to place all rows, the status keeps `h-1` and upper rows clip via the existing `put` bounds check. The clamp (row >= 0, skip negative-row writes) applies only to the upper rows (greeting, hint, top rule); the composer rows, bottom rule and status positions derive from `h-1` and are never raised by the clamp.

## 18. Manual-verification strategy
Launch `./uncle` in a real terminal at ~24 and ~50 rows; confirm status is the last row with no blank line under the composer rule; type a long message and `/` to see feedback; start a run and confirm build page unchanged. Terminal use is a human/checklist item.

## Change-impact table

| Component | Planned change | Reason | Regression risk | Test coverage |
|---|---|---|---|---|
| `uncle_tui.py` `_draw_chat_composer` | Add `anchor_bottom` param; compute shifted row and offset-2 status; relocate feedback when anchored | AC-1..3 | Medium: shared with build page | home-layout-test (AC-4), asserting hard-coded baseline build offsets from BASELINE_REPORT B-3 |
| `uncle_tui.py` `_draw_homepage` | Pass `anchor_bottom=True`; size history area as `body_rows = max(0, greeting_block_start - top)`; empty `_text_view` when 0 rows | AC-1, AC-5 | Medium: `_text_view` coordinates | home-layout-test (AC-5) |
| `scripts/tests/home-layout-test.py` | New | Verification | Low | self |

## Traceability

| Requirement | Behavior | Invariant | Component | Automated test | Manual check |
|---|---|---|---|---|---|
| AC-1 | S-1 | V-1 | _draw_chat_composer | home-layout-test status_on_last_row | Run at 24/50 rows |
| AC-2 | S-2, S-3, S-4 | V-1 | _draw_chat_composer | home-layout-test no_gap | Visual check |
| AC-3 | S-5 | V-2 | _draw_chat_composer | home-layout-test feedback_visible (each condition alone; all active together draws only chat_error, then file choice over slash hint; non-compact feedback at row+4; compact feedback at row+1 clipped to width, hint absent while active and redrawn after clear), home-layout-test feedback_precedence_clip_and_no_free_row | Type `/` and long text |
| AC-4 | S-6, S-7 | V-3 | _draw_chat_composer | home-layout-test build_unchanged (compares against literal baseline offset constants from unmodified code) | Start a run |
| AC-5: history stays above the anchored block with `_text_view` consistent. The history area is body_rows = max(0, greeting_block_start - top) and shows the newest entries that fit; with 0 rows no history is drawn and `_text_view` is empty with its top at the greeting row; otherwise `_text_view['top']` equals the first drawn history row. The cursor is on the last visible wrapped composer row at the computed column, clamped to the screen (D-4). For heights below those that fit all rows, only these are required: no exception, in-bounds writes, status on row h-1 (h>=2), composer rows capped at min(extra, h-4), and history above the composer. | S-8 | V-2, V-4 | _draw_homepage | home-layout-test tiny_and_history (includes cursor row/column assertion), home-layout-test row_priority_overflow | Scroll history |
| AC-6 | all | all | whole repo | driver suites | n/a |

## Restrictions
| R-ID | Source | Requirements | Property | Mechanism | Rationale | CAP | Phase |
|---|---|---|---|---|---|---|---|
| R-1 | USER, CHANGE_REQUEST.md Summary/Out of scope | AC-1..AC-4 | Only home layout changes | `anchor_bottom` default False; edits limited to two functions | Minimal surface | none | CODING |
| R-2 | REPOSITORY, pytest.ini / run-python-tests.sh | AC-6 | New test must be named `*-test.py` in scripts/tests | file `home-layout-test.py` | Else never collected | none | CODING |

Feasibility evidence: `uncle_tui.py:7418` and `7203` inspected; `scripts/run-python-tests.sh` inspected (collects scripts/tests/*-test.py). Mechanism is a revisable DESIGN choice.

## Implementation sequence

1. Write failing layout test: fake-screen harness (records addnstr and move calls) and cases for AC-1..AC-5; run `python3 -B scripts/tests/home-layout-test.py` and confirm AC-1/AC-2 fail on current code. Before any edit to `uncle_tui.py`, hard-code the baseline build-page offsets as literal constants in the test, captured from the unmodified code and BASELINE_REPORT B-3; never derive them from the code under test. Also cover: a body_rows==0 case (no history drawn, empty `_text_view`); at tiny heights, composer rows, bottom rule and status equal their h-1-derived positions; newest history entries shown and empty-history `_text_view['top']` equals the greeting row; no two draws share a row.
   Owns: `scripts/tests/home-layout-test.py`
2. Implement anchored layout in `_draw_chat_composer` and `_draw_homepage` (shared function and caller edited together in one file; the second edit builds on the first's new parameter).
   Owns: `uncle_tui.py`
   Depends on: 1
3. Re-run the new test until green, then run `bash scripts/run-python-tests.sh -- home-layout-test` style subset if supported, else the file directly; record deviations in `.uncle/docs/IMPLEMENTATION_NOTES.md`.
   
   Protected verification paths: `scripts/tests/home-layout-test.py` is frozen after step 1 except for requirement-based repairs.
   Owns: `.uncle/docs/IMPLEMENTATION_NOTES.md`
   Depends on: 2

## 21. Scope cuts under time pressure

Cut first: tiny-terminal parametrization breadth, then the compact-mode feedback relocation polish (keep feedback visible but accept simplest placement). Never cut AC-1, AC-2, AC-4, nor the min(extra, h-4) composer cap and status-at-h-1 guarantee.

## 22. Risks and unresolved questions

| Risk | Mitigation |
|---|---|
| Mouse selection offsets drift if `top` is miscomputed | AC-5 asserts history rows and `_text_view['top']` equals first history row |
| Fake-screen harness needs many TUI attributes | D-3 stubbing; implementer records the stub list in notes |
| Shifting the block pushes the greeting off-screen on short terminals | Existing greeting-hide logic (7323) retained; clamp row >= 0 |

Clarifications to the risk rows above: the "clamp row >= 0" mitigation applies only to upper rows (greeting, hint, top rule); composer, bottom rule and status positions derive from h-1 and are never raised. The AC-5 check on `_text_view['top']` applies when body_rows > 0; when body_rows is 0, no history is drawn and `_text_view` is empty.

No blocking planning decisions remain.

## Adversarial review dispositions

| Finding | Disposition | Reason | Exact plan change |
|---|---|---|---|
| AR-001 | Accepted | D-2 hid the compact hint during feedback, contradicting the unchanged-hint rule; the exception must be explicit and temporary. | D-2 now states the compact feedback line replaces the hint row only while feedback is active and the hint is redrawn when it clears. |
| AR-002 | Accepted | Behavior for h<12 and oversized composers was unspecified while V-1 and AC-5 imply it. | Section 12 (s8) gets a rule: status h-1 and bottom rule h-2 whenever h>=2, upper rows clipped from the top; test strategy s11.1 asserts per-height. |
| AR-003 | Accepted | Clamping the whole row to >=0 would raise the composer and break status==h-1 adjacency; the clamp must apply only to upper rows. | Edit s12.1 and add a risk note in s19 so the clamp covers only greeting/hint/top rule, never composer, bottom rule or status. |
| AR-004 | Accepted | History area size and _text_view were undefined when the shifted block leaves no room above it. | Edit s1.1 to define body_rows = max(0, greeting_block_start - top) with empty _text_view at 0 rows; align AC-5 and s14.1.r2. |
| AR-005 | Accepted | Cursor placement was unspecified once the composer moves and wraps. | Add decision D-4 and extend AC-5 requirement: cursor on last visible wrapped composer row at computed column, clamped to screen. |
| AR-006 | Accepted | Several feedback conditions can be active but only one row exists, so priority must be fixed. | Edit D-2 to draw one feedback line with priority chat_error, file choice, slash hint; AC-3 test row updated to match. |
| AR-007 | Accepted | Plan clamped upper rows yet claimed adjacency everywhere; tiny-height contract must be explicit. | s8.1 and s1.1 define tiny-height behavior: status at h-1 (h>=2), no exception, upper rows drop greeting, hint, top rule; s11.1 and AC-5 assert only that below the fit height. |
| AR-008 | Accepted | Uncapped wrapped composer rows could overlap history or go negative; a cap is needed. | s1.1 caps composer rows at min(extra, h-4) with cursor on last visible composer row; s8.1, s11.1, AC-5 and s18.1 updated to match. |
| AR-009 | Accepted | The compact-mode hint is intentionally hidden while feedback is active; the plan should state this as an explicit exception to the unchanged-hint rule. | D-2 now states the compact hint-hiding exception to S-7, clipping to width, and redraw on clear; AC-3 updated. |
| AR-010 | Accepted | History area must be defined when the shifted block leaves no rows above it. | s1.1 defines body_rows = max(0, greeting_block_start - top); with 0 rows no history is drawn and _text_view is an empty region. |
| AR-011 | Accepted | A regression oracle must be fixed independently of the code under test, so literal baseline offsets are needed. | Added compatibility text (s7.1) and AC-4 test wording requiring literal baseline constants captured from unmodified code. |
| AR-012 | Accepted | Compact-mode feedback needs explicit clipping and hint-suppression rules to be testable. | Edited D-2 to state clipping at row+1 and hint suppression while feedback is active, redrawn when cleared. |
| AR-013 | Accepted | Feedback contains user-controlled text; stating it goes through the existing sanitizing `put` path locks in current behavior at no cost. | Section 8 (s8.1) states feedback and composer text is drawn via `put` with non-printable characters replaced, unchanged. |
| AR-014 | Accepted | Plan tests heights below 12, so the tiny-height contract must be explicit. | Section 8 (s8.1) and section 16 (s11.1) state: for h<12 only no-exception, in-bounds writes and history above the composer are asserted; status is on h-1 whenever h>=2. |
| AR-015 | Accepted | Row priority under overflow was unspecified; an explicit drop-never-overlap order makes tiny-height behavior testable. | s8.1 states priority from h-1 upward; s11.1 and AC-5 test it for composer heights beyond available space. |
| AR-016 | Accepted | Multiple simultaneous feedback conditions, clipping and no-free-row cases were unspecified. | D-2 now defines one feedback line with precedence, width clipping and fallback to hint row then greeting; AC-3 and s11.1 test each case. |
| AR-017 | Accepted | The plan used 'compact' without a threshold, so tests could not label heights reliably. | Decision D-1 and test strategy s11.1 now define compact via the existing greeting-hide condition and label each test height. |
| AR-018 | Accepted | History cutting and _text_view['top'] with empty history were unspecified. | Section 1 (s1.1) now states newest-entries-that-fit and top equals the greeting row when empty; AC-5 updated. |
| AR-019 | Accepted | Alternative A's '+3' conflicts with AC-4's offset of 2, and the regression test needs a fixed oracle rather than values computed from the code under test. | Clarify the offset note under s2.1, add a hard-coded baseline-offset oracle rule to s12.1, and update the s14.1.r1 coverage. |
