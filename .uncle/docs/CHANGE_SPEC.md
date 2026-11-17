# Change spec (Issue 286)

Omitted sections: Performance (negligible; retries bounded); Migration (none); Prototype isolation (not a prototype)

## 1. Change type
Bug fix / robustness.

## 2. Problem statement
Self-hosted reviewer/plan-edit output that fails the artifact schema is recorded as a missing delivery; the unattended run then exits 1 at IMPLEMENT even though the implementer delivered every acceptance row.

## 3. Current behavior
Baseline B-3..B-6.

## 4. Desired behavior
Schemas compile into smaller grammars; a schema-invalid final answer gets bounded validator-error feedback and retry; an unattended run whose only gap is a review delivery ends with a distinct, documented 'review incomplete' result.

## 5. Observable behavior table
| ID | Class | Trigger | Current behavior | Expected behavior | Verification |
|---|---|---|---|---|---|
| SB-1 | PRESERVE | Valid final answer | Accepted | Unchanged | existing suites |
| SB-2 | MODIFY | Final answer fails schema | ValueError after repair attempt | Validator errors sent back to model, up to 2 retries, then the same ValueError | new python suite with fake server |
| SB-3 | MODIFY | ID-list enums in reviewer/plan-edit schemas | Large enum grammars | IDs are plain strings in the wire schema, checked locally against the same allowed set | schema size + rejection tests |
| SB-4 | PRESERVE | Bounded updated-plan writer | No retries | Still none | existing test + new assertion |
| SB-5 | MODIFY | Unattended, implementation complete, review delivery missing/rejected | exit 1 'pending at IMPLEMENT' | Message 'review incomplete', distinct documented exit status | shell suite |
| SB-6 | PRESERVE | Unattended, acceptance rows not delivered | exit 1 / waive path | Unchanged | existing shell suites |

## 6. Invariant table
| ID | Status | Invariant | Scope | Enforcement point | Verification |
|---|---|---|---|---|---|
| SI-1 | EXISTING | Invalid output is never accepted as an artifact | all validators | http_agent.py validate | new test |
| SI-2 | STRENGTHENED | Schema feedback retries are bounded (max 2) | final-answer loop | http_agent.py | new test counting requests |
| SI-3 | STRENGTHENED | Allowed-ID checks still enforced after enum removal | worker packets, plan ops | local validator | new test with unknown ID |
| SI-4 | EXISTING | Missing acceptance rows are never reported as review-incomplete | implementation gate | implementation-gates.sh | shell test |
No RELAXED or REMOVED invariants.

## 7. Compatibility
Packet field names unchanged; existing exit 1 meaning retained for all other failures.

## 8. Error behavior
After retries exhausted the existing ValueError and saved rejected file remain.

## 10. Security
No secrets in feedback; the validator message is the only added content.

## 12. Rollback
Revert commit; no persisted state changes.

## 14. Non-goals
Provider-specific grammar tuning; changing aws-bedrock/anthropic-api no-fallback policy; interactive gate behavior.

## 15. Assumptions
Caller can treat a new documented non-zero exit code as distinct from 1 (UNRESOLVED check in uncle_headless.py).

## Acceptance criteria

| ID | Criterion | Verification |
|---|---|---|
| AC-1 | When a final answer fails schema validation, http_agent sends the validator error back to the model and retries at most 2 times before raising the existing 'violates the artifact schema' ValueError; a corrected answer on retry is accepted. | New suite scripts/tests/schema-feedback-retry-test.py with a stub constrained_completion: asserts request count, error text in the follow-up message, success on second try, failure after the bound. |
| AC-2 | The bounded updated-plan writer path performs no schema-feedback retry. | Same suite: UNCLE_UPDATED_PLAN_ANSWER_TOKENS set, assert exactly one request. |
| AC-3 | Allowed-ID enum lists (section/acceptance IDs) are removed from the schema sent to the model for reviewer and plan-edit outputs, and the same constraint is enforced by local validation; an unknown ID is still rejected. | Schema-size assertion (no enum list over 8 entries in wire schemas) and rejection test in the new suite plus existing schema suites. |
| AC-4 | In an unattended run where all acceptance rows are delivered and only a review delivery is missing or rejected, the driver prints 'review incomplete' and exits with a distinct documented status instead of the generic IMPLEMENT-pending exit 1; missing acceptance rows still behave as before. | New shell suite scripts/tests/review-incomplete-exit-test.sh for both cases. |
| AC-5 | Existing shell and Python verification commands show no new failures versus baseline. | bash scripts/run-shell-tests.sh; bash scripts/run-python-tests.sh |

