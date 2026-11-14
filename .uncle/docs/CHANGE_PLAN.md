# Change plan
Omitted sections: Schema/persistence (none); Concurrency (none); Migration (none); Feature flag (none, header-gated); Observability beyond constraint_mode (none)

Issue 268

Seeded from [unclehq/uncle#268](https://github.com/unclehq/uncle/issues/268).

## 1. Selected technical approach

- D-1: In `worker_schemas._op`, replace the optional `fields` and `new` objects of the generic op with arrays of `{name: enum(FIELD_NAMES+step), value: string}` pairs (items have both properties required, so no optional properties). Row `cells` stay a separate top-level array property (1 optional) on the generic op rather than nested inside fields/new.
- D-2: Keep the generic-op top-level optional props few: id, target, after, fields, new, cells, text, heading, block, blocks, before = ~11; reduce `block` object to required `kind` plus optional text/level/lang/items (4). Where `model_op`'s per-kind row `fields()`/set_step objects (worker_schemas.py:298-303, 356) push the total over 24, convert them to the same required pair arrays. The implementer measures with a counting helper and applies pair form until INV-1 holds.
- D-3: `plan_model.typed_op` normalizes `fields`/`new` first: a list of `{name,value}` becomes a dict (duplicate names: last wins); dicts pass through. List-valued step fields (`owns`, `depends_on`) in pair form carry a JSON-array-free comma string already accepted by `split_list` (plan_model.py:738). Row cells: before typed-op conversion, a top-level `cells` array is moved into the row payload (`new` for insert_row, `fields` for set_fields), producing the same dict the existing nested `cells` form produces. Nested-only `cells` inside `fields`/`new` remain supported unchanged (AC-3). If an op carries both top-level `cells` and nested `cells`, it is rejected with a ValueError (no silent precedence, so no row content is silently dropped).
- D-7 (bounds): every pair array has maxItems equal to the number of allowed field names for that schema (so duplicates cannot exceed the previous key set), `name` is an enum of those names, and `value` keeps the previous per-field string-length limit (8000 for fields, EDIT_MAX for new, as in worker_schemas.py:181-200; EDIT_MAX for cells items, maxItems 40). `typed_op` rejects a pair array longer than its allowed-name count or a value over its limit before normalizing.
- D-4: `_request` stores the `x-seren-schema-relaxed` header value per thread in a small holder (like `_record_budget_header`, no persistence); `x-seren-schema-check` may be recorded for diagnostics only and never affects mode or repair eligibility. Header rule: trim whitespace; any remaining non-empty `x-seren-schema-relaxed` value marks the response relaxed regardless of its contents (no malformed case); an absent or whitespace-only value leaves the mode unchanged; `x-seren-schema-check` alone never marks a response relaxed. `_final_call` clears the holder before `compatible_post` and, if relaxed, `constrained_completion` returns mode `json_schema_relaxed` (or the used mode + `_relaxed`). Return stays a 4-tuple. Regression coverage (AC-4/AC-6 traceability) includes a check-header-only case: a response carrying only `x-seren-schema-check` is not relaxed and its mode is unchanged.
- D-5: `http_agent` computes `relaxed = mode.endswith('_relaxed')`; guards at 1442 and 1447 become `final.startswith('{') and (not bounded_writer or relaxed)`, where `final` is the already-trimmed output. A relaxed bounded reply gets one targeted repair (existing `repair_answer`) only when its trimmed output begins with `{`; other invalid output (JSON array, scalar, null, or non-JSON text) raises the existing ValueError without repair. Non-relaxed bounded writers still raise without repair. `usage['constraint_mode']` carries the relaxed mode.
- D-6: Every updated-plan completion path must propagate the relaxed header. If streaming transport bypasses `_request`, read the same header at its response site; if headers are not exposed there, route those completions through the non-streaming transport (never leave a path that cannot report relaxed mode) and record the routing in IMPLEMENTATION_NOTES.

## 2. Alternatives considered
| Alt | Verdict |
|---|---|
| Drop generic op, rely on model_op variants | Rejected: kind-only callers and unknown-id paths still need it |
| Split schema per op kind (many small schemas) | Rejected: larger change, driver picks schema once |
| Only fix header handling | Rejected: leaves schemas unenforced on Claude |

## 3. Why preferred
Pair arrays remove ~129 optional props with a small normalizer in one place and keep every consumer on the dict contract.

## 4/5. Components
Modify: worker_schemas.py, plan_model.py, self_hosted_http.py, http_agent.py, tests. Do not modify: updated_plan_ops.py, driver shell scripts, project-plan schemas, plan_step_recovery.py, supervisor_runner.py (4-tuple preserved).

## 6-8. Data flow / interface
Model packet `fields`/`new` shape changes to pair arrays in the schema only; dict form still tolerated. No public CLI change. `docs/plan-model.md` updated if it shows the packet shape.

## 12. Error and recovery

Relaxed + invalid -> one targeted repair; still invalid -> existing ValueError and driver group retry. Header rule: trim whitespace from x-seren-schema-relaxed; any remaining non-empty value (whatever its contents) means relaxed; an absent or whitespace-only value leaves the mode unchanged (enforced path). x-seren-schema-check alone never marks a response relaxed.

## 14. Rollback
Revert the commits touching the files in the change-impact table; nothing persisted.

## 16-17. Automated and regression tests

New suite `scripts/tests/edit-schema-limits-test.py` covers AC-1,2,4,5,6 (tests of Git behavior: none). AC-5 repair applies only when the trimmed relaxed bounded reply starts with `{`; the suite includes a positive case (a `{`-leading reply that is schema-invalid gets exactly one repair) and negative cases (a schema-invalid or malformed reply whose trimmed text does not start with `{`, such as a JSON array, scalar, null, or other non-object, raises without repair). Existing updated-plan suites guard AC-3. Defect injection: restore the old generic op and confirm AC-1 fails; remove the relaxed guard and confirm AC-5 fails (regression test failing before the fix: AC-1 and AC-5). Verification commands: `bash scripts/run-python-tests.sh`, `bash scripts/run-shell-tests.sh`, and `bash scripts/run-python-tests.sh -- edit-schema-limits` (new suite is outside the default tier unless added to critical-suites.txt; step 4 adds it explicitly to the command list rather than editing the tier).

## 18. Manual verification
Optional live check with a Bedrock-backed Seren route (needs credentials, LIVE_VERIFICATION only): run an updated-plan stage and confirm no `x-seren-schema-relaxed`, or that a relaxed reply is repaired. Not required for coding.

## Restrictions

| ID | source_kind | Source | Reqs | Property | Mechanism | Rationale | CAP | Feasibility evidence | Phase |
|---|---|---|---|---|---|---|---|---|---|
| R-1 | USER | CHANGE_REQUEST Requested fix 1 | AC-1 | <=24 optional props per edit schema; pair arrays bounded by allowed-name count and previous per-field length limits (D-7) | Pair arrays (D-1/D-2) + counting test | Bedrock limit | CAP-PY | inspected worker_schemas.py:194-202,298-303 | CODING |
| R-2 | USER | CHANGE_REQUEST Requested fix 2 | AC-4, AC-5 | relaxed reply allows repair; only a non-empty (trimmed) x-seren-schema-relaxed value marks a response relaxed, whatever its contents; absent/blank values and x-seren-schema-check alone leave the mode and repair eligibility unchanged | D-4/D-5/D-6; header trimmed, any non-empty x-seren-schema-relaxed value = relaxed, absent/whitespace-only = unchanged; check header alone never relaxes; relaxed header propagated on every updated-plan completion path, with non-streaming fallback where streaming hides headers; tests cover arbitrary non-empty relaxed values, blank/absent, and check-only responses | Header is the only signal | CAP-PY | inspected http_agent.py:1442-1450, self_hosted_http.py:1375-1393 | CODING |
| R-3 | REPOSITORY | CLAUDE.md | AC-3 | Existing tests unweakened | No edits to existing assertions | policy | CAP-PY | n/a | CODING |
| R-4 | DESIGN | plan | AC-2, AC-3 | Consumers keep dict contract | D-3 normalizer in typed_op, including top-level cells mapping (insert_row->new, set_fields->fields; reject top-level plus nested cells) | one choke point | CAP-PY | plan_model.py:808-830 | CODING |

CAP-PY = python3 and the repository test runners (available locally).

## Change-impact table

| Component | Planned change | Reason | Regression risk | Test coverage |
|---|---|---|---|---|
| `scripts/lib/worker_schemas.py` | Pair-array fields/new; fewer optionals | INV-1 | Medium: other schema callers | edge-schema-limits-test, ops tests |
| `scripts/lib/plan_model.py` | typed_op accepts pair arrays and maps top-level cells into the row payload (nested cells win on conflict) | D-3 | Medium | edit-schema-limits-test, updated-plan-ops-test |
| `scripts/lib/self_hosted_http.py` | Capture relaxed header; any trimmed non-empty value yields relaxed mode; check header alone and blank/absent do not | D-4 | Low | edit-schema-limits-test (arbitrary non-empty value, blank, absent, check-only cases), self-hosted suites |
| `scripts/lib/http_agent.py` | Repair gate for relaxed | D-5 | Medium: EI-1 | edit-schema-limits-test, writer-retries |
| `scripts/tests/edit-schema-limits-test.py` | New suite | AC-1,2,4,5,6 | None | itself |
| `docs/plan-model.md` | Packet shape note if present | docs | None | none |

## Traceability

| Requirement | Behavior | Invariant | Component | Automated test | Manual check |
|---|---|---|---|---|---|
| AC-1 | B-1 | INV-1, INV-2 | worker_schemas.py | edit-schema-limits-test (optional-property count <=24; each pair array maxItems equals its allowed-name count; pair value maxLength equals the old per-field limit; over-count or over-long packet rejected) | none |
| AC-2 | B-2 | INV-3 | plan_model.py | edit-schema-limits-test: row ops (insert_row, set_fields) with top-level cells produce typed ops equal to the nested-dict form (new/fields); nested-only form unchanged; simultaneous top-level and nested cells are rejected | none |
| AC-3 | B-3, B-8 | INV-3 | plan_model.py | existing suites | none |
| A Converse/chat response whose `x-seren-schema-relaxed` header is non-empty after trimming whitespace (any content) reports a relaxed mode; an absent or whitespace-only value leaves the mode unchanged, and `x-seren-schema-check` alone never marks a response relaxed. | B-4 | INV-5 | self_hosted_http.py | edit-schema-limits-test (arbitrary non-empty relaxed values, whitespace-only, absent, and check-header-only case: x-seren-schema-check present, relaxed absent -> mode unchanged) | optional live |
| A relaxed bounded-writer reply that is invalid JSON or violates the artifact schema receives exactly one targeted repair only when its trimmed output begins with `{`; invalid output not beginning with `{` (e.g. a JSON array, scalar or null) raises the existing ValueError without repair. | B-5 | INV-4 | http_agent.py | edit-schema-limits-test (relaxed repair cases; negative non-object JSON case; test driving the updated-plan completion through its actual transport with a relaxed header and asserting relaxed mode) | optional live |
| AC-6 | B-6, B-7 | INV-4 | http_agent.py | edit-schema-limits-test (includes check-header-only bounded writer: no repair), writer-retries | none |

## Implementation sequence

1. **Step s1: sole owner of `scripts/tests/edit-schema-limits-test.py`: write the optional-property counter and all AC-1..AC-6 tests (AC-1 count and pair-array maxItems/maxLength bounds; AC-2 typed_op equivalence with literal expected dicts for insert_row->new and set_fields->fields top-level cells, nested-only legacy form, and simultaneous top-level+nested rejection; AC-4 header matrix; AC-5 repair cases incl. non-object JSON; AC-6 check-header-only bounded writer; updated-plan completion path transport/relaxed-header test).** — Owns: `scripts/tests/edit-schema-limits-test.py`
   Owns: `scripts/tests/edit-schema-limits-test.py`
2. **Step s2: pair-array schema in `_op`/`model_op`/set_step until INV-1 holds.** — Owns: `scripts/lib/worker_schemas.py` — Depends on: 1
   Owns: `scripts/lib/worker_schemas.py`
   Depends on: 1
3. **Step s3: `typed_op` pair normalizer plus top-level cells mapping (insert_row->new, set_fields->fields) and rejection of simultaneous top-level and nested cells, following the schema shape defined in step 2.** — Owns: `scripts/lib/plan_model.py` — Depends on: 1, 2
   Owns: `scripts/lib/plan_model.py`
   Depends on: 1, 2
4. **Step s4: header capture and relaxed mode in transport; mandatory deliverable: decide whether every updated-plan completion path exposes the relaxed header, and where streaming cannot, route those completions through the non-streaming transport (any `http_agent.py` call-selection change goes in step 5).** — Owns: `scripts/lib/self_hosted_http.py` — Depends on: 1
   Owns: `scripts/lib/self_hosted_http.py`
   Depends on: 1
5. **Step s5: relaxed repair gate (uses step 4's mode string; builds on step 4 contract).** — Owns: `scripts/lib/http_agent.py` — Depends on: 4
   Owns: `scripts/lib/http_agent.py`
   Depends on: 4
6. **Step s6: update docs and run the new suite command (no edits to the test file; failures return to the owning step).** — Owns: `docs/plan-model.md` — Depends on: 2, 3, 4, 5
   Owns: `docs/plan-model.md`
   Depends on: 2, 3, 4, 5

Steps 2 and 4 touch disjoint files and can run in parallel after step 1; step 3 follows step 2; step 5 follows step 4; step 6 follows 2, 3, 4 and 5.

## Scope cuts under time pressure

Cut first: docs update; then live check. Never cut: AC-1, AC-5, AC-3, and relaxed-header propagation on every updated-plan completion path (D-6 may change the transport, but not be dropped).

## Risks and unresolved questions

- Counting rule for Bedrock may be stricter than assumed; mitigated by whole-schema conservative count, with live check optional.
- Streaming path headers (D-6) resolved in implementation by inspection; if streaming cannot expose them, updated-plan completions are routed through the non-streaming transport, so this is not a blocker.
- Pair-array model output for list-valued step fields uses comma strings; verified by AC-2 test.

## Adversarial review dispositions

| Finding | Disposition | Reason | Exact plan change |
|---|---|---|---|
| AR-001 | Accepted | D-1/D-3 left the destination and conflict handling of top-level cells undefined, risking lost row data; a mapping rule is needed. | Rewrite D-1 (cells stays a top-level array) and D-3 (typed_op maps cells into new/fields; conflicts rejected; nested cells still supported); AC-2 and the s15 risk follow. |
| AR-002 | Accepted | Valid JSON that violates the artifact schema (array, scalar, null) must get the one repair AC-5 requires; only malformed JSON needs the '{' check. | D-5 (s1.1.i5) drops the startswith('{') test from the schema-violation guard; s8.1 adds a non-object negative test. |
| AR-003 | Accepted | AC-4 reporting is unconditional, so streaming header capture cannot be optional; unexposed headers must route to the non-streaming transport. | D-6 (s1.1.i6), R-2, AC-4, s14.1 and s15.1.i2 now require every updated-plan completion path to propagate the relaxed header or use the non-streaming transport. |
| AR-004 | Accepted | Spec and plan disagree on malformed/blank headers; a single trim-then-non-empty rule resolves it. | Edit s6.1, R-2 and AC-4 to state: trim whitespace; any non-empty x-seren-schema-relaxed value means relaxed; absent or whitespace-only leaves mode unchanged. |
| AR-005 | Accepted | Real gap: D-1 relocates row cells to a top-level array but D-3 defined no mapping or precedence, risking dropped row content. | D-3 (s1.1.i3) now maps top-level cells into the row payload with nested cells taking precedence; s11.1.r2 and AC-2 tests cover it. |
| AR-006 | Accepted | D-4 stores both headers without saying which controls relaxed mode; only a nonblank x-seren-schema-relaxed value should, so check-only must not enable repair. | Edit D-4 (s1.1.i4) to make only a nonblank relaxed header control the mode, and add a check-header-only regression case to AC-4/AC-6 traceability. |
| AR-007 | Accepted | Pair arrays would otherwise drop the finite key set and string-length bounds of the existing field objects. | Add a bounds rule to D-2 and D-3 (s1.1) and extend INV-1 coverage in R-1/AC-1 so tests assert maxItems and per-field maxLength. |
| AR-008 | Accepted | AC-5 and D-5 disagreed on non-`{` output; keeping the existing `{` guard is minimal and safe, so AC-5 is aligned to it and a negative case added. | Edit D-5 (s1.1.i5), AC-5 requirement (s12.1) and the s8.1 test list to state repair only for trimmed output starting with `{`, with a non-object negative test. |
| AR-009 | Accepted | D-1 relocates cells but D-3 never defined the destination or collision rule, so tests and normalizer could disagree. | D-3 gains a cells-mapping rule (insert_row->new, set_fields->fields, reject nested+top-level); AC-2 and R-4 updated. |
| AR-010 | Accepted | Spec section 8 (malformed header = enforced) conflicts with AC-4 and section 15; one rule on the relaxed header makes the test oracle definite. | D-4 (s1.1.i4) and R-2 state the header rule: trimmed non-empty x-seren-schema-relaxed marks relaxed; x-seren-schema-check alone never does; AC-4 tests and s11 row r3 cover arbitrary values and check-only. |
