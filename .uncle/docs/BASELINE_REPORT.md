# Baseline report (Issue 230)

Omitted sections: Reproduction (not run; the 402 is reproduced by a new fake-server test); Areas outside change folded into section 14.

## 1. Change-request summary
See .uncle/docs/CHANGE_REQUEST.md. HTTP 402 `budget_reached`/`balance_exhausted` from the host is reported as a Base URL/key problem; the parallel project-plan section schedulers treat it as any failure, discard the sections, and the single-pass fallback runs into the same limit. No code reads the host's budget headers (#213).

## 2. Repository architecture
Shell driver `scripts/stagegate.sh` runs stages; Python helpers in `scripts/lib/`. Self-hosted model client: `scripts/lib/self_hosted_http.py` (HTTP) and `scripts/lib/self_hosted.py` (runner `main`, exit codes). Supervisor diagnosis: `scripts/lib/supervisor.py`. Concurrency: `scripts/lib/unit_scheduler.py`, `scripts/lib/model-jobs.sh`.

## 3. Relevant code paths
| Path | Role |
|---|---|
| scripts/lib/self_hosted_http.py:30 | `REJECTED` tuple; 163 `_server_reason`; 930 `RETRYABLE_STATUS`; 1330-1332 and 1428-1430 raise `ValueError('Model API request failed (HTTP %d%s); check the Base URL, API key and model')` |
| scripts/lib/self_hosted.py:2224 `main`, 2208-2210 | catches `ValueError`, returns 1 |
| scripts/stagegate.sh:4281 `project_plan_section_run`, 4310 `_finish`, 4327 `_settle` | worker run/recovery/one retry |
| scripts/stagegate.sh:4342-4396 | bounded scheduler; failure drains workers and returns 1 |
| scripts/stagegate.sh:4398-4462 | unbounded scheduler; failure returns 1 |
| scripts/stagegate.sh:4557-4570 | PROJECT_PLAN stage: any failure removes investigation and runs single pass |
| scripts/stagegate.sh:2886, 4490 | `stop-reason` writes/reads |
| scripts/lib/supervisor.py:406-412 | `_EXTERNAL_CAPACITY` regex; used at :1241 |
| scripts/lib/unit_scheduler.py:65 | `capacity` (24 for self-hosted when unset) |

## 4. Current observable behavior
| ID | Trigger | Current result | Evidence | Must preserve? |
|---|---|---|---|---|
| B-1 | HTTP 402 from model API | ValueError 'check the Base URL, API key and model'; exit 1 | self_hosted_http.py:1330 | No (modified) |
| B-2 | One section worker fails | other workers drained, return 1, sections discarded, single pass runs | stagegate.sh:4374-4378, 4557-4570 | Yes for non-spending failures |
| B-3 | 429/5xx | retried per RETRYABLE_STATUS | self_hosted_http.py:930 | Yes |
| B-4 | 400/404/405/415/422/501 | treated as option rejection, next mode tried | self_hosted_http.py:30,1332 | Yes |
| B-5 | supervisor sees 429/quota/rate text | external capacity, no recurrence consumed | supervisor.py:406 | Yes |
| B-6 | `--max-budget-usd` cap (#212) | Uncle's own cap in scripts/lib/budget.py | commit 3a20810 | Yes, separate |

## 5. Existing invariants
| ID | Invariant | Current enforcement | Existing test | Confidence |
|---|---|---|---|---|
| I-1 | 402 is never retried | RETRYABLE_STATUS excludes it | self-hosted-retry-test.py | Medium |
| I-2 | On section failure no worker keeps writing into fallback | drain before return 1 (stagegate.sh:4374) | none found | Low |
| I-3 | Ordinary agent/validator failures keep supervisor recovery path | narrow regex | supervisor-test.py | Medium |

## 6. Interface contracts
Model client raises ValueError for HTTP errors; runner exit 1 on error. `stop-reason` is a one-line text file in `$STATE_DIR`. No schema involved.

## 7. Existing automated-test coverage
Python suites under scripts/tests/*-test.py (self-hosted-retry, self-hosted-flavor, supervisor-test, etc.); shell suites scripts/tests/*-test.sh. No test covers section-scheduler failure semantics or 402 handling. The Python and shell runners use separate temp dirs and bind no shared ports, so they form one parallel group.

## 9. Baseline test results
Commands come from scripts/run-shell-tests.sh and scripts/run-python-tests.sh (present in repo). Not run here; the driver's baseline (.uncle/workflow/green-check.baseline.tsv) is authoritative. Some Python suites are known to fail on a clean checkout.

## 10. Existing failures
None established by this stage.

## 12. Likely change surface
self_hosted_http.py, self_hosted.py, stagegate.sh (two schedulers + PROJECT_PLAN case), supervisor.py, unit_scheduler.py/model-jobs.sh (budget-aware concurrency), new tests.

## 13. Regression-sensitive components
Stage failure semantics in stagegate.sh; retry classification; supervisor recurrence logic.

## 14. Outside the change
Uncle's own `--max-budget-usd` cap; #231 plan check; host-side budget accounting; hosted-mode concurrency default.

## 15. Unknowns and assumptions
- Exact header names beyond `x-seren-budget-task-remaining-atomic` are unknown; only that one is relied on.
- Resume mechanism for finished sections: assumed existing section files in the investigation directory can be reused (verify in plan step).
- Exit code value for spending stop is a design choice.

## 16. Initial risk
Medium: shell scheduler edits are in a hot path with little test coverage; mitigated by new scheduler tests.

## Exact build and test commands executed

```sh
bash scripts/run-shell-tests.sh
bash scripts/run-python-tests.sh
```

