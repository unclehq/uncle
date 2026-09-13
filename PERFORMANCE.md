# Build performance profiling

Profiling is enabled by default for new-application and change builds, including
runs started through the TUI. New builds use the instrumentation; an already
running driver must be restarted to load the changes. Every invocation/resume
receives a distinct directory:

```text
.uncle/workflow/performance/<run-id>/
  run.json       wall time, exit status, sampling interval and errors
  events/        atomic stage boundaries and subprocess observations
  report.md      stages and processes ranked by elapsed time
  timeline.json  Chrome trace-event timeline
```

Read the latest run alongside the existing model, approval, and check metrics:

```sh
bash scripts/performance-report.sh .
```

To refresh only the latest timeline report while a build is running:

```sh
python3 scripts/lib/build_timing.py report .
```

Keep a copy of a run's directory when comparing changes. The existing metrics
report includes historical attempts; the timeline report covers one invocation.
Open `timeline.json` in a compatible trace viewer to see overlapping work.

## Where to focus

Start with workflow-stage wall times. Compare a slow stage with the existing
agent/reviewer, approval, and check records to distinguish model work, waiting
for a person, verification, and driver overhead. Then examine the subprocess
rows inside that stage. Work and process lifetimes overlap: summing nested or
parallel processes does **not** give the build's elapsed wall time.

Managed verification processes and native runner servers have explicit start
and completion events, exit status, and monotonic elapsed time. A process with
no completion event appears separately as unfinished; its displayed interval
is not proof that the process was alive throughout that interval.

Other descendants—including Git, shell/Python helpers, external model CLIs,
and tools they launch—are sampled every 0.5 seconds by default. Sampling shows
observed lifetime and CPU increments, not exact process start/exit times. It
can miss shorter processes and cannot distinguish a rapidly reused PID between
observations. Detached/reparented descendants may become unobservable. CPU
increments are available on POSIX; Windows reports them as unavailable. The
report includes sampling errors rather than treating missing observations as
zero work. Native Windows uses a process snapshot; POSIX uses `ps`.

## Controls and overhead

- `WORKFLOW_METRICS=0` disables instrumentation and existing performance metrics.
- `WORKFLOW_PROFILE_INTERVAL=1` samples once a second. Supported range is
  0.1–10 seconds; smaller intervals add overhead and catch shorter processes.
- Profiling records executable/script names, stage names, PIDs, timing, and exit
  status. It does not capture process arguments, prompts, or environment values.

Records are local, under the ignored workflow directory. Instrumentation does
not modify approval decisions, signing, or workflow exit codes. Sampling and
recording failures are best effort. Uncatchable termination of the supervisor
can leave a run marked running; preserve its events for inspection.

## Checklist and runner detail

The report includes checklist-item spans, paired tool calls, time to the first
runner event, time to the first assistant text, the 20 longest inter-event gaps
per attempt, and the gap from the final event to adapter completion. The
coverage table identifies missing responses and unpaired/unfinished tools.
These gaps are observed silence, not a claim about how much time a model spent
reasoning or waiting on an API. First-response latency starts when the observer
starts and includes adapter/server startup for native runners. HTTP polling and
CLI buffering limit timestamp precision.

Native Codex, Claude, Cline, and Kimi wire tool events are paired by invocation
ID. OpenCode tools are observed through canonical polled tool states. Legacy
streams are observed without modifying their bytes; normalized streams that
omit IDs or tool results cannot provide paired durations. Kimi HTTP snapshots
supply only the tool/message structure the installed server exposes. Missing
start/end events stay unavailable rather than being inferred from text. Native
adapter output is marked so the outer stream tap does not double-count it.

The execute-checklist prompt asks the agent to run these observational helpers
around each item, using its actual MC ID:

```sh
check_token=$(python3 "$UNCLE_TIMING_HELPER" check-start MC-001)
# Execute this item's checks; retain the token across separate tool calls.
python3 "$UNCLE_TIMING_HELPER" check-end "$check_token" finished
```

Use `blocked` or `failed` for those outcomes. Parallel items and retries use
separate tokens. A missing end remains unfinished. Timers do not set acceptance
status, prove a pass, or require a check to be rerun. An agent that omits these
commands leaves that item's time unavailable. Existing runs do not acquire the
new prompt until the stage is launched again; do not rerun completed checks
solely for profiling.

## Tokens and cost by part

Each timing table now includes input/output tokens, cache-read/cache-write
counts, total tokens, reported USD, estimated USD, and coverage. `parts.json`
contains the individual spans with the same fields and attribution labels;
`timeline.json` includes them in each event's details. Model usage updates are
stored alongside the other timing events.

Cumulative runner counters are converted to increments, so repeated polling
updates do not bill the same tokens twice. Cache-inclusive input totals include
cached tokens once. A separate model-usage table identifies those increments.
Native runners provide live updates; legacy streams may expose only the final
attempt total. Partial usage remains partial, and unknown usage/prices are not
shown as zero.

Checklist, tool, and timing-gap rows can show **shared usage reported during
that interval**. That means a usage update arrived while the interval was
active; it does not prove the tokens were generated exclusively for that check
or tool. Parallel intervals can share the same update. Never sum these rows
with each other or with their parent stage to calculate a bill. Raw subprocess
rows do not inherit token charges merely because they were running. No token
counts are estimated from elapsed time.

Estimates use the existing model pricing table or an absolute
`WORKFLOW_PRICING_FILE` path. The JSON maps exact model IDs to `input`, `output`,
`cache_read`, and `cache_write` rates, all in USD per million tokens. Unknown
rates produce `Unavailable`; known provider-reported costs remain visible in
the separate reported column. Pricing sources/rates are retained in the
individual records. Estimates are not invoices.
