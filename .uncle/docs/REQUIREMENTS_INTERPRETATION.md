## 1. Required functionality

Source: REQUIREMENTS.md R-001..R-004 (Must). No additional interpretation beyond:
- R-001/R-002 cover the live per-stage figure, per-stage and total subtotals, any cost column or label, and the `"Cost   " + ...` rows with their containing labels.
- R-004 print is on every normal exit, finished or stopped workflow.
- R-004 totals are session-wide: input, output, cache-read, cache-write.

## 2. Optional functionality

R-005 (Should): per-stage-group token breakdown at exit. Issue wording is conditional ("if cheap"), so it is optional. Print it only if derivable from existing data without new instrumentation. Totals (R-004) never depend on it.

## 3. Constraints

Source: REQUIREMENTS.md Constraints, Non-goals, Notes.
- No change to `scripts/lib/usage-cost.py`, `call_max_cost_usd`, `session-totals.json` content/schema, or metrics files.
- Change confined to `uncle_tui.py` display/exit logic.
- No new pricing, estimation or billing-mode logic.
- Token display (`_token_total`, `"Tokens " + ...` rows) stays unchanged.

## 4. User-visible behaviors

| ID | Trigger | Expected result | Failure behavior | Verification |
|---|---|---|---|---|
| B-001 | TUI live or after run | See REQUIREMENTS.md B-001. Cost-removal gaps: rows/labels removed, not blanked; token rows keep position order; no `$`-prefixed amount remains | Layout gap: see A-1 | Automated: render TUI text for live and post-run states, assert no `$\d` match and no "Cost" label; assert token rows still present |
| B-002 | Normal exit (finished or stopped) | See REQUIREMENTS.md B-002. Totals printed adjacent to `Total time:` / `PR:` lines | No usage data: see A-2 | Automated: run exit path with fixture session totals, assert four token figures in stdout; fixture with none, assert A-2 behavior |
| B-003 | Exit with usage data absent or partial | Print the token-totals lines with 0 for missing fields; never print a dollar amount; never fail the exit | Exit code and other end-of-run lines unaffected | Automated: fixtures with missing file, empty file, partial keys |

## 5. System behaviors

Source: REQUIREMENTS.md Data and state. Exit print reads existing `session-totals.json` / metrics data only; writes nothing new. No additional interpretation.

## 6. Failure behaviors

Source: REQUIREMENTS.md Failure behavior (TODO in source). Resolved by A-1, A-2, A-3; see B-001..B-003.

## 7. Ambiguities

A-1: layout after removing cost elements (source B-001 TODO). Resolved by ASSUMPTION A-1.
A-2: no usage data at exit (source B-002 TODO). Resolved by ASSUMPTION A-2.
A-3: exact wording/format of the exit line (source Verification TODO). Resolved by ASSUMPTION A-3.
A-4: R-005 required vs optional. Resolved: optional (see optional_functionality).
A-5: no reference images or mockups exist; no pixel verification possible.
A-6: root-level stray files (REQUIREMENTS_INTERPRETATION.md, UPDATED_CHANGE_PLAN.md, etc.) not read; not evidence.

## 8. Assumptions

ASSUMPTION A-1: removed cost elements leave no blank row, column, or label; surrounding rows collapse. Settled by: owner stating a layout.
ASSUMPTION A-2: with no usage data, print all four totals as 0 (line still appears). Settled by: owner preferring omission.
ASSUMPTION A-3: format is one labeled line per figure or one line containing the labels `input`, `output`, `cache-read`, `cache-write` with integer counts, styled like the `Total time:` line. Tests match labels and numbers, not exact whitespace. Settled by: owner supplying wording.
ASSUMPTION A-7: "dollar amount" means any `$` followed by digits, or a USD-formatted value, in TUI output. Settled by: owner.
ASSUMPTION A-8: if a stage-group breakdown is printed, it follows the totals and uses the same four figures per group.

## 9. Explicit non-goals

Source: REQUIREMENTS.md Non-goals. Also: no change to token display, no cost removal from stored data, no new output format file, no changes outside `uncle_tui.py` unless needed to read existing data.

## 10. Definition of done

Source: REQUIREMENTS.md Definition of done and Acceptance. Prerequisites: all checks automatable; no browser/GUI, external service or independent human sign-off required (no source requirement for one). Availability: terminal TUI render capture and subprocess exit capture: unknown until planning; representative session-totals fixtures: unknown, must be created.

| ID | Criterion (source) | Observable result | Verification | Prerequisite |
|---|---|---|---|---|
| D-1 | No dollar amount in TUI during/after run (Acceptance 1, R-001, R-002, I-001) | Rendered TUI text has no `$\d` and no Cost label in live, per-stage, and summary views | Automated render/text assertion plus source grep of `_live_cost`, `cost_subtotal`, `"Cost   "` removal | Render capture hook: unknown |
| D-2 | Tokens unchanged (R-003, DoD 2) | `_token_total` and `"Tokens " + ...` rows render same as before | Automated before/after render comparison on same fixture | Baseline render: unknown |
| D-3 | Exit prints token totals (Acceptance 2, R-004, B-002, I-002) | Stdout has input/output/cache-read/cache-write totals near `Total time:` / `PR:` after finished and stopped workflows | Automated exit-path run with fixture | Fixture: unknown |
| D-4 | Absent/partial usage (B-003, A-2) | Zeros printed, clean exit | Automated fixtures | Fixture: unknown |
| D-5 | Excluded files unchanged (DoD 4, Constraints) | No diff in `usage-cost.py`, `call_max_cost_usd` site, `session-totals.json` writer, metrics writers | Diff inspection of changed-path inventory | Observed: git available |
| D-6 | R-005 breakdown (optional) | If implemented, per-group figures sum to totals | Automated sum assertion | None |
