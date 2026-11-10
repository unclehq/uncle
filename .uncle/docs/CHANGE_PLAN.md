# Change plan: issue 231

Seeded from [unclehq/uncle#231](https://github.com/unclehq/uncle/issues/231).
Issue 231

Omitted sections: Schema/persistence (none beyond a marker file); Feature flag (none, bug fix); Concurrency (stage is sequential); Observability (stderr messages only, in section 12)

## 1. Selected technical approach

Decisions:

- D-1: Parser: in `plan_steps.paths()` the shape filter runs on every candidate token from either route. Route: if the Owns value contains any backticked span, only the backticked spans are candidates and unticked text on that line is ignored; if it has no backticks, the existing comma-split plain tokens are the candidates. Each candidate is tested after the existing comment-marker filter. Tick-route rule (keeps previously valid plans identical): a backticked span is dropped only if it contains whitespace or starts with a comment marker; any other token that passed validate before (e.g. `src/{a,b}.py`, `~`, `+`, `=`) is kept unchanged. The stricter plain-token path-shape test (`[\w./*?\[\]@-]+`, not `.`, `..`, `-`) applies to the no-ticks plain-token route. On both routes any token with a `..` path segment (`..`, `../x`, `a/../b`, `a/..`) is dropped, since owns controls which files a step may write; a name merely containing dots, e.g. `a..b.py`, is not a segment and is kept. The shape test is deliberately not a directory check: a directory-like token such as `src/` passes it and the validator's existing directory rejection (`plan_model.py:474-482`) still applies. Dropped tokens are returned through an optional `dropped` list argument; call sites (three Owns routes) print `warning: step N owns: dropped <token>` to stderr, once per parse and only when `dropped` is non-empty, so a plan with nothing dropped produces byte-identical stderr to today. Before printing, each token is sanitized by `plan_steps.safe_token(token)`: ANSI escape sequences and all control characters (including newlines) are removed, and the result is truncated to 80 characters with a trailing `...` when longer; the raw token is never written to stderr. Empty-result rule: if filtering drops every token, `paths()` returns an empty list, the step's owns is passed through empty, and the validator's existing missing-owns error applies (triggering the single repair turn); the dropped-token warnings print first.
- D-2: JSON route: filter `owns` values with the same shared predicate where `plan_model.py` builds a step's `owns` from `split_list`; `split_list` itself stays generic (it serves non-path lists). Same empty-result rule as D-1: a step whose owns all drop is passed through as empty owns (not repaired or substituted), and the validator's normal missing-owns error applies after the warnings, exactly as on the Markdown route.
- D-7: Warning format (governs D-1 and D-2; `N` in D-1 means `<label>`): both the parser route and the JSON route emit exactly `warning: step <label> owns: dropped <token>` on stderr, one line per dropped token, in input order, where `<label>` is the step's label as written in the plan. Both routes use the same formatting helper so the text cannot diverge. AC-2 and AC-3 tests assert this exact line.
- D-3: Add shell helper `plan_check_repair_once <label> <file> <check-cmd...>` in `stagegate.sh`. `<label>` is a fixed literal chosen by the call site, only `project-plan` or `updated-plan`; the helper rejects any other value (exit 2) and never derives it from plan text, validator output, or user input, so the marker path `$STATE_DIR/plan-check-repair-<label>` is always one of two known files. On every call, including on resume, the check runs first. On failure, the marker stores the sha256 of the plan file at the time of the prior repair attempt. If the marker is absent or its stored hash differs from the current plan hash (e.g. a human edited the plan), the helper writes the current hash to the marker, builds a prompt from new `prompts/plan-check-repair.md` plus the saved plan path and exact validator output, runs `run_initial_planning_agent`, then re-checks. Trust boundary: the prompt wraps the plan text and validator output in delimited blocks labelled untrusted data (never instructions) and tells the agent to edit only the plan file. Write scope: before the repair turn the driver snapshots content hashes and a path inventory (including untracked files) of the working tree outside `$STATE_DIR`, excluding the plan file; after the turn it compares them, and any change to another file counts as a failed repair (the stray changes are reported on stderr, the re-check is skipped, and the final-failure path is taken). If the marker exists and its stored hash equals the current plan hash, the helper makes no agent call and takes the final-failure path (exit 1 with the final-failure message). Marker lifecycle: the marker is removed whenever a check passes, so a later failure is a new failure and gets its own one repair; markers are also deleted whenever the stage regenerates its plan (the PROJECT_PLAN and UPDATED_PLAN generation paths remove `$STATE_DIR/plan-check-repair-<label>` before writing the new plan).
- D-4: Check `$STATE_DIR/spending-stop` twice. Before launching the repair agent: if present, write `stop-reason: spending_limit: ...`, print it, exit 1 without calling the agent. After the repair turn: if present, remove marker `$STATE_DIR/plan-check-repair-<label>` (the repair never completed, so a resume after the budget is raised gets a fresh repair), write `stop-reason: spending_limit: ...`, print it, exit 1 (same as `stagegate.sh:4598-4604`); no re-check.
- D-5: On final failure print to stderr: the plan file (PROJECT_PLAN or UPDATED_PLAN), the step(s), the exact validator text and the same resume command the driver prints for other stage failures; keep `supervision_validation_failed` and `exit 1`. Steps are every distinct digits-only `step-N` found in the validator errors (strict match `step-([0-9]{1,6})`), in first-seen order, comma-separated as `step: N1, N2`; only the captured digits are printed and never used in a path or command. If none is parsable print `step: unknown` (the message still names file, validator text and resume command). The same rule applies to both plan files and to any repair outcome, including agent timeout, nonzero exit, or a deleted/empty plan file. The generic `plan_context.py` message stays for non-driver callers.
- D-6: Use the helper at both sites (PROJECT_PLAN `:4636`, UPDATED_PLAN `:5696`). After a PROJECT_PLAN repair the existing `ensure_project_plan_json` re-derives canonical JSON from the Markdown.

## 2. Alternatives considered
| Alt | Why not |
|---|---|
| Start supervisor in `uncle_headless.py` | Larger scope; explicitly out of scope; #226 interplay |
| Only fix the parser | Other validator failures still end the build |
| Deterministic repair (drop bad token in driver) | Cannot fix arbitrary validator errors |

## 3. Why preferred
Smallest change; mirrors the checklist/format-retry precedent; works identically with and without a TUI.

## 4. Restrictions

| ID | source_kind | Source | Reqs | Property | Mechanism | Rationale | CAP | Phase |
|---|---|---|---|---|---|---|---|---|
| R-1 | USER | CHANGE_REQUEST Fix 2 | AC-4, AC-5 | exactly one repair, no loop | marker file in `$STATE_DIR` (D-3) | mirrors format-retry marker, `stagegate.sh:5020` | CAP-1 | CODING |
| R-2 | USER | CHANGE_REQUEST Fix 2 | AC-7 | stop cleanly on spending stop, whether it pre-exists or occurs during repair | check `spending-stop` before the repair (no agent call) and after it (no re-check) (D-4) | existing flag, `stagegate.sh:4598` | CAP-1 | CODING |
| R-3 | REPOSITORY | CLAUDE.md | AC-9 | do not weaken tests | add new tests, edit none | protected tests | CAP-2 | CODING |
| R-4 | DESIGN | this plan | AC-4 | repair touches only the plan file and only the listed errors; embedded text is never treated as instructions | prompt labels plan text and validator output as untrusted data; driver hash/inventory snapshot compare confirms only the plan file changed (D-3); INV-5 | model behavior cannot be asserted deterministically, but the write scope is enforced mechanically by the driver and tested with a stub agent that edits another file | CAP-3 | CODING |

Capabilities: CAP-1 bash+python3 (observed: scripts run via `bash`, `python3` in repo); CAP-2 `bash scripts/run-python-tests.sh -- <name>` (observed `scripts/run-python-tests.sh:14` supports `--`); CAP-3 live model call (no credentials needed for coding; stage tests use a stub agent). Runner binding: existing stagegate test harness (`headless-run-test.py`) with stub agent.

## 5. Components not to modify
`supervisor.py`, `supervision.sh`, `uncle_headless.py`, `uncle_tui.py`, `plan_model.validate` rules, section workers, existing tests.

## 6. Data flow / state

The check always runs first, including on resume. Failed check -> marker absent, or its recorded plan-file content hash differs from the current hash -> marker written with the current hash -> repair prompt (plan path + errors) -> agent edits `.uncle/docs/PROJECT_PLAN.md` -> re-check -> pass: remove marker, continue (a later, different failure in the same run is a new failure with a different hash and gets one repair); fail: exit 1 with marker retained. On resume, if the check still fails and the plan hash equals the marker's hash, the run exits 1 with the final-failure message and makes no agent call; a plan changed by hand or regenerated (different hash) clears the marker and gets one fresh repair. Spending stop during the repair turn: marker removed, exit 1 with spending_limit stop-reason, no re-check; a resume after the budget is raised repairs again. All `plan-check-repair-*` markers are also cleared when a new run begins.

## 7. Interfaces

`plan_steps.paths(value, dropped=None)` (backward compatible). New shared predicate `plan_steps.is_owns_junk(token)` (true only when the token contains whitespace, matches the comment-marker pattern, or contains a `..` path segment when split on `/`), used by D-1 (ticks) and D-2 (JSON route); every other token is kept, and the no-ticks route keeps its existing shape regex. A token that is exactly `.`, `..` or `-` is also rejected. New helper `plan_steps.safe_token(token)` strips ANSI escapes and control characters and truncates to 80 characters (appending `...`); every dropped-token warning uses it. New prompt `prompts/plan-check-repair.md`.

## 8. Compatibility

A previously valid plan yields an identical owns list, except that a backticked span containing whitespace is now dropped (it was kept before, but the validator already rejected such tokens, so no previously valid plan changes). Dropped-token warnings go to stderr once per parse and only when something was dropped.

## 9. Error and recovery

See D-4, D-5. Repair-turn outcomes: (a) Spending stop: D-4 applies. (b) Agent times out or exits non-zero: the re-check is skipped and the final-failure path (D-5) runs with the marker left set. (c) Agent exits zero but the plan file is byte-identical to its pre-repair content (hash compared): no-op repair; the re-check is skipped and the final-failure path runs with the marker set. (d) The plan file is deleted or empty after the repair: same final-failure path; the message names the file and says it is missing or empty. (e) Agent exits zero and the file is present, non-empty and changed: the check re-runs; pass removes the marker, fail takes the final-failure path. Every final failure prints the file, the validator output from the original failure, and the resume command (the step is omitted when no step-N is parsable), keeps `supervision_validation_failed` set, and exits 1 with no further re-check. The stage test (AC-4..AC-9) covers cases (b), (c) and (d) with a stub agent that exits non-zero, edits nothing, and truncates the file, asserting exit 1, marker present, and exactly one agent call.

## 10. Rollback plan

Revert the commit; delete `$STATE_DIR/plan-check-repair-*` if present. A leftover marker is not harmless while the plan is unchanged: it suppresses the one repair turn. It is cleared when the stage regenerates its plan (the plan hash differs) or a new run begins (see section 6), but remove it on rollback to avoid confusion.

## 11. Automated-test strategy

New tests (new files; not in default tier unless added):

- `scripts/tests/plan-owns-path-shape-test.py`: AC-1, AC-2, AC-3, plus the empty-result case (every Owns token dropped on both routes gives empty owns, warnings printed, and the validator's missing-owns error is reported).
- `scripts/tests/plan-check-repair-test.py`: AC-4..AC-9 using the stub-agent harness patterns from `headless-run-test.py` and `self-hosted-spending-stop-test.py`.

Defect-injection: stage test must fail if the helper is bypassed (agent-call count 0) or if the marker is ignored (count 2).
Bug-fix regression tests that fail before the fix: AC-2 (backticked `foo bar`), AC-4 stage test.

## 12. Regression-test strategy
Existing `plan-owns-comment-marker-test.py`, `plan-executability-test.py`, `updated-plan-*`, spending-stop and headless tests via the driver's baseline commands.

## Verification commands
```
bash scripts/run-shell-tests.sh
bash scripts/run-python-tests.sh
bash scripts/run-python-tests.sh -- plan-owns-path-shape plan-check-repair
```
The third line is added after step 4 creates the suites; the first two are the baseline commands (group `1 2`).

## 13. Manual-verification strategy
Live run (LIVE_VERIFICATION, needs model credentials): headless run whose plan has an invalid Owns token; observe one repair turn and continuation. Not a coding prerequisite.

## Implementation sequence

1. Parser + shared junk predicate (`is_owns_junk`: whitespace or comment marker only; every previously valid token kept; rejects any `..` path segment) + warnings (emitted only when `dropped` is non-empty). Immediately after this step, run the existing suites (`bash scripts/run-python-tests.sh`, `bash scripts/run-shell-tests.sh`) and compare against the baseline; any existing test asserting clean stderr that now fails is a plan deviation to record, not a test to edit.
   Owns: `scripts/lib/plan_steps.py`
2. JSON-route filter in step construction using the shared predicate and the D-7 warning format. A step whose owns all drop passes through with empty owns and the validator decides (same empty-result rule as the Markdown route); no new validator rule.
   Owns: `scripts/lib/plan_model.py`
   Depends on: 1
3. Repair prompt. Owns the untrusted-data labeling: plan text and validator output are wrapped in delimited blocks labelled untrusted data, never instructions, and the agent is told to edit only the plan file.
   Owns: `prompts/plan-check-repair.md`
4. Driver helper, both call sites, final-failure message. Owns the driver-side checks: fixed labels only, marker holding the plan hash, spending-stop check before and after the repair (marker removed on a spending stop), detection of non-plan-file changes by hash and path inventory, handling of non-zero exit, timeout, unchanged, missing or empty plan file, and marker clearing on plan regeneration and at new-run start.
   Owns: `scripts/stagegate.sh`
   Depends on: 3
5. Parser/model tests: exact owns lists for a ticked line with extra prose (prose ignored), a no-ticks line, and a ticked span with whitespace (dropped); brace, tilde, plus and equals tokens kept, with a parity check against the validator over a token corpus; golden previously-valid inputs yielding identical owns and empty stderr; one warning per dropped token per parse; `src/` passing the shape test and still rejected by validate; all tokens dropped on both Markdown and JSON routes giving empty owns, warnings first, then the validator's missing-owns error; `../x`, `a/../../b` and `/abs` on both routes; exact warning lines `warning: step <label> owns: dropped <token>` in input order on all Markdown routes and the JSON route.
   Owns: `scripts/tests/plan-owns-path-shape-test.py`
   Depends on: 1, 2
6. Stage/headless tests with a stub agent, asserting agent-call counts, marker state and exit status: fail-repair-pass-then-fail-again (2 calls total); fail with marker present and unchanged hash (0 new calls, exit 1); marker set with a valid plan continues; resume with a changed plan hash (one repair); stale marker for a different hash and a regenerated plan with a leftover marker (one repair each); spending-stop pre-existing (0 calls, stop-reason line, exit 1) and during repair (no re-check, marker absent, resume calls the agent again); stub agent exiting non-zero, timing out, editing nothing, truncating or deleting the plan file (exit 1, marker set, one call, message naming file and resume command); stub agent that also edits another file (treated as failed repair); prompt contents carry the untrusted-data labels; final-failure stderr for no step, one step, several steps and the UPDATED_PLAN label, with file, step, validator text and resume command; hostile validator error (`step-1; rm`, newline, escape) printing only digits with the marker name one of the two fixed labels; and the `ensure_project_plan_json` re-derivation after a PROJECT_PLAN repair.
   Owns: `scripts/tests/plan-check-repair-test.py`
   Depends on: 4
7. Reconcile and write notes, including the post-step-1 existing-suite comparison against baseline for the new stderr warnings.
   
   Steps 1-2 and 3 are independent; 5 and 6 are independent of each other.
   
   Step 1 also adds `safe_token` (ANSI/control stripping, 80-char cap with ellipsis) used by all warning call sites; step 5 tests that a dropped token containing an ANSI escape, a newline and a 200-character run is printed sanitized and truncated, and that tokens with any `..` path segment are dropped.
   
   Step inventory: S1 {paths, R-1 n/a, D-1, CAP-1}; S2 {D-2, CAP-1}; S3 {D-3, CAP-3}; S4 {D-3..D-6, R-1, R-2, CAP-1}; S5 {AC-1..AC-3, `..`-segment drop cases, CAP-2}; S6 {AC-4..AC-9, CAP-2}.
   Owns: `.uncle/docs/IMPLEMENTATION_NOTES.md`
   Depends on: 5, 6

## Change-impact table
| Component | Planned change | Reason | Regression risk | Test coverage |
|---|---|---|---|---|
| `scripts/lib/plan_steps.py` | shape filter on ticks, `dropped` arg, predicate | drop junk Owns spans | Medium: used by 3 routes | plan-owns-comment-marker, new path-shape test |
| `scripts/lib/plan_model.py` | filter owns on JSON route | same for JSON | Low | new path-shape test, plan-executability |
| `scripts/stagegate.sh` | repair helper, two call sites, message | one repair turn | Medium: central driver | new stage test, shell suites |
| `prompts/plan-check-repair.md` | new prompt | instruct limited repair | Low | stage test (prompt contents) |
| `scripts/tests/plan-owns-path-shape-test.py` | new | AC-1..3 | None | itself |
| `scripts/tests/plan-check-repair-test.py` | new | AC-4..9 | None | itself |
| `.uncle/docs/IMPLEMENTATION_NOTES.md` | deviations | workflow rule | None | n/a |

## Traceability

| Requirement | Behavior | Invariant | Component | Automated test | Manual check |
|---|---|---|---|---|---|
| AC-1 | BH-2 | INV-1 | plan_steps.py | path-shape test | none |
| AC-2 | BH-3, BH-11 | INV-1 | plan_steps.py | path-shape test | none |
| AC-3 | BH-4 | INV-1 | plan_model.py | path-shape test | none |
| AC-4 | BH-5 | INV-2, INV-5 | stagegate.sh, prompt | plan-check-repair test (includes: prompt marks plan text and validator output as untrusted; stub agent that edits a non-plan file is treated as a failed repair) | live headless run |
| AC-5: When the repair fails or has already been used, the driver prints to stderr the plan file, `step: <N[, M...]>` (every distinct digits-only step number named in the errors, comma-separated, or `step: n/a` if none), the validator text and the driver's standard resume command, then exits 1 with no further agent call. | BH-6 | INV-2, INV-3 | stagegate.sh | plan-check-repair test | live headless run |
| AC-6 | BH-7 | INV-2 | stagegate.sh | plan-check-repair test | none |
| AC-7: a spending stop stops the stage cleanly. If `spending-stop` exists before the repair, the agent is not called; if it appears during the repair turn, no re-check runs and the repair marker is removed so that a resume repairs again. Both cases write `stop-reason: spending_limit` and exit 1. | BH-8 | INV-4 | stagegate.sh | plan-check-repair test | none |
| AC-8 | BH-9 | INV-2 | stagegate.sh | plan-check-repair test | live headless run |
| AC-9 | BH-10 | INV-1 | all | baseline commands | none |

## Scope cuts under time pressure
Cut first: UPDATED_PLAN repair (AC-6), then the JSON-route filter (AC-3). Keep parser filter and PROJECT_PLAN repair.

## Risks and unresolved questions
- The checked-out tree already contains the comment-marker filter; the issue's parser description is partly stale. No blocking questions.
- Repair may over-edit: mitigated by prompt and re-check.
- Re-check after repair in the fast path depends on `ensure_project_plan_json` re-deriving from Markdown; step 6 test must cover it.

## Adversarial review dispositions

| Finding | Disposition | Reason | Exact plan change |
|---|---|---|---|
| AR-001 | Accepted | The plan lacked an empty-result rule; passing empty owns to the validator makes the existing error trigger the single repair turn. | Add empty-owns rule to D-1 and D-2 (s1.2.i1, s1.2.i2) and a test case to the path-shape test (s11.2.i1). |
| AR-002 | Accepted | D-3 and section 6 disagreed on marker lifecycle; keying the marker to the plan file hash lets a hand-edited plan get a fresh repair while an unchanged one exits 1. | Edit D-3 (s1.2.i3) and section 6 (s6.1) so the marker stores the plan hash, and a different hash on resume allows one repair. |
| AR-003 | Accepted | D-4 exits without re-check and leaves the marker set, so a resume after the budget is raised would skip repair and fail; removing the marker on spending stop fixes it. | D-4 removes the marker on a spending stop during repair; AC-7 and section 6 updated to match. |
| AR-004 | Accepted | The parser's tick and no-tick branches treated shape testing differently; one rule over every candidate token removes the ambiguity. | D-1 (s1.2.i1) now applies the shape filter to every candidate token from either route and ignores unticked text on any line with ticks. |
| AR-005 | Accepted | The final-failure message must be deterministic and testable when errors name zero, one, or several steps, for either plan file. | D-5 (s1.2.i5) now specifies stderr output, every distinct digits-only step-N or 'step: unknown', file, validator text, resume command; AC-5 matches. |
| AR-006 | Accepted | Section 8 overclaimed; spaced backticked tokens were previously kept, and warning channel/repetition were unspecified. | Reword s8.1 to state the exact compatibility rule and add a once-per-parse stderr warning rule to D-1 (s1.2.i1). |
| AR-007 | Accepted | The strict path-shape regex would drop tokens like `src/{a,b}.py` that validate accepted today; a drop-only-junk rule preserves previously valid plans. | D-1 (s1.2.i1), the interface in s7.1 and step-1 now drop only whitespace-containing or comment-marker spans from ticks; every other token is kept. |
| AR-008 | Accepted | Plan was silent on empty-owns results after filtering; stating that the validator decides keeps the filter simple and reuses existing validator errors. | Added empty-result rule to D-1 and D-2 (s1.2.i1, s1.2.i2): emptied owns pass through as empty and the validator decides. |
| AR-009 | Accepted | Real ambiguity: a retained marker must not suppress re-checking or repair for an edited plan. | D-3 and section 6 now say the check always re-runs first and the marker stores the plan hash, so a changed hash gets a fresh repair. |
| AR-010 | Accepted | Marker lifetime across plan regeneration was unspecified and 'harmless if left' contradicted the one-repair rule. | D-3 clears repair markers when the stage regenerates its plan; s10 rollback no longer calls leftover markers harmless. |
| AR-011 | Accepted | Repair-turn outcomes other than a spending stop and errors lacking step-N were unspecified; the final-failure message must degrade gracefully. | Edit D-5 and section 9 to define the message when no step-N is parsable and for agent timeout, nonzero exit, or deleted/empty plan file. |
| AR-012 | Accepted | New stderr warnings could break existing clean-stderr assertions, and existing tests may not be edited, so the plan must gate warnings and check suites early. | D-1 states warnings print only when dropped is non-empty; step 1 and step 7 run existing suites against baseline right after the parser change. |
| AR-013 | Accepted | Real gap: repair prompt embeds model-authored text and the repair agent's write scope was unspecified; prompt wording alone is insufficient. | Edit D-3 to label plan text and validator output as untrusted data and to hash-check that only the plan file changed; update R-4 and AC-4. |
| AR-014 | Accepted | Marker file names and printed step numbers derive from unconstrained text; fixing the label to a literal and the step to digits-only removes path and output injection. | Edit D-3 (label is a fixed literal) and D-5 (step digits-only) in section 1. |
| AR-015 | Accepted | Dropped tokens are model-written and echoed to stderr, so control characters and ANSI escapes must be neutralised and length bounded. | D-1 and section 7 now require a sanitize step (strip control/ANSI, cap 80 chars with ellipsis) before warning output; step-7 notes record it. |
| AR-016 | Accepted | owns decides which files a step may write, so tokens with a `..` segment must be dropped by the shared predicate on both routes. | D-1 and the s7 predicate definition now reject any `..` path segment; step 1 owns it; step 5 tests it. |
| AR-017 | Accepted | A stale marker could suppress the one repair for a changed plan; keying the marker to the plan content hash and clearing it at run start removes that. | Section 6 states marker hash/new-run clearing; section 10 rollback no longer calls a leftover marker harmless. |
| AR-018 | Accepted | The plan left unclear whether a later, different failure in the same run gets its own repair; the proposed rule is clear and consistent with R-1. | D-3 (s1.2.i3) and section 6 (s6.1) now state: marker cleared on pass, later failure gets one repair, failure with marker present exits 1 with no agent call. |
| AR-019 | Accepted | A crashed, timed-out or no-op repair needs a defined outcome; skipping the re-check and failing finally is simpler and safer than re-checking an untouched or damaged file. | Section 9 now defines non-zero exit, timeout, unchanged file and empty or deleted file as final failure with the marker set and no re-check. |
| AR-020 | Accepted | A single exact warning format shared by the parser route and the JSON route makes AC-2 and AC-3 testable. | Added decision D-7 to section 1 fixing the exact warning line, stream, ordering and one-line-per-token rule for both routes. |
| AR-021 | Accepted | Plan was silent on all-dropped spans and directory-like tokens; settling it keeps behavior defined without weakening the validator. | D-1 now states that all-dropped yields empty owns left to the validator, and `src/` passes the shape test and is still rejected by the validator. |
| AR-022 | Accepted | The final-failure diagnostic must be testable when the error names zero or several steps, with stream and resume text fixed. | D-5 (s1.2.i5) now specifies stderr, digits-only comma-separated steps or `step: n/a`, and the driver's standard resume command; AC-5 updated to match. |
| AR-023 | Accepted | A pre-existing spending-stop (e.g. on resume) would otherwise launch a repair agent call that cannot succeed and spends budget. | D-4 and R-2 now check spending-stop before launching the repair (no agent call) and after it (no re-check); AC-7 covers both. |
