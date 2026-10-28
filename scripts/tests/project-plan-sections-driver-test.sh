#!/usr/bin/env bash
# run_project_plan_sections: one outline first, then every other worker at the same time, the plan assembled
# and validated (section 13 built by the driver), and any failure leaves nothing behind so the single-pass
# plan can run.  A plan whose workers left too few requirement mappings gets one traceability worker.
set -uo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
fails=0
export WORKFLOW_PLAN_BLOCKS=0     # this suite covers the Markdown-body packets; project-plan-blocks-driver-test.sh covers typed blocks
check() { local what="$1"; shift; if "$@"; then :; else echo "FAIL: $what"; fails=$((fails + 1)); fi; }

awk '/^(project_plan_section_run|project_plan_section_finish|project_plan_section_settle|run_project_plan_sections)\(\) \{/,/^}/' "$ROOT/scripts/stagegate.sh" > "$TMP/fn.sh"
check "function extracted" test -s "$TMP/fn.sh"

# Section files a well-behaved worker would write, from the test's own fixture: with trace lines, and without.
export ROOT_DIR="$ROOT"
python3 -B - "$TMP/good" "$TMP/bare" <<'PY'
import importlib.util, os, sys
from pathlib import Path
root = Path(os.environ['ROOT_DIR'])
spec = importlib.util.spec_from_file_location('t', root / 'scripts' / 'tests' / 'project-plan-sections-test.py')
module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
for target, trace in ((sys.argv[1], True), (sys.argv[2], False)):
    Path(target).mkdir(parents=True)
    module.good_files(target, trace=trace)
(Path(sys.argv[2]) / 'trace.md').write_text(module.section(13, '| R-1 | B-1 |'))
PY

run_case() {   # name mode fixture
    local name="$1" mode="$2" fixture="${3:-good}" dir="$TMP/$1"
    mkdir -p "$dir/.uncle/workflow/logs"
    (
        cd "$dir"
        ROOT="$ROOT"; STATE_DIR=".uncle/workflow"; LOG_DIR=".uncle/workflow/logs"
        if [[ "${JSON_MODE:-}" == hosted ]]; then stage_supports_structured_output() { return 0; }; fi
        if [[ "${JSON_MODE:-}" == local ]]; then stage_uses_self_hosted() { return 0; }; fi
        run_claude() {   # prompt stage
            local worker="${2#project-plan-section-}" parts="$STATE_DIR/project-plan-sections"
            printf '%s %s\n' "$worker" "$(python3 -c 'import time; print("%.2f" % time.time())')" >> "$STATE_DIR/order"
            case "$worker" in
                outline) ;;
                trace) for f in outline design state domain components flow steps sequence decisions restrictions limits bounds behaviors handling checks invariants guards tests defects obligations commands closing; do [[ -s "$parts/$f.md" ]] || echo "trace started before $f" >> "$STATE_DIR/violations"; done ;;
                behaviors|handling|checks|decisions|restrictions|limits|bounds) ;;      # written from the requirements alone: they start with the outline
                *) [[ -s "$parts/outline.md" ]] || echo "$worker started before the outline" >> "$STATE_DIR/violations" ;;
            esac
            sleep 0.4
            [[ "$mode:$worker" != fail:tests ]] || return 1
            if [[ "$mode:$worker" == chat:commands ]]; then   # answers in chat, writes no file
                python3 -c 'import json,sys; print(json.dumps({"type":"result","result":sys.stdin.read()}))' \
                    < "$TMP/$fixture/commands.md" > "$LOG_DIR/project-plan-section-commands.jsonl"
                printf '%s end %s\n' "$worker" "$(python3 -c 'import time; print("%.2f" % time.time())')" >> "$STATE_DIR/order"
                return 0
            fi
            if [[ "$mode:$worker" == silent:commands ]]; then   # writes nothing, says nothing useful, then does it on the retry
                if [[ -e "$STATE_DIR/silent-once" ]]; then cp "$TMP/$fixture/commands.md" "$parts/commands.md"; return 0; fi
                touch "$STATE_DIR/silent-once"; echo done > "$LOG_DIR/project-plan-section-commands.jsonl"; return 0
            fi
            if [[ -n "${UNCLE_WORKER_PACKET_PATH:-}" ]]; then   # JSON modes: the answer is a packet, never a file
                echo "$worker schema=${UNCLE_OUTPUT_SCHEMA_FILE:-none} out=${UNCLE_STRUCTURED_OUTPUT_PATH:-none} json=$(grep -c -- '--json\|JSON object' "$1")" >> "$STATE_DIR/json-calls"
                if [[ "$mode:$worker" == badpacket:commands ]]; then echo '{"sections":[]}' > "$UNCLE_WORKER_PACKET_PATH"; return 0; fi
                if [[ "$mode:$worker" == silentpacket:commands && ! -e "$STATE_DIR/silent-once" ]]; then touch "$STATE_DIR/silent-once"; return 0; fi
                ROOT_DIR="$ROOT" python3 -B - "$TMP/$fixture/$worker.md" "$UNCLE_WORKER_PACKET_PATH" "$worker" <<'PY'
import os, sys, json
sys.path.insert(0, os.environ['ROOT_DIR'] + '/scripts/lib')
import project_plan_sections as sections, worker_schemas
text = open(sys.argv[1]).read()
data, body = sections.trace_lines(text)
trace = [{'kind': kind, 'requirement': req, 'ids': ids} for kind, rows in data.items() for req, ids in rows.items()]
packet = {'schema': 'uncle.artifact/v1', 'kind': worker_schemas.SECTION_KIND,
          'sections': [{'heading': heading, 'body': content or '(empty)'} for heading, content in sections.blocks(body)]}
if trace:
    packet['trace'] = trace
json.dump(packet, open(sys.argv[2], 'w'))
PY
                printf '%s end %s\n' "$worker" "$(python3 -c 'import time; print("%.2f" % time.time())')" >> "$STATE_DIR/order"
                return 0
            fi
            if [[ "$mode:$worker" == lane:closing ]]; then
                printf '## 7. Domain invariants\nstolen\n' > "$parts/$worker.md"
            else
                cp "$TMP/$fixture/$worker.md" "$parts/$worker.md"
            fi
            printf '%s end %s\n' "$worker" "$(python3 -c 'import time; print("%.2f" % time.time())')" >> "$STATE_DIR/order"
        }
        . "$TMP/fn.sh"
        run_project_plan_sections "$dir/plan.md" > "$STATE_DIR/out" 2>&1; echo $? > "$STATE_DIR/rc"
    )
}
starts() { grep -v ' end ' "$1/.uncle/workflow/order" | awk '{print $1}'; }

run_case ok ok
w="$TMP/ok/.uncle/workflow"
check "success: returns 0"                         test "$(cat "$w/rc")" == 0
check "success: plan assembled"                    grep -q '^# Project plan' "$TMP/ok/plan.md"
check "success: the outline started with the early workers"  bash -c 'head -n8 <<< "$1" | grep -qx outline' _ "$(starts "$TMP/ok")"
check "success: twenty-two workers ran, no model trace"   bash -c 'test "$(grep -vc " end " "$1")" == 22 && ! grep -q "^trace " "$1"' _ "$w/order"
check "success: section 13 was built by the driver" grep -q '| R-1 | B-1, B-2 | I-1 | C-1 | T-1 | none |' "$TMP/ok/plan.md"
check "success: nothing started before the outline" test ! -e "$w/violations"
check "success: phase two ran concurrently"        python3 - "$w/order" <<'PY'
import sys
rows = [line.split() for line in open(sys.argv[1])]
starts = {r[0]: float(r[1]) for r in rows if r[1] != 'end'}
ends = {r[0]: float(r[2]) for r in rows if r[1] == 'end'}
phase_two = [n for n in starts if n not in ('outline', 'behaviors', 'handling', 'checks', 'decisions', 'restrictions', 'limits', 'bounds')]
# every phase-two worker started before any phase-two worker finished: they overlapped
sys.exit(0 if len(phase_two) == 14 and max(starts[n] for n in phase_two) < min(ends[n] for n in phase_two) else 1)
PY
check "success: phase two began after the outline finished" python3 - "$w/order" <<'PY'
import sys
rows = [line.split() for line in open(sys.argv[1])]
ends = {r[0]: float(r[2]) for r in rows if r[1] == 'end'}
starts = {r[0]: float(r[1]) for r in rows if r[1] != 'end'}
sys.exit(0 if all(starts[n] >= ends['outline'] - 0.05 for n in starts if n not in ('outline', 'behaviors', 'handling', 'checks', 'decisions', 'restrictions', 'limits', 'bounds')) else 1)
PY
check "success: the early workers started before the outline finished" python3 - "$w/order" <<'PY'
import sys
rows = [line.split() for line in open(sys.argv[1])]
ends = {r[0]: float(r[2]) for r in rows if r[1] == 'end'}
starts = {r[0]: float(r[1]) for r in rows if r[1] != 'end'}
sys.exit(0 if all(starts[n] < ends['outline'] for n in ('behaviors', 'handling', 'checks', 'decisions', 'restrictions', 'limits', 'bounds')) else 1)
PY

run_case bare ok bare
w="$TMP/bare/.uncle/workflow"
check "no mappings: a traceability worker ran, last" bash -c 'test "$(grep -v " end " "$1" | tail -n1 | cut -d" " -f1)" == trace' _ "$w/order"
check "no mappings: the plan is still assembled"     test "$(cat "$w/rc")" == 0
check "no mappings: it ran after every other worker" test ! -e "$w/violations"
check "no mappings: its section is used"             grep -q '| R-1 | B-1 |' "$TMP/bare/plan.md"

run_case chat chat
w="$TMP/chat/.uncle/workflow"
check "answered in chat: the plan is assembled"      test "$(cat "$w/rc")" == 0
check "answered in chat: the worker ran once"        test "$(grep -c '^commands ' "$w/order" | tr -d ' ')" == 2
check "answered in chat: its answer is in the plan"  grep -q '^## Verification commands' "$TMP/chat/plan.md"

run_case silent silent
w="$TMP/silent/.uncle/workflow"
check "silent worker: assembled after one retry"     test "$(cat "$w/rc")" == 0
check "silent worker: it was run a second time"      test "$(grep -v ' end ' "$w/order" | grep -c '^commands ')" == 2

run_case failed fail
w="$TMP/failed/.uncle/workflow"
check "worker failure: returns nonzero"            test "$(cat "$w/rc")" != 0
check "worker failure: no plan left behind"        test ! -e "$TMP/failed/plan.md"
check "worker failure: no traceability worker"     bash -c '! grep -q "^trace " "$1"' _ "$w/order"

run_case lane lane
check "section out of lane: returns nonzero"       test "$(cat "$TMP/lane/.uncle/workflow/rc")" != 0
check "section out of lane: no plan left"          test ! -e "$TMP/lane/plan.md"

# Forced JSON: hosted Claude gets a schema per worker, a local model the packet path only; both deliver packets
# the driver renders into the section files, and the plan comes out the same.
JSON_MODE=hosted run_case jhosted ok
w="$TMP/jhosted/.uncle/workflow"
check "hosted json: plan assembled"               test "$(cat "$w/rc")" == 0
check "hosted json: twenty-two workers, no model trace"  bash -c 'test "$(grep -vc " end " "$1")" == 22 && ! grep -q "^trace " "$1"' _ "$w/order"
check "hosted json: every worker had a schema"    bash -c 'test "$(grep -c "schema=.*/schemas/" "$1")" == 22 && ! grep -q "schema=none" "$1"' _ "$w/json-calls"
check "hosted json: the answer path is the packet" bash -c 'grep -q "out=.*/behaviors.json" "$1"' _ "$w/json-calls"
check "hosted json: prompts name the JSON answer" bash -c 'test "$(grep -c "json=0" "$1")" == 0' _ "$w/json-calls"
check "hosted json: the schema lists the lane's headings" python3 - "$w/project-plan-sections/schemas/behaviors.json" <<'PY'
import json, sys
schema = json.load(open(sys.argv[1]))
heading = schema['properties']['sections']['items']['properties']['heading']
sys.exit(0 if any('6.' in h for h in heading['enum']) and not any('7.' in h for h in heading['enum']) and 'trace' in schema['properties'] else 1)
PY
check "hosted json: section 13 built by the driver" grep -q '| R-1 | B-1, B-2 | I-1 | C-1 | T-1 | none |' "$TMP/jhosted/plan.md"
check "hosted json: the section files are rendered" test -s "$w/project-plan-sections/behaviors.md"

JSON_MODE=local run_case jlocal ok
w="$TMP/jlocal/.uncle/workflow"
check "local json: plan assembled"                test "$(cat "$w/rc")" == 0
check "local json: packet path, no schema flag"   bash -c '! grep -q "schema=/\|schema=.*schemas" "$1" && grep -q "out=none" "$1"' _ "$w/json-calls"

JSON_MODE=hosted run_case jsilent silentpacket
w="$TMP/jsilent/.uncle/workflow"
check "no packet: the worker is run once more"    test "$(cat "$w/rc")" == 0
check "no packet: exactly two commands runs"      test "$(grep -v ' end ' "$w/order" | grep -c '^commands ')" == 2

JSON_MODE=hosted run_case jbad badpacket
w="$TMP/jbad/.uncle/workflow"
check "bad packet: refused after one retry"       test "$(cat "$w/rc")" != 0
check "bad packet: no plan left behind"           test ! -e "$TMP/jbad/plan.md"

# Under the TUI every stage runs through native_stage.py (steering); schema mode must work there too, or the
# outline worker is refused instantly and the whole plan falls back to the single pass (noinit, 85 s, no threads).
check "schema mode is allowed through native_stage" bash -c '! grep -q "client_cmd\[0\]\" != python3" "$1/scripts/stagegate.sh"' _ "$ROOT"
check "a refused schema run is a loud message"       grep -qF 'asked for schema-checked output, which this runner cannot give' "$ROOT/scripts/stagegate.sh"

# On by default, on every runner: the sectional plan is attempted before the self-hosted/hosted split.
block="$(awk '/^        PROJECT_PLAN\)$/,/^        ADVERSARIAL_REVIEW\)$/' "$ROOT/scripts/stagegate.sh" | head -n 60)"
check "sections default on"                        grep -qF 'WORKFLOW_PROJECT_PLAN_SECTIONS:-1' <<< "$block"
check "sections are tried before the runner split" bash -c 'a=$(grep -n "run_project_plan_sections" <<< "$1" | head -1 | cut -d: -f1); b=$(grep -n "stage_uses_self_hosted project-plan" <<< "$1" | head -1 | cut -d: -f1); [ "$a" -lt "$b" ]' _ "$block"
check "a sectioned plan reaches the same conversion" grep -qF 'project_plan_sectioned" == 1 ]] || stage_uses_self_hosted' <<< "$block"

[[ "$fails" == 0 ]] && echo "project-plan-sections-driver-test.sh: all checks passed" || exit 1
