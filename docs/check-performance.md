# Check time limits and repeated work

Driver verification commands have a 900-second limit per command. Shell regression
suites have a 600-second limit per suite. Override these for known long checks with
`WORKFLOW_CHECK_TIMEOUT_SECONDS` and `WORKFLOW_SHELL_SUITE_TIMEOUT_SECONDS` (positive
seconds, at most 86400). If a driver command launches the entire shell suite runner,
set its command limit long enough for all batches to finish.

A timeout kills the owned process tree, records exit 124, and prints a TIMEOUT
message with the configured limit. It is a failed execution, never a pass. Other
independent checks continue. Driver checks do not inherit live steering settings.

To inspect repeated commands and their individual durations, statuses, states,
and log paths:

```sh
python3 scripts/check-performance.py /path/to/project
```

The report reads existing check metrics without executing anything. Multiple runs
are not automatically redundant: code edits, changed fixtures, environment changes,
and external services can require reruns. Use the listed states and evidence to
locate unnecessary repetitions before introducing result reuse. This report does
not skip checks or count old evidence as new verification.

The HTTP self-hosted runner also emits `self_hosted_turn` records into the
stage JSONL stream. Each record identifies a request group and turn, lists the
tool names and UTF-8 argument byte counts, and reports that response's output
tokens (null when unavailable), finish reason and phase. Arguments, paths,
document contents and reasoning are not included in these records. Sizes are
measured before reasoning cleanup, so they describe the received generation.
Repeated large `write_file` calls expose document rewrites; small `edit_file`
calls expose targeted repairs. Final-only responses have an empty tool list.

These per-turn records are diagnostic metadata. The result event still owns
the cumulative usage total. Likewise, `performance-report.sh` shows overlapping
stage, attempt and continuation views: do not add a stage total to its steps.
Count Agent/Reviewer attempt totals once when calculating run usage.
