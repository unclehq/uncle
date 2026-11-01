#!/usr/bin/env bash
# Once the checklists have run, a repair that cannot proceed goes to the final audit; it must not send the run back through
# MANUAL_CHECKLIST. Without the checklist-ran marker, REPAIR -> MANUAL_CHECKLIST -> VALIDATE_CHECKLIST -> REPAIR cycled with no agent
# call and no limit (thousands of state transitions in one gates case under a slow machine).
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
temp="$(mktemp -d)"
trap 'rm -rf "$temp"' EXIT
PASS=0; FAIL=0
check() { if [[ "$2" == "$3" ]]; then PASS=$((PASS + 1)); else FAIL=$((FAIL + 1)); echo "FAIL [$1] expected [$2] got [$3]" >&2; fi; }

sed -n '/^test_review_next_stage() {/,/^}/p' "$ROOT/scripts/stagegate.sh" > "$temp/fn.sh"
grep -q '^test_review_next_stage() {' "$temp/fn.sh" || { echo 'FATAL: could not extract test_review_next_stage'; exit 2; }
STATE_DIR="$temp/state"; mkdir -p "$STATE_DIR"
repair_exhausted() { return "${EXHAUSTED:-1}"; }
green_application_not_runnable() { return "${UNRUNNABLE:-1}"; }
. "$temp/fn.sh"

EXHAUSTED=1 UNRUNNABLE=1; rm -f "$STATE_DIR/checklist-ran"
check "no marker, repair left: the checklists still run" MANUAL_CHECKLIST "$(test_review_next_stage)"
EXHAUSTED=0 UNRUNNABLE=0
check "no marker, repair spent and app unrunnable: the audit" FINAL_AUDIT "$(test_review_next_stage)"
EXHAUSTED=1 UNRUNNABLE=1; : > "$STATE_DIR/checklist-ran"
check "marker present: the audit, never the checklists again" FINAL_AUDIT "$(test_review_next_stage)"
check "the disabled-repair branch honours the marker" 1 "$(grep -c 'if \[\[ -e "\$STATE_DIR/checklist-ran" \]\]; then set_state FINAL_AUDIT; else set_state MANUAL_CHECKLIST; fi' "$ROOT/scripts/stagegate.sh")"
check "VALIDATE_CHECKLIST records the marker" 1 "$(grep -c ': > "\$STATE_DIR/checklist-ran"' "$ROOT/scripts/stagegate.sh")"

if [[ "$FAIL" -ne 0 ]]; then echo "stagegate-checklist-ran-routes-to-audit-test.sh: $FAIL failed"; exit 1; fi
echo "stagegate-checklist-ran-routes-to-audit-test.sh: $PASS checks passed"
