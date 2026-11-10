# Change plan (Issue 230)

Seeded from [unclehq/uncle#230](https://github.com/unclehq/uncle/issues/230).

Omitted sections: Schema/persistence (only a new stop-reason string); Migration (none); Concurrency beyond scheduler (none); Feature flag (none, behavior only triggers on a 402 spending body).

Issue 230

## 1. Selected technical approach

- D-1: `SpendingStop(Exception)` in `self_hosted_http.py` with fields code, scope, limit_atomic, used_atomic, suggested_increase_atomic, balance_atomic; helper `parse_spending_stop(code, body)` returns it only for HTTP 402 + JSON body whose top-level `code` equals exactly (case-sensitive, not nested) `budget_reached` or `balance_exhausted`. Any other casing, nesting or code returns None and the existing ValueError path is unchanged. Both ValueError sites (1330, 1428) call it first. Sanitizing: each atomic field must be absent or a JSON integer (bool, float, string, or any other type invalidates the SpendingStop, so the existing ValueError path runs); an absent atomic field yields a SpendingStop with that field set to None. `scope` must be a string, is reduced to printable ASCII (0x20-0x7E, other characters dropped) and truncated to 64 characters before reaching stderr, the marker, or stop-reason. Stopped-line rendering: budget_reached prints the limit/suggested-increase wording; balance_exhausted prints the balance wording; any clause whose figure is None is omitted entirely, and the line never prints `None`, `$0` (unless the figure is genuinely 0), or an empty placeholder.
- D-2: `self_hosted.py main` catches SpendingStop, prints the Stopped line to stderr, writes a JSON marker, and returns 75. Marker contract: stagegate.sh (not the runner) creates a per-run directory with mode 0700 and passes each worker its own distinct marker path inside it via env `UNCLE_SPENDING_STOP_FILE`, never shared between workers; the runner only writes to the path it is given (temp file plus atomic rename) and never creates the directory. stagegate.sh deletes all marker paths at stage start so a stale marker from a prior run is never read, and removes the directory and its files at stage end. Schema: one JSON object `{"code": str, "scope": str|null, "limit_atomic": int|null, "used_atomic": int|null, "suggested_increase_atomic": int|null, "balance_atomic": int|null}`; a missing field is null. Stopped-line rendering: USD = atomic/1e6 rounded up to 2 decimals (e.g. 1500001 atomic -> $1.51); a null figure renders as `unknown`. The runner emits 75 for every caller; only the PROJECT_PLAN stage interprets it (D-4), and only when a parsing marker is present; otherwise, and for every other caller, any nonzero exit including 75 is an ordinary failure exactly as before.
- D-3: Spending-stop handling applies only when the scheduler is invoked by the PROJECT_PLAN stage (caller passes an explicit opt-in); in every other stage that shares the schedulers, exit 75 is an ordinary nonzero failure exactly as before. When opted in, a worker subshell records exit 75 as a spending stop ONLY if that worker's marker file (in the stagegate-owned 0700 per-run directory) exists and parses as a valid SpendingStop JSON marker; exit 75 with a missing or unparseable marker (e.g. another child returning EX_TEMPFAIL) is an ordinary failure. On a validated spending stop: set flag `stopped`, start no new workers, drain running, keep finished sections, return 75. Precedence: if any worker has a validated spending stop, the scheduler returns 75 regardless of other worker failures; the fallback never runs; sections of non-spending failures and killed sections are not kept as finished and are redone on resume; the stop-reason also records the count of non-spending failures (e.g. `spending_limit: <figures>; other_failures=N`). Only when no worker has a validated spending stop do non-spending failures behave as today (ordinary failure status, fallback runs; AC-8, SB-10 unchanged). The shell test includes a mixed case (75 plus another failure) asserting exit 75, no fallback, finished sections kept.
- D-4: PROJECT_PLAN case only (the only place 75 is interpreted as a spending stop): if scheduler returns 75, do not delete investigation/sections, write `spending_limit: <figures>` to `$STATE_DIR/stop-reason`, exit 75. Other failure: unchanged. Every other stage and caller treats any nonzero exit, including 75, as an ordinary failure with unchanged behavior.
- D-5: Resume is conditional and crash-safe. (1) Skip gate: sections are skipped only when the prior stop-reason in `$STATE_DIR/stop-reason` begins with `spending_limit`; for any other state (no stop-reason, other failure, stale directory) the sections directory is removed at stage start exactly as today, so every section is redone. A spending stop must not remove the sections directory or finished final files, and the `spending_limit` stop-reason is consumed (cleared) once the resumed run starts. (2) Atomic publish: each section worker writes its output(s) to temp names (`$name.md.tmp.$$`, and `$name.json.tmp.$$` for json+md sections) and renames them atomically to the final names only after the worker exits 0 (json before md, so the final `.md` marks completion). (3) Resume check: a section is skipped only when every final output file (`$name.md`, or both `$name.json` and `$name.md`) exists and is non-empty; temp names are never treated as finished. At the start of a resumed run all leftover `*.tmp.*` files in the sections directory are deleted, and any section with a missing, empty or partial final set (e.g. `.json` without `.md`) is rerun and its outputs overwritten.
- D-6: Budget-aware cap: pure function `budget_cap(remaining_atomic, typical_call_atomic, configured_concurrency)` in `unit_scheduler.py` returns `min(configured_concurrency, max(1, floor(remaining_atomic / typical)))`, where typical is `typical_call_atomic` if it is a positive integer, else 400000 (integer floor division; remaining_atomic <= 0 gives cap 1). Typical cost is 400000 atomic until at least one call has finished, then the integer mean (floor, minimum 1) spend per finished call. The cap bounds total concurrent workers (running plus newly launched) and never exceeds configured concurrency; running workers are never killed, new workers wait until the running count is below the cap. The client writes the remaining-budget header value atomically (temp file plus rename) to the per-worker path in env `UNCLE_BUDGET_REMAINING_FILE`, a file separate from the stop marker (`UNCLE_SPENDING_STOP_FILE`). Each worker gets its own distinct path for each of the two names, so parallel workers never write the same file; the paths live in the stagegate-created 0700 per-run directory. The scheduler removes all such files at stage start, so a stale file from a prior run never caps a resumed run, and re-reads them before launching each worker, using the minimum remaining value across the valid per-worker files. A header value that is not a non-negative base-10 integer is ignored (treated as absent). Absent or unparseable file/header: no cap.
- D-7: `_EXTERNAL_CAPACITY` gains patterns anchored to the client error prefix: `^\s*HTTP\s+402:` (multiline) and the exact tokens `\b(budget_reached|balance_exhausted)\b`. Unanchored `status\s*402` / `http\s*402` are not added, so validator output that merely mentions 402 (e.g. a line number or amount) stays False.

## 2. Alternatives
A) Parse in shell from logs (fragile, rejected). B) Retry the fallback with lower concurrency (still hits the limit, rejected).

## 3. Why preferred
Typed exception at the source, status propagated by exit code, existing files reused; smallest surface.

## 4. Components to modify
See change-impact table.

## 5. Not to modify

`scripts/lib/budget.py`, hosted-mode defaults, plan validators (#231), existing tests.

Non-goal: spending-stop behavior is limited to the PROJECT_PLAN stage; all other stages and callers sharing the schedulers or the runner keep existing failure handling, treating exit 75 as an ordinary nonzero failure.

## 6. Data flow
402 -> SpendingStop -> runner exit 75 + marker -> worker subshell exit 75 -> scheduler return 75 -> stage stop-reason + exit 75.

## 8. Interfaces

New exit code 75; new internal env vars `UNCLE_SPENDING_STOP_FILE` and `UNCLE_BUDGET_REMAINING_FILE`, two separate files whose paths are set per worker by the scheduler (each worker writes its own per-worker file per name; stagegate clears them at stage start; the scheduler reads the minimum remaining value across workers); new stop-reason value `spending_limit`; section outputs are written under temp names `<final>.tmp.<pid>` and renamed to the final name only on worker success (leftover temp files are deleted at stage start).

File-path contract (owned by step 1, consumed by step 3, which depends on step 1): stagegate.sh supplies each worker its own distinct path for UNCLE_SPENDING_STOP_FILE and UNCLE_BUDGET_REMAINING_FILE inside a per-run 0700 directory; the runner only writes to the paths given.

## 10. Compatibility

All other statuses and messages unchanged (AC-2, AC-8). Section reuse on resume applies only after a `spending_limit` stop; every other rerun removes sections and redoes all of them as before.

## 12. Error and recovery

Unparseable 402 body -> existing ValueError. Exit 75 whose marker is missing or does not parse -> ordinary failure (existing behavior, fallback may run); it is never a spending stop, so no `spending_limit` stop-reason is produced and no `unknown` figures are rendered. Stale markers are prevented by clearing per-worker marker paths at stage start, inside the stagegate-owned 0700 per-run directory. Recovery: operator raises limit and reruns; finished sections reused.

## 14. Rollback plan
Revert the change; no data migration. Leftover `spending_limit` stop-reason is plain text.

## 16. Automated-test strategy

| Test | Covers |
|---|---|
| scripts/tests/self-hosted-spending-stop-test.py | AC-1, AC-2, AC-7 (cap function) |
| scripts/tests/project-plan-spending-stop-test.sh | AC-3, AC-4, AC-5, AC-8 (stubbed workers via exit codes, bounded and unbounded) |
| scripts/tests/supervisor-test.py additions | AC-6 |

- Stale-sections case (AC-8): project-plan-spending-stop-test.sh includes a case with non-empty section files present but no `spending_limit` stop-reason; it asserts the stale sections are removed and all sections are redone.
- Mixed-outcome case (AR-013, AR-017): project-plan-spending-stop-test.sh runs one stubbed worker exiting 75 alongside another worker with an ordinary failure; it asserts the scheduler exits 75, the fallback does not run, finished sections are kept, and the non-spending failure count is recorded in stop-reason.
- AC-7 coverage detail: self-hosted-spending-stop-test.py tests budget_cap boundaries (remaining 0 and negative, remaining below typical, exact multiple, floor rounding, typical <= 0, result never above configured concurrency). project-plan-spending-stop-test.sh additionally runs the scheduler with stubbed workers and a budget side file: a low remaining value limits total concurrent workers, while an absent or non-integer value leaves concurrency unchanged.

Regression tests that fail before the fix: all new SB tests. Cap tests pin exact values (configured concurrency 14, typical 400000): remaining 10000000 gives 14 (floor 25, clamped); 1000000 gives 2 (floor of 2.5); 399999 gives 1; 0 gives 1; -5 gives 1; typical 0 or negative falls back to 400000; a non-integer header leaves concurrency unchanged. The shell test project-plan-spending-stop-test.sh includes a mixed case (one stubbed worker exits 75 while another fails with an ordinary nonzero exit, in both bounded and unbounded schedulers) asserting scheduler exit 75, no fallback run, and finished sections kept. Verification commands are those of the baseline plus explicit runs of the new suites: `bash scripts/run-python-tests.sh -- self-hosted-spending-stop`, `bash scripts/run-shell-tests.sh -- project-plan-spending-stop` (step 1 confirms the exact runner argument form).

## 18. Manual verification
None required; optional hosted run with a low task limit.

## 19. Observability
One Stopped line; stop-reason carries figures.

## Restrictions

| ID | Source | Property | Mechanism | Rationale | CAP | Phase | Requirement |
|---|---|---|---|---|---|---|---|
| R-1 | USER CHANGE_REQUEST Fix 2 | keep finished work, no fallback | exit 75 propagation (D-3, D-4), accepted only with a valid marker in the stagegate-owned 0700 per-run dir | simplest cross-process signal | CAP-shell | CODING | AC-3..5 |
| R-2 | USER Fix 4 | cap total concurrent workers by remaining budget: max(1, floor(remaining/typical)), never above configured concurrency | D-6 budget_cap: each worker writes its own per-worker budget-remaining file; stagegate clears them at stage start; scheduler reads the minimum remaining value; cap = min(configured, max(1, floor(remaining/typical))), typical<=0 uses 400000; non-integer header ignored | only header named in request is used | CAP-python | CODING | AC-7 |
| R-3 | DESIGN | existing errors unchanged | parse only exact codes | avoid false positives | CAP-python | CODING | AC-2 |

Feasibility: stagegate.sh:4342-4462 and self_hosted.py:2224 inspected; runners are local bash/python3, no live credentials needed (tests use fake server and stub workers).

## Change-impact table

| Component | Planned change | Reason | Regression risk | Test coverage |
|---|---|---|---|---|
| scripts/lib/self_hosted_http.py | SpendingStop, parser, header capture | SB-1, SB-9 | Medium | self-hosted-spending-stop-test.py |
| scripts/lib/self_hosted.py | catch SpendingStop, exit 75, write per-worker JSON marker atomically (null for missing fields); render Stopped line per code (budget_reached vs balance_exhausted wording), omitting clauses with missing figures, never printing None or $0 for absent values; render USD rounded up to 2 decimals / `unknown` | SB-3, SB-6 | Low | spending-stop tests |
| scripts/lib/unit_scheduler.py | budget_cap function | SB-9 | Low | spending-stop-test.py |
| scripts/stagegate.sh | both schedulers, section skip, PROJECT_PLAN case; 75 interpreted only in the PROJECT_PLAN stage, other callers treat 75 as ordinary failure | SB-3..5, SB-7 | High | project-plan-spending-stop-test.sh |
| scripts/lib/supervisor.py | regex extension | SB-8 | Low | supervisor-test.py |
| scripts/tests/supervisor-test.py | new cases: anchored 'HTTP 402:' / budget_reached text is external capacity (true); ordinary validator failure text mentioning 402 elsewhere (e.g. 'line 402', 'status 402 items') is false | AC-6 | Low | itself |
| scripts/tests/self-hosted-spending-stop-test.py | new | AC-1,2,7 | None | itself; includes Stopped-line rendering cases: budget_reached with all figures, balance_exhausted with balance, and bodies missing figures (no None/$0 in output) |
| scripts/tests/project-plan-spending-stop-test.sh | new | AC-3,4,5,8 | None | itself |

## Traceability

| Requirement | Behavior | Invariant | Component | Automated test | Manual check |
|---|---|---|---|---|---|
| AC-1, AC-2 | SB-1, SB-2 | SI-1, SI-5 | self_hosted_http.py | self-hosted-spending-stop-test.py (incl. Stopped-line rendering for both codes and missing-figure bodies) | none |
| AC-3, AC-4 | SB-3..6 | SI-2, SI-3, SI-4 | stagegate.sh, self_hosted.py | project-plan-spending-stop-test.sh | none |
| AC-5 | SB-7 | SI-3 | stagegate.sh | project-plan-spending-stop-test.sh | none |
| AC-6: external-capacity detection matches only the anchored client error prefix 'HTTP 402:' or the exact codes budget_reached/balance_exhausted; ordinary validator failures, including text that mentions 402 elsewhere, return false. | SB-8 | SI-6 | supervisor.py | supervisor-test.py | none |
| AC-7: with a known remaining budget, total concurrent workers are limited to min(configured concurrency, max(1, floor(remaining/typical))); typical = 400000 until a call finishes (and whenever typical<=0), then the integer mean of finished calls; remaining<=0 gives 1; an absent or non-integer header leaves concurrency unchanged; verified by both a pure-function boundary test and a scheduler-level cap test. | SB-9 | SI-7 | unit_scheduler.py | self-hosted-spending-stop-test.py | none |
| AC-8 | SB-10 | SI-6 | stagegate.sh | project-plan-spending-stop-test.sh | none |

## Implementation sequence

1. Client and runner: SpendingStop, parser (with D-1 field validation: integer-only atomic fields, scope sanitized to 64 printable ASCII chars), header capture, exit 75, per-worker atomic JSON marker with USD round-up rendering and `unknown` for missing figures, budget_cap, plus their Python test (marker schema, rounding, null fields, non-integer atomic fields, control characters, oversized scope); runner writes only to marker/budget paths it is given; confirm runner argument form for `-- suite`. IDs: D-1, D-2, D-6.
   Owns: `scripts/lib/self_hosted_http.py`, `scripts/lib/self_hosted.py`, `scripts/lib/unit_scheduler.py`, `scripts/tests/self-hosted-spending-stop-test.py`
2. Supervisor regex and test (independent of step 1). D-7.
   Owns: `scripts/lib/supervisor.py`, `scripts/tests/supervisor-test.py`
3. Schedulers, section skip-on-resume, PROJECT_PLAN case, and shell test; stagegate creates the per-run 0700 marker/budget dir, passes per-worker paths, treats exit 75 as a spending stop only if the marker parses (else ordinary failure; shell test covers 75 with no/garbage marker), removes the dir at stage end; builds on step 1's exit code contract. D-3, D-4, D-5.
   Owns: `scripts/stagegate.sh`, `scripts/tests/project-plan-spending-stop-test.sh`
   Depends on: 1

## Scope cuts under time pressure

First cut SB-9 budget-aware cap (D-6, AC-7: cap=max(1,floor(remaining/typical)) bounded by configured concurrency), then SB-8; the stop/keep/resume core (SB-1, 3-7) is retained.

## Risks and unresolved questions
- stagegate.sh scheduler edits are in a hot path; mitigated by preserve test AC-8.
- Host header set beyond one name is unverified; cap is skipped when absent.
- #213 reopen/note is a human follow-up outside the code change.

## Adversarial review dispositions

| Finding | Disposition | Reason | Exact plan change |
|---|---|---|---|
| AR-001 | Accepted | D-3 contradicted itself on mixed failures; the spending stop must win so the fallback never discards kept work. | Rewrote D-3 (s1.1.i3): any worker exit 75 makes the scheduler return 75, fallback skipped, failed sections rerun on resume. |
| AR-002 | Accepted | A non-empty file does not prove a section is complete; killed workers can leave partial output, so completeness must be tied to exit 0 plus an atomic rename. | D-5 (s1.1.i5) now requires temp-file plus atomic rename on exit 0, skips only final names, and deletes leftover temp/partial outputs at stage start. |
| AR-003 | Accepted | The Stopped message was undefined for balance_exhausted and for 402 bodies missing figures; a rendering rule is needed. | D-1 gains rendering rule (balance wording, omit missing clauses, never None/$0); runner row and test row updated to match. |
| AR-004 | Accepted | budget_cap rounding, floor value, bad typical and running-vs-new semantics were unspecified and untestable. | D-6 (s1.1.i6) defines cap=max(1,floor(remaining/typical)), typical<=0 uses 400000, bounds total workers; R-2, AC-7 and scope-cut text aligned. |
| AR-005 | Accepted | D-6 said one shared file while section 8 lists two env vars; parallel workers would race and stale files could cap a resumed run. | Edit D-2, D-6, section 8 (s7.1) and R-2 so each worker writes its own per-worker file per name, stagegate clears them at stage start, and the scheduler reads the minimum remaining value. |
| AR-006 | Accepted | Real gap: the plan scoped 75 handling to PROJECT_PLAN without saying other stages sharing the schedulers treat 75 as an ordinary failure. | Edit D-3 and D-4 to state that only PROJECT_PLAN interprets 75 as a spending stop; other stages treat it as ordinary failure. |
| AR-007 | Accepted | Exit 75 leaves the runner for every caller, so the plan must say only PROJECT_PLAN interprets it. | D-2, D-3 and D-4 now scope 75 handling to PROJECT_PLAN; other callers treat 75 as an ordinary failure. |
| AR-008 | Accepted | D-3 contradicted itself on mixed failures; the spending stop must win so work is kept and the fallback never runs. | Rewrote D-3 (s1.1.i3) so any worker exit 75 makes the scheduler return 75 regardless of other failures, with no fallback. |
| AR-009 | Accepted | Unconditional skip-if-exists could reuse stale sections and break the baseline where non-spending reruns redo everything. | D-5 now limits skipping to runs resuming after a spending_limit stop-reason; compatibility text and shell test coverage updated. |
| AR-010 | Accepted | A non-empty final name can be a partial write from a killed worker, so existence alone cannot prove completion. | D-5 now requires workers to write temp names and atomically rename on success; resume checks only final names and deletes leftover temps. |
| AR-011 | Accepted | A shared budget file written by concurrent workers could race or carry stale values into a resumed run; the file contract needs to be explicit. | Rewrote D-6 (s1.1.i6) so each worker writes its own budget file atomically, stagegate clears stale files at stage start, and the most recent value wins. |
| AR-012 | Accepted | Unanchored 402 patterns could match unrelated validator output and wrongly flag external capacity, violating AC-6. | D-7 now anchors to the client error prefix (HTTP 402:) plus exact codes; supervisor test row and AC-6 add a negative case. |
| AR-013 | Accepted | D-3 contradicted itself on mixed failures; AC-8 covers only the pure non-spending case, so the mixed rule must be explicit and tested. | Rewrote D-3 precedence (75 if any worker hit a spending stop; stop-reason records non-spending failure count) and added a mixed-case test note in section 16. |
| AR-014 | Accepted | Exit 75 alone is ambiguous (EX_TEMPFAIL); trusting it requires a stagegate-owned, protected, parseable marker. | Edit D-2, D-3, D-6, section 9 recovery, R-1, steps 1 and 3: stagegate-owned 0700 per-run dir; 75 counts only with a parsing marker, else ordinary failure. |
| AR-015 | Accepted | Marker fields come from a remote 402 body and reach stderr and stop-reason, so strict type validation and scope sanitizing are needed. | D-1 now accepts only the two codes and integer atomic fields, rejects other types, and truncates scope to 64 printable ASCII characters; step 1 test coverage updated. |
| AR-016 | Accepted | A killed worker can leave a truncated non-empty section, so existence alone is not proof of completion; atomic rename makes the final name mean 'finished'. | D-5 now requires temp-file write plus atomic rename on exit 0, skip only on final names, and deletion of leftover temp files; interface section notes the temp naming. |
| AR-017 | Accepted | D-3 contradicted itself on mixed outcomes; any worker exit 75 must return 75 and skip the fallback, matching AC-8 for pure non-spending failures. | Rewrote D-3 precedence in s1.1.i3 and added a mixed-case test note to section 16. |
| AR-018 | Accepted | Mixed outcomes (a worker exiting 75 plus other failures) are real behavior of D-3 and were untested; a mixed case is cheap to add. | Section 16 test strategy text now requires a mixed shell-test case asserting exit 75, no fallback, finished sections kept. |
| AR-019 | Accepted | The budget cap needs a precise testable definition and a scheduler-level test, not just a pure-function test. | D-6 (s1.1.i6), AC-7, R-2 fix the formula, rounding, defaults and bad-header handling; s11 adds boundary and scheduler cap tests. |
| AR-020 | Accepted | D-5's non-empty test was ambiguous for partial outputs such as a .json without its .md; requiring all outputs to exist and be non-empty removes the ambiguity. | Rewrote D-5 (s1.1.i5) to skip only when every output file exists and is non-empty, otherwise rerun and overwrite. |
| AR-021 | Accepted | The marker contract (location, schema, staleness, concurrency, USD rendering) was undefined and is needed for a testable Stopped line. | D-2 now defines per-worker marker paths cleared at stage start, a JSON schema, and USD rounding; section 12 and step 1 agree. |
| AR-022 | Accepted | 402 matching variants were unspecified; an exact, case-sensitive top-level match avoids false positives and missing figures should not defeat detection. | D-1 (s1.1.i1) now states exact case-sensitive top-level code match and None for missing numeric fields. |
