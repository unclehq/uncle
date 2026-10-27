
# Project brief

Issue 113

> Seeded from [unclehq/uncle#113](https://github.com/unclehq/uncle/issues/113).
> Replace the placeholder guidance below with specifics before running the driver.

## Summary

Remove cost display from the TUI; print token totals when Uncle exits

## Problem

## Problem

The TUI shows a dollar COST for runs and stages (`uncle_tui.py`: `_live_cost`, the per-stage cost subtotals, and the session summary). The figure is not meaningful:

- Many runs use subscription or session-limit billing, so there is no per-call price.
- Self-hosted and free models report `$0` or nothing.
- Where the runner reports no cost the TUI shows an estimate (`estimated_cost_usd`), so one column mixes reported, estimated and missing values.
- Sums across runners and billing modes add numbers that do not mean the same thing.

## Requested change

1. **Remove COST from the TUI display**: the live per-stage figure, the per-stage and total subtotals, and any cost column or label. Keep token counts.
2. **Print token totals when Uncle exits**: on normal exit (including after a finished or stopped workflow), print total input, output, cache-read and cache-write tokens for the session, broken down by stage group if cheap. This sits beside the existing "Total time:" / "PR:" lines printed at the end of a run.

## Notes

- Cost data can stay in `session-totals.json` and the metrics files; this is about what the TUI shows and prints.
- `usage-cost.py` and `call_max_cost_usd` (the supervisor's dollar cap) are separate and are not part of this issue.

## Acceptance

- No dollar amounts appear in the TUI during or after a run.
- Exiting Uncle prints the session's token totals.

## Scope

- Remove the dollar-cost figures that `uncle_tui.py`'s session panel currently
  renders: the live per-stage estimate (`_live_cost`), the per-stage `Cost`
  row and its `Reported + projected` label (`_session_panel_lines`, the
  `"STAGE", "Cost of usage so far"` header, `cost_subtotal`, and the
  `Cost   ...` rows at both per-stage and TOTALS level), and any cost-specific
  style branch in `_session_panel_attr`.
- Keep the existing `Tokens` row and token subtotal/TOTALS behavior in the
  session panel unchanged.
- On normal Uncle exit (finished or stopped workflow), print the session's
  total input, output, cache-read and cache-write token counts, next to the
  existing `Total time:` / `PR:` lines printed by
  `scripts/lib/finished_extras.py`'s `print` command. Break the totals down
  by stage group (`parent_stage`) when that is cheap to compute from the
  already-read `session-totals.json` records.

## Non-goals

- `usage-cost.py` and `call_max_cost_usd` (the supervisor's dollar cap) are
  explicitly out of scope (stated in Notes).
- Removing cost data from `session-totals.json` or other metrics files; the
  issue says cost data may stay there (Notes). Only TUI display/printing
  changes.
- Any change to what counts as a "normal exit" (crash/interrupt handling is
  TODO: the issue does not say whether the token-totals line is expected on a
  Ctrl-C-interrupted exit, as opposed to a workflow that is itself in
  `stopped` state, which it does name explicitly).

## Functional requirements

| ID | Requirement | Priority |
|---|---|---|
| R-001 | Remove the live per-stage cost figure, the per-stage and TOTALS `Cost` subtotal rows, the `Cost of usage so far` header text, and the `Reported + projected` label from the TUI session panel (`uncle_tui.py` `_session_panel_lines`, `_live_cost`, `_session_panel_attr`). | Must |
| R-002 | Keep the TUI's existing token count display (`Tokens` row, per-stage and TOTALS subtotals) unchanged. | Must |
| R-003 | On normal Uncle exit (a finished or stopped workflow), print total input, output, cache-read and cache-write token counts for the session. | Must |
| R-004 | Print the exit token totals beside the existing `Total time:` / `PR:` lines (same exit print point, `scripts/lib/finished_extras.py`). | Must |
| R-005 | Break the printed exit totals down by stage group when cheap to compute from `session-totals.json`. | Should |
| R-006 | No dollar amount (`$` followed by a digit) appears anywhere in the TUI during or after a run. | Must |

## User-visible behavior

| ID | Trigger | Expected result | On failure |
|---|---|---|---|
| B-001 | A stage runs or finishes while the TUI session panel is visible. | Panel shows stage title, `Time`, and `Tokens` rows only; no `Cost` row, no `Cost of usage so far` header, no `Reported + projected` label, no live per-stage dollar figure. | TODO: issue does not state what the panel should show if `session-totals.json` is missing/unreadable; current code already handles this for tokens (`Unavailable`/`(partial)`) — no new failure behavior is requested. |
| B-002 | Uncle exits normally (workflow finished or stopped) and the `Total time:` / `PR:` lines are printed. | A token-totals line (input, output, cache-read, cache-write, summed across the session) prints beside those lines; stage-group breakdown lines print too, when cheap to derive. | TODO: issue does not say what to print if `session-totals.json` is missing, empty, or unreadable at exit. `finished_extras.py`'s existing `parenthetical()` treats that as "no data" (empty string) rather than an error; TODO: confirm the token-totals line should do the same (e.g. print zeros, or omit the line) rather than raising. |

## Domain rules and invariants

| ID | Invariant | Consequence if violated |
|---|---|---|
| I-001 | No TUI-rendered string contains `$` followed by a digit, during or after a run. | Acceptance criterion "No dollar amounts appear in the TUI" is violated. |
| I-002 | The exit print always includes a token-totals line on a normal exit (finished or stopped workflow). | Acceptance criterion "Exiting Uncle prints the session's token totals" is violated. |
| I-003 | `session-totals.json` and other metrics/cost files on disk are left untouched by this change. | Backward compatibility with existing cost tooling (`usage-cost.py`, metrics consumers) breaks. |

## Data and state

- Authoritative state is unchanged: `.uncle/workflow/session-totals.json`
  (read by `uncle_tui.py::_restore_session_totals` and by
  `finished_extras.py::parenthetical`), containing per-stage records with
  `stage`, `elapsed_seconds`, `started_at`, `ended_at`, and usage fields
  (`total_tokens`/`reported_total_tokens`, or `input_tokens`,
  `output_tokens`, `cache_read_tokens`, `cache_write_tokens`,
  `input_includes_cache`) per the existing `_token_total` reader.
- No new persisted state is requested by the issue; the exit token totals are
  derived from the existing file at print time.
- `run-started-at` stamp file (`finished_extras.py::STAMP`) is unrelated and
  untouched.

## Interfaces

- `uncle_tui.py`: `_session_panel_lines`, `_live_cost`, `_session_panel_attr`
  (display surface being reduced); `_token_total`, `parent_stage` (existing
  helpers to reuse, not change, for the token-only panel and for any
  stage-group breakdown logic shared with the exit print).
- `scripts/lib/finished_extras.py`: `print` CLI command, `total_line`,
  `pr_line`, `parenthetical` (exit print surface where the new token-totals
  line is added). TODO: issue does not specify whether the token-totals line
  is a new function here, reusing `parenthetical`'s record-reading pattern,
  or implemented elsewhere; this is an implementation choice for the change
  plan, not settled by the issue text.
- No new CLI flags, APIs, or external services are implied by the issue.

## Constraints

- Python 3 stdlib only (`curses` TUI, no framework/build step), matching the
  existing files touched.
- Must not change `usage-cost.py` or `call_max_cost_usd` (Notes, explicitly
  out of scope).
- Must not remove cost data from `session-totals.json` or other metrics
  files (Notes).

## Failure behavior

- TODO: the issue does not describe failure behavior for a missing/unreadable
  `session-totals.json` at exit time, for malformed records, or for a crash
  (non-normal exit). Existing code's pattern for the analogous `Total time:`
  line (`finished_extras.py::total_line`) is to print `'unknown'`/skip
  silently on error; `parenthetical` returns `''` on any read/parse error.
  Whether the new token-totals print should follow the same "fail silent,
  never crash the exit print" convention is not stated by the issue and is
  left as a TODO for the change plan.

## Verification

- Automated: a test can assert no TUI-rendered line (from `_session_panel_lines`
  or any other panel renderer) matches `$` followed by a digit, satisfying
  R-006/I-001. No reference image or screenshot is provided with this issue,
  so there is no pixel-tolerance check to state here.
- Automated: a test can run `finished_extras.py print` against a fixture
  `session-totals.json` and assert a token-totals line appears containing the
  expected input/output/cache-read/cache-write sums, satisfying R-003/R-004/
  I-002.
- TODO: the issue does not specify the exact text/format of the token-totals
  line (labels, ordering of input/output/cache-read/cache-write, whether
  stage-group lines are required or merely permitted when "cheap"). This
  format must be fixed in the change plan, not invented here.
- Manual: visually confirm, by running a workflow in the TUI, that no cost
  figures appear during a run and that the exit screen shows the token
  totals — TODO: owner has not stated whether this manual check is required
  or whether the automated checks above are considered sufficient.

## Definition of done

- R-001 through R-006 are implemented and automated-verified as above.
- No dollar amount appears in any TUI-rendered output, during or after a run.
- A normal Uncle exit (finished or stopped workflow) prints the session's
  token totals beside `Total time:` / `PR:`.
- `session-totals.json` and other metrics/cost files remain unchanged by this
  issue's code paths.
- `usage-cost.py` and `call_max_cost_usd` are untouched.

## Open questions

- TODO: Exact text/format and line ordering for the new token-totals exit
  print (R-003/R-004) — not stated by the issue.
- TODO: Whether the per-stage-group breakdown (R-005) is required or merely
  encouraged ("if cheap") — the issue's own wording ("by stage group if
  cheap") already hedges this, so the change plan should treat it as Should,
  not Must, unless the owner says otherwise.
- TODO: Behavior when `session-totals.json` is missing, empty, or malformed
  at exit time (print zeros? omit the line? match `total_line`'s `'unknown'`
  convention?) — not stated by the issue.
- TODO: Whether the token-totals exit print is also expected on an abnormal
  exit (e.g. Ctrl-C outside of a "stopped" workflow state) or only on the two
  cases the issue names (finished, stopped) — not stated by the issue.
