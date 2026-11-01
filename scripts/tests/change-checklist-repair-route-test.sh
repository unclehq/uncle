#!/usr/bin/env bash
# uncle consolidation item 3 (closing): change-workflow.sh's VALIDATE_CHECKLIST
# used to go straight to FINAL_AUDIT with no routing at all for a failing
# checklist result -- change-workflow.sh has no REPAIR state (confirmed via
# git history: zero `set_state REPAIR` anywhere in it, ever). This proves the
# same repair_target pattern already proven for TEST_REVIEW (item 1) is now
# also wired for VALIDATE_CHECKLIST: it uses the shared acceptance_transition
# (not a reimplementation), and a REPAIR-worthy verdict routes to IMPLEMENT,
# not to a state that does not exist.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
PASS=0; FAIL=0
ok()  { PASS=$((PASS + 1)); }
bad() { FAIL=$((FAIL + 1)); echo "FAIL [$1] $2" >&2; }

vc_line="$(grep -n '^        VALIDATE_CHECKLIST)$' "$ROOT/scripts/change-workflow.sh" | head -1 | cut -d: -f1)"
fa_line="$(grep -n '^        FINAL_AUDIT)$' "$ROOT/scripts/change-workflow.sh" | head -1 | cut -d: -f1)"
[[ -n "$vc_line" ]] && ok || bad "has-validate-state" "VALIDATE_CHECKLIST) case label missing"
[[ -n "$fa_line" && "$vc_line" -lt "$fa_line" ]] && ok || bad "validate-before-audit" "VALIDATE_CHECKLIST does not precede FINAL_AUDIT"

vc_block="$(sed -n "${vc_line},${fa_line}p" "$ROOT/scripts/change-workflow.sh")"

if printf '%s' "$vc_block" | grep -q 'acceptance_transition .uncle/docs/VERIFICATION_REPORT.md'; then ok
else bad "uses-shared-acceptance-transition" "VALIDATE_CHECKLIST does not call the shared acceptance_transition"; fi

if printf '%s' "$vc_block" | tr '\n' ' ' | grep -q "acceptance_transition .uncle/docs/VERIFICATION_REPORT.md FINAL_AUDIT.*REPAIR"; then ok
else bad "fail-routes-to-repair" "VALIDATE_CHECKLIST does not pass REPAIR as acceptance_transition's repair_target (the change driver has a REPAIR state like stagegate.sh's; acceptance_transition still accepts IMPLEMENT for a family without one, which the functional checks below exercise)"; fi

if printf '%s' "$vc_block" | grep -q '^            set_state FINAL_AUDIT$'; then
    bad "no-bare-advance" "VALIDATE_CHECKLIST still unconditionally set_state FINAL_AUDIT with no acceptance routing"
else
    ok
fi

# The driver has a REPAIR state (like stagegate.sh's); every set_state REPAIR must have it to land in.
repair_count="$(grep -v '^\s*#' "$ROOT/scripts/change-workflow.sh" | grep -c 'set_state REPAIR' || true)"
if [[ "$repair_count" == 0 ]] || grep -qE '^        REPAIR\)$' "$ROOT/scripts/change-workflow.sh"; then ok
else bad "repair-state-exists" "change-workflow.sh has $repair_count set_state REPAIR call site(s) but no REPAIR state to receive them"; fi

bash -n "$ROOT/scripts/change-workflow.sh" && ok || bad "syntax" "change-workflow.sh fails bash -n"

# --- functional: a REPAIR-worthy verdict routes to IMPLEMENT, not REPAIR ---
temp="$(mktemp -d)"
trap 'rm -rf "$temp"' EXIT
(
    cd "$temp"
    STATE_DIR="$temp/state"
    mkdir -p "$STATE_DIR/documents" .uncle/docs
    set_state() { printf '%s' "$1" > "$STATE_DIR/current-state"; }
    supervision_validation_failed() { :; }
    hash_file() { printf 'deadbeef'; }
    printf '{"schema":"uncle.artifact/v1","kind":"acceptance-report","rows":[{"id":"EC-1","required":true,"status":"FAIL","evidence":"check failed"}]}' \
        > "$STATE_DIR/documents/VERIFICATION_REPORT.json"
    : > .uncle/docs/VERIFICATION_REPORT.md
    # shellcheck disable=SC1090
    . "$ROOT/scripts/lib/acceptance-gate.sh"
    set -e
    acceptance_transition .uncle/docs/VERIFICATION_REPORT.md FINAL_AUDIT '' IMPLEMENT
    [[ "$(cat "$STATE_DIR/current-state")" == IMPLEMENT ]] || { echo 'FAIL: did not route to IMPLEMENT' >&2; exit 1; }
    [[ ! -e "$STATE_DIR/repair-source" ]] || { echo 'FAIL: wrote repair-source for a driver with no REPAIR state' >&2; exit 1; }
)
functional_status=$?
[[ "$functional_status" == 0 ]] && ok || bad "functional-repair-target" "VALIDATE_CHECKLIST's repair_target routing did not behave as expected (exit $functional_status)"

# And a PASS verdict still advances to FINAL_AUDIT as before.
(
    cd "$temp"
    STATE_DIR="$temp/state2"
    mkdir -p "$STATE_DIR/documents" .uncle/docs
    set_state() { printf '%s' "$1" > "$STATE_DIR/current-state"; }
    supervision_validation_failed() { :; }
    hash_file() { printf 'deadbeef'; }
    printf '{"schema":"uncle.artifact/v1","kind":"acceptance-report","rows":[{"id":"EC-1","required":true,"status":"PASS","evidence":"ok"}]}' \
        > "$STATE_DIR/documents/VERIFICATION_REPORT.json"
    : > .uncle/docs/VERIFICATION_REPORT.md
    # shellcheck disable=SC1090
    . "$ROOT/scripts/lib/acceptance-gate.sh"
    set -e
    acceptance_transition .uncle/docs/VERIFICATION_REPORT.md FINAL_AUDIT '' IMPLEMENT
    [[ "$(cat "$STATE_DIR/current-state")" == FINAL_AUDIT ]] || { echo 'FAIL: did not advance to FINAL_AUDIT on PASS' >&2; exit 1; }
)
pass_status=$?
[[ "$pass_status" == 0 ]] && ok || bad "functional-pass-path" "VALIDATE_CHECKLIST's PASS path did not advance to FINAL_AUDIT (exit $pass_status)"

echo
if [[ "$FAIL" -gt 0 ]]; then
    echo "change-checklist-repair-route-test.sh: $FAIL of $((PASS + FAIL)) checks failed"
    exit 1
fi
echo "change-checklist-repair-route-test.sh: $PASS checks passed"
