# Change Spec — Issue 187

Omitted sections: Performance (none); Security (none); Migration (none); Prototype isolation (not a prototype)

## 1. Change type
Feature (TUI layout).

## 2. Problem statement
On the home page the status bar floats above the bottom edge with a blank row between composer and status (baseline B-1).

## 3. Current behavior
See baseline B-1, B-2.

## 4. Desired behavior
On the home page the status bar occupies the last screen row; no blank row separates the composer's bottom rule from the status row.

## 5. Observable behavior table
| ID | Class | Trigger | Current behavior | Expected behavior | Verification |
|---|---|---|---|---|---|
| S-1 | MODIFY | Draw home page at any height >= minimum usable | Status not on last row | Status text drawn on row h-1 | Fake-screen unit test; manual run |
| S-2 | MODIFY | Draw home page, non-compact | Blank row between bottom rule and status | Status row = bottom rule row + 1 | Fake-screen unit test |
| S-3 | PRESERVE | Home page compact | Status adjacent to rule (B-2) | Adjacent and on last row | Unit test |
| S-4 | PRESERVE | Composer wraps to N rows (1..6) | Status shifts with extra (B-5) | Status stays on h-1; composer block moves up so adjacency holds | Unit test parametrized |
| S-5 | PRESERVE | chat_error / file choice / '/' typed | Feedback visible (B-6) | Feedback still visible on some row not overlapping the status | Unit test |
| S-6 | PRESERVE | Build page draw | Layout per B-3 | Identical row positions to baseline | Unit test comparing row offsets |
| S-7 | PRESERVE | Status text, hints, greeting, logo | B-7 | Unchanged text | Unit test string checks |
| S-8 | PRESERVE | Chat history on home page | B-4 | History still renders above composer and scrolls | Unit test + manual |

## 6. Invariant table
| ID | Status | Invariant | Scope | Enforcement point | Verification |
|---|---|---|---|---|---|
| V-1 | NEW | On the home page the status row is h-1 and no blank row lies between bottom rule and status | _draw_homepage | draw code | home-layout test |
| V-2 | EXISTING | Drawing never raises and writes only inside the screen (I-1) | Home/build | put guards | home-layout test at tiny sizes |
| V-3 | EXISTING | Build page layout unchanged (B-3) | _draw_running | composer offsets | home-layout test |
| V-4 | EXISTING | Cursor stays on screen and on the composer row (I-2) | composer | cursor guard | home-layout test |

No RELAXED or REMOVED invariants.

## 7. Compatibility requirements
`_draw_chat_composer` stays callable from `_draw_chat_panel` unchanged.

## 8. Error and failure behavior
On terminals too short to fit all rows, drawing degrades without exceptions (V-2); status row has priority for the last row.

## 12. Rollback expectations
Revert the edit to `uncle_tui.py`; no persisted state.

## 14. Explicit non-goals
Any other home layout or status content change; build-page layout; logo/greeting/hint text.

## 15. Assumptions and unresolved questions
Assumptions A1-A3 from baseline. Feedback line placement is a planning decision (see plan D-2).

## Acceptance criteria

| ID | Criterion | Verification |
|---|---|---|
| AC-1 | On the home page (state menu) at heights of at least 12 rows and widths 40, 80 and 120, the status text is drawn on row h-1. | Automated fake-screen test captures addnstr calls and asserts the status string's row equals h-1; manual run in a real terminal. |
| AC-2 | On the home page there is no empty row between the composer's bottom rule and the status row, for composers of 1 through 6 wrapped rows and for compact and non-compact heights. | Automated test asserts status_row == bottom_rule_row + 1 across the parametrized cases. |
| AC-3 | Pending feedback (chat_error, file choice, slash-command hint) remains visible on the home page and never overlaps the status row. | Automated test sets each condition and asserts the feedback text appears on a row different from h-1. |
| AC-4 | The build page (state running) composer and status row positions are unchanged from before the change, and the status/hint/greeting text is unchanged. | Automated test records row offsets relative to the composer for build state and asserts the baseline offsets (status = composer_row + extra + 2); text assertions. |
| AC-5 | Drawing the home page at very small sizes (e.g. 5x20, 1x10) raises no exception, and chat history on the home page still renders above the composer. | Automated test draws at tiny sizes and with history entries, asserting no exception and history text present above the composer row. |
| AC-6 | Existing shell and Python suites show no new failures relative to baseline. | Driver re-runs bash scripts/run-shell-tests.sh and bash scripts/run-python-tests.sh and compares against baseline. |

