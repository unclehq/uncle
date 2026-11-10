# Manual checklist

## Coverage

### MC-100
- Required for acceptance: YES
- Exclusive resources: none
- Depends on: none
- Exact action: Run the PROJECT_PLAN stage against a local fake model server that returns HTTP 402 with JSON code `budget_reached` (limit, used, suggested_increase figures) for one of the parallel section calls while others succeed; capture the console output and exit code.
- Expected result: Running sections finish, no new sections start, no single-pass fallback runs, one line `Stopped: the task spending limit ($X) was reached; about $Y more lets the next step start.` is printed, and the exit code is 75.
- Evidence to capture: Console transcript, exit code, list of section files left on disk.
- Actual result: 
- Status: NOT RUN

### MC-102
- Required for acceptance: YES
- Exclusive resources: none
- Depends on: MC-100
- Exact action: Make the fake server accept calls again, rerun the PROJECT_PLAN stage, and count the model calls the server receives.
- Expected result: Only sections that had not finished before the stop are run; finished sections are reused and the plan completes.
- Evidence to capture: Server request log showing per-section calls, final stage result.
- Actual result: 
- Status: NOT RUN

### MC-103
- Required for acceptance: YES
- Exclusive resources: none
- Depends on: none
- Exact action: Run the PROJECT_PLAN stage with the fake server returning HTTP 402 with `balance_exhausted` and, separately, a 402 with an unrelated code or non-JSON body, and HTTP 401.
- Expected result: balance_exhausted shows balance wording with no `None` or bogus `$0`, exit 75; the unrelated 402, non-JSON 402 and 401 still show the original `check the Base URL, API key and model` error and are not treated as a spending stop.
- Evidence to capture: Console output and exit code for each of the three cases.
- Actual result: 
- Status: NOT RUN

### MC-104
- Required for acceptance: YES
- Exclusive resources: none
- Depends on: none
- Exact action: Run the PROJECT_PLAN stage where one section worker fails with an ordinary non-spending error (e.g. HTTP 500 repeatedly) and no worker hits a 402.
- Expected result: Behavior is unchanged from before: workers drain, sections are discarded, the single-pass fallback runs, and exit is not 75.
- Evidence to capture: Console transcript showing fallback invocation and exit code.
- Actual result: 
- Status: NOT RUN

### MC-105
- Required for acceptance: YES
- Exclusive resources: none
- Depends on: none
- Exact action: Run the PROJECT_PLAN stage with a fake server that returns the `x-seren-budget-task-remaining-atomic` header with a low value (e.g. 1000000) on replies, and observe how many section calls run at once; repeat with the header absent.
- Expected result: With the low header, concurrent section calls are capped (about 2 for 1000000), at least 1; with the header absent, concurrency is the configured default.
- Evidence to capture: Server log of peak concurrent requests for both runs.
- Actual result: 
- Status: NOT RUN

## Invariants

### MC-201
- Required for acceptance: YES
- Exclusive resources: none
- Depends on: none
- Exact action: Run a PROJECT_PLAN stage against a fake model server that returns HTTP 402 {"code":"budget_reached","scope":"task","limit_atomic":5000000,"suggested_increase_atomic":1500001} on one of the parallel section calls while others succeed. Observe stderr and the process exit code.
- Expected result: Output contains one line starting 'Stopped: the task spending limit' with $5.00 and $1.51, never mentions Base URL/API key, never prints None; exit code is 75.
- Evidence to capture: Captured stderr/stdout and exit code.
- Actual result: 
- Status: NOT RUN

### MC-203
- Required for acceptance: YES
- Exclusive resources: none
- Depends on: MC-202
- Exact action: Make the fake server accept calls again and rerun the PROJECT_PLAN stage after the spending stop, counting section worker invocations.
- Expected result: Only sections without complete final outputs are run; finished sections are not rerun, leftover temp files are removed, and the stage completes.
- Evidence to capture: Invocation count per section and final sections listing.
- Actual result: 
- Status: NOT RUN

### MC-204
- Required for acceptance: YES
- Exclusive resources: none
- Depends on: none
- Exact action: Trigger an ordinary non-spending worker failure (non-402 exit 1) in a PROJECT_PLAN run, and separately a 402 with an unrelated body, 401, and a non-JSON 402 body.
- Expected result: Ordinary failure drains workers, discards sections and runs the single-pass fallback as before; the 401/unrelated/non-JSON 402 cases show the existing 'check the Base URL, API key and model' message and are not treated as a spending stop (exit not 75).
- Evidence to capture: Output text, exit codes, fallback log.
- Actual result: 
- Status: NOT RUN

### MC-205
- Required for acceptance: YES
- Exclusive resources: none
- Depends on: none
- Exact action: Run a PROJECT_PLAN stage where one worker exits 75 with no or garbage marker file, and another stage-run where one worker has a valid 402 stop while a second worker fails ordinarily.
- Expected result: Unmarked 75 is an ordinary failure (no spending_limit stop-reason, fallback may run); the mixed case exits 75, no fallback, finished sections kept, and stop-reason records other_failures=1.
- Evidence to capture: Exit codes, stop-reason contents, fallback log.
- Actual result: 
- Status: NOT RUN

### MC-206
- Required for acceptance: YES
- Exclusive resources: none
- Depends on: none
- Exact action: Run a non-PROJECT_PLAN stage that shares the schedulers with a worker that exits 75.
- Expected result: It is handled as an ordinary failure with unchanged behavior; no spending_limit stop-reason is written.
- Evidence to capture: Exit code, stop-reason file absence.
- Actual result: 
- Status: NOT RUN

### MC-207
- Required for acceptance: YES
- Exclusive resources: none
- Depends on: none
- Exact action: Run the scheduler with the fake host sending remaining-budget header values 1000000, 0, then a non-integer value, and none, with configured concurrency 14; record the peak concurrent workers.
- Expected result: Peak concurrency is 2 for 1000000, 1 for 0, and 14 for the non-integer and absent cases.
- Evidence to capture: Peak concurrent worker counts per case.
- Actual result: 
- Status: NOT RUN

## resources

### MC-301
- Required for acceptance: YES
- Exclusive resources: dir:project-plan-state
- Depends on: none
- Exact action: Run the PROJECT_PLAN stage with 14 parallel section workers against a fake model server that returns HTTP 402 {"code":"budget_reached","limit_atomic":5000000,"suggested_increase_atomic":1500001} for one call while others succeed; observe terminal output and the stage exit code.
- Expected result: Exactly one line like 'Stopped: the task spending limit ($5.00) was reached; about $1.51 more lets the next step start.' is printed, the stage exits 75, no single-pass fallback starts, and no 'check the Base URL, API key and model' text appears.
- Evidence to capture: Terminal transcript, exit code, contents of the stop-reason file, and a listing of the sections directory.
- Actual result: 
- Status: NOT RUN

### MC-302
- Required for acceptance: YES
- Exclusive resources: dir:project-plan-state
- Depends on: MC-301
- Exact action: After MC-301, raise the fake server limit so it accepts calls and rerun the PROJECT_PLAN stage, counting how many section workers are invoked.
- Expected result: Only sections without complete final outputs are rerun; previously finished sections are reused, the spending_limit stop-reason is cleared, and the stage completes.
- Evidence to capture: Worker invocation log or count, sections directory before and after, and stop-reason file state.
- Actual result: 
- Status: NOT RUN

### MC-303
- Required for acceptance: YES
- Exclusive resources: dir:project-plan-state
- Depends on: none
- Exact action: Run the PROJECT_PLAN stage against a fake server returning 402 balance_exhausted with a balance figure and no limit figures, then again with a 402 whose body is not JSON or has an unrelated code.
- Expected result: The balance_exhausted case prints the balance wording with no 'None', no '$0' for missing figures, and exits 75. The unrelated 402 keeps the existing 'check the Base URL, API key and model' error and the ordinary failure path including the fallback.
- Evidence to capture: Both terminal transcripts, the exit codes, and whether the fallback ran.
- Actual result: 
- Status: NOT RUN

### MC-304
- Required for acceptance: YES
- Exclusive resources: dir:project-plan-state
- Depends on: none
- Exact action: Run the PROJECT_PLAN stage with a fake server that sends an x-seren-budget-task-remaining-atomic header of 1000000 on replies, then rerun with the header absent.
- Expected result: With the header set, no more than 2 section workers run at once, since floor(1000000/400000) is 2. With the header absent, the normal concurrency applies.
- Evidence to capture: Timestamped worker start and finish log showing peak concurrent workers for each run.
- Actual result: 
- Status: NOT RUN

## Regressions

### MC-401
- Required for acceptance: YES
- Exclusive resources: none
- Depends on: none
- Exact action: Run the PROJECT_PLAN stage with a stubbed section worker that fails with an ordinary nonzero exit (e.g. 1) while other workers succeed, using both the bounded and unbounded scheduler configurations.
- Expected result: Running workers drain, the scheduler returns failure, the sections are discarded, the single-pass fallback runs as before, no spending_limit stop-reason is written, and the exit code is not 75.
- Evidence to capture: Stage output, exit code, contents of stop-reason (absent or not spending_limit), and the log line showing the fallback invoked.
- Actual result: 
- Status: NOT RUN

### MC-403
- Required for acceptance: YES
- Exclusive resources: none
- Depends on: none
- Exact action: Run the self-hosted runner as a worker in a non-PROJECT_PLAN stage (or the scheduler without the PROJECT_PLAN opt-in) with a worker that exits 75 and no marker, and also with exit 75 plus a garbage marker file.
- Expected result: Exit 75 is treated as an ordinary failure exactly as before: no spending_limit stop-reason, no spending Stopped message, and existing failure/fallback handling applies.
- Evidence to capture: Exit code, stop-reason contents, and stage output for both cases.
- Actual result: 
- Status: NOT RUN

### MC-404
- Required for acceptance: YES
- Exclusive resources: none
- Depends on: none
- Exact action: Start a PROJECT_PLAN run with non-empty stale section files present but no prior spending_limit stop-reason, using stubbed workers that record each invocation.
- Expected result: The stale sections directory is removed and every section worker is invoked again, as in current behavior.
- Evidence to capture: Worker invocation log listing all sections and the sections directory state before and after.
- Actual result: 
- Status: NOT RUN

### MC-405
- Required for acceptance: YES
- Exclusive resources: none
- Depends on: none
- Exact action: With no budget header present in model replies (and separately with a non-integer header value), run the section scheduler with 14 stubbed workers and observe how many start concurrently.
- Expected result: Concurrency is unchanged from the configured default and is not capped.
- Evidence to capture: Peak concurrent worker count log for each case.
- Actual result: 
- Status: NOT RUN

### MC-406
- Required for acceptance: YES
- Exclusive resources: none
- Depends on: none
- Exact action: Run the supervisor diagnosis on an ordinary validator failure text that mentions 402 incidentally (e.g. 'line 402', 'status 402 items') and on a 429 rate-limit text.
- Expected result: The 402-mention validator text is not classified as external capacity, while 429/rate-limit text still is, and normal recovery consumption is unchanged.
- Evidence to capture: Printed external_capacity_failure result for each input.
- Actual result: 
- Status: NOT RUN
