#!/usr/bin/env bash
# run_updated_change_plan_edit_writers (the change workflow): writers run at the same time, their patches are merged and published,
# and any failure returns nonzero with nothing published so the single synthesis call can run.
set -uo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
TMP="$(mktemp -d)"; trap 'rm -rf "$TMP"' EXIT
fails=0
export WORKFLOW_UPDATED_PLAN_OPS=0 WORKFLOW_UPDATED_PLAN_EDITS=1 WORKFLOW_UPDATED_PLAN_EDIT_SLICE=3 WORKFLOW_UPDATED_PLAN_HEDGE_SECONDS=300
check() { local what="$1"; shift; if "$@"; then :; else echo "FAIL: $what"; fails=$((fails + 1)); fi; }
awk '/^(updated_change_plan_launch_writer|run_updated_change_plan_edit_writers)\(\) \{/,/^}/' "$ROOT/scripts/change-workflow.sh" > "$TMP/fn.sh"
check "function extracted" test -s "$TMP/fn.sh"

run_case() {   # name mode [hosted|local]
    local name="$1" mode="$2" runner="${3:-hosted}" dir="$TMP/$1"
    mkdir -p "$dir/.uncle/workflow/documents" "$dir/.uncle/workflow/logs" "$dir/.uncle/docs"
    ROOT_DIR="$ROOT" python3 -B - "$dir" <<'PY'
import json, sys
d = sys.argv[1] + '/.uncle/workflow/documents/'
plan = {'schema': 'uncle.artifact/v1', 'kind': 'change-plan', 'narrative': '# Project plan\n\n## 1. Overview\nAlpha.\nBeta.\n\n## 2. Tests\nT-1.\n'}
json.dump(plan, open(d + 'CHANGE_PLAN.json', 'w'))
json.dump({'schema': 'uncle.artifact/v1', 'kind': 'adversarial-review',
           'findings': [{'id': 'AR-%d' % n} for n in range(1, 7)]}, open(d + 'ADVERSARIAL_REVIEW.json', 'w'))
PY
    printf 'SEALED\n\n```json\n{"schema":"uncle.artifact/v1","kind":"change-plan","dispositions":[],"patch":{}}\n```\n' > "$dir/prompt.md"
    (
        cd "$dir"
        ROOT="$ROOT"; STATE_DIR=".uncle/workflow"; LOG_DIR=".uncle/workflow/logs"; UPDATED_PLAN_PROMPT="$dir/prompt.md"
        MODEL_UPDATED_PLAN=m; EFFORT_UPDATED_PLAN=low; BUDGET_UPDATED_PLAN=
        UPDATED_PLAN_ADVISOR_PIDS=()      # a top-level array in the driver; the extracted functions read it
        stage_uses_self_hosted() { [[ "$runner" == local ]]; }
        stage_supports_structured_output() { [[ "$runner" == hosted ]]; }
        run_claude() {   # prompt stage
            local n="${2#updated-change-plan-worker-edits-}"; [[ "$2" != updated-change-plan-worker-resolve-* ]] || n=resolve
            printf '%s %s\n' "$n" "$(python3 -c 'import time; print("%.2f" % time.time())')" >> "$STATE_DIR/starts"
            grep -q 'You own exactly these findings' "$1" || echo "no slice note: $n" >> "$STATE_DIR/violations"
            echo "$2 schema=${UNCLE_OUTPUT_SCHEMA_FILE:-none} out=${UNCLE_STRUCTURED_OUTPUT_PATH:-none} packet=${UNCLE_WORKER_PACKET_PATH:-none} kinds=$(grep -o '"kind":"[a-z-]*"' "$1" | sort -u | tr '\n' ' ')" >> "$STATE_DIR/calls"
            if [[ "$mode:$n" == slow:2 ]]; then sleep 30; fi
            sleep 1
            if [[ "$mode:$n" == limit:2 ]]; then echo "cause: You've hit your session limit" > "$LOG_DIR/updated-change-plan-worker-edits-2.log"; return 1; fi
            [[ "$mode:$n" != fail:2 && "$mode:$n" != fail:2-* && "$mode:$n" != failonce:2 ]] || return 1
            if [[ "$2" == updated-change-plan-worker-resolve-* ]]; then
                echo resolver >> "$STATE_DIR/resolver-calls"
                [[ "$mode" == resolve || "$mode" == resolve-retry ]] || return 1
                local old_text="Alpha."
                if [[ "$mode" == resolve-retry && "$2" != *-retry ]]; then old_text="Alpha. (misquoted)"; fi
                printf '{"resolutions":[{"group":"G1","patch":{"replace_text":[{"heading":"## 1. Overview","old":"%s","new":"MERGED."}]}}]}' "$old_text" > "$UNCLE_WORKER_PACKET_PATH"
                return 0
            fi
            python3 -B - "$n" "$mode" "$UNCLE_WORKER_PACKET_PATH" "$1" <<'PY'
import json, re, sys
n, mode, target, prompt = sys.argv[1:5]
ids = re.search(r'You own exactly these findings: ([^.]*)\.', open(prompt).read()).group(1).split(', ')
old = 'Alpha.' if n == '1' else ('Alpha.' if mode in ('clash', 'resolve', 'resolve-fail', 'resolve-retry') else 'Beta.')
body = {'dispositions': [{'finding': i, 'disposition': 'Accepted', 'reason': 'r', 'plan_change': 'c'} for i in ids],
        'patch': {'replace_text': [{'heading': '## 1. Overview', 'old': old, 'new': 'X%s.' % re.sub(r'[^0-9].*', '', n)}]}}
json.dump(body, open(target, 'w'))
PY
        }
        . "$TMP/fn.sh"
        run_updated_change_plan_edit_writers > "$STATE_DIR/out" 2>&1; echo $? > "$STATE_DIR/rc"
    )
}

run_case ok ok
w="$TMP/ok/.uncle/workflow"
check "success: returns 0"                    test "$(cat "$w/rc")" == 0
check "success: plan published"               grep -q 'X1\.' "$TMP/ok/.uncle/docs/CHANGE_PLAN.md"
check "success: both edits are in the plan"   grep -q 'X2\.' "$TMP/ok/.uncle/docs/CHANGE_PLAN.md"
check "success: every finding has a row"      bash -c 'for n in 1 2 3 4 5 6; do grep -q "AR-$n" "$1" || exit 1; done' _ "$TMP/ok/.uncle/docs/CHANGE_PLAN.md"
check "success: each writer got its slice"    test ! -e "$w/violations"
check "success: writers overlapped"           python3 - "$w/starts" <<'PY'
import sys
t = sorted(float(l.split()[1]) for l in open(sys.argv[1]))
sys.exit(0 if len(t) == 2 and t[1] - t[0] < 0.9 else 1)
PY

run_case failonce failonce
w="$TMP/failonce/.uncle/workflow"
check "failed writer: asked again, returns 0"   test "$(cat "$w/rc")" == 0
check "failed writer: one writer per finding"   bash -c 'for s in 2-1 2-2 2-3; do grep -q "edits-$s " "$1" || exit 1; done' _ "$w/calls"
check "failed writer: its siblings did not rerun" test "$(grep -c "edits-1 " "$w/calls")" == 1
check "failed writer: every finding still has a row" bash -c 'for n in 1 2 3 4 5 6; do grep -q "AR-$n" "$1" || exit 1; done' _ "$TMP/failonce/.uncle/docs/CHANGE_PLAN.md"
check "failed writer: said what it was doing"   grep -q 'asking again, one finding at a time' "$w/out"

WORKFLOW_UPDATED_PLAN_HEDGE_SECONDS=1 run_case slow slow
w="$TMP/slow/.uncle/workflow"
check "slow writer: a twin finishes the stage"  test "$(cat "$w/rc")" == 0
check "slow writer: the twin was started"       grep -q 'is slow; starting a twin' "$w/out"
check "slow writer: its twin's answer is used"  grep -q 'twin delivered first' "$w/out"
check "slow writer: the plan has every finding" bash -c 'for n in 1 2 3 4 5 6; do grep -q "AR-$n" "$1" || exit 1; done' _ "$TMP/slow/.uncle/docs/CHANGE_PLAN.md"
check "slow writer: did not wait for it"        python3 - "$w/starts" <<'PY'
import sys
t = [float(l.split()[1]) for l in open(sys.argv[1])]
sys.exit(0 if max(t) - min(t) < 20 else 1)
PY

run_case limit limit
w="$TMP/limit/.uncle/workflow"
check "account limit: stops without retrying"  bash -c 'test "$(cat "$1/rc")" != 0 && ! grep -q "asking again" "$1/out" && grep -q "account limit" "$1/out"' _ "$w"
check "account limit: no extra writers ran"    test "$(wc -l < "$w/starts" | tr -d ' ')" == 2

run_case fail fail
check "writer failure: nonzero"               test "$(cat "$TMP/fail/.uncle/workflow/rc")" != 0
check "writer failure: nothing published"     test ! -e "$TMP/fail/.uncle/docs/CHANGE_PLAN.md"

run_case resolve resolve
w="$TMP/resolve/.uncle/workflow"
check "overlap: resolved, returns 0"          test "$(cat "$w/rc")" == 0
check "overlap: one resolver call"            test "$(wc -l < "$w/resolver-calls")" -eq 1
check "overlap: the resolution is published"  grep -q 'MERGED\.' "$TMP/resolve/.uncle/docs/CHANGE_PLAN.md"
check "overlap: the other edit still merged"  bash -c '! grep -q "Alpha\." "$1"' _ "$TMP/resolve/.uncle/docs/CHANGE_PLAN.md"
check "overlap: resolver sent only the group" bash -c 'grep -q "Group G1" "$1" && ! grep -q "Group G2" "$1"' _ "$w/updated-change-plan-edits/prompts/resolve-G1.md"

run_case retry resolve-retry
w="$TMP/retry/.uncle/workflow"
check "bad resolver answer: retried once, then merged" test "$(cat "$w/rc")" == 0
check "bad resolver answer: the group ran twice"       test "$(wc -l < "$w/resolver-calls")" -eq 2
check "bad resolver answer: the retry is published"    grep -q 'MERGED\.' "$TMP/retry/.uncle/docs/CHANGE_PLAN.md"
check "bad resolver answer: retry prompt carries the reason" grep -q 'previous answer was rejected' "$w/updated-change-plan-edits/prompts/resolve-G1.retry.md"

run_case clash resolve-fail
check "resolver failure: nonzero"             test "$(cat "$TMP/clash/.uncle/workflow/rc")" != 0
check "resolver failure: nothing published"   test ! -e "$TMP/clash/.uncle/docs/CHANGE_PLAN.md"

run_case local ok local
w="$TMP/local/.uncle/workflow"
check "local model: fan-out runs, returns 0"   test "$(cat "$w/rc")" == 0
check "local model: packet path, no schema flag" bash -c '! grep -q "schema=/\|schema=\\.uncle" "$1" && grep -q "out=none" "$1" && ! grep -q "packet=none" "$1"' _ "$w/calls"
check "local model: plan published"            test -s "$TMP/local/.uncle/docs/CHANGE_PLAN.md"

run_case hosted ok hosted
w="$TMP/hosted/.uncle/workflow"
check "hosted: returns 0"                      test "$(cat "$w/rc")" == 0
check "hosted: every writer had its schema"    bash -c 'test "$(grep -c "edits-[0-9] schema=.*schemas/[0-9].json out=.*/[0-9].json" "$1")" == 2' _ "$w/calls"
check "each prompt names one packet kind"      bash -c 'for f in "$1"/*.md; do test "$(grep -o "\"kind\":\"[a-z-]*\"" "$f" | sort -u | wc -l | tr -d " ")" == 1 || exit 1; done' _ "$w/updated-change-plan-edits/prompts"

run_case hostedresolve resolve hosted
w="$TMP/hostedresolve/.uncle/workflow"
check "hosted resolver: schema and answer path" bash -c 'grep -q "resolve-G1 schema=.*schemas/resolve-G1.json out=.*/resolutions-G1.json" "$1"' _ "$w/calls"

block="$(awk '/^        UPDATED_PLAN\)$/,/^        VALIDATE_UPDATED_PLAN\)$/' "$ROOT/scripts/change-workflow.sh")"
check "a failed fan-out runs the single call"  grep -qF 'run_updated_change_plan_edit_writers; then' <<< "$block"
check "on by default"                          grep -qF 'WORKFLOW_UPDATED_PLAN_EDITS:-1' "$ROOT/scripts/change-workflow.sh"

[[ "$fails" == 0 ]] && echo "updated-change-plan-edits-driver-test.sh: all checks passed" || exit 1
