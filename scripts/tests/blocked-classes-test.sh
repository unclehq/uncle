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
eval "$(awk '/^write_waivers\(\)/,/^}$/' "$ROOT/scripts/stagegate.sh")"
ROOT="$ROOT"   # record_waiver looks for the popup helper under it
eval "$(awk '/^acceptance_setup_pause\(\)/,/^}$/' "$ROOT/scripts/stagegate.sh")"
eval "$(awk '/^acceptance_human_continue\(\)/,/^}$/' "$ROOT/scripts/stagegate.sh")"
eval "$(awk '/^acceptance_after_waiver\(\)/,/^}$/' "$ROOT/scripts/stagegate.sh")"
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

# --- a waiver settles one check, not the report -----------------------------
# The worst class wins the verdict, so an impossible check outranks a setup
# one. Waiving it must not carry the setup checks along: those could still
# pass, and skipping them would lose real verification to a formality.
rm -rf "$STATE_DIR/waivers"
report $'| C1 | YES | PASS | ok |\n| C2 | YES | BLOCKED-IMPOSSIBLE | no window under 500px |\n| C3 | YES | BLOCKED-SETUP | tree not committed |'
STATE=""
run_transition report.md NEXT <<< 'accepted: the platform cannot do it' \
    && fail "outstanding setup must still pause after a waiver"
[ -z "$STATE" ] || fail "a waiver must not advance past outstanding setup, went to '$STATE'"
[ -s "$STATE_DIR/waivers/C2" ] || fail "the waiver should still be recorded"
grep -q "C3" <<< "$OUT" || fail "it must name the setup check that remains"

# With the setup done, the same waiver lets it reach the audit -- and the
# signature that remains is announced rather than treated as a failure.
report $'| C1 | YES | PASS | ok |\n| C2 | YES | BLOCKED-IMPOSSIBLE | no window under 500px |\n| C3 | YES | BLOCKED-HUMAN | awaiting Brian |'
STATE=""
run_transition report.md FINAL_AUDIT < /dev/null || fail "a waived impossible check plus a signature must continue"
[ "$STATE" = "FINAL_AUDIT" ] || fail "it must reach the audit, went to '$STATE'"
grep -q "C3" <<< "$OUT" || fail "it must name who it waits on"

# And with nothing else outstanding, it simply advances.
report $'| C1 | YES | PASS | ok |\n| C2 | YES | BLOCKED-IMPOSSIBLE | no window under 500px |'
STATE=""
run_transition report.md NEXT < /dev/null || fail "a waived impossible check alone must advance"
[ "$STATE" = "NEXT" ] || fail "it must advance, went to '$STATE'"

# --- a waiver never turns into a pass ---------------------------------------
# The report still says the check was not performed; the waiver only records
# that a human accepted that. Anything else would launder an unrun check.
report $'| C1 | YES | PASS | ok |\n| C2 | YES | BLOCKED-IMPOSSIBLE | no window under 500px |'
[ "$(acceptance_result report.md)" = "BLOCKED-IMPOSSIBLE" ] \
    || fail "the verdict must stay BLOCKED-IMPOSSIBLE even with a waiver on disk"

# --- preflight lets a pending signature through, and nothing else -----------
# Implementation does not consume a signature. A run that stopped before
# implementing because a reviewer had not signed yet stopped for something the
# next stage was never going to read -- and because the IMPLEMENT state
# re-checks the same report, letting it through in one place and not the other
# is a loop between the two rather than a gate.
eval "$(awk '/^preflight_acceptable\(\)/,/^}$/' "$ROOT/scripts/stagegate.sh")"
preflight_acceptable PASS          || fail "a passing preflight must implement"
preflight_acceptable BLOCKED-HUMAN || fail "a pending signature must not stop implementation"
preflight_acceptable BLOCKED-SETUP && fail "missing setup must stop implementation"
preflight_acceptable BLOCKED-IMPOSSIBLE && fail "an impossible prerequisite must stop implementation"
preflight_acceptable REPAIR        && fail "a failed prerequisite must stop implementation"
preflight_acceptable UNKNOWN       && fail "an unreadable report must stop implementation"

# --- a blocker settled at the gate does not send the run back --------------
# PREFLIGHT_REPORT.md is the agent's document and is never edited, so a
# prerequisite handed over at the gate leaves the report still saying
# BLOCKED-SETUP. Asking the report alone would re-run a whole agent stage to
# rediscover a file the operator just typed a path to, which is minutes and
# tokens spent to learn nothing. preflight_settled reads the gate's records
# alongside the report.
eval "$(awk '/^preflight_settled\(\)/,/^}$/' "$ROOT/scripts/stagegate.sh")"
settle_work="$(mktemp -d)"
trap 'rm -rf "$settle_work"' EXIT
cd "$settle_work"
STATE_DIR="$settle_work/.uncle/workflow"
mkdir -p "$STATE_DIR"
cat > PREFLIGHT_REPORT.md <<'MD'
## Acceptance gate

| ID | Required | Status | Evidence |
|---|---|---|---|
| P-1 | YES | PASS | python3 found |
| P-2 | YES | BLOCKED-SETUP | tests/fixtures/oracle.json absent |
| P-3 | YES | BLOCKED-SETUP | SOURCE_REVIEW_APPROVAL.md absent |
MD

preflight_settled PASS          || fail "a passing preflight must implement"
preflight_settled BLOCKED-HUMAN || fail "a pending signature must not stop implementation"
preflight_settled REPAIR        && fail "a failed prerequisite must stop implementation"
preflight_settled UNKNOWN       && fail "an unreadable report must stop implementation"
preflight_settled BLOCKED-SETUP && fail "unsettled setup blockers must stop implementation"

# One of two settled is still not settled: a partial answer must not advance.
mkdir -p "$STATE_DIR/provided"
printf 'id: P-2\n' > "$STATE_DIR/provided/P-2"
preflight_settled BLOCKED-SETUP && fail "one outstanding blocker must still stop implementation"

# Provided and waived both count, and they are the only two things that do.
mkdir -p "$STATE_DIR/waivers"
printf 'id: P-3\n' > "$STATE_DIR/waivers/P-3"
preflight_settled BLOCKED-SETUP || fail "provided and waived blockers must let the run continue"

# A record for some unrelated id settles nothing.
rm -f "$STATE_DIR/provided/P-2"
printf 'id: P-9\n' > "$STATE_DIR/provided/P-9"
preflight_settled BLOCKED-SETUP && fail "a record for another id must not settle P-2"
cd "$ROOT"

# The two gates that ask the question must ask it the same way.
grep -q 'preflight_settled "$(acceptance_result PREFLIGHT_REPORT.md)"' \
    "$ROOT/scripts/stagegate.sh" \
    || fail "the IMPLEMENT re-check must use the same predicate as the PREFLIGHT gate"

# And the gate must not answer a provided prerequisite by re-running the stage.
grep -q 're-running preflight to probe them' "$ROOT/scripts/stagegate.sh" \
    && fail "providing a prerequisite must not re-run the preflight agent"

# --- the audit is told where the waivers are ---------------------------------
# A waiver the auditor never reads is a waiver that buys nothing: the run
# advances one stage and then stops on rows the audit cannot account for. The
# path the driver writes and the path the prompt reads have to be the same one.
grep -q '\.uncle/workflow/waivers' "$ROOT/prompts/final-audit.md" \
    || fail "the final-audit prompt must point at the waiver directory"
grep -q 'never verification' "$ROOT/prompts/final-audit.md" \
    || fail "the audit must be told a waiver is not verification"
case "$(waive_file EXAMPLE)" in
    */.uncle/workflow/waivers/EXAMPLE|*/workflow/waivers/EXAMPLE) ;;
    *) fail "waivers are written somewhere the prompt does not name: $(waive_file EXAMPLE)" ;;
esac

# --- the preflight blocker gate: review / provide / skip / decline ---------
# A blocker used to mean "provide it or sign a waiver", and stopping was the
# failure case. The gate now asks, and each answer is a recorded choice.
eval "$(awk '/^record_gate_decision\(\)/,/^}$/' "$ROOT/scripts/stagegate.sh")"
eval "$(awk '/^preflight_blocked_review\(\)/,/^}$/' "$ROOT/scripts/stagegate.sh")"
eval "$(awk '/^preflight_blocked_menu\(\)/,/^}$/' "$ROOT/scripts/stagegate.sh")"
eval "$(awk '/^preflight_blocked_gate\(\)/,/^}$/' "$ROOT/scripts/stagegate.sh")"
eval "$(awk '/^record_provided_inputs\(\)/,/^}$/' "$ROOT/scripts/stagegate.sh")"
. "$ROOT/scripts/lib/human-input.sh"
. "$ROOT/scripts/lib/sha256.sh"

gate_work="$(mktemp -d)"
trap 'rm -rf "$gate_work"' EXIT
cd "$gate_work"
STATE_DIR="$gate_work/.uncle/workflow"
mkdir -p "$STATE_DIR"
cat > PREFLIGHT_REPORT.md <<'MD'
## Acceptance gate

| ID | Required | Status | Evidence |
|---|---|---|---|
| P-1 | YES | PASS | python3 found |
| P-2 | YES | BLOCKED-SETUP | tests/fixtures/oracle.json absent |
MD

run_gate() {
    : > out.txt
    local rc=0
    ( preflight_blocked_gate "$@" > out.txt 2>&1 ) || rc=$?
    OUT="$(cat out.txt)"
    return "$rc"
}

# Review shows the evidence and asks again; decline stops cleanly, recorded.
run_gate PREFLIGHT_REPORT.md BLOCKED-SETUP P-2 <<< $'r\nd' \
    || fail "decline must exit cleanly"
grep -q "oracle.json absent" <<< "$OUT" || fail "review must show the blocker evidence"
grep -q "Declined at the preflight gate" <<< "$OUT" || fail "decline must say what happened"
grep -q "decline" "$STATE_DIR/gate-decisions" || fail "a decline must be recorded"
[ ! -e "$STATE_DIR/waivers/P-2" ] || fail "declining must not record a waiver"
[ ! -e "$STATE_DIR/provided/P-2" ] || fail "declining must not mark anything provided"

# An invalid answer re-asks rather than guessing.
run_gate PREFLIGHT_REPORT.md BLOCKED-SETUP P-2 <<< $'x\nd' \
    || fail "decline after an invalid answer must exit cleanly"
grep -q "answer r, p, s, or d" <<< "$OUT" || fail "an invalid answer must re-ask"

# A closed stdin is pending, not a decline nobody chose.
run_gate PREFLIGHT_REPORT.md BLOCKED-SETUP P-2 < /dev/null \
    && fail "no answer must not pass for a decision"
grep -q "remains pending" <<< "$OUT" || fail "a closed stdin must leave the run pending"

# Skip records one decision covering the outstanding ids -- no per-id popup.
run_gate PREFLIGHT_REPORT.md BLOCKED-SETUP P-2 <<< 's' \
    || fail "skip must let the run continue"
grep -q "Skipped BLOCKED-SETUP" <<< "$OUT" || fail "skip must say what happened"
grep -q "Operator chose skip" "$STATE_DIR/waivers/P-2" || fail "skip must record an honest waiver"
grep -q "skip" "$STATE_DIR/gate-decisions" || fail "a skip must be recorded"
# It settles the blocker for this run without marking it provided, and the
# report row stays blocked: a skip is not a pass.
preflight_settled BLOCKED-SETUP || fail "a skipped blocker must count as settled"
[ ! -e "$STATE_DIR/provided/P-2" ] || fail "a skip is not a provided prerequisite"
[ "$(acceptance_result PREFLIGHT_REPORT.md)" = "BLOCKED-SETUP" ] \
    || fail "a skip must not turn the report row into a pass"

# The same choices cover an impossible prerequisite.
run_gate PREFLIGHT_REPORT.md BLOCKED-IMPOSSIBLE P-2 <<< 's' \
    || fail "skip must cover an impossible prerequisite"
grep -q "Skipped BLOCKED-IMPOSSIBLE" <<< "$OUT" || fail "skip must name the class"

# Provide settles what lands; the statement goes where the blocker named it.
rm -rf "$STATE_DIR/waivers" "$STATE_DIR/gate-decisions" "$STATE_DIR/human-input-attempted"
run_gate PREFLIGHT_REPORT.md BLOCKED-SETUP P-2 <<< $'p\ns\n\ny\napproved by Brian at the gate\n' \
    || fail "providing must settle the blocker"
grep -q "Prerequisites settled at the gate" <<< "$OUT" || fail "it must say the gate settled"
[ -s tests/fixtures/oracle.json ] || fail "the statement must land where the blocker named"
grep -q "^id: P-2" "$STATE_DIR/provided/P-2" || fail "the provided record must name the id"
preflight_settled "$(acceptance_result PREFLIGHT_REPORT.md)" \
    || fail "a provided blocker must count as settled"

# The provide guard: one dialog attempt per blocker set, then the menu says so.
rm -rf "$STATE_DIR/provided" "$STATE_DIR/gate-decisions" "$STATE_DIR/human-input-attempted" tests
run_gate PREFLIGHT_REPORT.md BLOCKED-SETUP P-2 <<< $'p\n\np\nd\n' \
    || fail "decline after the guard must still exit cleanly"
grep -q "did not resolve them" <<< "$OUT" || fail "a second identical provide must hit the guard"
grep -q "Declined at the preflight gate" <<< "$OUT" || fail "decline must remain available"

cd "$ROOT"

echo 'blocked-classes-test.sh: repair, setup pause, human continue, waiver record/honor/scope, and preflight gate review/provide/skip/decline passed'
