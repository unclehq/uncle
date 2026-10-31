#!/usr/bin/env bash
# Checklist construction and execution each have one canonical owner. Driver
# verification runs in the background while implementation settles, then
# test-review and both checklist stages consume its completed result. No
# evidence worker may be asked to judge a PENDING placeholder.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"

python3 - "$ROOT/scripts/stagegate.sh" <<'PY'
import sys

text = open(sys.argv[1], encoding="utf-8").read()

def state(name, next_name):
    # The dispatcher and the durable workflow loop both have case labels.
    # The latter is the final occurrence and is the state machine under test.
    start = text.rindex(f"\n        {name})\n")
    end = text.index(f"\n        {next_name})\n", start)
    return text[start:end]

test_review = state("TEST_REVIEW", "VALIDATE_TEST_REVIEW")
if "early_checklist_start" in test_review:
    raise SystemExit("test review must not start checklist workers before green evidence exists")
if "green_wait_final" not in test_review:
    raise SystemExit("test review workers must receive completed driver evidence")
if test_review.index("green_wait_final") > test_review.index("run_stage TEST_REVIEW"):
    raise SystemExit("test review must wait for green evidence before launching workers")

implementation = state("IMPLEMENT", "WAIT_IMPLEMENT_APPROVAL")
if "run_green_check_auto" not in implementation:
    raise SystemExit("application implementation must start driver verification")

validate_review = state("VALIDATE_TEST_REVIEW", "MANUAL_CHECKLIST")
if "green_wait_final" not in validate_review or "route_unrunnable_application" not in validate_review:
    raise SystemExit("manual checklist must be preceded by completed runnable green evidence")

manual = state("MANUAL_CHECKLIST", "VALIDATE_MANUAL_CHECKLIST")
if "green_wait_final" not in manual or manual.count("run_stage MANUAL_CHECKLIST") != 1:
    raise SystemExit("manual checklist must run once after green evidence is complete")

execute = state("EXECUTE_CHECKLIST", "VALIDATE_CHECKLIST")
if "early_stream_collect" in execute or "CHECKLIST_STREAM_PRECOMPLETED" in execute:
    raise SystemExit("execute checklist must run the full checklist once, not stream partial evidence")
if execute.count("run_stage EXECUTE_CHECKLIST") != 1:
    raise SystemExit("execute checklist must launch its full worker fan-out once")
if "green_wait_final" not in execute:
    raise SystemExit("execute checklist must require completed green evidence")

audit = state("FINAL_AUDIT", "VALIDATE_AUDIT")
if "green_wait_final" not in audit or "run_green_check_auto" not in audit:
    raise SystemExit("final audit must retain a green-check reuse guard")

manual_panel = text[text.index("run_manual_checklist_panel() {"):text.index("# Checklist work consumes a completed driver green-check")]
if "start_streamed_checklist_lens" in manual_panel or "workers-complete" in manual_panel:
    raise SystemExit("manual checklist must not start execute workers from partial lenses")

print("OK")
PY

python3 - "$ROOT/scripts/change-workflow.sh" <<'PY'
import sys

text = open(sys.argv[1], encoding="utf-8").read()

def state(name, next_name):
    start = text.rindex(f"\n        {name})\n")
    end = text.index(f"\n        {next_name})\n", start)
    return text[start:end]

implementation = state("IMPLEMENT", "WAIT_IMPLEMENT_APPROVAL")
if "manual-checklist-base" in implementation or "start_codex_bg" in implementation:
    raise SystemExit("change implementation must not start a speculative base checklist")

checklist = state("CHECKLIST", "VALIDATE_MANUAL_CHECKLIST")
if "run_checklist_panel full" not in checklist:
    raise SystemExit("change workflow must build one full checklist after implementation")
if "manual-checklist-base" in checklist or "manual-checklist-delta" in checklist:
    raise SystemExit("change workflow must not use base/delta checklist passes")

execute = state("EXECUTE_CHECKLIST", "VALIDATE_CHECKLIST")
# uncle consolidation phase (c): the worker fan-out + fast-path check moved
# into the shared checklist_execute_worker_fastpath (scripts/lib/checklist-stage.sh),
# used by both stagegate.sh and change-workflow.sh, so the literal
# run_parallel_checklist_workers call itself is checked once, in the shared
# function, rather than once per driver.
call_lines = [line for line in execute.splitlines()
              if "checklist_execute_worker_fastpath" in line and not line.strip().startswith("#")]
if len(call_lines) != 1:
    raise SystemExit("change execute checklist must call the shared worker fan-out once")
shared_lib = open(f"{sys.argv[1].rsplit('/', 1)[0]}/lib/checklist-stage.sh", encoding="utf-8").read()
fastpath = shared_lib[shared_lib.index("checklist_execute_worker_fastpath() {"):]
fastpath = fastpath[:fastpath.index("\n}\n")]
if fastpath.count("run_parallel_checklist_workers") != 1:
    raise SystemExit("the shared worker fan-out must launch run_parallel_checklist_workers once")
if "wait_green_check_bg" not in execute:
    raise SystemExit("change execute workers must require completed green evidence")

audit = state("FINAL_AUDIT", "VALIDATE_AUDIT")
if "start_green_check_bg" not in audit or "wait_green_check_bg" not in audit:
    raise SystemExit("change final audit must retain a green-check reuse guard")

implementation = state("IMPLEMENT", "WAIT_IMPLEMENT_APPROVAL")
if "start_green_check_bg" not in implementation:
    raise SystemExit("change implementation must start driver verification")

if "wait_green_check_bg" not in checklist:
    raise SystemExit("change manual checklist must require completed green evidence")

print("OK")
PY
