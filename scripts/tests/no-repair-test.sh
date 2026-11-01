#!/usr/bin/env bash
# A new application build does not repair (WORKFLOW_REPAIR, default 0): a failure goes to the unresolved-evidence
# ledger and the run continues to the final audit, nothing is marked PASS, and no route enters the REPAIR state.
# WORKFLOW_REPAIR=1 restores the bounded repair stage.
set -uo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
SCRIPT="${NO_REPAIR_TEST_SCRIPT:-$ROOT/scripts/stagegate.sh}"   # an override lets a mutated copy be tested without touching the real file
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
fails=0
check() { local what="$1"; shift; if "$@"; then :; else echo "FAIL: $what"; fails=$((fails + 1)); fi; }

# --- the switch and what it forces ---------------------------------------------------------------------------
config="$(awk '/^WORKFLOW_REPAIR="\$\{WORKFLOW_REPAIR:-0\}"/{p=1} p{print} p&&/^fi$/{exit}' "$SCRIPT")"
check "the WORKFLOW_REPAIR switch exists" test -n "$config"
settings() {   # env assignments... -> "AUTO ATTEMPTS"
    env -i bash --norc --noprofile -c "$(printf '%s\n' "$@" "UNATTENDED=1" "WORKFLOW_AUTO_REPAIR=\${WORKFLOW_AUTO_REPAIR:-1}" \
        'if [[ -z "${WORKFLOW_AUTO_REPAIR_ATTEMPTS:-}" ]]; then WORKFLOW_AUTO_REPAIR_ATTEMPTS=2; fi' "$config" \
        'echo "$WORKFLOW_AUTO_REPAIR $WORKFLOW_AUTO_REPAIR_ATTEMPTS"')"
}
check "default: auto repair is off and no attempts remain" test "$(settings)" == "0 0"
check "default: an explicit attempt count cannot bring it back" test "$(settings 'WORKFLOW_AUTO_REPAIR_ATTEMPTS=3' 'WORKFLOW_AUTO_REPAIR=1')" == "0 0"
check "WORKFLOW_REPAIR=1 leaves the repair settings alone" test "$(settings 'WORKFLOW_REPAIR=1')" == "1 2"

# --- the unrunnable-application route, run for real -----------------------------------------------------------
route() {   # env assignments... -> "rc state-list ledger-lines"
    local out
    out="$(env -i bash --norc --noprofile -c "$(printf '%s\n' "$@")
        STATE_DIR='$TMP/state'; mkdir -p \"\$STATE_DIR\"; : > \"\$STATE_DIR/states\"; : > \"\$STATE_DIR/ledger\"; rm -f \"\$STATE_DIR/runtime-unrunnable-recorded\"
        $(awk '/^route_unrunnable_application\(\) \{/{p=1} p{print} p&&/^}/{exit}' "$SCRIPT")
        green_application_not_runnable() { return 0; }
        reconcile_scaffold_mismatches() { return 1; }
        record_nonblocking_failure() { printf '%s\\n' \"\$1\" >> \"\$STATE_DIR/ledger\"; }
        record_test_failure_disposition() { :; }
        set_state() { printf '%s\\n' \"\$1\" >> \"\$STATE_DIR/states\"; }
        LOG_DIR=\"\$STATE_DIR\"
        rc=0; route_unrunnable_application > /dev/null 2>&1 || rc=\$?
        echo \"\$rc \$(tr '\\n' ',' < \"\$STATE_DIR/states\") \$(tr '\\n' ',' < \"\$STATE_DIR/ledger\")\"")"
    printf '%s' "$out"
}
check "repair off: the unrunnable app goes to the audit, not to REPAIR" test "$(route 'WORKFLOW_REPAIR=0' 'UNATTENDED=1')" == "2 FINAL_AUDIT, green-check,"
check "repair off: the same in an attended run" test "$(route 'WORKFLOW_REPAIR=0' 'UNATTENDED=0')" == "2 FINAL_AUDIT, green-check,"
check "repair on: an unattended run still schedules its one repair" test "$(route 'WORKFLOW_REPAIR=1' 'UNATTENDED=1')" == "2 REPAIR, "
check "repair on: an attended run still stops for a person" test "$(route 'WORKFLOW_REPAIR=1' 'UNATTENDED=0')" == "1  "

# --- the FINAL_AUDIT self-loop: one caller sits inside FINAL_AUDIT and treats a return of 2 as "go round again". With the
# "not runnable" condition still true on the next pass (the stale log, as in the incident), setting FINAL_AUDIT from
# FINAL_AUDIT must not loop: the failure is recorded once per run, then the audit is allowed to run.
cat > "$TMP/loop-harness.sh" <<HARNESS
$(awk '/^route_unrunnable_application\(\) \{/{p=1} p{print} p&&/^}/{exit}' "$SCRIPT")
green_application_not_runnable() { return 0; }      # permanently true: the log is stale and never changes the verdict
reconcile_scaffold_mismatches() { return 1; }
record_nonblocking_failure() { printf '%s\\n' "\$1" >> "\$STATE_DIR/ledger"; }
record_test_failure_disposition() { :; }
set_state() { printf '%s\\n' "\$1" >> "\$STATE_DIR/states"; }
LOG_DIR="\$STATE_DIR"
driver_pass() {    # the shape of the FINAL_AUDIT call site: iterations until it stops asking to go round again, capped at 10
    local n=0 rc
    while [[ \$n -lt 10 ]]; do
        n=\$((n + 1)); rc=0
        route_unrunnable_application > /dev/null 2>&1 || rc=\$?
        [[ "\$rc" == 2 ]] || break
    done
    echo "\$n \$rc"
}
HARNESS
final_audit_loop() {   # run-id [env assignments...] -> "iterations rc ledger-lines" for one pass; the state dir persists across calls
    local run="$1"; shift
    env -i bash --norc --noprofile -c "$(printf '%s\n' "$@")
        STATE_DIR='$TMP/loop-state'; mkdir -p \"\$STATE_DIR\"; : >> \"\$STATE_DIR/ledger\"
        [[ '$run' == none ]] || echo '$run' > \"\$STATE_DIR/run-started-at\"
        . '$TMP/loop-harness.sh'
        result=\"\$(driver_pass)\"
        echo \"\$result \$(wc -l < \"\$STATE_DIR/ledger\" | tr -d ' ')\""
}
rm -rf "$TMP/loop-state"
check "repair off: FINAL_AUDIT stops asking to go round again (2 passes, returns 0), recording once" test "$(final_audit_loop run-1 'WORKFLOW_REPAIR=0' 'UNATTENDED=1')" == "2 0 1"
check "repair off: a second pass in the same run adds nothing and does not loop" test "$(final_audit_loop run-1 'WORKFLOW_REPAIR=0' 'UNATTENDED=1')" == "1 0 1"
check "repair off: a new run records its own failure once, then also stops" test "$(final_audit_loop run-2 'WORKFLOW_REPAIR=0' 'UNATTENDED=1')" == "2 0 2"
rm -rf "$TMP/loop-state"
check "repair off: with no run stamp it still terminates and records once" test "$(final_audit_loop none 'WORKFLOW_REPAIR=0' 'UNATTENDED=1')" == "2 0 1"
rm -rf "$TMP/loop-state"
check "repair on: the original one-repair-then-stop behaviour is unchanged (no endless loop either)" test "$(final_audit_loop run-1 'WORKFLOW_REPAIR=1' 'UNATTENDED=1' | cut -d' ' -f1)" -le 3

# --- REPAIR is reachable only through a guard ------------------------------------------------------------------
python3 - "$SCRIPT" <<'PY'
import re, sys
lines = open(sys.argv[1]).read().splitlines()
problems = []
for number, line in enumerate(lines, 1):
    if line.strip() != 'set_state REPAIR':
        continue
    window = '\n'.join(lines[max(0, number - 75):number - 1])
    # verification_integrity_failure stops the run (exit 1) and the REPAIR handler routes it on resume.
    if 'verification_integrity_failure()' in window and 'exit 1' in '\n'.join(lines[number:number + 4]):
        continue
    if not re.search(r'green_failure_route|WORKFLOW_REPAIR', window):
        problems.append(number)
sys.exit(1 if problems else 0)
PY
check "every set_state REPAIR is behind a guard" test $? == 0
check "the REPAIR handler carries a disabled-repair route" grep -q "Repair is disabled for new application builds; \$(basename" "$SCRIPT"
check "a checklist FAIL goes to the audit when repair is off" grep -q "checklist acceptance recorded a FAIL; repair is disabled" "$SCRIPT"

[[ "$fails" == 0 ]] && echo "no-repair-test.sh: all checks passed" || { echo "no-repair-test.sh: $fails failure(s)"; exit 1; }
