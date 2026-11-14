# Baseline report
Omitted sections: Reproduction (needs live Bedrock; evidence is the issue text); Existing failures (none documented in repo; driver baseline is authority)

## 1. Change-request summary
Issue 268 (CHANGE_REQUEST.md): updated-plan edit schemas carry 130+ optional properties, so Claude-on-Bedrock cannot grammar-enforce them and the Seren route silently relaxes to json_object. Fix (1): keep each edit schema <=24 optional properties. Fix (2): when the reply carries `x-seren-schema-relaxed`, treat the schema as unenforced and allow targeted repair for bounded writers.

## 2. Repository architecture
Shell-driven workflow with Python libs in `scripts/lib/`. Schemas: `worker_schemas.py`. Op semantics: `plan_model.py`. Writer orchestration: `updated_plan_ops.py`. HTTP agent loop: `http_agent.py`. Transport: `self_hosted_http.py`.

## 3. Relevant code paths
- `scripts/lib/worker_schemas.py:185-219` `_op(ids, model)`: generic variant (194-202) lists `fields` and `new` objects with every `FIELD_NAMES`+step name optional (`_strings` at 181), plus `cells`; `block` object (191-193); anyOf adds `_new_step` (222-229) and `model_op` set_fields/insert_row variants.
- `worker_schemas.py:279-303` `model_op`: per-row-kind `fields()` objects, all optional (298-303).
- `worker_schemas.py:356` set_step fields, also all optional.
- `plan_model.py:734-735` FIELD_NAMES, OP_NAMES; `plan_model.py:808-830` `typed_op(model, flat)` reads `flat['fields']` as a dict (`fields.items()`); `new_step_op` at 891.
- `updated_plan_ops.py:147,568,586,910,989,1092` call `pm.typed_op` on model-written flat ops.
- `self_hosted_http.py:1375-1393` `_request` returns parsed JSON only; response headers used solely by `_record_budget_header` (212). `_final_call` 1506-1533; `constrained_completion` 1536-1568 (Bedrock/Anthropic profile returns mode 'json_schema' at 1546; other profiles loop modes). `compatible_post` 262.
- `http_agent.py:1352-1356` bounded writer: `attempts[:1]`; `1442-1450` repair_answer skipped when `bounded_writer`; `repair_answer` 1304-1320; `usage['constraint_mode']=mode` 1421.

## 4. Current observable behavior
| ID | Trigger | Current result | Evidence | Must preserve? |
|---|---|---|---|---|
| EB-1 | Updated-plan writer sent schema with >24 optional props to Claude via Seren/Bedrock | Server relaxes to json_object; reply may violate schema; writer fails after full re-ask (~2.5 min) | issue text; http_agent.py:1442-1450 | No (fix) |
| EB-2 | Reply carries `x-seren-schema-relaxed` | Header ignored; mode recorded 'json_schema' | self_hosted_http.py:1385-1393 | No (fix) |
| EB-3 | Non-bounded writer, schema-violating JSON | `repair_answer` targeted repair | http_agent.py:1442-1448 | Yes |
| EB-4 | Bounded writer, enforced-schema reply violating schema | ValueError, driver retries group | http_agent.py:1449 | Yes |
| EB-5 | Model writes flat op with `fields`/`new` as dict of strings | `typed_op` applies it | plan_model.py:808-830 | Yes (still accepted) |
| EB-6 | Servers without the header (OpenAI, vLLM, Ollama, Bedrock native) | Behavior as EB-3/EB-4 | self_hosted_http.py:1523-1546 | Yes |

## 5. Existing invariants
| ID | Invariant | Current enforcement | Existing test | Confidence |
|---|---|---|---|---|
| EI-1 | Bounded updated-plan writer never grows a prompt-mode or tool-repair tail when schema was enforced | `attempts[:1]`, `not bounded_writer` guards (http_agent.py:1352-1356,1442-1449) | updated-plan-writer-retries-test.py | Medium |
| EI-2 | Ops reaching `apply_ops` are typed/validated by `typed_op`; unknown ids/ops raise PlanError | plan_model.py:808+ | updated-plan-ops-test.py | High |
| EI-3 | Op ids/targets constrained to enum of known ids when ids given | worker_schemas.py:189 `pick` | updated-plan-ops-test.py (assumed) | Medium |
| EI-4 | Response headers never leak the API key; budget header recorded atomically | self_hosted_http.py:212-225 | self-hosted-spending-stop-test.py | Medium |

## 6. Current API, schema, interface contracts
Edit-op packet: `{ops:[{op,id,target,after,fields:{name:str...},text,new:{...},block,heading,blocks}...]}`; `fields`/`new` are string-valued objects. `constrained_completion` returns `(text, reason, usage, mode)`; mode strings feed `usage['constraint_mode']` and error text. Docs: `docs/plan-model.md`.

## 7. Existing automated-test coverage
Python suites in `scripts/tests/*-test.py` (runner `scripts/run-python-tests.sh`, critical tier from `scripts/tests/critical-suites.txt`); shell suites via `scripts/run-shell-tests.sh`. Relevant: updated-plan-ops-test.py, updated-plan-writer-retries-test.py, updated-plan-fast-path-test.py, updated-plan-nested-section-test.py, self-hosted-*-test.py. No test counts optional properties or reads schema-relaxed headers. The two runners use separate temp dirs and no shared ports (per workflow guidance), so they run as one parallel group.

## 9. Baseline test results
Commands come from scripts/run-python-tests.sh and scripts/run-shell-tests.sh (task guidance). No pre-existing failure was documented in the files read; some Python suites may fail on a clean checkout. I did not run them: the driver's baseline (`.uncle/workflow/green-check.baseline.tsv`) is authoritative.

## 12. Likely change surface
`worker_schemas.py`, `plan_model.py` (typed_op input normalization), `self_hosted_http.py`, `http_agent.py`, tests under `scripts/tests/`, `docs/plan-model.md` if it documents the packet shape.

## 13. Regression-sensitive components
`typed_op` and all updated_plan_ops callers; schema consumers other than updated-plan writers (`_op` kind-only callers, `model_op`); bounded-writer retry logic; `compatible_post` streaming path (may bypass `_request`); `plan_step_recovery.py` and `supervisor_runner.py` call `constrained_completion` and unpack 4 values.

## 14. Outside the change
Typed project-plan sections schema (issue says untested), Seren server behavior, driver retry grouping, non-updated-plan schemas, approval gates.

## 15. Unknowns and assumptions
- Exact optional-property counting rule used by Bedrock (assumed: every non-required property across the whole schema incl. all anyOf branches and nested objects). UNRESOLVED precisely; plan counts conservatively.
- Whether streaming transport exposes response headers (to inspect in implementation).
- Header value format of `x-seren-schema-relaxed`: assumed any non-empty value means unenforced.

## 16. Initial risk assessment
| Risk | Level |
|---|---|
| Reshaping `fields` breaks model-written packets already accepted by consumers | Medium |
| `model_op` per-kind row `fields` alone may exceed 24 | Medium |
| Header not visible on streaming path | Medium |
| Allowing repair for bounded writers breaks EI-1 when schema was enforced | Low (gated on header) |

## Exact build and test commands executed

```sh
bash scripts/run-python-tests.sh
bash scripts/run-shell-tests.sh
```

## Parallel verification groups

```text
1 2
```

