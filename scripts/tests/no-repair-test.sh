#!/usr/bin/env bash
# A new application build does not repair (WORKFLOW_REPAIR, default 0): a failure goes to the unresolved-evidence
# ledger and the run continues to the final audit, nothing is marked PASS, and no route enters the REPAIR state.
# WORKFLOW_REPAIR=1 restores the bounded repair stage.
set -uo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
SCRIPT="$ROOT/scripts/stagegate.sh"
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
        STATE_DIR='$TMP/state'; mkdir -p \"\$STATE_DIR\"; : > \"\$STATE_DIR/states\"; : > \"\$STATE_DIR/ledger\"
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
