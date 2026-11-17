# Baseline report (Issue 286)

Omitted sections: Reproduction result (cannot reproduce without a grammar-limited provider; mocked in tests); Areas outside change folded into section 12

## 1. Change-request summary
See .uncle/docs/CHANGE_REQUEST.md (Issue 286): unattended runs exit 1 at IMPLEMENT when self-hosted reviewer JSON fails the output schema after a grammar-constrained mode is unavailable/too large and the call falls back to a looser mode.

## 2. Repository architecture
Bash drivers (`scripts/change-workflow.sh`, `scripts/lib/*.sh`) call Python self-hosted runners (`scripts/lib/self_hosted.py`, `http_agent.py`, `self_hosted_http.py`). Output schemas live in `scripts/lib/worker_schemas.py`, `runner_schema.py`, `updated_plan_ops.py`.

## 3. Relevant code paths
- `scripts/lib/self_hosted_http.py:1534` `_final_call` (modes json_schema/json_object/prompt); `:1568` `constrained_completion` falls through `caps['modes']`, a rejected mode (HTTP in `REJECTED`, line 30, includes 400) is skipped. aws-bedrock/anthropic-api profiles (`:1571`) have no fallback.
- `scripts/lib/http_agent.py:1344-1463` final-answer loop; `validate(final)` at 1450; for non-bounded writers a `{`-prefixed invalid answer goes to `repair_answer` (1442-1458); otherwise `ValueError` with `save_rejected('schema')` (658) is raised. No validator-error feedback to the model.
- `scripts/lib/self_hosted.py:2463-2548` reviewer loop; `:2473` raises InvalidReviewerDocument when the delivery file is absent; `:2506-2544` one retry (`format_retried`) appending the error to the prompt; second failure re-raises.
- `scripts/change-workflow.sh:4600-4640` repair-once then 'Implementation remains incomplete' then `implementation_incomplete_choice`; non-zero/other status -> `exit 1`.
- `scripts/lib/implementation-gates.sh:76-83` unattended with no rejected rows returns 1.
- Schemas with `enum`: `worker_schemas.py` (20 occurrences), `runner_schema.py` (5), `updated_plan_ops.py` (1), `self_hosted.py` (8).

## 4. Current observable behavior
| ID | Trigger | Current result | Evidence | Must preserve? |
|---|---|---|---|---|
| B-1 | Server accepts json_schema | Answer shaped by server, validated locally | http_agent.py:1450 | Yes |
| B-2 | json_schema rejected with 400 | Falls to next mode, mode remembered in caps['rejected'] | self_hosted_http.py:1588-1596 | Yes |
| B-3 | Final answer fails schema, starts with `{` | repair_answer attempted | http_agent.py:1456-1458 | Yes |
| B-4 | Final answer fails schema, repair unavailable | ValueError 'violates the artifact schema', rejected text saved to .uncle/workflow/logs | http_agent.py:1459 | Yes (message prefix) |
| B-5 | Reviewer delivery missing/invalid | One prompt-appended retry, then InvalidReviewerDocument | self_hosted.py:2527-2544 | Yes |
| B-6 | Implementation incomplete, unattended, no rejected rows | Prints 'run remains pending at IMPLEMENT', return 1, driver exit 1 | implementation-gates.sh:76-83 | MODIFY only for review-delivery-only case |

## 5. Existing invariants
| ID | Invariant | Current enforcement | Existing test | Confidence |
|---|---|---|---|---|
| I-1 | Invalid output is never published as a reviewer artifact | self_hosted.py:2506-2529 | self-hosted suites | Medium |
| I-2 | Retries are bounded | format_retried flag; attempts list | self-hosted-retry-test.py (HTTP-level) | Medium |
| I-3 | Unattended never waives an empty row set | implementation-gates.sh:76-83 | implementation-gate shell suites (unverified names) | Medium |
| I-4 | A schema-valid answer is the only accepted answer | validate() http_agent.py:1450 | UNRESOLVED exact test | Medium |

## 6. Interface contracts
Worker packet/plan-op JSON schemas (worker_schemas.py, updated_plan_ops.py) are consumed by the validator and by other stages; field names must not change. Exit status of `change-workflow.sh` is consumed by `uncle_headless.py:504`.

## 7. Existing automated-test coverage
Python suites `scripts/tests/*-test.py` (runner `bash scripts/run-python-tests.sh`, default tier from scripts/tests/critical-suites.txt) and shell suites (`bash scripts/run-shell-tests.sh`). Shell and Python runners use separate temp dirs and bind no shared ports, so they run as one parallel group. Self-hosted suites include self-hosted-retry-test.py (transport retries), -flavor, -refused-options.

## 9. Baseline test results
Commands are from CLAUDE.md-style runner guidance and the scripts present (scripts/run-shell-tests.sh, scripts/run-python-tests.sh). Not executed here; the driver baseline supplies results. Some Python suites are known to fail on a clean checkout.

## 10. Existing failures
None documented beyond the note above. UNRESOLVED which suites fail at baseline; see .uncle/workflow/green-check.baseline.tsv.

## 12. Likely change surface
http_agent.py final-answer loop; self_hosted_http.py (grammar-too-large detection); worker_schemas.py / updated_plan_ops.py / runner_schema.py (enum shrink); self_hosted.py reviewer loop; change-workflow.sh and implementation-gates.sh (unattended review-incomplete result); a new Python suite.

## 13. Regression-sensitive components
schema validation shared by all stages; bounded updated-plan writer (must not gain retries, http_agent.py:1352-1356); implementation gate used by interactive runs.

## 15. Unknowns and assumptions
- Exact set of schemas exceeding provider grammar limits is unknown; enum shrink is applied to ID-list enums only.
- Whether a distinct exit code is acceptable to callers (uncle_headless.py) is unknown; assumed any non-zero is a failure and a documented code is additive.

## 16. Initial risk assessment
Medium: shared validation path; loosening enums moves ID checking to local validation, which must remain strict.

## Exact build and test commands executed

```sh
bash scripts/run-shell-tests.sh
bash scripts/run-python-tests.sh
```

