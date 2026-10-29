#!/usr/bin/env bash
# Checklist construction and execution each have one canonical owner.  Do not
# restart either stage speculatively while another stage is still producing an
# input: that duplicates worker/browser work and can create conflicting reports.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"

python3 - "$ROOT/scripts/stagegate.sh" <<'PY'
import sys

text = open(sys.argv[1], encoding="utf-8").read()

for required in (
    "early_checklist_start",
    "early_checklist_join",
    "early_checklist_usable",
    "start_streamed_checklist_lens",
    "early_stream_collect",
    "UNCLE_CHECKLIST_EARLY",
):
    if required not in text:
        raise SystemExit(f"missing checklist performance path: {required}")

def state(name, next_name):
    # The dispatcher and the durable workflow loop both have case labels.
    # The latter is the final occurrence and is the state machine under test.
    start = text.rindex(f"\n        {name})\n")
    end = text.index(f"\n        {next_name})\n", start)
    return text[start:end]

test_review = state("TEST_REVIEW", "VALIDATE_TEST_REVIEW")
if test_review.count("early_checklist_start") != 1:
    raise SystemExit("test review must start exactly one speculative manual checklist")

manual = state("MANUAL_CHECKLIST", "VALIDATE_MANUAL_CHECKLIST")
if "early_checklist_join" not in manual or "early_checklist_usable" not in manual:
    raise SystemExit("manual checklist must adopt its completed speculative packet")
if "run_stage MANUAL_CHECKLIST" in manual:
    raise SystemExit("manual checklist must adopt the early packet, never rerun the panel")

execute = state("EXECUTE_CHECKLIST", "VALIDATE_CHECKLIST")
if "early_stream_collect" not in execute or "CHECKLIST_STREAM_PRECOMPLETED" not in execute:
    raise SystemExit("execute checklist must adopt streamed worker evidence")
if "executing only uncovered checks" not in execute:
    raise SystemExit("execute checklist must not replay streamed checks")

stream_start = text[text.index("start_streamed_checklist_lens() {"):text.index("early_stream_join() {")]
if "ready_lenses" not in stream_start or 'coverage invariants resources regressions' not in stream_start:
    raise SystemExit("early execute stream must include every already-valid checklist lens")
if 'run_parallel_checklist_workers "$partial" "$output"' not in stream_start:
    raise SystemExit("ready checklist lenses must use one shared scheduler")

manual_panel = text[text.index("run_manual_checklist_panel() {"):text.index("# Manual checklist construction is independent")]
if 'start_streamed_checklist_lens "$directory" "first-ready"' not in manual_panel:
    raise SystemExit("manual checklist must stream from the first valid worker packet")
if '"$directory/workers-complete"' not in manual_panel:
    raise SystemExit("manual checklist stream monitor must terminate after worker retries")
if 'if [[ "$lens" == coverage' in manual_panel:
    raise SystemExit("manual checklist must not wait specifically for coverage before streaming")

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
if execute.count("run_parallel_checklist_workers") != 1:
    raise SystemExit("change execute checklist must launch its worker fan-out once")

print("OK")
PY
