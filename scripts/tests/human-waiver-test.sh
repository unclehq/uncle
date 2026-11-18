#!/usr/bin/env bash
# An unattended run that ends with BLOCKED-HUMAN checklist rows must record a waiver for each
# one. Without it the final audit finds no waiver and rates the row HIGH, which blocks the release
# for a check no machine can perform. Also checks that stagegate.sh's post-checklist shortcuts
# route BLOCKED-HUMAN through acceptance_human_continue instead of only logging a nonblocking failure.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
COUNT=0
fail() { echo "FAIL: $*"; exit 1; }
ok() { COUNT=$((COUNT + 1)); }

run_case() { # $1 = UNATTENDED value, $2 = WORKFLOW_UNATTENDED_HUMAN_WAIVER value
    (
        export ROOT UNATTENDED="$1" WORKFLOW_UNATTENDED_HUMAN_WAIVER="$2"
        STATE_DIR="$TMP/state-$1-$2"; export STATE_DIR
        mkdir -p "$STATE_DIR"
        . "$ROOT/scripts/lib/waivers.sh"
        . "$ROOT/scripts/lib/acceptance-gate.sh"
        set_state() { echo "$1" > "$STATE_DIR/next"; }
        record_unattended_gate() { echo "$1 $2" >> "$STATE_DIR/gates"; }
        acceptance_json_ids() { [[ "$2" == BLOCKED-HUMAN ]] && printf 'MC-106\nMC-207\n'; return 0; }
        acceptance_human_continue .uncle/docs/VERIFICATION_REPORT.md FINAL_AUDIT > "$STATE_DIR/out" 2>&1
    )
}

# Unattended: every BLOCKED-HUMAN row gets a waiver naming the report, the run moves on, and the gate is ledgered.
run_case 1 1
S="$TMP/state-1-1"
for id in MC-106 MC-207; do
    [[ -s "$S/waivers/$id" ]] || fail "no waiver written for $id"
    grep -q "^id: $id$" "$S/waivers/$id" || fail "waiver for $id does not name it"
    grep -q "^report: .uncle/docs/VERIFICATION_REPORT.md$" "$S/waivers/$id" || fail "waiver for $id does not name the report"
    grep -q "Deferred to the person" "$S/waivers/$id" || fail "waiver for $id has the wrong reason"
    ok
done
[[ "$(cat "$S/next")" == FINAL_AUDIT ]] || fail "state not advanced to FINAL_AUDIT"
grep -q '^waiver ' "$S/gates" || fail "waiver not ledgered as an unattended gate"
ok

# Opting out leaves the rows open; the run still advances.
run_case 1 0
[[ ! -e "$TMP/state-1-0/waivers" ]] || fail "waiver written although WORKFLOW_UNATTENDED_HUMAN_WAIVER=0"
[[ "$(cat "$TMP/state-1-0/next")" == FINAL_AUDIT ]] || fail "opt-out did not advance"
ok

# Attended: nobody waives on a person's behalf.
run_case 0 1
[[ ! -e "$TMP/state-0-1/waivers" ]] || fail "attended run wrote a waiver"
ok

# Routing: both post-checklist shortcuts in stagegate.sh must hand BLOCKED-HUMAN to the waiver step.
SG="$ROOT/scripts/stagegate.sh"
grep -q 'checklist_acceptance" == BLOCKED-HUMAN' "$SG" || fail "stagegate.sh no longer routes BLOCKED-HUMAN checklist results"
python3 - "$SG" <<'PY' || fail "stagegate.sh routing is wrong"
import re, sys
s = open(sys.argv[1]).read()
m = re.search(r'if \[\[ "\$checklist_acceptance" == BLOCKED-HUMAN \]\]; then(.*?)\n\s*fi\n', s, re.S)
assert m and 'acceptance_human_continue .uncle/docs/VERIFICATION_REPORT.md FINAL_AUDIT' in m.group(1), 'postflight path does not call acceptance_human_continue'
assert re.search(r'!= PASS && "\$checklist_acceptance" != UNKNOWN && "\$checklist_acceptance" != BLOCKED-HUMAN', s), 'nonblocking shortcut still swallows BLOCKED-HUMAN'
PY
ok

echo "human-waiver-test.sh: $COUNT checks passed"
