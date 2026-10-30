#!/usr/bin/env bash
# reconcile_scaffold_mismatches / route_unrunnable_application's use of it:
# a scaffold file that is only mechanically wrong (a stale test-discovery
# glob, a CommonJS require() in an ES module) must be fixed deterministically,
# recorded as an attributed deviation, and re-baselined -- without ever
# spending the repair budget on a file REPAIR usually cannot even touch.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
temp="$(mktemp -d)"
trap 'rm -rf "$temp"' EXIT
PASS=0; FAIL=0
ok()  { PASS=$((PASS + 1)); }
bad() { FAIL=$((FAIL + 1)); echo "FAIL [$1] $2" >&2; }
check() { if [[ "$2" == "$3" ]]; then ok; else bad "$1" "expected [$2] got [$3]"; fi; }

sed -n '/^# A failed assertion can be useful delivery evidence/,/^promote_winner_work() {/p' "$ROOT/scripts/stagegate.sh" \
    | sed '$d' > "$temp/fns.sh"
grep -q '^reconcile_scaffold_mismatches() {' "$temp/fns.sh" || { echo 'FATAL: could not extract reconcile_scaffold_mismatches'; exit 2; }
grep -q '^route_unrunnable_application() {' "$temp/fns.sh" || { echo 'FATAL: could not extract route_unrunnable_application'; exit 2; }

STATE_DIR="$temp/project/.uncle/workflow"
LOG_DIR="$STATE_DIR/logs"
GREEN_MD="$temp/project/green-check.md"
GREEN_CLASS="$temp/project/green-check.tsv"
mkdir -p "$STATE_DIR/documents" "$LOG_DIR" "$temp/project/.uncle/docs" "$temp/project/tests"
cd "$temp/project"

captured=0; green_calls=0
capture_verification_inputs() { captured=$((captured + 1)); : > "$STATE_DIR/verification.manifest"; }
run_green_check_auto() { green_calls=$((green_calls + 1)); :; }
green_wait_final() { :; }
set_state() { printf '%s\n' "$1" > "$STATE_DIR/next"; }
# shellcheck disable=SC1090
source "$temp/fns.sh"

# --- scenario 1: a real, fixable scaffold mismatch -------------------------
cat > vitest.config.js <<'EOF'
export default { test: { include: ['tests/unit/**/*.test.{js,jsx}'] } };
EOF
echo "test('x', () => {})" > tests/engine.test.js
printf 'Error: No test files found\n' > "$LOG_DIR/green-check.log"

reconcile_scaffold_mismatches
check "a fixable mismatch is reconciled" "0" "$?"
check "the scaffold file was actually fixed" "yes" "$(grep -q 'tests/\*.test.js' vitest.config.js && echo yes || echo no)"
check "a deviation was recorded" "yes" "$(grep -q 'Driver scaffold reconciliation' .uncle/docs/IMPLEMENTATION_NOTES.md 2>/dev/null && echo yes || echo no)"
check "the deviation names the file" "yes" "$(grep -q 'vitest.config.js' .uncle/docs/IMPLEMENTATION_NOTES.md 2>/dev/null && echo yes || echo no)"
check "inputs were re-baselined" "1" "$captured"
check "verification was re-run" "1" "$green_calls"
[[ -e "$STATE_DIR/scaffold-reconcile-attempted" ]] || bad "marker-written" "one-shot marker not recorded"

reconcile_scaffold_mismatches || status=$?
check "a second call is a one-shot no-op" "1" "${status:-0}"
check "it does not re-capture inputs again" "1" "$captured"

# --- scenario 2: route_unrunnable_application uses it and skips REPAIR -----
printf 'Error: No test files found\n' > "$LOG_DIR/green-check.log"
rm -f "$STATE_DIR/scaffold-reconcile-attempted"
cat > vitest.config.js <<'EOF'
export default { test: { include: ['tests/unit/**/*.test.{js,jsx}'] } };
EOF
green_application_not_runnable_calls=0
green_check_log_fixed=0
# Simulate the real effect of green_wait_final: once reconciliation runs,
# the next verification pass would actually find the now-discoverable test
# and publish a clean log. green_application_not_runnable reads that file
# directly, so make the stubbed run_green_check_auto produce it.
run_green_check_auto() { green_calls=$((green_calls + 1)); printf 'ok\n' > "$LOG_DIR/green-check.log"; }
UNATTENDED=1
route_unrunnable_application
status=$?
check "route_unrunnable_application proceeds once reconciliation resolves it" "0" "$status"
check "no repair was scheduled" "" "$(cat "$STATE_DIR/repair-source" 2>/dev/null || true)"
check "state was never set to REPAIR" "" "$(cat "$STATE_DIR/next" 2>/dev/null || true)"

# --- scenario 3: nothing to reconcile falls through to REPAIR, unchanged ---
rm -f "$STATE_DIR/scaffold-reconcile-attempted" "$STATE_DIR/repair-source" "$STATE_DIR/next"
rm -f vitest.config.js
printf 'src/App.jsx (2:23): "reduce" is not exported by "src/calc.js"\n' > "$LOG_DIR/green-check.log"
touch "$STATE_DIR/parallel-implementation-complete"
status=0
route_unrunnable_application || status=$?
check "an unfixable-by-reconciliation failure still routes to REPAIR" "2" "$status"
check "...with the existing sentinel source" "$STATE_DIR/runtime-unrunnable-application" "$(cat "$STATE_DIR/repair-source" 2>/dev/null)"

echo
if [[ "$FAIL" -gt 0 ]]; then
    echo "scaffold-reconcile-driver-test.sh: $FAIL of $((PASS + FAIL)) checks failed"
    exit 1
fi
echo "scaffold-reconcile-driver-test.sh: $PASS checks passed"
