#!/usr/bin/env bash
# run_updated_change_plan_edit_writers (the change workflow) in ops mode: writers receive the plan model and answer with ops that name ids;
# the merge publishes the same section patch, and every failure still returns nonzero with nothing published.
set -uo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
TMP="$(mktemp -d)"; trap 'rm -rf "$TMP"' EXIT
fails=0
export WORKFLOW_UPDATED_PLAN_OPS=1 WORKFLOW_UPDATED_PLAN_EDITS=1 WORKFLOW_UPDATED_PLAN_EDIT_SLICE=3 WORKFLOW_UPDATED_PLAN_HEDGE_SECONDS=300
check() { local what="$1"; shift; if "$@"; then :; else echo "FAIL: $what"; fails=$((fails + 1)); fi; }
awk '/^(updated_change_plan_launch_writer|run_updated_change_plan_edit_writers)\(\) \{/,/^}/' "$ROOT/scripts/change-workflow.sh" > "$TMP/fn.sh"
check "function extracted" test -s "$TMP/fn.sh"

run_case() {   # name mode [hosted|local]
    local name="$1" mode="$2" runner="${3:-hosted}" dir="$TMP/$1"
    mkdir -p "$dir/.uncle/workflow/documents" "$dir/.uncle/workflow/logs" "$dir/.uncle/docs"
    python3 -B - "$dir" "$ROOT" <<'PY'
import json, sys
sys.path.insert(0, sys.argv[2] + '/scripts/lib')
import updated_plan_synthesis_prompt as P
d = sys.argv[1] + '/.uncle/workflow/documents/'
narrative = ('# Project plan\n\n## 1. Observable behaviors\n\n| ID | Trigger | Observable result | Failure behavior | Requirement IDs |\n'
             '|---|---|---|---|---|\n| B-1 | click | appended | unchanged | UB-1 |\n| B-2 | key | same | same | UB-2 |\n\n## 2. Notes\n\nKept.\n')
plan = {'schema': 'uncle.artifact/v1', 'kind': 'change-plan', 'narrative': narrative}
review = {'schema': 'uncle.artifact/v1', 'kind': 'adversarial-review', 'findings': [{'id': 'AR-%d' % n} for n in range(1, 7)]}
workers = {'schema': 'uncle.artifact/v1', 'kind': 'updated-plan-worker-packets', 'workers': [], 'findings': []}
json.dump(plan, open(d + 'CHANGE_PLAN.json', 'w'))
json.dump(review, open(d + 'ADVERSARIAL_REVIEW.json', 'w'))
open(sys.argv[1] + '/prompt.md', 'w').write(P.prompt(plan, review, workers, change=True))
PY
    (
        cd "$dir"
        ROOT="$ROOT"; STATE_DIR=".uncle/workflow"; LOG_DIR=".uncle/workflow/logs"; UPDATED_PLAN_PROMPT="$dir/prompt.md"
        MODEL_UPDATED_PLAN=m; EFFORT_UPDATED_PLAN=low; BUDGET_UPDATED_PLAN=
        UPDATED_PLAN_ADVISOR_PIDS=()      # a top-level array in the driver; the extracted functions read it
        stage_uses_self_hosted() { [[ "$runner" == local ]]; }
        stage_supports_structured_output() { [[ "$runner" == hosted ]]; }
        run_claude() {   # prompt stage
            local n="${2#updated-change-plan-worker-edits-}"; [[ "$2" != updated-change-plan-worker-resolve-* ]] || n=resolve
            printf '%s\n' "$n" >> "$STATE_DIR/starts"
            echo "$2 schema=${UNCLE_OUTPUT_SCHEMA_FILE:-none} out=${UNCLE_STRUCTURED_OUTPUT_PATH:-none} packet=${UNCLE_WORKER_PACKET_PATH:-none} kinds=$(grep -o '"kind":"[a-z-]*"' "$1" | sort -u | tr '\n' ' ')" >> "$STATE_DIR/calls"
            sleep 0.2
            [[ "$mode:$n" != fail:2 && "$mode:$n" != fail:2-* && "$mode:$n" != failonce:2 ]] || return 1
            if [[ "$2" == updated-change-plan-worker-resolve-* ]]; then
                echo resolver >> "$STATE_DIR/resolver-calls"
                [[ "$mode" == resolve || "$mode" == resolve-retry ]] || return 1
                local id="B-1"
                if [[ "$mode" == resolve-retry && "$2" != *-retry ]]; then id="B-9"; fi
                printf '{"resolutions":[{"group":"G1","ops":[{"op":"set_fields","id":"%s","fields":{"failure":"MERGED"}}]}]}' "$id" > "$UNCLE_WORKER_PACKET_PATH"
                return 0
            fi
            python3 -B - "$n" "$mode" "$UNCLE_WORKER_PACKET_PATH" "$1" <<'PY2'
import json, re, sys
n, mode, target, prompt = sys.argv[1:5]
text = open(prompt).read()
ids = re.search(r'You own exactly these findings: ([^.]*)\.', text).group(1).split(', ')
row = 'B-1' if (n.startswith('1') or mode in ('resolve', 'resolve-retry', 'resolve-fail')) else 'B-2'
body = {'dispositions': [{'finding': i, 'disposition': 'Accepted', 'reason': 'r', 'plan_change': 'c'} for i in ids],
        'ops': [{'op': 'set_fields', 'id': row, 'fields': {'failure': 'X%s' % re.sub(r'[^0-9].*', '', n)}}]}
json.dump(body, open(target, 'w'))
PY2
        }
        . "$TMP/fn.sh"
        run_updated_change_plan_edit_writers > "$STATE_DIR/out" 2>&1; echo $? > "$STATE_DIR/rc"
    )
}

run_case ok ok
w="$TMP/ok/.uncle/workflow"; doc="$TMP/ok/.uncle/docs/CHANGE_PLAN.md"
check "success: returns 0"                       test "$(cat "$w/rc")" == 0
check "success: both edits are in the plan"      bash -c 'grep -q "| B-1 | click | appended | X1 |" "$1" && grep -q "| B-2 | key | same | X2 |" "$1"' _ "$doc"
check "success: untouched section is intact"     grep -q '^Kept\.$' "$doc"
check "success: every finding has a row"         bash -c 'for n in 1 2 3 4 5 6; do grep -q "AR-$n" "$1" || exit 1; done' _ "$doc"
check "success: writers got the model, not the plan text" bash -c 'grep -q "## Plan model (JSON)" "$1" && ! grep -q "Base project plan JSON" "$1" && grep -q "updated-plan-edit-ops-packet" "$1"' _ "$w/updated-change-plan-edits/prompts/1.md"

run_case failonce failonce
w="$TMP/failonce/.uncle/workflow"
check "failed writer: asked again, returns 0"    test "$(cat "$w/rc")" == 0
check "failed writer: one writer per finding"    bash -c 'for s in 2-1 2-2 2-3; do grep -q "edits-$s " "$1" || exit 1; done' _ "$w/calls"

run_case fail fail
check "writer failure: nonzero, nothing published" bash -c 'test "$(cat "$1/.uncle/workflow/rc")" != 0 && test ! -e "$1/.uncle/docs/CHANGE_PLAN.md"' _ "$TMP/fail"

run_case resolve resolve
w="$TMP/resolve/.uncle/workflow"
check "overlap: resolved, returns 0"             test "$(cat "$w/rc")" == 0
check "overlap: one resolver call"               test "$(wc -l < "$w/resolver-calls")" -eq 1
check "overlap: the resolution is published"     grep -q '| B-1 | click | appended | MERGED |' "$TMP/resolve/.uncle/docs/CHANGE_PLAN.md"
check "overlap: resolver is shown the current row" grep -q '"failure": "unchanged"' "$w/updated-change-plan-edits/prompts/resolve-G1.md"

run_case retry resolve-retry
w="$TMP/retry/.uncle/workflow"
check "bad resolver answer: retried once, then merged" bash -c 'test "$(cat "$1/rc")" == 0 && test "$(wc -l < "$1/resolver-calls")" -eq 2' _ "$w"
check "bad resolver answer: the retry names the missing id" grep -q "B-9" "$w/updated-change-plan-edits/prompts/resolve-G1.retry.md"
check "bad resolver answer: the retry is published" grep -q 'MERGED' "$TMP/retry/.uncle/docs/CHANGE_PLAN.md"

run_case clash resolve-fail
check "resolver failure: nonzero, nothing published" bash -c 'test "$(cat "$1/.uncle/workflow/rc")" != 0 && test ! -e "$1/.uncle/docs/CHANGE_PLAN.md"' _ "$TMP/clash"

run_case local ok local
w="$TMP/local/.uncle/workflow"
check "local model: fan-out runs, returns 0"     test "$(cat "$w/rc")" == 0
check "local model: no schema flag, packet path" bash -c '! grep -q "schema=/\|schema=\.uncle" "$1" && grep -q "out=none" "$1" && ! grep -q "packet=none" "$1"' _ "$w/calls"

run_case hosted ok hosted
w="$TMP/hosted/.uncle/workflow"
check "hosted: returns 0"                        test "$(cat "$w/rc")" == 0
check "hosted: no protected paths for a change plan, and every schema lists the ids" python3 - "$w/updated-change-plan-edits/schemas" <<'PY'
import json, sys
one = json.load(open(sys.argv[1] + '/1.json'))['properties']
two = json.load(open(sys.argv[1] + '/2.json'))['properties']
ids = one['ops']['items']['properties']['id']['enum']
sys.exit(0 if 'protected_verification_paths' not in one and 'protected_verification_paths' not in two and 'B-2' in ids and 'patch' not in one else 1)
PY
check "each prompt names one packet kind"        bash -c 'for f in "$1"/*.md; do test "$(grep -o "\"kind\":\"updated-plan-[a-z-]*\"" "$f" | sort -u | wc -l | tr -d " ")" == 1 || exit 1; done' _ "$w/updated-change-plan-edits/prompts"
check "a local grammar picks the ops kind"       python3 -B - "$ROOT" "$w/updated-change-plan-edits/prompts/1.md" "$w/updated-change-plan-edits/prompts/resolve-G1.md" <<'PY'
import sys, importlib.util
sys.path.insert(0, sys.argv[1] + '/scripts/lib')
import self_hosted as S
got = S.reviewer_artifact_kind(open(sys.argv[2]).read())
sys.exit(0 if got == 'updated-plan-edit-ops-packet' else 1)
PY

run_case hostedresolve resolve hosted
check "hosted resolver: schema and answer path"  bash -c 'grep -q "resolve-G1 schema=.*schemas/resolve-G1.json out=.*/resolutions-G1.json" "$1"' _ "$TMP/hostedresolve/.uncle/workflow/calls"
check "ops mode is the default"                  grep -qF 'WORKFLOW_UPDATED_PLAN_OPS:-1' "$ROOT/scripts/change-workflow.sh"

[[ "$fails" == 0 ]] && echo "updated-change-plan-ops-driver-test.sh: all checks passed" || exit 1
