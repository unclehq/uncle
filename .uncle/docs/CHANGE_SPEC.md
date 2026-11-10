# Change spec (Issue 230)

Omitted sections: Migration (none); Prototype isolation (not a prototype); Performance (no new requirement beyond not spawning doomed calls).

## 1. Change type
Bug fix plus feature (spending-stop handling, budget-aware concurrency).

## 2. Problem statement
A host spending stop (HTTP 402) discards parallel plan work, triggers a doomed fallback, and is reported as a config error. See CHANGE_REQUEST.md; baseline B-1, B-2.

## 3. Current behavior
Baseline B-1, B-2, B-5.

## 4. Desired behavior
Recognized typed stop; running workers finish; finished sections kept; no fallback; `stop-reason` = `spending_limit` with figures; distinct exit code; one-line message; resume reuses finished sections; concurrency limited by remaining task budget header.

## 5. Observable behavior table
| ID | Class | Trigger | Current behavior | Expected behavior | Verification |
|---|---|---|---|---|---|
| SB-1 | ADD | 402 with code budget_reached or balance_exhausted | ValueError about Base URL | Typed `SpendingStop` carrying code, scope, limit, used, suggested increase, balance; message names limit and suggested amount | self-hosted-spending-stop-test.py |
| SB-2 | PRESERVE | Other HTTP errors (401, 403, 400-class, other 402 bodies) | Baseline B-1/B-3/B-4 | Unchanged messages and handling | existing + new negative test |
| SB-3 | MODIFY | SpendingStop in a bounded section worker | drain, return 1, discard, fallback | start no new workers, let running finish, keep finished sections, return distinct status | shell scheduler test |
| SB-4 | MODIFY | Same in unbounded scheduler | same | same | shell scheduler test |
| SB-5 | MODIFY | PROJECT_PLAN stage sees spending status | single-pass fallback | skip fallback, write `spending_limit: ...` to stop-reason, exit with dedicated code | shell scheduler test |
| SB-6 | ADD | Spending stop | none | print one line `Stopped: the task spending limit ($X) was reached; about $Y more lets the next step start.` | test asserts output |
| SB-7 | ADD | Resume after limit raised | all sections rerun | only missing sections run | resume test |
| SB-8 | MODIFY | supervisor sees HTTP 402/budget_reached/balance_exhausted | diagnosed like a bug | `external_capacity_failure` true | supervisor-test.py |
| SB-9 | ADD | Reply carries `x-seren-budget-task-remaining-atomic` | ignored | Parallel workers started capped by remaining budget / typical per-call cost (min 1); stop before a call the host would refuse | unit test of pure cap function + scheduler test |
| SB-10 | PRESERVE | Non-spending worker failure | drain, return 1, fallback | unchanged | shell scheduler test |

## 6. Invariant table
| ID | Status | Invariant | Scope | Enforcement point | Verification |
|---|---|---|---|---|---|
| SI-1 | NEW | A spending stop is never reported as a Base URL/key problem | model client | self_hosted_http.py | SB-1 test |
| SI-2 | NEW | After a SpendingStop no new section worker starts | both schedulers | stagegate.sh | scheduler test |
| SI-3 | NEW | Finished sections survive a spending stop | section dir | stagegate.sh | scheduler + resume test |
| SI-4 | NEW | Spending stop never triggers the single-pass fallback | PROJECT_PLAN | stagegate.sh | scheduler test |
| SI-5 | EXISTING | 402 is not retried | HTTP client | RETRYABLE_STATUS | retry test |
| SI-6 | EXISTING | Non-spending failures keep fallback behavior | PROJECT_PLAN | stagegate.sh | SB-10 test |
| SI-7 | EXISTING | Uncle's own budget cap is independent | budget.py | unchanged | existing tests |
No RELAXED or REMOVED invariants.

## 7. Compatibility
Other runners and error text for non-spending errors unchanged. `stop-reason` gains a new value only.

## 8. Error behavior
Malformed or non-JSON 402 body, or unknown code: falls back to existing generic error. Missing budget headers: no cap, current concurrency applies. Worker killed by a stop before writing: its section is missing and reruns on resume.

## 10. Security
Stop message and figures contain no API key or request content.

## 12. Rollback
Revert the commit; no persisted format change except a new stop-reason string.

## 14. Non-goals
Changing Uncle's own cap; host accounting; #231; changing default concurrency; GitHub issue edits (#213 note is a human follow-up).

## 15. Assumptions
- Atomic units are millionths of a USD.
- Typical per-call cost is derived from spend observed so far in the stage, with a conservative constant default when none is known.
- Exit code: 75 (EX_TEMPFAIL); name `SPENDING_STOP_EXIT`.

## Acceptance criteria

| ID | Criterion | Verification |
|---|---|---|
| AC-1 | HTTP 402 with JSON code `budget_reached` or `balance_exhausted` raises a typed SpendingStop (not ValueError); message names the limit and suggested increase (or balance). | scripts/tests/self-hosted-spending-stop-test.py with a fake server |
| AC-2 | Other HTTP errors (e.g. 401, 402 with unrelated body, non-JSON body) keep the existing ValueError message. | Negative cases in self-hosted-spending-stop-test.py |
| AC-3 | In both bounded and unbounded section schedulers, after a SpendingStop in one of 14 workers no new worker starts, running workers finish, and finished sections remain on disk. | Shell scheduler test project-plan-spending-stop-test.sh |
| AC-4 | On spending stop the PROJECT_PLAN stage does not run the single-pass fallback, writes stop-reason beginning `spending_limit` with the host figures, prints the one-line Stopped message, and exits with code 75. | project-plan-spending-stop-test.sh asserts fallback not invoked, file content, output, exit code |
| AC-5 | A resume after the stop with the server accepting calls runs only sections that had not finished. | Resume case in project-plan-spending-stop-test.sh counting worker invocations |
| AC-6 | supervisor.external_capacity_failure is true for 'HTTP 402: {"code":"budget_reached"}' and for balance_exhausted, and remains false for ordinary validator failures. | supervisor-test.py additions |
| AC-7 | With a remaining-task-budget header value, the number of concurrently started section workers is capped to remaining/typical-cost (minimum 1), and absent header leaves concurrency unchanged. | Python unit test of pure cap function plus scheduler test |
| AC-8 | A non-spending worker failure still drains workers, returns failure and runs the single-pass fallback as before. | project-plan-spending-stop-test.sh preserve case; existing suites stay green |
| AC-9 | The new tests are included in the verification commands and the full shell and Python runners show no regression against baseline. | Driver verification commands |

