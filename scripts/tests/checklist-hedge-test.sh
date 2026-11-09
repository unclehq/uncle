#!/usr/bin/env bash
set -uo pipefail

# Hedged checklist workers (scripts/lib/checklist-lanes.sh): a single-check worker that is far slower than its siblings gets a twin,
# the first valid packet wins, and the loser is stopped. Hermetic: the workers are fakes whose speed is chosen by label.

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
TMP="$(mktemp -d)"; trap 'rm -rf "$TMP"' EXIT
FAILED=0 COUNT=0
ok() { COUNT=$((COUNT + 1)); }
bad() { COUNT=$((COUNT + 1)); FAILED=$((FAILED + 1)); echo "FAIL: $1"; }
expect() { if eval "$2"; then ok; else bad "$1"; fi; }

LOG_DIR="$TMP/logs"; mkdir -p "$LOG_DIR"
. "$ROOT/scripts/lib/checklist-lanes.sh"

# Worker speed by label (seconds), and what it writes.
worker_speed() {
    case "$1" in
        "${SLOW_LABEL:-none}") echo "${SLOW_SECONDS:-6}" ;;
        "${SLOW_LABEL:-none}h") echo "${TWIN_SECONDS:-1}" ;;
        *) echo 1 ;;
    esac
}
checklist_run_worker() {
    local prompt="$1" label="$2" size="$3" packet="$4" seconds
    seconds="$(worker_speed "$label")"
    echo "$label started"
    sleep "$seconds"
    [[ "${FAIL_LABEL:-none}" != "$label" ]] || exit 1
    case "$label" in *h) printf '{"who":"twin"}' > "$packet" ;; *) printf '{"who":"primary"}' > "$packet" ;; esac
}

run_case() {   # $1 = batches file; sets WALL and leaves the packets in $DIR
    DIR="$TMP/case-$RANDOM"; mkdir -p "$DIR"
    packet_names=(); failed=0
    local t0=$SECONDS
    checklist_run_lanes "$DIR" "$1" "$TMP/template.md" > "$TMP/out.txt" 2>&1
    WALL=$((SECONDS - t0))
}
printf 'worker template\n' > "$TMP/template.md"
printf 'MC-1\nMC-2\nMC-3\nMC-4\n' > "$TMP/four-single"

# 1. A straggler gets a twin and the twin wins.
SLOW_LABEL=group-1-batch-4 SLOW_SECONDS=8 TWIN_SECONDS=1 WORKFLOW_EXECUTE_CHECKLIST_HEDGE_SECONDS=1
export SLOW_LABEL SLOW_SECONDS TWIN_SECONDS WORKFLOW_EXECUTE_CHECKLIST_HEDGE_SECONDS
run_case "$TMP/four-single"
expect "a straggler is replaced by its twin well before it would have finished" '(( WALL < 7 ))'
expect "the twin's packet is the one used" 'grep -q twin "$DIR/group-1-batch-4.json"'
expect "the run says the worker was slow and that the twin won" 'grep -q "is slow" "$TMP/out.txt" && grep -q "twin delivered first" "$TMP/out.txt"'
expect "a hedge is not a failure" '[[ "$failed" == 0 ]]'
expect "the fast workers were not hedged" '! grep -q "group-1-batch-1 is slow\|group-1-batch-2 is slow\|group-1-batch-3 is slow" "$TMP/out.txt"'
sleep 1
expect "the slow primary was stopped (it never overwrote the twin's packet)" 'grep -q twin "$DIR/group-1-batch-4.json"'

# 2. Hedging off: nothing is duplicated and the straggler is waited for.
WORKFLOW_EXECUTE_CHECKLIST_HEDGE_SECONDS=0; export WORKFLOW_EXECUTE_CHECKLIST_HEDGE_SECONDS
SLOW_SECONDS=4; export SLOW_SECONDS
run_case "$TMP/four-single"
expect "with hedging off the straggler is waited for" '(( WALL >= 4 )) && grep -q primary "$DIR/group-1-batch-4.json" && ! grep -q "is slow" "$TMP/out.txt"'

# 3. A lane of several checks is never hedged: its checks share a resource and must not overlap.
WORKFLOW_EXECUTE_CHECKLIST_HEDGE_SECONDS=1; export WORKFLOW_EXECUTE_CHECKLIST_HEDGE_SECONDS
printf 'MC-1\nMC-2\nMC-3\nMC-4 MC-5\n' > "$TMP/multi"
SLOW_SECONDS=5; export SLOW_SECONDS
run_case "$TMP/multi"
expect "a multi-check lane is not hedged however slow it is" '! grep -q "is slow" "$TMP/out.txt" && grep -q primary "$DIR/group-1-batch-4.json" && (( WALL >= 5 ))'

# 4. The primary finishes before the twin: the twin is stopped and the primary's packet stands.
SLOW_SECONDS=4 TWIN_SECONDS=9; export SLOW_SECONDS TWIN_SECONDS
run_case "$TMP/four-single"
expect "when the primary wins the twin is stopped" 'grep -q "is slow" "$TMP/out.txt" && grep -q primary "$DIR/group-1-batch-4.json" && (( WALL < 8 ))'

# 5. A failing worker that was not slow is reported, exactly as before.
SLOW_LABEL=none FAIL_LABEL=group-1-batch-2; export SLOW_LABEL FAIL_LABEL
run_case "$TMP/four-single"
expect "a failed worker is reported and marks the stage failed" '[[ "$failed" == 1 ]] && grep -q "Worker group-1-batch-2 did not complete" "$TMP/out.txt"'
unset FAIL_LABEL

echo "checklist-hedge-test: $COUNT checks, $FAILED failures"
[[ "$FAILED" == 0 ]]
