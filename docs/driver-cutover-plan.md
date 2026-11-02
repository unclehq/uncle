# Driver cutover plan: from a bash state machine to a Python one

Status: in progress on `rewrite/driver-in-python`. Last updated with the measurements below.

## Why

A full run of the test suite costs about 2,850 CPU-seconds on one laptop, and most of it is process launches the two bash drivers
(`stagegate.sh`, `change-workflow.sh`) make: about 39,000 Python helper starts (17-25 ms of CPU each) and 35,000 git starts per full
run. Nothing smaller has paid off. Measured, in this order:

| Change | Measured effect |
|---|---|
| Compile cache for helpers (`PYTHONPYCACHEPREFIX`) | none (55.0 s vs 54.8 s CPU, gates group 2) |
| `python3 -S` | under 1 ms per launch |
| Pure-bash `tr`, `dirname`, `awk`, `head` replacements; `perf_record` and `document_budget` rewritten | about 3-4% CPU over five slices; each further slice is at the noise floor |
| Persistent worker, shared by a whole run, serving helper calls without a new interpreter | -43% CPU on a Python-heavy group (86 s to 49 s), but it broke tests and hung, so it was removed |

Interpreter startup is the cost, so only launching fewer processes helps, and the profile is flat: no single helper is above about 4%
of launches. The gain only arrives when most calls stop starting a process.

## Target architecture

One long-lived Python **host** per driver run. It is the future driver. Stage by stage it takes over from the bash loop:

1. **Host process.** Started by the driver, serves helper calls over a private loopback socket, one forked child per call from a warm
   interpreter. Calls use the same scripts and arguments as today, so the helpers and their tests do not change. Falls back to a plain
   `python3` start whenever the host is absent, slow or wrong.
2. **Host-native helpers.** The helpers the drivers call most become functions in the host (no fork, no argument parsing round trip).
3. **State handlers.** Per state, the handler moves from a bash `case` arm into the host; the bash loop shrinks to "read state, call
   host, act on its answer".
4. **Cutover.** The bash loop is replaced by the host's loop. `stagegate.sh` and `change-workflow.sh` become thin launchers.

Each stage has to leave the whole suite green and has a measured CPU number against the previous stage. A stage that does not pay is
dropped.

## Invariants the host must keep

- **Same observable behaviour per call:** argv, working directory, environment, stdout, stderr, exit status. Stdin is only served when
  it is `/dev/null`; any call that reads stdin runs the real interpreter.
- **A host failure is never a workflow failure.** Connection refused, a timeout, a malformed reply or a dead host all fall back to a
  plain `python3` start of the same command.
- **No orphans, no shared state across runs.** One host per driver, bound to `127.0.0.1` on an ephemeral port with a per-run token;
  it exits when its driver exits; children are bounded by an alarm.
- **No change to protected files, approvals, hashes or locks.** Those stay with the existing code until a stage ports them with a
  differential test.

## Verification

- A differential test per ported function: the old implementation is the oracle, on a grid of inputs.
- Host protocol tests: argv/env/cwd/stdout/stderr/rc parity, 50 concurrent calls, host killed mid-run, call that hangs, large output.
- Full pool after every stage: all suites pass, CPU-seconds and wall time recorded here.

## Log

| Stage | Result |
|---|---|
| Slices 1-5 (see table above) | committed; about -3% to -4% CPU |
| Stage 1: per-run Python host serves helper calls | full pool: all suites pass; CPU about -15%, wall about -6.5% (clean A/B below) |
| Stage 1b and the first slice of stage 3: served `build_timing` stage/report, `reviewer_output --from`, `writer_deadline stop`, inline scripts replaced | gates group 7 CPU 82.7 s -> 40.0 s, group 2 53.1 s -> 28.7 s when run alone; real Python launches in groups 2+5+7: about 4,200 -> 1,074 |

### Clean A/B of the whole pool, host off vs on (same code, nothing else running, two runs each)

| | Wall | CPU | Result |
|---|---|---|---|
| Host off | 384 s, 388 s | 3,360 s, 3,394 s | 2 suites failed each time (one was the host's own test, which needs the host) |
| Host on | 362 s, 358 s | 2,869 s, 2,864 s | all 424 pass both times |

### What the measurements say about the rest of the cutover

- Wall time barely follows CPU. Across many full runs CPU fell by about 15% while wall fell by about 6.5%. At 22 and 30 workers wall time was 355 s and 381 s (CPU 3,079 s and 3,437 s, three failures at 30): the machine, not the worker count, is the limit.
- The pool averages about 7 busy cores out of 14. A suite alone shows no idle time (`supervision-driver`: 53.5 s wall for 59.2 s CPU) but takes about 3x as long inside the pool, so the loss is contention on fork/exec and the file system, not sleeping.
- What is left to port is small per item: `runner_timing.py`'s live stream (about 18% of the remaining real Python launches), about 300 inline scripts, the lock and process-control helpers. Each is about 1% of CPU; wall time would move less. Replacing the bash loop (stage 4) needs the whole model runner in Python.

