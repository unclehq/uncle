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
