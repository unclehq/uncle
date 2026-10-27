# Project plan

## 1. Architecture

Python 3 stdlib curses app (`uncle_tui.py`); no framework, build step, browser or new dependency. Change is two-sided: (a) subtraction of cost display from the session panel (C-1); (b) a new pure, curses-free module `uncle_token_exit.py` (C-2, C-3, C-4) imported by `uncle_tui.py`, whose `__main__` block prints token totals after `curses.wrapper` returns (D-1, D-2). Exit print reads `.uncle/workflow/session-totals.json` from disk, independent of the curses object, so finished, stopped and non-unattended exits all print. Cost data in `session-totals.json`, metrics files, `scripts/lib/usage-cost.py` and `call_max_cost_usd` are untouched (R-1..R-3, R-5). Tests are stdlib `unittest` against pure functions and `UncleTUI.__new__` + `_session_panel_lines()` (D-8), plus the existing bash panel test (C-6); defect injections run in parallel scratch copies (C-7). Layering: domain (aggregation, line formatting) in `uncle_token_exit.py`; UI/transport (curses, stdout print) stays in `uncle_tui.py`.

## 2. Authoritative state

- Authoritative: `.uncle/workflow/session-totals.json` (existing writer, unchanged, R-3). Token fields per record: `input_tokens`, `output_tokens`, `cache_read_tokens`, `cache_write_tokens`; stage key via `row['stage']`.
- Derived, never stored: exit totals and group breakdown are recomputed from the file at each exit; no cache, no new file (D-1, D-6).
- Existing in-memory panel state in `UncleTUI` (token totals shown by `_token_total`) is unchanged (R-4); cost-only fields/bookkeeping are deleted (C-1).
- Restart/exit: nothing new persists; a missing, empty, partial or malformed file yields zeros (D-4).

## 3. Domain model

- `Totals` = dict `{input:int, output:int, cache_read:int, cache_write:int}`; each non-negative integer, counted exactly as stored (D-6).
- `Groups` = `dict[str, Totals]` keyed by `parent_stage(row['stage'])` (D-5); per-group figures sum to `Totals` (checked by T-10).
- Record = one session-totals row; unusable values (missing key, non-numeric) contribute 0; unreadable/malformed file contributes all zeros (D-4).
- Exit line = text rendering of Totals (+ optional group lines) in format D-3; contains no `$` followed by a digit (R-6).
- Removed concepts: live cost, stage cost subtotal, total cost, `dollars` formatting, Cost style attributes. Interfaces: `session_token_totals(path)->dict`, `token_totals_lines(totals, groups=None)->list[str]`, `session_token_groups(path)->dict[str,dict]` (D-2).

## 4. Components and responsibilities

| ID | Component | Responsibility | Files |
|---|---|---|---|
| C-1 | Cost removal | Delete `_live_cost`, `dollars`, `cost_subtotal`, `Cost   ` rows, `Cost of usage so far`/`Reported + projected` labels, Cost style branches in `_session_panel_attr`, cost bookkeeping in `_session_panel_lines`; rows collapse (D-7); also owns the `uncle_tui.py` import and `__main__` call to C-3 (D-2) | `uncle_tui.py` |
| C-2 | Token totals aggregator | Pure `session_token_totals(path)` returning four ints; missing/empty/partial/malformed -> 0 (D-4) | `uncle_token_exit.py` |
| C-3 | Exit printer | Pure `token_totals_lines(totals, groups=None)` in D-3 format; invoked from `__main__` after `curses.wrapper`, after any `finished_build_lines()` output, on every normal exit | `uncle_token_exit.py` (function); `uncle_tui.py` (call, via C-1) |
| C-4 | Group breakdown (R-005) | `session_token_groups(path)` reusing `parent_stage`; per-group four figures | `uncle_token_exit.py` |
| C-5 | Panel/exit tests | Unit tests T-1..T-4 (panel) and T-5..T-11 (aggregator, printer, `__main__` subprocess) | `scripts/tests/tui-no-cost-test.py`, `scripts/tests/tui-token-exit-test.py` |
| C-6 | Existing-test alignment | Update assertions expecting Cost rows | `scripts/tests/tui-session-panel-test.sh` |
| C-7 | Defect injection | Mutation list + parallel runner (T-12) | `scripts/tests/tui-token-mutations.py`, `scripts/tests/tui-token-mutate-test.py` |
| C-8 | Project metadata | `.gitignore` additions (D-10), `.uncle/launch.json` `{"kind":"none"}` (D-9) | `.gitignore`, `.uncle/launch.json` |

`uncle_tui.py` is owned solely by C-1's step; `uncle_token_exit.py` solely by C-2/C-3/C-4's step.

## 5. Data flow

1. Run: workflow writers append usage to `session-totals.json` (unchanged). Live/post-run panel: `_session_panel_lines()` renders token rows only (no cost rows or `$`) from existing in-memory state (B-001).
2. Exit: curses UI ends -> `curses.wrapper` returns in `__main__` -> existing `Total time:`/`PR:` lines (`finished_build_lines()`) print -> `session_token_totals(path)` and `session_token_groups(path)` read the file -> `token_totals_lines(totals, groups)` -> stdout (B-002).
3. Failure path: file missing/empty/malformed/partial -> aggregator returns zeros, line still printed, exit code and other lines unaffected (B-003, D-4); reader exceptions are caught inside the aggregator so exit never fails.
4. Tests: fixtures written to temp dirs (R-9); `__main__` test runs a subprocess against the fixture and asserts four labels and numbers with no `$\d`; mutation runner copies repo to per-mutation scratch dirs and runs one test each concurrently.

## 6. Observable behaviors

| ID | Trigger | Observable result | Failure behavior | Class | Requirements |
|---|---|---|---|---|---|
| B-1 | TUI session panel rendered live (workflow running) | No cost label, `Cost` row, `Cost of usage so far`/`Reported + projected` subtitle, or `$`+digit amount; remaining rows collapse with no blank gap (D-7, A-1) | A leftover cost element is a defect; no fallback rendering | MODIFY | R-001, R-002, R-003, B-001 |
| B-2 | Session panel rendered after run finished or stopped (per-stage and total subtotals) | Per-stage and total subtotals show no cost figure, column or label; no `$`+digit | As B-1 | MODIFY | R-001, R-002, B-001 |
| B-3 | Session panel token display, any state | `Tokens ` rows and `_token_total` render exactly as before the change, in the same relative order | Any token-row change is a regression | PRESERVE | R-003, B-001 |
| B-4 | Normal exit from Uncle (finished or stopped workflow) | After any `Total time:` / `PR:` lines, stdout has one line `Tokens used: input N, output N, cache-read N, cache-write N` with session-wide integer totals from `session-totals.json`, and no `$` amount (D-3, D-6) | See B-6 | ADD | R-004, B-002 |
| B-5 | Normal exit where session-totals records carry stage names | After the totals line, one `  <group>: input N, output N, cache-read N, cache-write N` line per stage group (via `parent_stage`); group figures sum to the totals (D-5, A-8) | No groups derivable: totals line only | ADD | R-005 |
| B-6 | Exit where `session-totals.json` is missing, empty, malformed, or lacks some keys | Totals line still printed with 0 for each unavailable field; no dollar amount; exit code and other end-of-run lines unchanged (D-4, A-2) | Aggregator never raises into the exit path | ADD | R-004, B-003 |

## 7. Domain invariants

| ID | Invariant | Scope | Enforcement point | Automated test | Violation impact |
|---|---|---|---|---|---|
| I-1 | No dollar amount (`$` followed by a digit, or USD-formatted value) and no `Cost` label appear in any TUI session-panel render (live, per-stage, total, post-run). Status: STRENGTHENED (EXISTING token display retained). | TUI render output, all run states | C-1 `uncle_tui.py` (`_session_panel_lines`, `_session_panel_attr`; `_live_cost`, `dollars`, `cost_subtotal` deleted) | see 10 | Acceptance 1 fails; users see a meaningless mixed reported/estimated figure |
| I-2 | Every normal exit prints one token-totals line with input, output, cache-read, cache-write integers, after any `finished_build_lines()` output, for finished and stopped workflows alike. Status: NEW. | `__main__` exit path | C-3 `uncle_tui.py` `__main__` calling `uncle_token_exit.token_totals_lines`; D-1 reads disk, not curses state | see 10 | Acceptance 2 fails; token usage is lost at session end |
| I-3 | Exit token print never raises and never changes the exit code: a missing, empty, malformed or partial `session-totals.json` yields 0 for each absent figure and the line is still printed. Status: NEW. | `session_token_totals`, `session_token_groups`, `__main__` hook | C-2 `uncle_token_exit.py` (tolerant parse, D-4); C-3 | see 10 | Crash or lost end-of-run lines (`Total time:`, `PR:`) when usage data is absent |
| I-4 | Exit output contains no dollar amount (R-6): only token counts are emitted, cost fields in stored records are never read or printed. Status: NEW. | Exit output, `token_totals_lines` | C-2/C-3 `uncle_token_exit.py` reads only the four `*_tokens` keys | see 10 | Reintroduces the removed misleading cost figure at exit |
| I-5 | Token display is unchanged: `_token_total` and `Tokens ` panel rows render the same strings as before the change (R-4), and surrounding rows collapse with no blank row or label where Cost rows were (A-1, D-7). Status: EXISTING (token display) / MODIFY (layout collapse). | Session panel render | C-1 `uncle_tui.py` | see 10 | Token information regresses or panel shows gaps |
| I-6 | Exit read is read-only and confined: `session-totals.json`, metrics files, `scripts/lib/usage-cost.py` and `call_max_cost_usd` are neither modified nor rewritten; no new pricing/estimation logic (R-1, R-2, R-3, R-5). Status: EXISTING. | Changed-path inventory, runtime file writes | C-2 opens the file read-only; change confined to `uncle_tui.py`, `uncle_token_exit.py`, tests | see 10 | Out-of-scope behavior change in supervisor cap or stored data |
| I-7 | Totals are exact sums of stored fields (D-6): no inclusive-cache adjustment or estimation; when a group breakdown is printed (R-005), per-group figures sum to the totals line. Status: NEW. | `session_token_totals`, `session_token_groups` | C-2, C-4 `uncle_token_exit.py` (groups via `parent_stage`) | see 10 | Misreported token counts; breakdown inconsistent with totals |

## 8. Failure handling

| ID | Condition | Required handling | Behaviors |
|---|---|---|---|
| F-1 | `session-totals.json` missing or unreadable | Aggregator returns all four fields as 0; the totals line is still printed | B-6 |
| F-2 | File empty or malformed JSON | As F-1; no exception reaches `__main__` | B-6 |
| F-3 | A record lacks one or more token keys, or has a non-integer value | Missing or invalid field counts as 0 for that record; other fields and records still sum | B-6 |
| F-4 | Exit printer raises unexpectedly | `__main__` catches it, prints nothing extra, and keeps the original exit code and the other end-of-run lines | B-4, B-6 |
| F-5 | Records have no usable stage name | Group breakdown is omitted; the totals line is unaffected | B-5 |
| F-6 | Cost fields present in stored records | Ignored for display and exit output; stored data is untouched (R-3) | B-1, B-2, B-4 |

## 9. Concurrency model

None for the feature. The aggregator is a single synchronous read of `session-totals.json` after `curses.wrapper` returns, when the TUI has stopped writing, so there is no shared mutable state. It is a pure read-only function with no locking and no writes. A concurrent writer could leave a partially written file; that is handled as malformed JSON (F-2). Verification parallelism (mutation scratch copies) is owned by the verification-commands section.

## 10. Automated-test strategy

Runner: stdlib `unittest` (no curses, no browser, no network, no new deps). Tests construct `UncleTUI.__new__` and call `_session_panel_lines()` (D-8). Fixtures are written inline into per-test `tempfile` dirs (outputs stay outside protected paths). Expected values are hand-computed literals in the test (e.g. fixture rows 100/20/5/3 + 40/10/0/7 → input 140, output 30, cache-read 5, cache-write 10), never produced by calling the code under test. Git fixtures, if any, use `-c commit.gpgsign=false -c tag.gpgsign=false` and `--no-gpg-sign` (R-7).

### Test inventory

| ID | File | Observable assertion | Independently grounded expected result | Prerequisites | Evidence retained | Covers |
|---|---|---|---|---|---|---|
| T-1 | `scripts/tests/tui-no-cost-test.py` | Live-run panel lines (stage running, tokens + cost fields present in fixture) contain no regex `\$\s*\d` and no `Cost` label / `Cost of usage so far` / `Reported + projected` | Fixture deliberately includes `cost_usd` and `estimated_cost_usd` values (e.g. 1.23) so a leak is detectable; expected: zero matches | python3, fixture session-totals | unittest output | R-001, R-002, B-001, D-1 |
| T-2 | same | Post-run (finished) panel: same regex/label absence, incl. per-stage and total subtotal rows | Zero matches; no blank row left where Cost rows were (consecutive-empty-line count unchanged vs hand-written expected line list) (A-1) | same | unittest output | R-001, R-002, B-001, D-1 |
| T-3 | same | `Tokens ` rows equal literal expected strings for the fixture | Strings hand-written from the pre-change baseline render of the same fixture (captured once from the unmodified tree into the test as literals) | baseline render captured at plan baseline run | unittest output | R-003, D-2 |
| T-4 | same | Source text of `uncle_tui.py` contains none of `_live_cost`, `cost_subtotal`, `"Cost   "`, `dollars(` | Zero occurrences | none | unittest output | R-001, R-002, D-1 |
| T-5 | `scripts/tests/tui-token-exit-test.py` | `session_token_totals(path)` on a full fixture returns four ints; `token_totals_lines` output has labels `input`,`output`,`cache-read`,`cache-write` with those integers | 140/30/5/10 (hand-summed) | tempdir fixture | unittest output | R-004, B-002, D-3 |
| T-6 | same | Missing file → all four 0, line still produced, no exception | `input 0, output 0, cache-read 0, cache-write 0` | none | unittest output | R-004, B-003, D-4 |
| T-7 | same | Empty (0-byte) file → zeros | same | none | unittest output | B-003, D-4 |
| T-8 | same | Partial keys (rows lacking cache fields, one row lacking all) → missing counted as 0, present summed | hand-summed literals | none | unittest output | B-003, D-4 |
| T-9 | same | Malformed JSON / non-object records / non-int values → zeros or skipped, no exception, no `$` in output | zeros; no exception | none | unittest output | B-003, D-4 |
| T-10 | same | `session_token_groups` per-group figures sum to `session_token_totals` for a fixture with ≥2 groups and sub-stages (via `parent_stage`) | Hand-assigned group sums; group sums == totals per field | none | unittest output | R-005, D-6 |
| T-11 | same | Subprocess runs `uncle_tui.py` exit path (stopped-workflow fixture, curses stubbed/not entered) and captures stdout: contains four token figures adjacent to/after `Total time:`/`PR:` lines when present, exit code 0, no `$\d` | Hand-written totals; stopped and finished variants; with no session file → zeros line, exit 0 | python3 subprocess, tempdir cwd | stdout capture in temp dir | R-004, B-002, B-003, D-3, D-4 |
| T-13 | `scripts/tests/tui-session-panel-test.sh` (existing, updated) | Existing panel assertions pass with Cost expectations removed and Token expectations unchanged | Existing expected strings minus Cost rows | bash, python3 | script output | R-001, R-002, R-003 |
| T-12 | `scripts/tests/tui-token-mutate-test.py` (list in `tui-token-mutations.py`) | Every injected defect is rejected (its named test fails in the scratch copy); runner exits non-zero if any mutation survives or any scratch run errors | See defect table | copy of `uncle_tui.py`, `uncle_token_exit.py`, tests into per-mutation temp dir; no install | per-mutation result lines in temp dir | R-001..R-005, B-001..B-003 |

### Defect injections (T-12; all started concurrently, each in its own scratch copy and temp output dir, each running only its named test)

| Mutation | Defect | Must be rejected by |
|---|---|---|
| M-1 | Re-add a `Cost   ` row with `$1.23` to `_session_panel_lines` | T-1 |
| M-2 | Re-add `Cost of usage so far` subtitle | T-2 |
| M-3 | Change a `Tokens ` row format | T-3 |
| M-4 | Aggregator drops the cache-write sum | T-5 |
| M-5 | Aggregator raises on missing file | T-6 |
| M-6 | Aggregator raises on empty file | T-7 |
| M-7 | Missing key treated as error / row skipped entirely | T-8 |
| M-8 | Malformed JSON propagates exception | T-9 |
| M-9 | Group sum off by one | T-10 |
| M-10 | Exit printer emits `$` amount | T-11 |
| M-11 | `__main__` omits the print on stopped-workflow exit | T-11 |

Self-check: T-12 also asserts each unmutated scratch copy passes its named test first (so a mutation "failing" for an unrelated reason is not counted).

### Dev tooling / input provenance failures

No update tooling is delivered. Input failures (missing/empty/malformed/partial `session-totals.json`) are covered by T-6..T-9, T-11. Lack of curses terminal is handled by not entering curses in tests.

### Protected verification paths (frozen during verification)

`scripts/tests/tui-no-cost-test.py`, `scripts/tests/tui-token-exit-test.py`, `scripts/tests/tui-session-panel-test.sh`, `scripts/tests/tui-token-mutations.py`, `scripts/tests/tui-token-mutate-test.py`, plus all other existing `scripts/tests/tui-*-test.*`. Fixtures are inline (no separate fixture dir); no test config file exists. Generated outputs go to `mktemp -d` dirs, never under `scripts/tests/` or `.uncle/`.

### Acceptance coverage

D-1 → T-1, T-2, T-4, T-13; D-2 → T-3, T-13; D-3 → T-5, T-11; D-4 → T-6..T-9, T-11; D-5 → diff inspection of changed-path inventory (file-hash comparison of `scripts/lib/usage-cost.py` and untouched files before/after; no commit required); D-6 → T-10. No mandatory human sign-off: no source requires one and all properties are automatable. Parallelism: T-12 mutations run concurrently; unit-test files share no ports or writable fixtures and may run in parallel groups.

## 11. Manual-test strategy

None required. All behaviors (B-1..B-6) are checkable by automated tests on rendered panel text, the pure aggregator and printer, and a subprocess exit run. The requirements name no independent human sign-off, and there is no GUI, browser or external service. Optional spot check M-1 is not mandatory and is not a sign-off: run Uncle interactively, let a workflow finish or stop, and look at the terminal for no `$` amounts in the panel and a `Tokens used:` line after `Total time:`. Until a person actually observes it, M-1 is reported as NOT RUN.

## 12. Implementation order

Steps 1, 2, 4–9 share no files and no read-time dependencies; the driver may run adjacent ones together. Interfaces are fixed by the plan (D-2, D-3, D-4, D-8), so tests are written from them, not from code.

1. **Cost removal in session panel (C-1)** — delete `_live_cost`, `dollars`, `cost_subtotal`, `Cost   ` rows, the `Cost of usage so far`/`Reported + projected` labels, Cost style branches in `_session_panel_attr`, and cost bookkeeping in `_session_panel_lines` (D-7: rows collapse, no subtitle). Also add the `uncle_token_exit` import and the `__main__` call after `curses.wrapper`, printed after any `finished_build_lines()` output, reading disk totals per D-1 (this is the hook that step 3 would otherwise describe, per D-2). Token rows and `_token_total` stay untouched (R-4). Owns: `uncle_tui.py` — Depends on: none
2. **Token aggregator, exit printer, group breakdown (C-2, C-3, C-4)** — new pure module with `session_token_totals(path)->dict`, `token_totals_lines(totals, groups=None)->list[str]` and `session_token_groups(path)->dict[str,dict]`. Output format per D-3, zero fallback per D-4, groups via `parent_stage` per D-5, cache fields as stored per D-6. Owns: `uncle_token_exit.py` — Depends on: none
3. **Exit hook wiring (merged into step 1 per D-2)** — the hook is applied by step 1's owner; `uncle_tui_exit_hook.txt` is a placeholder name only and is not created. Owns: `uncle_tui_exit_hook.txt` — Depends on: 2
4. **No-cost panel tests (B-001, D-1, D-2)** — unittest cases T-1..T-4 using `UncleTUI.__new__` and `_session_panel_lines()` (D-8): no `$\d` and no `Cost` in live and post-run panels, Tokens rows equal fixture-expected strings, source has no removed cost symbols. Owns: `scripts/tests/tui-no-cost-test.py` — Depends on: none
5. **Token exit tests (B-002, B-003, D-3, D-4, D-6)** — unittest cases T-5..T-11: full, missing, empty, partial and malformed fixtures, group sums equal totals, and a `__main__`-path subprocess with a stopped-workflow fixture asserting the four figures and no `$`. Fixtures live in temp dirs. Owns: `scripts/tests/tui-token-exit-test.py` — Depends on: none
6. **Update existing Cost assertions** — change expectations in the existing session-panel shell test that look for Cost rows so they match the collapsed layout. Do not weaken token assertions. Owns: `scripts/tests/tui-session-panel-test.sh` — Depends on: none
7. **Mutation list** — the data file for T-12: the five defects (re-add Cost row → T-1; drop cache-write sum → T-5; missing file raises → T-6; print `$` → T-11; group sum off by one → T-10), each with its single target test. Owns: `scripts/tests/tui-token-mutations.py` — Depends on: none
8. **Parallel mutation runner** — the T-12 runner: copies the tree into a scratch dir per mutation, applies the mutation, runs only its target test, all mutations started at once. Passes only if every mutation is rejected. Written against the step 7 and step 4/5 test IDs, so it does not wait on them. Owns: `scripts/tests/tui-token-mutate-test.py` — Depends on: none
9. **Scaffold metadata** — write `.uncle/launch.json` as `{"kind":"none"}` (D-9) and append the D-10 entries to `.gitignore` (`.pytest_cache/`, `.DS_Store`, `.env`, `.env.*`, `test-results/`) if the planning-stage write did not land; `__pycache__/` and `*.pyc` are already ignored. Owns: `.gitignore`, `.uncle/launch.json` — Depends on: none

Cut first if time expires: step 7/8 (defect injection), then R-005 group output (C-4) in step 2. Never cut steps 1, 2, 4 or 5.

## 13. Requirement traceability

| Requirement | Behavior | Invariant | Component | Automated test | Manual check |
|---|---|---|---|---|---|
| B-001 | B-1, B-2, B-3 | I-1, I-5 | C-1 | T-1, T-2, T-12 | M-1 |
| B-002 | B-4 | I-2, I-4, I-6 | C-2, C-3 | T-5, T-11, T-12 | M-1 |
| B-003 | B-6 | I-3 | C-2, C-3 | T-6, T-7, T-8, T-9, T-11, T-12 | M-1 |
| R-001 | B-1, B-2 | I-1, I-5 | C-1 | T-1, T-2, T-4, T-12, T-13 | M-1 |
| R-002 | B-1, B-2 | I-1, I-5 | C-1 | T-1, T-2, T-4, T-12, T-13 | M-1 |
| R-003 | B-1, B-3 | I-5, I-6 | C-1 | T-3, T-12, T-13 | M-1 |
| R-004 | B-4, B-6 | I-2, I-3, I-4, I-7 | C-2, C-3 | T-5, T-6, T-11, T-12 | M-1 |
| R-005 | B-5 | I-7 | C-4 | T-10, T-12 | M-1 |

## 14. Explicit non-goals

- No change to `scripts/lib/usage-cost.py`, `call_max_cost_usd`, `session-totals.json` schema/content, or metrics writers (R-1, R-2, R-3).
- No change to token display (`_token_total`, `Tokens ` rows) (R-4); no new pricing, estimation, or billing-mode logic (R-5).
- No removal of cost data from stored files; no new output file or format.
- No framework, linter, formatter, browser, or new dependency; no pixel/visual verification (A-5).
- No inclusive-cache adjustment of token figures (D-6).
- No mandatory human sign-off: every acceptance check is automatable and no source requirement demands one.
- No real project commits; no changes outside `uncle_tui.py`, `uncle_token_exit.py`, the listed tests, `.gitignore`, and `.uncle/launch.json`.

## 15. Risks and unresolved questions

No blocking planning decisions remain; the A-1..A-3 and A-7/A-8 defaults are binding and settle on owner override only.

| ID | Risk | Mitigation |
|---|---|---|
| K-1 | Outline D-2 and step 3 conflict (`uncle_tui_exit_hook.txt` named, then dropped). | Binding resolution: step 3 is merged into the `uncle_tui.py` owner and no hook file is created. The final step table must not list it. |
| K-2 | `session-totals.json` record field names (`input_tokens`, `output_tokens`, `cache_read_tokens`, `cache_write_tokens`) and `stage` key come from the outline and are unverified against the writer. | The implementer reads the writer and a real file before coding. Aggregator tolerates absent keys (D-4), so a mismatch yields zeros, not a crash. T-5 fixtures must use the real shape. |
| K-3 | Cost removal in `_session_panel_lines` may shift row ordering or styling and break Tokens rows. | T-3 compares Tokens rows to fixture-expected strings; `tui-session-panel-test.sh` is updated, not weakened. |
| K-4 | `__main__` exit print could be skipped on a stopped-workflow or exception path. | D-1 reads from disk after `curses.wrapper`; T-11 covers the stopped fixture. |
| K-5 | Stray `$` plus digits in unrelated exit output (for example `PR:` URLs) could trip the no-dollar check. | The no-dollar assertions apply to TUI render and token lines (R-6, A-7), with fixtures that contain no unrelated `$`. |
| K-6 | Existing tests may also depend on Cost labels beyond the one `.sh` file. | The implementer greps `scripts/tests/` for `Cost` and aligns every hit. Removing a cost assertion is allowed only for an assertion about a removed element. |

## Decision Record

| ID | Decision | Reason |
|---|---|---|
| D-1 | Exit totals are read from disk `session-totals.json` in `__main__`, not from the curses object. | The curses object is gone after `curses.wrapper` returns. Reading from disk makes finished, stopped and non-unattended exits all print (R-004, B-002). |
| D-2 | The aggregator and printer live in a new importable module `uncle_token_exit.py` with `session_token_totals(path)->dict`, `token_totals_lines(totals, groups=None)->list[str]` and `session_token_groups(path)->dict[str,dict]`. Step 1 owns the one `uncle_tui.py` edit (import plus `__main__` call). Step 3 is merged into step 1, and `uncle_tui_exit_hook.txt` is not created. | Fixing the interface in the plan lets step 2 and the test steps run in parallel. `uncle_tui.py` has one owner, so no two steps write it. A pure module can be unit-tested without curses. |
| D-3 | The output is `Tokens used: input N, output N, cache-read N, cache-write N`, one line of comma-free integers. Group lines follow as `  <group>: input N, ...` when groups exist. | It matches A-3 and A-8. It matches the style of the `Total time:` line. Tests match labels and numbers, not whitespace. |
| D-4 | A missing, empty or malformed file, or absent keys, gives all four figures as 0. The line is still printed and the exit code is unchanged. | A-2 and B-003. Exit must never fail because of usage data. |
| D-5 | R-005 is implemented. Groups come from `parent_stage(row['stage'])` over existing session-totals records. | The data already exists, so no new instrumentation is needed. That meets the issue's "if cheap" condition. Totals do not depend on the groups. |
| D-6 | Cache fields are counted exactly as stored, with no inclusive-cache adjustment and no estimation. | R-5 forbids new estimation or billing logic. Adjusting would make the printed figures differ from the stored data. |
| D-7 | After the Cost rows are removed, the surrounding rows collapse. The `Cost of usage so far` header leaves no subtitle line and no blank row. | A-1. Rows are removed, not blanked, so no dollar figure or label remains (R-6). |
| D-8 | Tests use stdlib `unittest` with `UncleTUI.__new__` and `_session_panel_lines()`, as `tui-complete-dialog-test.py` does. They do not use curses. | This follows the repo convention. It is deterministic and runs unattended, with no terminal needed. |
| D-9 | `.uncle/launch.json` is `{"kind":"none"}`. | The app is an interactive curses TUI with no non-destructive demo invocation. |
| D-10 | `.gitignore` already ignores `.uncle/*`, `__pycache__/` and `*.pyc`. Step 9 appends `.pytest_cache/`, `.DS_Store`, `.env`, `.env.*` and `test-results/`. | These entries fill the gaps in the stack's usual ignore set. The planning stage could not write the file, so step 9 owns it. |

## Restriction Inventory

Feasibility evidence: no file was re-probed by this worker; "outline" means `.uncle/workflow/project-plan-sections/outline.md` and "interp" means `.uncle/docs/REQUIREMENTS_INTERPRETATION.md`. Each probe listed is to be run in the named phase. Runner for all rows is `python3 -m unittest` (stdlib) plus `bash scripts/tests/tui-session-panel-test.sh`. No config file exists or is needed. Capabilities: CAP-PY (python3 stdlib), CAP-UT (unittest discovery of `scripts/tests/tui-*-test.py`), CAP-DIFF (file-hash and path-inventory diff, no commit needed), CAP-TMP (temp dirs for outputs and scratch copies), CAP-GITFX (disposable git fixture with signing off).

| ID | source_kind | Source location | Req IDs | Required property | Selected mechanism | Rationale | CAP | Runner/config binding | Feasibility evidence | Phase |
|---|---|---|---|---|---|---|---|---|---|---|
| R-1 | USER | REQUIREMENTS.md Notes (`usage-cost.py` separate); interp §3 | R-001, R-002, D-5 | `scripts/lib/usage-cost.py` is byte-identical after the change | Step ownership excludes the file. T-13 (a hash/inventory comparison in the verification command) compares its sha256 with the pre-change snapshot. | The file is outside the issue and the user said so explicitly. | CAP-DIFF | Verification commands run `shasum -a 256` before and after. No runner config. | Path named in the user text. Probe at CODING: `test -f scripts/lib/usage-cost.py` and record its hash. | CODING |
| R-2 | USER | REQUIREMENTS.md Notes (`call_max_cost_usd` supervisor cap); interp §3 | R-001, R-002, D-5 | The `call_max_cost_usd` definition and use sites are unchanged | Only `uncle_tui.py` and the new module are edited. T-13 greps `call_max_cost_usd` in changed files and compares occurrence counts and context hashes before and after. | The cap is a separate supervisor feature and must keep enforcing the dollar limit. | CAP-DIFF | Same hash/grep commands as R-1. | Probe at CODING: `grep -rn call_max_cost_usd .` and record the pre-change listing. Occurrences in non-owned files must not change. | CODING |
| R-3 | USER | REQUIREMENTS.md Notes (cost data stays in `session-totals.json` and metrics files); interp §3, §5 | R-004, B-002, B-003 | `session-totals.json` and metrics files keep content and schema. The exit print only reads them and writes no file. | `session_token_totals(path)` and `session_token_groups(path)` open the file read-only. T-11 runs the `__main__` path on a fixture in a temp dir and asserts the fixture hash is unchanged and no new files appear. | Existing consumers and the cost data the user chose to keep depend on the schema. | CAP-PY, CAP-TMP | `scripts/tests/tui-token-exit-test.py` T-5..T-11. Fixtures are built in the test and written only to a temp dir. | Schema fields `input_tokens`, `output_tokens`, `cache_read_tokens`, `cache_write_tokens` and `stage` come from outline C-2. Probe at CODING: grep the `session-totals.json` writer and confirm the key names before implementing the aggregator. | CODING |
| R-4 | USER | REQUIREMENTS.md Requested change 1 ("Keep token counts"); interp §3 | R-003, D-2 | `_token_total` and the `Tokens ` rows render the same as before | The cost removal edit leaves those code paths untouched. T-3 compares the Tokens rows on a fixture with a literal expected string taken from the pre-change render captured at baseline. T-12 injection "drop Tokens row" must fail T-3. | Token counts are the one metric the user wants kept visible. | CAP-PY, CAP-UT | `scripts/tests/tui-no-cost-test.py` T-3 and the updated `tui-session-panel-test.sh`. | Outline C-1 and C-5 name these symbols. Probe at CODING: grep `_token_total` and `"Tokens "` in `uncle_tui.py`, then capture the baseline render before editing. | CODING |
| R-5 | USER | REQUIREMENTS.md Requested change; interp §3 (no new pricing, estimation or billing-mode logic) | R-001, R-004 | No pricing, estimation or billing-mode code is added. Cache counts are summed as stored (outline D-6). | The aggregator only sums the four integer fields, with no multiplication or lookup tables. T-5 uses fixture values whose expected sums are computed by hand in the test. T-10 checks that group sums equal totals. | The issue states cost figures are not meaningful across billing modes, and estimation would reintroduce them. | CAP-PY | `scripts/tests/tui-token-exit-test.py` T-5 and T-10. | Probe at CODING: review the diff for `price`, `rate`, `estimated` and `usd` identifiers in added lines. | CODING |
| R-6 | USER | REQUIREMENTS.md Acceptance ("No dollar amounts appear in the TUI"); interp A-7 | R-001, R-002, B-001, D-1 | No `$` followed by a digit and no USD-formatted value in the TUI render or the exit output. No `Cost` label remains. | `_live_cost`, `dollars`, `cost_subtotal` and the `Cost   ` rows are deleted. T-1 and T-2 render the live and post-run panels from fixtures that include nonzero cost fields and regex-assert no `\$\s*\d` and no `Cost`. T-4 greps the source for the removed names. T-11 applies the same regex to exit stdout. | Cost data stays in the fixtures on purpose, so the test proves the display ignores it rather than that the data was absent. | CAP-PY, CAP-UT | `scripts/tests/tui-no-cost-test.py` T-1, T-2, T-4, and `tui-token-exit-test.py` T-11. Injections run through `tui-token-mutate-test.py`. | Probe at CODING: `grep -n "_live_cost\|cost_subtotal\|Cost   \|dollars" uncle_tui.py` and record the pre-change line numbers. Panel rendering is callable without curses via `UncleTUI.__new__` plus `_session_panel_lines()`, as in `tui-complete-dialog-test.py` (outline D-8). Probe at CODING: confirm that call works on a fixture. | CODING |
| R-7 | DESIGN | Carried forward from the stage's git-signing rule; outline R-7 | all | Tests and fixtures never use the user's signer or GPG agent. Any git fixture is disposable. | The planned tests need no git. If one is added, it runs `git -c commit.gpgsign=false -c tag.gpgsign=false` with `--no-gpg-sign`, sets repo-local signing config, and runs in a temp dir. Global git config is never changed. | Avoids pinentry or key access during unattended runs. | CAP-GITFX | Applies to any test file under `scripts/tests/`. T-13 greps the test files for `git commit` without `--no-gpg-sign`. | Planned tests use `unittest` only and do not call git. Probe at CODING: grep the new tests for `git`. | CODING |
| R-8 | DESIGN | Carried forward from the stage's no-commit rule; outline R-8 | all | Building, testing and verification need no project commit and no clean working tree. | Protected inputs are snapshotted by sha256 and path inventory, including untracked files, before changes and compared after. No step commits. | The repo already has unrelated uncommitted work (`.uncle/docs/REQUIREMENTS.md`, `scripts/lib/native_stage.py`, others), and it must not be overwritten. | CAP-DIFF | Hash and inventory commands live in `## Verification commands`. | Git status at stage start shows modified and untracked files, so clean-tree checks are infeasible and not used. | CODING |
| R-9 | DESIGN | Carried forward from the protected-paths rule; outline R-9 | all | Tests and the mutation runner are frozen during verification. Generated outputs stay outside protected paths. | Protected set: `scripts/tests/tui-no-cost-test.py`, `scripts/tests/tui-token-exit-test.py`, `scripts/tests/tui-token-mutations.py`, `scripts/tests/tui-token-mutate-test.py`, `scripts/tests/tui-session-panel-test.sh`. Mutations run in `tempfile` scratch copies, each with its own output directory, and report to a temp path. | A repair stage must not be able to weaken a test to make a command pass. | CAP-TMP, CAP-DIFF | Verification commands hash the protected set before and after. Mutation scratch copies are under the system temp dir. | `scripts/tests/` is the existing home of `tui-*-test.py` per outline Stack. Probe at CODING: `ls scripts/tests/tui-*-test.*` and confirm the discovery naming. | CODING |

LIVE_VERIFICATION: none. The TUI is exercised without curses or a terminal, and no authentication, third-party service or credential is needed. Prerequisite evidence paths: none. Resume uses the Verification commands only.

## Parallel verification groups

```text
1 2 3 4 5
```

## Verification commands

```sh
python3 -m py_compile uncle_tui.py uncle_token_exit.py
python3 scripts/tests/tui-no-cost-test.py
python3 scripts/tests/tui-token-exit-test.py
bash scripts/tests/tui-session-panel-test.sh
python3 scripts/tests/tui-token-mutate-test.py
```
