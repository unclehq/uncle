# Change plan (Issue 286)

Omitted sections: Schema/persistence (none); Migration (none); Concurrency (none); Feature flag (env override only)

Source: https://github.com/unclehq/uncle/issues/286
Issue 286

## 1. Selected technical approach
Three independent changes: (A) schema-feedback retry in the http_agent final-answer loop; (B) shrink wire schemas by dropping long ID enums and validating IDs locally; (C) distinct 'review incomplete' unattended result.

## 2. Alternatives considered
- Prompt-only retry at reviewer level (exists, one shot, no validator context in the model call) - insufficient.
- Split schemas - larger churn than enum removal.
- Treat review-incomplete as success - rejected, hides failure.

## 3. Why preferred
Smallest surface addressing each suggested change in the request; reuses existing validate() and exit-code plumbing.

## 4. Components to modify
See change-impact table.

## 5. Not to modify
`scripts/lib/self_hosted_http.py` mode fallback and aws-bedrock/anthropic-api no-fallback policy; bounded writer path; existing tests.

## 6. Data-flow
validate() failure -> append assistant answer + user message with validator error -> constrained_completion again (max 2) -> existing error path.

## 8. Interface changes
Wire schemas lose `enum` on ID fields; local validator gains equivalent membership check. New documented exit status 3 for review-incomplete (decision D-1: 3 chosen because 1 is generic failure and 2 is used internally by implementation_incomplete_choice).

## 10. Compatibility
Fields unchanged; other failures still exit 1.

## 12. Error and recovery

Retries exhausted -> existing ValueError plus saved rejected file. Retries use the same deadline (`deadline` in http_agent) so total time stays bounded.

Feedback sanitization: the user message fed back to the provider after a schema rejection contains only a schema path (e.g. `ops[2].id`) and a fixed constraint description chosen from a closed set of templates (e.g. 'value not in the allowed set', 'required field missing', 'wrong type'). It never contains rejected values, local file paths, or raw exception text. The raw error still goes only to stderr diagnostics and the saved rejected file.

## 14. Rollback plan
Revert the commit; no persisted state or migration.

## 16. Automated-test strategy

New `scripts/tests/schema-feedback-retry-test.py` (AC-1,2,3) and `scripts/tests/review-incomplete-exit-test.sh` (AC-4). The Python suite must count requests and assert: (a) an object-shaped schema failure triggers at most two additional constrained_completion calls and zero repair_answer calls; (b) malformed JSON still follows the existing repair_final path. Add both names to scripts/tests/critical-suites.txt and run explicitly: `bash scripts/run-python-tests.sh -- schema-feedback-retry`, `bash scripts/run-shell-tests.sh` includes the shell suite via the tier file.

## 17. Regression-test strategy
Full baseline commands (AC-5); bounded-writer single-request assertion.

## 18. Manual verification
Optional live run against a grammar-limited provider; not required (LIVE_VERIFICATION phase, no credentials needed for coding).

## 19. Observability
Stderr line 'Self hosted: schema rejected; feeding errors back (attempt n/2)'; usage constraint_mode unchanged.

## Restrictions

| ID | source_kind | Source | Reqs | Property | Mechanism | CAP | Phase |
|---|---|---|---|---|---|---|---|
| R-1 | USER | CHANGE_REQUEST suggestion 2 | AC-1 | bounded retry | Env UNCLE_SCHEMA_FEEDBACK_RETRIES accepts only the integers 0, 1, or 2 (surrounding whitespace trimmed). Unset, empty, non-numeric, decimal, negative, or above-2 values are invalid and use the default 2; the value is never clamped. 0 disables schema-feedback retries. Bounded writers always use 0 regardless of the variable. For non-bounded writers, schema failures (ValueError from validate, not json.JSONDecodeError) use at most 2 additional constrained_completion calls carrying the validation feedback; these REPLACE the existing schema-error repair attempt (repair_final/repair_answer is never invoked for schema failures). After the retries are exhausted, the final rejection is saved (save_rejected) and the existing schema ValueError is raised with no further repair. Malformed-JSON (JSONDecodeError) repair is unchanged. | CAP-PY | CODING |
| R-2 | REPOSITORY | http_agent.py:1352-1356 | AC-2 | bounded writer: zero schema-feedback retries; existing recovery unchanged | skip schema-feedback retry when bounded_writer; stream-stop regrammar recovery (http_agent.py:1373-1383) and relaxed-schema repair (:1439-1458) remain unchanged | CAP-PY | CODING |
| R-3 | DESIGN | CHANGE_REQUEST suggestion 1 | AC-3 | grammar size | strings + local check; no `enum` on any targeted ID field regardless of allowed-set size; local membership validation per supplied set; empty allowed set rejects every supplied ID | CAP-PY | CODING |

## Change-impact table

| Component | Planned change | Reason | Regression risk | Test coverage |
|---|---|---|---|---|
| scripts/lib/http_agent.py | feedback retry loop around constrained_completion+validate; for non-bounded writers, schema (ValueError) failures use schema feedback instead of repair_final/repair_answer, capped at two extra constrained_completion calls; after two failed retries the rejection is saved and the existing ValueError is raised without repair; JSON-parse failures retain existing repair_final handling | AC-1, AC-2 | Medium | schema-feedback-retry-test |
| scripts/lib/worker_schemas.py | drop ID enums from every targeted ID field of the wire schemas (any allowed-set size), add local membership validation; empty allowed set rejects every ID | AC-3 | Medium | schema-feedback-retry-test, existing schema suites |
| scripts/lib/updated_plan_ops.py | same for plan-op ID fields: no enum on the wire schema, local membership validation, empty set rejects every ID | AC-3 | Medium | same |
| scripts/change-workflow.sh | review-incomplete exit path | AC-4 | Medium | review-incomplete-exit-test |
| scripts/lib/implementation-gates.sh | distinguish review-only gap in unattended branch | AC-4 | Medium | same |
| scripts/tests/schema-feedback-retry-test.py | new | AC-1..3 | Low | self |
| scripts/tests/review-incomplete-exit-test.sh | new | AC-4 | Low | self |
| scripts/tests/critical-suites.txt | register new suites | AC-5 | Low | runners |

## Traceability

| Requirement | Behavior | Invariant | Component | Automated test | Manual check |
|---|---|---|---|---|---|
| AC-1 | SB-2 (ordering: for non-bounded writers, a schema-invalid answer gets schema feedback that replaces repair_final, with at most two additional constrained_completion calls and never a repair_answer call, after 2 failed retries the rejection is saved and the existing ValueError is raised, malformed-JSON (JSONDecodeError) repair_final handling is unchanged, bounded writers always use 0 retries) | SI-1, SI-2 | http_agent.py | schema-feedback-retry-test, with separate cases: (a) schema-invalid object: total requests are the initial call plus at most 2 constrained_completion calls, and repair_answer is never called, (b) malformed JSON: the existing repair_final path is unchanged, (c) UNCLE_SCHEMA_FEEDBACK_RETRIES parsing table: unset->2, ''->2, '0'->0, '1'->1, '2'->2, '-1'->2, '3'->2, '99'->2, 'abc'->2, '1.5'->2, ' 1 '->2 (invalid, so default), (d) bounded writers always use 0 retries, request counts are asserted never to exceed 3 total completions. | none |
| AC-2 | SB-4 | SI-2 | http_agent.py | schema-feedback-retry-test: a bounded writer's completed, non-relaxed, schema-invalid response makes exactly one request and raises the existing schema ValueError, separate cases assert stream-stop regrammar and relaxed-schema repair still behave as before | none |
| AC-3 | SB-3 | SI-3 | worker_schemas.py, updated_plan_ops.py | schema-feedback-retry-test: for allowed ID sets of sizes 0, 1, 8 and 9, assert no `enum` key on each targeted ID field (field-specific, not a size threshold, unrelated enums are not asserted on), and verify local membership accepts every member and rejects a non-member, for the empty set assert every supplied ID is rejected | none |
| AC-4 | SB-5, SB-6 | SI-4 | change-workflow.sh, implementation-gates.sh | review-incomplete-exit-test | optional live |
| AC-5 | SB-1 | SI-1 | all | baseline commands | none |

## Implementation sequence

1. Schema feedback retry in the final-answer loop (grep `validate(final)` in http_agent.py). Ordering: in the `except ValueError` (schema) branch, for non-bounded writers the feedback retry replaces repair_final: at most two additional constrained_completion calls, then save the rejection and raise the existing schema ValueError with no further repair. The `except json.JSONDecodeError` branch keeps its existing repair_final behavior. Feedback is built from the schema path plus a fixed constraint description only (no rejected values, local paths, or raw exception text); a sanitization test covers this. Bounded writers perform zero schema-feedback retries; their existing relaxed-schema repair and stream-stop regrammar recovery are unchanged.
   Owns: `scripts/lib/http_agent.py`
2. Remove ID enums from wire schemas and add local membership validation; locate via grep `enum` in worker_schemas.py/updated_plan_ops.py; independent of step 1 (different files)
   Owns: `scripts/lib/worker_schemas.py`, `scripts/lib/updated_plan_ops.py`
3. Review-incomplete unattended result and docs of exit status
   Owns: `scripts/change-workflow.sh`, `scripts/lib/implementation-gates.sh`
4. New tests and tier registration. Include a test where the validator exception text contains a sentinel secret and a local path, asserting neither appears in any message sent on the retry request.
   Owns: `scripts/tests/schema-feedback-retry-test.py`, `scripts/tests/review-incomplete-exit-test.sh`, `scripts/tests/critical-suites.txt`
   Depends on: 1, 2, 3

## Scope cuts under time pressure

Steps 1-4 are required for completion; deferring step 2 or 3 requires an explicitly approved scope revision. If time runs short, step 1 (the core fix) lands first and remaining steps stay pending, not cut.

## Risks and unresolved questions
- Which schemas actually exceed provider grammar limits is unmeasured; step 2 targets ID-list enums only.
- Callers of the driver exit code (uncle_headless.py:504) must tolerate status 3; implementer checks and records any deviation in IMPLEMENTATION_NOTES.md.

## Adversarial review dispositions

| Finding | Disposition | Reason | Exact plan change |
|---|---|---|---|
| AR-001 | Accepted | The scope-cut text let mandatory acceptance criteria AC-3 and AC-4 be dropped, contradicting the spec's completion criteria. | Replace the scope-cuts section text so steps 1-4 are required and deferring step 2 or 3 needs an approved scope revision. |
| AR-002 | Accepted | The plan did not say how schema feedback relates to the existing repair attempt, so the request bound could silently grow. | Edit R-1 and s16.1.r1 to state that, for non-bounded writers, schema feedback replaces repair_final for schema errors, and that after 2 failed retries the rejection is saved and the existing ValueError raised. |
| AR-003 | Accepted | R-1 names an env override but gave no parsing or range rules, so the hard maximum of two was not enforceable or testable. | R-1 mechanism now defines accepted values 0-2, default 2 for unset/invalid, 0 disables, bounded writers always 0; AC-1 test cases added. |
| AR-004 | Accepted | The single-request assertion conflicts with preserved bounded-writer recovery (stream-stop regrammar at http_agent.py:1373-1383, relaxed-schema repair at :1439-1458), so it must be scoped. | R-2, AC-2 tests and step-1 now state bounded writers do zero schema-feedback retries, existing recovery unchanged, and the single-request assertion covers only a completed non-relaxed schema-invalid response. |
| AR-005 | Accepted | The plan left unsettled whether schema feedback replaces, precedes or follows repair_final in http_agent.py:1449-1460; an explicit ordering fixes the request bound. | AC-1 behaviors/tests and step-1 text now state feedback replaces repair_final for schema errors, JSON-parse repair is unchanged, and both paths are tested separately. |
| AR-006 | Accepted | Forwarding raw validator text could leak rejected values or local paths to the provider, violating the no-secrets requirement. | Added sanitized-feedback rule to s9 (Error and recovery) and a sanitization test requirement to step-1 and step-4. |
| AR-007 | Accepted | Repair precedence was unspecified, so request-count tests could approve different bounds; feedback must replace repair_answer for schema failures. | Edit R-1 mechanism, s16.1.r1 change and s11.1 test strategy to state schema failures use at most two extra constrained_completion calls and never repair_answer; JSON-parse repair unchanged. |
| AR-008 | Accepted | The override had no range or invalid-input rule, so retry-bound tests lacked an oracle. | R-1 mechanism defines parsing (default 2, integers 0-2, else 2, 0 disables); AC-1 tests cover unset/0/1/2/negative/3/empty/malformed. |
| AR-009 | Accepted | A size-based enum proxy would pass short ID enums and could fail unrelated enums; field-specific assertions across set sizes are a real oracle. | AC-3 tests, R-3 mechanism, and s16.1 r2/r3 changes now require per-field enum absence and local membership tests for allowed-set sizes 0, 1, 8, 9, with empty set rejecting every ID. |
