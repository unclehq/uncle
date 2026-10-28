#!/usr/bin/env bash
# run_updated_change_plan_decide (the change workflow): the writers decide and edit straight from the review, the lens specialists run beside them, and one
# reconciler adds what the specialists asked for and no writer did.  Every failure returns nonzero with nothing published (the
# caller then runs the specialist round and the writers as before), except a failed specialist or reconciler, which costs only
# the extra edits.
set -uo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
TMP="$(mktemp -d)"; trap 'rm -rf "$TMP"' EXIT
fails=0
export WORKFLOW_UPDATED_PLAN_OPS=1 WORKFLOW_UPDATED_PLAN_EDITS=1 WORKFLOW_UPDATED_PLAN_DECIDE=1 WORKFLOW_UPDATED_PLAN_EDIT_SLICE=3 WORKFLOW_UPDATED_PLAN_HEDGE_SECONDS=300
check() { local what="$1"; shift; if "$@"; then :; else echo "FAIL: $what"; fails=$((fails + 1)); fi; }
awk '/^(updated_change_plan_launch_writer|run_updated_change_plan_edit_writers|updated_change_plan_start_reconcile|run_updated_change_plan_decide)\(\) \{/,/^}/' "$ROOT/scripts/change-workflow.sh" > "$TMP/fn.sh"
check "functions extracted" test "$(grep -c '^[a-z_]*() {' "$TMP/fn.sh")" == 4

run_case() {   # name mode [hosted|local]
    local name="$1" mode="$2" runner="${3:-hosted}" dir="$TMP/$1"
    mkdir -p "$dir/.uncle/workflow/documents" "$dir/.uncle/workflow/logs" "$dir/.uncle/docs"
    python3 -B - "$dir" <<'PY'
import json, sys
d = sys.argv[1] + '/.uncle/workflow/documents/'
narrative = ('# Project plan\n\n## 1. Observable behaviors\n\n| ID | Trigger | Observable result | Failure behavior | Requirement IDs |\n'
             '|---|---|---|---|---|\n| B-1 | click | appended | unchanged | UB-1 |\n| B-2 | key | same | same | UB-2 |\n\n## 2. Notes\n\nKept.\n')
json.dump({'schema': 'uncle.artifact/v1', 'kind': 'change-plan', 'narrative': narrative}, open(d + 'CHANGE_PLAN.json', 'w'))
json.dump({'schema': 'uncle.artifact/v1', 'kind': 'adversarial-review',
           'findings': [{'id': 'AR-%d' % n, 'fix': 'fix %d' % n} for n in range(1, 7)]}, open(d + 'ADVERSARIAL_REVIEW.json', 'w'))
PY
    (
        cd "$dir"
        ROOT="$ROOT"; STATE_DIR=".uncle/workflow"; LOG_DIR=".uncle/workflow/logs"
        MODEL_UPDATED_PLAN=m; EFFORT_UPDATED_PLAN=low; BUDGET_UPDATED_PLAN=; CODEX_EFFORT_REVIEW=low
        UPDATED_PLAN_ADVISOR_PIDS=()
        stage_uses_self_hosted() { [[ "$runner" == local ]]; }
        stage_supports_structured_output() { [[ "$runner" == hosted ]]; }
        ensure_project_plan_json() { return 0; }
        require_file() { [[ -s "$1" ]]; }
        stamp() { python3 -c 'import time; print("%.2f" % time.time())'; }
        run_codex() {   # prompt output name effort: a lens specialist
            printf 'advisor %s start %s\n' "$3" "$(stamp)" >> "$STATE_DIR/events"
            sleep 0.5
            [[ "$mode" != advisors-fail ]] || { echo 'not json' > "$2"; return 0; }
            python3 -B - "$2" <<'PY2'
import json, sys
json.dump({'schema': 'uncle.artifact/v1', 'kind': 'updated-plan-worker-packet', 'findings': [
    {'id': 'AR-1', 'gap': 'g', 'evidence': 'e', 'risk': 'r', 'required_correction': 'Add the verification note to B-1'}]}, open(sys.argv[1], 'w'))
PY2
            printf 'advisor %s end %s\n' "$3" "$(stamp)" >> "$STATE_DIR/events"
        }
        run_claude() {   # prompt stage
            local n="${2#updated-change-plan-worker-edits-}"
            printf '%s start %s\n' "$2" "$(stamp)" >> "$STATE_DIR/events"
            sleep 0.3
            if [[ "$2" == updated-change-plan-worker-reconcile ]]; then
                echo "$(grep -c 'You decide no finding' "$1") $(grep -c 'Add the verification note to B-1' "$1") $(grep -c 'X1' "$1")" >> "$STATE_DIR/reconcile-saw"
                [[ "$mode" != reconcile-fail ]] || return 1
                printf '{"dispositions":[],"ops":[{"op":"set_fields","id":"B-1","fields":{"verification":"FROM_SPECIALIST"}},{"op":"set_fields","id":"B-1","fields":{"failure":"OVERWRITE"}}]}' > "$UNCLE_WORKER_PACKET_PATH"
                return 0
            fi
            echo "$2 specialists=$(grep -c 'Collated specialist corrections' "$1") schema=${UNCLE_OUTPUT_SCHEMA_FILE:-none}" >> "$STATE_DIR/calls"
            [[ "$mode:$n" != fail:2 && "$mode:$n" != fail:2-* ]] || return 1
            if [[ "$2" == updated-change-plan-worker-resolve-* ]]; then
                printf '{"resolutions":[{"group":"G1","ops":[{"op":"set_fields","id":"B-1","fields":{"failure":"MERGED"}}]}]}' > "$UNCLE_WORKER_PACKET_PATH"
                return 0
            fi
            python3 -B - "$n" "$mode" "$UNCLE_WORKER_PACKET_PATH" "$1" <<'PY3'
import json, re, sys
n, mode, target, prompt = sys.argv[1:5]
ids = re.search(r'You own exactly these findings: ([^.]*)\.', open(prompt).read()).group(1).split(', ')
row = 'B-1' if (n.startswith('1') or mode == 'resolve') else 'B-2'
body = {'dispositions': [{'finding': i, 'disposition': 'Accepted', 'reason': 'r', 'plan_change': 'c'} for i in ids],
        'ops': [{'op': 'set_fields', 'id': row, 'fields': {'failure': 'X%s' % re.sub(r'[^0-9].*', '', n)}}]}
json.dump(body, open(target, 'w'))
PY3
        }
        . "$TMP/fn.sh"
        run_updated_change_plan_decide > "$STATE_DIR/out" 2>&1; echo $? > "$STATE_DIR/rc"
    )
}

run_case ok ok
w="$TMP/ok/.uncle/workflow"; doc="$TMP/ok/.uncle/docs/CHANGE_PLAN.md"
check "ok: returns 0"                              test "$(cat "$w/rc")" == 0
check "ok: the deciders' edits are in the plan"    bash -c 'grep -q "| X1 |" "$1" && grep -q "| B-2 | key | same | X2 |" "$1"' _ "$doc"
check "ok: the specialists' correction was added"  grep -q 'FROM_SPECIALIST' "$doc"
check "ok: a reconciler edit to a field a decider changed is dropped" bash -c '! grep -q OVERWRITE "$1"' _ "$doc"
check "ok: every finding has a disposition"        bash -c 'for n in 1 2 3 4 5 6; do grep -q "AR-$n" "$1" || exit 1; done' _ "$doc"
check "ok: the writers read no specialist corrections" bash -c 'grep "edits-" "$1" | grep -qv "specialists=0" && exit 1; exit 0' _ "$w/calls"
check "ok: the specialists started with the writers, not after them" python3 - "$w/events" <<'PY'
import sys
rows = [line.split() for line in open(sys.argv[1])]
adv = [float(r[3]) for r in rows if r[0] == 'advisor' and r[2] == 'start']
wri = [float(r[2]) for r in rows if r[0].startswith('updated-change-plan-worker-edits') and r[1] == 'start']
sys.exit(0 if len(adv) == 3 and len(wri) == 2 and max(adv) - min(wri) < 1.0 else 1)
PY
check "ok: the reconciler ran once, after the specialists and the writers" python3 - "$w/events" <<'PY'
import sys
rows = [line.split() for line in open(sys.argv[1])]
rec = [float(r[2]) for r in rows if r[0] == 'updated-change-plan-worker-reconcile']
adv = [float(r[3]) for r in rows if r[0] == 'advisor' and r[2] == 'end']
sys.exit(0 if len(rec) == 1 and len(adv) == 3 and rec[0] >= max(adv) else 1)
PY
check "ok: the reconciler saw the corrections and the writers' edits" grep -q '^1 1 1$' "$w/reconcile-saw"
check "ok: hosted reconciler had a schema listing the ids" python3 - "$w/updated-change-plan-edits/schemas/reconcile.json" <<'PY'
import json, sys
s = json.load(open(sys.argv[1]))
sys.exit(0 if 'B-2' in s['properties']['ops']['items']['properties']['id']['enum'] else 1)
PY

run_case conflict resolve
w="$TMP/conflict/.uncle/workflow"; doc="$TMP/conflict/.uncle/docs/CHANGE_PLAN.md"
check "conflict: resolved and reconciled, returns 0" bash -c 'test "$(cat "$1/rc")" == 0 && grep -q "MERGED" "$2" && grep -q FROM_SPECIALIST "$2"' _ "$w" "$doc"

run_case rfail reconcile-fail
check "reconciler failure: the deciders' plan is still published" bash -c 'test "$(cat "$1/.uncle/workflow/rc")" == 0 && grep -q "| X1 |" "$1/.uncle/docs/CHANGE_PLAN.md" && ! grep -q FROM_SPECIALIST "$1/.uncle/docs/CHANGE_PLAN.md"' _ "$TMP/rfail"

run_case afail advisors-fail
w="$TMP/afail/.uncle/workflow"
check "specialist failure: the plan is published and no reconciler ran" bash -c 'test "$(cat "$1/rc")" == 0 && ! grep -q reconcile "$1/events"' _ "$w"

run_case wfail fail
check "writer failure: nonzero and nothing published" bash -c 'test "$(cat "$1/.uncle/workflow/rc")" != 0 && test ! -e "$1/.uncle/docs/CHANGE_PLAN.md"' _ "$TMP/wfail"

run_case local ok local
check "local model: decides, edits and reconciles" bash -c 'test "$(cat "$1/rc")" == 0 && grep -q FROM_SPECIALIST "$2"' _ "$TMP/local/.uncle/workflow" "$TMP/local/.uncle/docs/CHANGE_PLAN.md"

WORKFLOW_UPDATED_PLAN_DECIDE=0 run_case off ok
check "switched off: returns nonzero at once, runs nothing" bash -c 'test "$(cat "$1/rc")" != 0 && test ! -e "$1/events"' _ "$TMP/off/.uncle/workflow"

block="$(awk '/^        UPDATED_PLAN\)$/,/^        VALIDATE_UPDATED_PLAN\)$/' "$ROOT/scripts/change-workflow.sh")"
check "the stage tries deciding before the specialist round" bash -c 'a=$(grep -n "run_updated_change_plan_decide" <<< "$1" | head -1 | cut -d: -f1); b=$(grep -n "run_updated_change_plan_panel" <<< "$1" | head -1 | cut -d: -f1); [ -n "$a" ] && [ "$a" -lt "$b" ]' _ "$block"
check "deciding is on by default"                 grep -qF 'WORKFLOW_UPDATED_PLAN_DECIDE:-1' "$ROOT/scripts/change-workflow.sh"

[[ "$fails" == 0 ]] && echo "updated-change-plan-decide-driver-test.sh: all checks passed" || exit 1
