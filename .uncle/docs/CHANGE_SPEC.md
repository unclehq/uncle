# Change spec
Omitted sections: Migration (no persisted data); Prototype isolation (none); Performance (only the re-ask saving); Security (no new exposure beyond reading two non-secret headers)

## 1. Change type
Bug fix.

## 2. Problem statement
Updated-plan edit schemas exceed Bedrock's 24-optional-property grammar limit, so Claude models are not schema-constrained; the adapter also ignores the `x-seren-schema-relaxed` signal and, for bounded writers, skips repair, costing a full re-ask per bad packet.

## 3. Current behavior
See baseline EB-1, EB-2.

## 4. Desired behavior
Every edit schema sent for an updated-plan writer has at most 24 optional properties; a reply flagged relaxed is treated as unenforced and a bounded writer may run the targeted repair step.

## 5. Observable behavior table
| ID | Class | Trigger | Current behavior | Expected behavior | Verification |
|---|---|---|---|---|---|
| B-1 | MODIFY | Driver builds an updated-plan edit schema (any ids/model shape) | 133-159 optional props | <=24 optional props counted over whole schema | AC-1 test |
| B-2 | MODIFY | Model writes generic-op `fields`/`new` as required array of `{name,value}` pairs | not accepted | Converted to the same typed ops as dict form | AC-2 test |
| B-3 | PRESERVE | Model writes `fields`/`new` as dict of strings (EB-5) | applied | Still applied identically | AC-3 test |
| B-4 | ADD | Response has `x-seren-schema-relaxed` | ignored | Mode reported as relaxed/unenforced | AC-4 test |
| B-5 | MODIFY | Bounded writer reply relaxed and schema-invalid | ValueError, group re-ask | Targeted repair runs once | AC-5 test |
| B-6 | PRESERVE | Bounded writer reply not relaxed and schema-invalid | ValueError, no repair | Unchanged | AC-6 test |
| B-7 | PRESERVE | Non-bounded writer schema-invalid | targeted repair | Unchanged | existing + AC-6 |
| B-8 | PRESERVE | Server sends no header | no change | No change | existing suites |

## 6. Invariant table
| ID | Status | Invariant | Scope | Enforcement point | Verification |
|---|---|---|---|---|---|
| INV-1 | NEW | No edit schema has >24 optional properties | worker_schemas._op/model_op outputs | schema builders | AC-1 |
| INV-2 | EXISTING | Enum-constrained ids still restrict op id/target/after | edit schemas | `_op` pick | AC-1 |
| INV-3 | EXISTING | typed_op validates every op before apply | plan_model | typed_op | existing ops test |
| INV-4 | STRENGTHENED | Bounded writer repair only when schema enforcement is known absent (relaxed header) | http_agent | final-answer path | AC-5, AC-6 |
| INV-5 | EXISTING | Headers other than the two named are not persisted; API key never logged | self_hosted_http | _request | existing spending/budget suites |

No RELAXED or REMOVED invariants.

## 7. Compatibility
Dict-form `fields`/`new` remain accepted by consumers. `constrained_completion` keeps its 4-tuple return.

## 8. Error and failure behavior
Relaxed + repair still invalid: raise the existing schema ValueError (driver retries group). Header absent/malformed: treat as enforced.

## 12. Rollback
Revert the commit; no persisted state.

## 14. Non-goals
Project-plan typed sections schema; Seren server changes; changing driver retry grouping; budgets.

## 15. Assumptions
Any non-empty `x-seren-schema-relaxed` value signals unenforced schema. Optional-property count is measured over the entire schema including all anyOf branches and nested objects (conservative).

## Acceptance criteria

| ID | Criterion | Verification |
|---|---|---|
| AC-1 | For representative inputs (ids list, real plan model, kind-only, intent), every updated-plan edit schema built by worker_schemas has at most 24 optional properties across the whole schema, and op id/target/after enums are preserved. | New suite scripts/tests/edit-schema-limits-test.py counts optional properties recursively and asserts <=24 and enum presence. |
| AC-2 | A generic op whose `fields` or `new` is an array of `{name,value}` pairs (name from the field-name enum) is converted by typed_op to the same typed op as the equivalent dict form, including step fields and rows. | New test compares typed_op output for pair form vs dict form. |
| AC-3 | Dict-form `fields`/`new` still produce identical typed ops; existing updated-plan suites pass unchanged. | bash scripts/run-python-tests.sh and updated-plan-ops-test.py. |
| AC-4 | When a Converse/chat response carries a non-empty `x-seren-schema-relaxed` header, constrained_completion reports a mode marked relaxed; without the header the mode is unchanged. | New test stubbing the transport/_request seam with and without the header. |
| AC-5 | A bounded updated-plan writer whose relaxed reply fails schema validation runs targeted repair_answer once and returns the repaired packet; the failure text and constraint_mode record the relaxed mode. | New http_agent test with stubbed constrained_completion returning a relaxed mode and invalid then repaired JSON. |
| AC-6 | A bounded writer whose non-relaxed reply violates the schema still raises the schema ValueError without repair, and a non-bounded writer still repairs. | Extended updated-plan-writer-retries-test.py or the new suite. |

