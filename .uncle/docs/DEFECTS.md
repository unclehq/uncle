# Defects

## D-2

- **Status:** NOT RUN
- **Evidence:** Not executed end-to-end; see Findings and D-2
- **Expected result:** Fake HTTP 402 server driving real PROJECT_PLAN stage; console, exit 75, no fallback.
- **Actual result:** Not performed end-to-end. Partial: stub test shows valid marker returns 75, stop-reason starts spending_limit, finished section kept, dependent not started. Fallback absence and the printed line from a real stage not observed.

## D-2

- **Status:** NOT RUN
- **Evidence:** Not executed end-to-end; see Findings and D-2
- **Expected result:** Rerun after stop; only unfinished sections run.
- **Actual result:** Not performed. Partial: stub test shows done+resume skips, no .done reruns. No server call count. Declared dependency MC-100 not met.

## D-2

- **Status:** NOT RUN
- **Evidence:** Not executed end-to-end; see Findings and D-2
- **Expected result:** balance_exhausted wording and exit 75; unrelated 402, non-JSON 402 and 401 keep old error.
- **Actual result:** Not performed end-to-end. Unit level: ParseTests/RenderTests (balance line, missing figures omitted, not-a-spending-stop) passed. No 401 case, no exit code from a real stage.

## D-2

- **Status:** NOT RUN
- **Evidence:** Not executed end-to-end; see Findings and D-2
- **Expected result:** Ordinary failure: drain, discard, fallback runs, exit not 75.
- **Actual result:** Not performed end-to-end. Partial: stub test shows ordinary failure returns 1 and writes no stop-reason. Fallback invocation not observed.

## D-2

- **Status:** NOT RUN
- **Evidence:** Not executed end-to-end; see Findings and D-2
- **Expected result:** Peak concurrent section calls capped to about 2 for header 1000000; default when absent.
- **Actual result:** Peak concurrency not measured. Partial: cap function gave 14/2/1/1/1 for 10000000/1000000/399999/0/-5 and unchanged for non-integer/absent.

## D-2

- **Status:** NOT RUN
- **Evidence:** Not executed end-to-end; see Findings and D-2
- **Expected result:** Stopped line with $5.00 and $1.51, no Base URL text, exit 75.
- **Actual result:** Not performed end-to-end. Unit level: test_usd_rounds_up and test_budget_reached_line passed. No real stage stderr or exit code.

## D-2, D-3

- **Status:** NOT RUN
- **Evidence:** Not executed end-to-end; see Findings and D-2
- **Expected result:** Rerun after stop; temp files removed; stage completes.
- **Actual result:** Not performed. Depends on MC-202, which does not exist in the checklist (checklist defect).

## D-2

- **Status:** NOT RUN
- **Evidence:** Not executed end-to-end; see Findings and D-2
- **Expected result:** Ordinary failure and 401/unrelated/non-JSON 402 keep old behavior.
- **Actual result:** Not performed end-to-end. Partial: ordinary failure returns 1; ParseTests test_not_a_spending_stop passed. No fallback or message observed.

## D-2

- **Status:** NOT RUN
- **Evidence:** Not executed end-to-end; see Findings and D-2
- **Expected result:** Unmarked 75 ordinary; mixed case exits 75, finished kept, other_failures=1.
- **Actual result:** Partial, bounded scheduler stub only: 75 with no marker returns 1; garbage marker returns 1 and writes no stop-reason; mixed returns 75, keeps section a, stop-reason has other_failures=1. Fallback absence and the unbounded scheduler not observed.

## D-2

- **Status:** NOT RUN
- **Evidence:** Not executed end-to-end; see Findings and D-2
- **Expected result:** Non-PROJECT_PLAN stage with exit-75 worker is an ordinary failure.
- **Actual result:** Not performed. No test exercises the opt-out (also flagged in TEST_REVIEW.md COVERAGE).

## D-2

- **Status:** NOT RUN
- **Evidence:** Not executed end-to-end; see Findings and D-2
- **Expected result:** Peak workers 2/1/14/14 for header 1000000/0/non-integer/absent at concurrency 14.
- **Actual result:** Peak workers not measured. Cap function results 2 and 1 for 1000000 and 0, and unchanged for non-integer/absent, observed in stub test.

## D-2

- **Status:** NOT RUN
- **Evidence:** Not executed end-to-end; see Findings and D-2
- **Expected result:** 14 workers, one 402; one Stopped line, exit 75, no fallback, no Base URL text.
- **Actual result:** Not performed (no fake server, no 14-worker run). See MC-100 partial evidence.

## D-2

- **Status:** NOT RUN
- **Evidence:** Not executed end-to-end; see Findings and D-2
- **Expected result:** Rerun reuses finished sections, clears spending_limit stop-reason.
- **Actual result:** Not performed. Depends on MC-301. Stop-reason clearing is not covered by any test.

## D-2

- **Status:** NOT RUN
- **Evidence:** Not executed end-to-end; see Findings and D-2
- **Expected result:** balance_exhausted wording, exit 75; unrelated 402 keeps old error and fallback.
- **Actual result:** Not performed end-to-end. Same unit evidence as MC-103.

## D-2

- **Status:** NOT RUN
- **Evidence:** Not executed end-to-end; see Findings and D-2
- **Expected result:** At most 2 concurrent workers with header 1000000; default when absent.
- **Actual result:** Not measured. Same partial evidence as MC-105.

## D-2

- **Status:** NOT RUN
- **Evidence:** Not executed end-to-end; see Findings and D-2
- **Expected result:** Ordinary failure, bounded and unbounded schedulers: drain, discard, fallback, not 75.
- **Actual result:** Bounded: returns 1, no stop-reason. Unbounded scheduler and fallback not exercised.

## D-2

- **Status:** NOT RUN
- **Evidence:** Not executed end-to-end; see Findings and D-2
- **Expected result:** Exit 75 without marker or with garbage marker in non-PROJECT_PLAN use is ordinary.
- **Actual result:** Not performed. Stub test covers 75 without/garbage marker only inside the PROJECT_PLAN opt-in path.

## D-2

- **Status:** NOT RUN
- **Evidence:** Not executed end-to-end; see Findings and D-2
- **Expected result:** Stale sections without spending_limit stop-reason are removed, all sections rerun.
- **Actual result:** Not performed. Unit-level only: done-but-not-resuming reruns. Stage-start cleanup untested.

## D-2

- **Status:** NOT RUN
- **Evidence:** Not executed end-to-end; see Findings and D-2
- **Expected result:** Concurrency unchanged for absent/non-integer header, 14 workers.
- **Actual result:** Peak not measured. Cap function leaves concurrency unchanged for both cases.
