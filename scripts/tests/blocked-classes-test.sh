#!/usr/bin/env bash
# What the driver does with each kind of blocked check.
#
# One word for three situations made them one dead stop, and the worst of the
# three -- a required check no environment can perform -- made a run
# unfinishable with no way to say so. These are the four outcomes that
# distinction has to produce.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
. "$ROOT/scripts/lib/acceptance.sh"

work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT
cd "$work"
STATE_DIR="$work/workflow"
mkdir -p "$STATE_DIR"

# The two driver functions under test, lifted with their dependencies. Keeping
# them here rather than sourcing stagegate.sh avoids running a whole workflow
# to exercise a state transition.
STATE=""
set_state() { STATE="$1"; }
gate_prompt() { printf '%s' "$1"; }
eval "$(awk '/^waive_file\(\)/,/^}$/' "$ROOT/scripts/stagegate.sh")"
eval "$(awk '/^waived_ids\(\)/,/^}$/' "$ROOT/scripts/stagegate.sh")"
eval "$(awk '/^record_waiver\(\)/,/^}$/' "$ROOT/scripts/stagegate.sh")"
eval "$(awk '/^acceptance_transition\(\)/,/^}$/' "$ROOT/scripts/stagegate.sh")"

# The transition both sets state and, on some paths, exits the shell. Run it in
# a subshell so its exit cannot end this test, and have that subshell hand back
# the state it reached -- an unwritten state file is a path that exited before
# setting one, which is exactly what a refusal looks like.
run_transition() {
    : > out.txt
    : > state.txt
    local rc=0
    ( acceptance_transition "$1" "$2" > out.txt 2>&1
      printf '%s' "$STATE" > state.txt ) || rc=$?
    OUT="$(cat out.txt)"
    STATE="$(cat state.txt)"
    return "$rc"
}
report() {
    printf '## Acceptance gate\n\n| ID | Required | Status | Evidence |\n|---|---|---|---|\n%s\n' "$1" > report.md
}
fail() { echo "FAIL: $1" >&2; exit 1; }

# --- a defect goes to repair, as before -------------------------------------
report '| C1 | YES | FAIL | assertion fired |'
STATE=""
run_transition report.md NEXT < /dev/null
[ "$STATE" = "REPAIR" ] || fail "a FAIL must go to repair, went to '$STATE'"
[ "$(cat "$STATE_DIR/repair-source")" = "report.md" ] || fail "repair source not recorded"

# --- setup pauses and names the actions -------------------------------------
report $'| C1 | YES | PASS | ok |\n| C2 | YES | BLOCKED-SETUP | safaridriver not enabled |'
STATE=""
run_transition report.md NEXT < /dev/null && fail "setup must not advance"
[ -z "$STATE" ] || fail "setup must not change state, set '$STATE'"
grep -q "C2" <<< "$OUT" || fail "setup must name the blocking check"
grep -q "doable in this environment" <<< "$OUT" || fail "setup must say it is doable"

# --- a signature is not a fault: the run goes on to its audit ---------------
report $'| C1 | YES | PASS | ok |\n| C2 | YES | BLOCKED-HUMAN | awaiting Brian |'
STATE=""
run_transition report.md FINAL_AUDIT < /dev/null || fail "human sign-off must not stop the run"
[ "$STATE" = "FINAL_AUDIT" ] || fail "human sign-off must continue to the audit, went to '$STATE'"
grep -q "C2" <<< "$OUT" || fail "it must say what awaits signing"
grep -q "cannot complete" <<< "$OUT" || fail "it must say the run still cannot complete"

# --- impossible: declining the waiver stops the run -------------------------
report $'| C1 | YES | PASS | ok |\n| C2 | YES | BLOCKED-IMPOSSIBLE | no window under 500px |'
STATE=""
run_transition report.md NEXT < /dev/null && fail "an unwaived impossible check must stop the run"
[ -z "$STATE" ] || fail "declining a waiver must not change state, set '$STATE'"
grep -q "amend" <<< "$OUT" || fail "it must point at amending the plan"
[ ! -e "$STATE_DIR/waivers/C2" ] || fail "declining must not record a waiver"

# An empty reason is a decline, not a blank waiver.
STATE=""
run_transition report.md NEXT <<< '' && fail "an empty reason must not waive"
[ ! -e "$STATE_DIR/waivers/C2" ] || fail "an empty reason must not record a waiver"

# --- impossible: a typed reason records a waiver and continues --------------
STATE=""
run_transition report.md NEXT <<< 'Chrome cannot size a window below 500px; requirement covers 320 via emulation only' \
    || fail "a recorded waiver must let the run continue"
[ "$STATE" = "NEXT" ] || fail "a waiver must advance, went to '$STATE'"
[ -s "$STATE_DIR/waivers/C2" ] || fail "the waiver must be written"
grep -q "^id: C2" "$STATE_DIR/waivers/C2" || fail "the waiver must name the check"
grep -q "^reason: Chrome cannot size" "$STATE_DIR/waivers/C2" || fail "the waiver must keep the reason"
grep -q "^report: report.md" "$STATE_DIR/waivers/C2" || fail "the waiver must name the report"

# It is remembered: the same report does not ask again.
STATE=""
run_transition report.md NEXT < /dev/null || fail "an existing waiver must be honored"
[ "$STATE" = "NEXT" ] || fail "an existing waiver must advance, went to '$STATE'"
grep -q "waived" <<< "$OUT" || fail "it must say the check was waived"

# A waiver covers the id it was written for and no other.
report $'| C1 | YES | PASS | ok |\n| C3 | YES | BLOCKED-IMPOSSIBLE | different check |'
STATE=""
run_transition report.md NEXT < /dev/null && fail "a waiver must not cover another check"
[ -z "$STATE" ] || fail "an unwaived check must not advance on another's waiver"

# --- a waiver never turns into a pass ---------------------------------------
# The report still says the check was not performed; the waiver only records
# that a human accepted that. Anything else would launder an unrun check.
report $'| C1 | YES | PASS | ok |\n| C2 | YES | BLOCKED-IMPOSSIBLE | no window under 500px |'
[ "$(acceptance_result report.md)" = "BLOCKED-IMPOSSIBLE" ] \
    || fail "the verdict must stay BLOCKED-IMPOSSIBLE even with a waiver on disk"

echo 'blocked-classes-test.sh: repair, setup pause, human continue, and waiver record/honor/scope passed'
