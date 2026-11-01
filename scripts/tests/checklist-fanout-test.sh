#!/usr/bin/env bash
# run_parallel_checklist_workers with an absolute STATE_DIR (as the live driver has), both ways:
# lanes (the default: conflicting checks run in order inside one worker, everything else beside them)
# and the old barrier groups (WORKFLOW_EXECUTE_CHECKLIST_LANES=0).
set -uo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
fails=0
check() { local what="$1"; shift; if "$@"; then :; else echo "FAIL: $what"; fails=$((fails + 1)); fi; }

for fn in run_parallel_checklist_workers checklist_run_worker; do
    awk -v f="$fn" '$0 ~ "^" f "\\(\\) \\{" {p=1} p {print} p && /^}/ {exit}' "$ROOT/scripts/stagegate.sh" > "$TMP/$fn.sh"
    check "$fn extracted" test -s "$TMP/$fn.sh"
done

# run_case <name> <lanes-env> <resources-json-per-check...> : each argument is "ID|res,res|dep,dep"; groups from them
run_case() {
    local name="$1" lanes="$2"; shift 2
    local dir="$TMP/$name"; mkdir -p "$dir/.uncle/workflow/documents" "$dir/.uncle/workflow/checklist-groups" "$dir/.uncle/workflow/logs"
    python3 - "$dir" "$@" <<'PY'
import json, os, sys
checks = []
for spec in sys.argv[2:]:
    cid, resources, depends = (spec.split('|') + ['', ''])[:3]
    check = {'id': cid, 'required': os.environ.get('CASE_OPTIONAL') != '1', 'exact_action': 'a', 'expected_result': 'b',
             'depends_on': [d for d in depends.split(',') if d]}
    if resources != '?':
        check['exclusive_resources'] = [r for r in resources.split(',') if r]
    checks.append(check)
json.dump({'schema': 'uncle.artifact/v1', 'kind': 'manual-checklist', 'checks': checks},
          open(sys.argv[1] + '/.uncle/workflow/documents/MANUAL_CHECKLIST.json', 'w'))
# the old barrier groups file, for the non-lane path: every check alone unless told otherwise
open(sys.argv[1] + '/.uncle/workflow/checklist-groups/groups.txt', 'w').write(' '.join(c['id'] for c in checks[:3]) + '\n' + '\n'.join(c['id'] for c in checks[3:]) + '\n')
PY
    (
        cd "$dir"
        ROOT="$ROOT"; PROJECT_ROOT="$PWD"; STATE_DIR="$PWD/.uncle/workflow"; LOG_DIR="$STATE_DIR/logs"
        PARALLEL_CHECKLIST_WORKERS=1; BUDGET_EXECUTE=""; WORKFLOW_EXECUTE_CHECKLIST_LANES="$lanes"
        run_claude() {   # prompt stage
            local ids; ids="$(grep -o 'Execute `[^`]*`' "$1" | sed 's/Execute `//; s/`//' | tr '\n' ' ')"
            printf '%s | %s | %s\n' "$2" "$(python3 -c 'import time; print("%.2f" % time.time())')" "$ids" >> "$STATE_DIR/calls"
            sleep 1.5
            printf '%s | %s | %s\n' "$2" "$(python3 -c 'import time; print("%.2f" % time.time())')" "end" >> "$STATE_DIR/calls"
            python3 - "$UNCLE_WORKER_PACKET_PATH" $ids <<'PY'
import json, sys
json.dump({'schema': 'uncle.artifact/v1', 'kind': 'checklist-execution-worker-packet', 'results': [
    {'id': i, 'action': 'a', 'expected_result': 'b', 'actual_result': 'c', 'evidence': 'e', 'status': 'PASS'} for i in sys.argv[2:]]},
    open(sys.argv[1], 'w'))
PY
        }
        . "$ROOT/scripts/lib/checklist-lanes.sh"
        . "$TMP/checklist_run_worker.sh"
        . "$TMP/run_parallel_checklist_workers.sh"
        run_parallel_checklist_workers > "$STATE_DIR/out" 2>&1; echo $? > "$STATE_DIR/rc"
    )
}
state() { echo "$TMP/$1/.uncle/workflow"; }
collated() { python3 -c 'import json,sys; print(len(json.load(open(sys.argv[1]))["results"]))' "$(state "$1")/documents/EXECUTE_CHECKLIST_WORKERS.json"; }

# No required rows must replace stale results without launching a worker or
# expanding an unset Bash array. Optional observations are not claimed as PASS.
for driver in stagegate change-workflow; do
    awk '/^run_parallel_checklist_workers\(\) \{/ {p=1} p {print} p && /^}/ {exit}' "$ROOT/scripts/$driver.sh" > "$TMP/run_parallel_checklist_workers.sh"
    CASE_OPTIONAL=1 run_case "$driver-optional" 1 'OPTIONAL|'
    check "$driver optional: successful exit" test "$(cat "$(state "$driver-optional")/rc")" == 0
    check "$driver optional: no workers" test ! -e "$(state "$driver-optional")/calls"
    check "$driver optional: no fabricated results" test "$(collated "$driver-optional")" == 0
done
awk '/^run_parallel_checklist_workers\(\) \{/ {p=1} p {print} p && /^}/ {exit}' "$ROOT/scripts/stagegate.sh" > "$TMP/run_parallel_checklist_workers.sh"
run_case empty 1
check 'empty: successful exit' test "$(cat "$(state empty)/rc")" == 0
check 'empty: no workers' test ! -e "$(state empty)/calls"
check 'empty: empty results' test "$(collated empty)" == 0

# --- lanes: three checks on one port form a lane; the rest run beside it, no barriers --------------------
run_case lanes 1 'A|port:4173' 'B|' 'C|port-4173' 'D|' 'E|port:4173' 'F|' 'G|dir:x'
calls="$(state lanes)/calls"
check "lanes: workers launched (the path bug made this empty)" test -s "$calls"
check "lanes: collated file exists"                            test -s "$(state lanes)/documents/EXECUTE_CHECKLIST_WORKERS.json"
check "lanes: all seven checks collated"                       test "$(collated lanes)" == 7
check "lanes: the port checks share ONE worker, in order"      grep -qE '\| A C E *$' "$calls"
check "lanes: the rest are pooled, none duplicated"            bash -c 'for i in B D F G; do test "$(grep -cE "\| [^|]*\b$i\b[^|]*$" "$1")" == 1 || exit 1; done' _ "$calls"
check "lanes: no check was executed twice"                     bash -c 'for i in A B C D E F G; do test "$(grep -E "[|] .*\b$i\b" "$1" | grep -vc "end")" -le 1 || exit 1; done' _ "$calls"
check "lanes: workers overlapped (no barrier between them)"    python3 - "$calls" <<'PY'
import sys
rows = [l.split(' | ') for l in open(sys.argv[1]).read().splitlines()]
starts = {r[0]: float(r[1]) for r in rows if r[2].strip() != 'end'}
ends = {r[0]: float(r[1]) for r in rows if r[2].strip() == 'end'}
# Free checks are pooled by the production defaults, so this fixture now has
# a resource lane and one free-check batch. Both must overlap; requiring three
# workers would reintroduce the one-check-per-session policy under test.
sys.exit(0 if len(starts) >= 2 and max(starts.values()) < min(ends.values()) else 1)
PY
check "lanes: nothing uncovered"                               test -z "$(python3 -B "$ROOT/scripts/lib/checklist_coverage.py" "$(state lanes)/documents/MANUAL_CHECKLIST.json" "$(state lanes)/documents/EXECUTE_CHECKLIST_WORKERS.json")"

# --- a checklist that declared nothing is still executed by one packet worker ---------------------------
run_case undeclared 1 'A|?' 'B|?' 'C|?'
check "undeclared: one worker runs its serial lane"             test -s "$(state undeclared)/calls"
check "undeclared: every row is collated"                       test "$(collated undeclared)" == 3

# --- everything conflicting is one lane, executed by one worker ------------------------------------------
run_case allconflict 1 'A|p' 'B|p' 'C|p'
check "all conflicting: one worker"                            test -s "$(state allconflict)/calls"
check "all conflicting: every row is collated"                 test "$(collated allconflict)" == 3

# --- the old barrier path is still there behind the switch -----------------------------------------------
run_case barrier 0 'A|' 'B|' 'C|' 'D|' 'E|'
check "barrier path: workers ran"                              test -s "$(state barrier)/calls"
check "barrier path: every check collated"                     test "$(collated barrier)" == 5
check "barrier path: group 2 started after group 1 ended"      python3 - "$(state barrier)/calls" <<'PY'
import sys
rows = [l.split(' | ') for l in open(sys.argv[1]).read().splitlines()]
first = [float(r[1]) for r in rows if r[0].endswith('group-1-batch-1') and r[2].strip() == 'end']
later = [float(r[1]) for r in rows if 'group-2' in r[0] and r[2].strip() != 'end']
sys.exit(0 if first and later and min(later) >= max(first) - 0.05 else 1)
PY

[[ "$fails" == 0 ]] && echo "checklist-fanout-test.sh: all checks passed" || exit 1
