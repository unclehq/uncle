#!/usr/bin/env bash
# uncle consolidation phase (d): MODULE_INTERFACES is now a real, distinct
# state both drivers transition through once, between plan approval and
# IMPLEMENT -- not a side-effect buried inside the implementation functions.
# This proves: (a) the state machine actually visits MODULE_INTERFACES for
# both families, between plan approval and IMPLEMENT; (b) a failed derivation
# never blocks the transition to IMPLEMENT (fail-open, as derive_module_interfaces
# itself has always documented); (c) the state handler is one shared function,
# not two independent copies.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
PASS=0; FAIL=0
ok()  { PASS=$((PASS + 1)); }
bad() { FAIL=$((FAIL + 1)); echo "FAIL [$1] $2" >&2; }

# --- (c) one shared handler, not two copies ---------------------------------

grep -q '^module_interfaces_stage() {' "$ROOT/scripts/lib/module-interfaces-stage.sh" \
    && ok || bad "shared-handler-exists" "module_interfaces_stage is not defined in the shared lib"

for driver in stagegate.sh change-workflow.sh; do
    grep -Fq '. "$ROOT/scripts/lib/module-interfaces-stage.sh"' "$ROOT/scripts/$driver" \
        && ok || bad "sources-shared-lib-$driver" "$driver does not source module-interfaces-stage.sh"
    n="$(grep -c '^        MODULE_INTERFACES)$' "$ROOT/scripts/$driver" || true)"
    [[ "$n" == 1 ]] || bad "one-case-label-$driver" "$driver has $n MODULE_INTERFACES) case labels, expected exactly 1"
    [[ "$n" != 1 ]] || ok
    block="$(sed -n '/^        MODULE_INTERFACES)$/,/^        IMPLEMENT)$/p' "$ROOT/scripts/$driver" | sed '1d;$d')"
    [[ -n "$block" ]] || { echo "FATAL: could not extract the MODULE_INTERFACES case body from $driver"; exit 2; }
    if grep -q 'module_interfaces_stage ' <<<"$block"; then ok
    else bad "calls-shared-handler-$driver" "$driver's MODULE_INTERFACES case does not call the shared module_interfaces_stage function"; fi
    # Each driver's own case body must not reimplement derive/set_state itself
    # -- the whole point is that the logic lives once, in the shared function.
    if grep -q 'derive_module_interfaces\|set_state IMPLEMENT' <<<"$block"; then
        bad "no-reimplementation-$driver" "$driver's MODULE_INTERFACES case reimplements logic that belongs only in the shared function"
    else
        ok
    fi
done

# --- (a) the state machine actually transitions through MODULE_INTERFACES --

# stagegate.sh: both of PREFLIGHT's fresh-from-plan-approval exits (the
# backgrounded-probe path and the blocking-probe path) must route through
# MODULE_INTERFACES, not straight to IMPLEMENT. stagegate.sh has two
# PREFLIGHT) case labels (the dispatcher and the main loop); anchor on the
# one immediately before MODULE_INTERFACES.
mi_line="$(grep -n '^        MODULE_INTERFACES)$' "$ROOT/scripts/stagegate.sh" | head -1 | cut -d: -f1)"
preflight_line="$(grep -n '^        PREFLIGHT)$' "$ROOT/scripts/stagegate.sh" | awk -F: -v m="$mi_line" '$1 < m { line = $1 } END { print line }')"
preflight_block="$(sed -n "${preflight_line},${mi_line}p" "$ROOT/scripts/stagegate.sh")"
set_implement_count="$(grep -c 'set_state IMPLEMENT' <<<"$preflight_block" || true)"
[[ "$set_implement_count" == 0 ]] || bad "stagegate-preflight-skips-mi" "stagegate.sh's PREFLIGHT state still transitions directly to IMPLEMENT ($set_implement_count call site(s)) instead of through MODULE_INTERFACES"
[[ "$set_implement_count" != 0 ]] || ok
set_mi_count="$(grep -c 'set_state MODULE_INTERFACES' <<<"$preflight_block" || true)"
[[ "$set_mi_count" -ge 2 ]] && ok || bad "stagegate-preflight-routes-mi" "stagegate.sh's PREFLIGHT state has $set_mi_count set_state MODULE_INTERFACES call site(s), expected at least 2 (background and blocking paths)"

# change-workflow.sh: WAIT_UPDATED_PLAN_APPROVAL must route through
# MODULE_INTERFACES, not straight to IMPLEMENT.
wupa_line="$(grep -n '^        WAIT_UPDATED_PLAN_APPROVAL)$' "$ROOT/scripts/change-workflow.sh" | head -1 | cut -d: -f1)"
mi_line_cw="$(grep -n '^        MODULE_INTERFACES)$' "$ROOT/scripts/change-workflow.sh" | head -1 | cut -d: -f1)"
wupa_block="$(sed -n "${wupa_line},${mi_line_cw}p" "$ROOT/scripts/change-workflow.sh")"
if grep -q 'set_state IMPLEMENT' <<<"$wupa_block"; then
    bad "change-workflow-wupa-skips-mi" "change-workflow.sh's WAIT_UPDATED_PLAN_APPROVAL still transitions directly to IMPLEMENT instead of through MODULE_INTERFACES"
else
    ok
fi
if grep -q 'set_state MODULE_INTERFACES' <<<"$wupa_block"; then ok
else bad "change-workflow-wupa-routes-mi" "change-workflow.sh's WAIT_UPDATED_PLAN_APPROVAL does not route to MODULE_INTERFACES"; fi

bash -n "$ROOT/scripts/stagegate.sh" && ok || bad "syntax-stagegate" "stagegate.sh fails bash -n"
bash -n "$ROOT/scripts/change-workflow.sh" && ok || bad "syntax-change-workflow" "change-workflow.sh fails bash -n"
bash -n "$ROOT/scripts/lib/module-interfaces-stage.sh" && ok || bad "syntax-shared" "module-interfaces-stage.sh fails bash -n"

# --- (b) a failed derivation never blocks the transition to IMPLEMENT ------
# Functional, not just structural: actually call module_interfaces_stage with
# a deliberately failing derive_module_interfaces and confirm it still
# transitions to IMPLEMENT (not an error exit, not stuck in MODULE_INTERFACES).

temp="$(mktemp -d)"
trap 'rm -rf "$temp"' EXIT
functional_status=0
(
    cd "$temp"
    STATE_DIR="$temp/state"
    mkdir -p "$STATE_DIR/documents"
    state_file="$STATE_DIR/current-state"
    set_state() { printf '%s' "$1" > "$state_file"; }
    derive_module_interfaces() { return 1; }  # simulates every failure mode: disabled, crashed agent, malformed output
    # shellcheck disable=SC1090
    . "$ROOT/scripts/lib/module-interfaces-stage.sh"
    set -e
    module_interfaces_stage .uncle/docs/UPDATED_PROJECT_PLAN.md
    [[ "$(cat "$state_file")" == IMPLEMENT ]] || { echo 'FAIL: a failed derivation did not transition to IMPLEMENT' >&2; exit 1; }
) || functional_status=$?
if [[ "$functional_status" == 0 ]]; then ok
else bad "fails-open-functional" "module_interfaces_stage did not fail open when derive_module_interfaces failed (exit $functional_status)"; fi

# And the success path: a passing derivation also transitions to IMPLEMENT
# (fail-open must not be the only path that reaches it).
success_status=0
(
    cd "$temp"
    STATE_DIR="$temp/state2"
    mkdir -p "$STATE_DIR/documents"
    state_file="$STATE_DIR/current-state"
    set_state() { printf '%s' "$1" > "$state_file"; }
    derive_module_interfaces() { return 0; }
    # shellcheck disable=SC1090
    . "$ROOT/scripts/lib/module-interfaces-stage.sh"
    set -e
    module_interfaces_stage .uncle/docs/UPDATED_PROJECT_PLAN.md
    [[ "$(cat "$state_file")" == IMPLEMENT ]] || { echo 'FAIL: a successful derivation did not transition to IMPLEMENT' >&2; exit 1; }
) || success_status=$?
[[ "$success_status" == 0 ]] && ok || bad "success-path-functional" "module_interfaces_stage did not transition to IMPLEMENT on a successful derivation (exit $success_status)"

echo
if [[ "$FAIL" -gt 0 ]]; then
    echo "module-interfaces-stage-test.sh: $FAIL of $((PASS + FAIL)) checks failed"
    exit 1
fi
echo "module-interfaces-stage-test.sh: $PASS checks passed"
