#!/usr/bin/env bash
# Merge-conflict stop reason: statuses 0, 4 and 1 through the dispatch stagegate.sh calls (AC-6).
set -u
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
fail=0
check() { # name expected actual
    if [[ "$2" == "$3" ]]; then echo "PASS $1"; else echo "FAIL $1: expected [$2] got [$3]"; fail=1; fi
}

grep -q 'workflow_merge_dispatch 4' "$ROOT/scripts/stagegate.sh" || { echo "FAIL stagegate.sh does not dispatch merge status 4"; fail=1; }

run_case() { # name status stderr-content
    local name="$1" status="$2" content="$3"
    export STATE_DIR="$TMP/$name"; mkdir -p "$STATE_DIR"
    printf '%s' "$content" > "$TMP/$name.err"
    rc=0
    out="$(ROOT="$ROOT" bash -c '. "$ROOT/scripts/lib/model-jobs.sh"; workflow_merge_dispatch "$1" "$2"' _ "$status" "$TMP/$name.err" 2>&1)" || rc=$?
    reason=""; [[ ! -f "$STATE_DIR/stop-reason" ]] || reason="$(cat "$STATE_DIR/stop-reason")"
    flag=no; [[ ! -e "$STATE_DIR/updated-plan-writers-exhausted" ]] || flag=yes
}

run_case ok 0 ''
check "status 0 rc" 0 "$rc"; check "status 0 reason" "" "$reason"; check "status 0 flag" no "$flag"

run_case one 1 'boom'
check "status 1 rc" 1 "$rc"; check "status 1 reason" "" "$reason"

run_case conflict 4 $'updated-plan ops: edits  clash\n  on   s2\n'
check "status 4 rc" 4 "$rc"
check "status 4 reason" "updated-plan: merge conflict: edits clash on s2" "$reason"
check "status 4 flag" yes "$flag"
[[ "$out" == *"edits clash on s2"* ]] && echo "PASS status 4 output" || { echo "FAIL status 4 output: $out"; fail=1; }

run_case empty 4 $'  \n '
check "empty reason" "updated-plan: merge conflict: unspecified" "$reason"
check "empty flag" yes "$flag"

long="$(printf 'x%.0s' $(seq 1 700))"
run_case long 4 "updated-plan ops: $long"
check "long reason" "updated-plan: merge conflict: ${long:0:500}" "$reason"

exit "$fail"
