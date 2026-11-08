# Baseline Report — Issue 187

Omitted sections: Reproduction (not a bug report); Baseline test results as run output (driver supplies; see section 9); Flaky behavior (none documented)

## 1. Change-request summary
See CHANGE_REQUEST.md: on the home page, pin the status bar to the very bottom row and remove the blank row between the composer and the status line. Other layout/status content is out of scope.

## 2. Repository architecture
Uncle is a Python curses TUI (`uncle_tui.py`, single large module) plus shell/Python workflow scripts under `scripts/`. Tests are `scripts/tests/*-test.py` (Python) and `*-test.sh` (shell). Home page is state `menu`; the build page is state `running`; both share `_draw_chat_composer`.

## 3. Relevant code paths
- `uncle_tui.py:6894-6902` `draw()`: state `menu` erases the screen and calls `_draw_homepage(h, w)`.
- `uncle_tui.py:7168-7257` `_draw_homepage`: `compact = h < len(LOGO)+12` (7183); `footer_rows = 8 if compact else 12` (7184); `body_rows` (7196-7201); `top = max(run_y, h - body_rows - footer_rows)` (7203); `row = top + body_rows` (7250) is passed to `_draw_chat_composer`.
- `uncle_tui.py:7313-7430` `_draw_chat_composer(row, h, w, left, width, compact)`: greeting at row(+1 non-compact) (7337); hint at row+1/+3 (7353); top rule row+2/+5 (7354); `composer_row = row + (3 if compact else 6)` (7359); `extra` = wrapped composer lines beyond first (7367); bottom rule `composer_row+1+extra` (7385); `status_row = composer_row + extra + (2 if build or compact else 3)` (7418) — the non-compact home page therefore leaves one blank row between the bottom rule and the status; feedback row `status_row+1` (7422-7428: chat_error, file choice, slash-command hint); `_draw_file_picker(composer_row, ...)` (7430).
- `_draw_chat_panel` (7431) calls the same composer for other pages (chat panel).
- Build page (`_draw_running`, 7469) also uses the composer with `build=True` (status offset 2).

## 4. Current observable behavior
| ID | Trigger | Current result | Evidence | Must preserve? |
|---|---|---|---|---|
| B-1 | Home page, non-compact height | Status row sits 3 rows below composer first row (+extra), i.e. one blank row after the bottom rule; space below status is left blank (footer_rows=12 reserve) | 7203, 7359, 7418 | No (to be modified) |
| B-2 | Home page, compact height (h < len(LOGO)+12) | Status directly follows bottom rule (offset 2) but is not on the last row | 7418 | Adjacency yes; position modified |
| B-3 | Build page (state running) | Status offset 2 below composer, no blank row | 7418 | Yes |
| B-4 | Home page with chat history | History fills rows above composer (`body_rows = h - footer_rows - run_y`) | 7199-7201 | Yes (history still visible, scrollable) |
| B-5 | Composer text wraps | Composer grows up to 6 rows, status moves down by `extra` | 7364-7367 | Yes |
| B-6 | chat_error / chat_choices / '/' typed | One-line feedback drawn at status_row+1 | 7422-7428 | Yes (must stay visible) |
| B-7 | Status text content | model/stage/triage label left, project+branch+mode right | 7386-7421 | Yes, unchanged |
| B-8 | File picker open | Drawn relative to composer_row | 7430 | Yes |

## 5. Existing invariants
| ID | Invariant | Current enforcement | Existing test | Confidence |
|---|---|---|---|---|
| I-1 | Drawing never raises on tiny terminals: every addnstr is wrapped in `curses.error` handlers and `put` bounds-checks y | `put` guards (7211-7219, 7327-7335) | None found | Medium |
| I-2 | Cursor is drawn only within the screen | `cursor_y < h and cursor_x < w-1` (7379) | None found | Medium |
| I-3 | Composer shows at most 6 rows | `shown = min(6, h-composer_row-3)` (7364) | None found | Medium |

## 6. Current API, schema, and interface contracts
No external API/schema. Internal: `_draw_chat_composer(row, h, w, left, width, compact=True)` is also called from `_draw_chat_panel` (7436); signature must remain compatible with that caller.

## 7. Existing automated-test coverage
No existing test exercises `_draw_homepage` or `_draw_chat_composer` (grep of scripts/tests for draw/stdscr found only supervisor-test.py). Layout is currently unverified by automation. Suites are independent processes with own temp dirs, so the shell and Python runners are safe to group.

## 8. (see verification_commands field)

## 9. Baseline test results
No results produced here (driver runs them). Commands come from `scripts/run-shell-tests.sh` and `scripts/run-python-tests.sh`, as mandated by the stage rules and `pytest.ini`/`scripts/run-all-tests.sh`. No pre-existing failure is documented in the repository for the changed area; the stage notes some Python suites already fail on a clean checkout (driver baseline is authoritative).

## 12. Likely change surface
`uncle_tui.py` `_draw_homepage` and `_draw_chat_composer` only; one new Python test file.

## 13. Regression-sensitive components
Build page layout (shared composer), chat panel (`_draw_chat_panel`), file picker placement, cursor placement, short-terminal behavior, history viewport/scroll (`_home_page_rows`, `_text_view` mouse selection coordinates derive from `top`).

## 14. Areas explicitly outside the change
Status text content, hints, greeting, logo, composer behavior, build page layout, other pages, workflow scripts.

## 15. Unknowns and assumptions
- A1: "Status bar" = the model/project status row drawn at `status_row`.
- A2: "Very bottom" = last screen row `h-1`.
- A3: Where the one-line feedback (B-6) goes once status owns the last row is unspecified; planner decides.
- A4: How to instantiate the TUI object under test without a terminal is unknown; implementer must find a stub approach.

## 16. Initial risk assessment
Medium-low: pure drawing change in one function pair, but zero existing layout tests and shared composer with the build page; mouse selection coordinates depend on `top`.

## Exact build and test commands executed

```sh
bash scripts/run-shell-tests.sh
bash scripts/run-python-tests.sh
```

## Parallel verification groups

```text
1 2
```

