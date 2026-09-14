#!/usr/bin/env bash
set -euo pipefail

# AC-12..AC-14: what the drivers do when a resumed run finds a file that a
# triage action changed. The edits are applied through the real guard so the
# ledger row exists; the drivers are then run exactly as the TUI runs them.
#
#   AC-12  an approved document changed → the driver reopens the gate that
#          approved it (exit 0, mapped WAIT_* state); approvals/ is untouched
#          until the operator answers; a decline keeps the old digest, an
#          accept records the new one.
#   AC-13  a protected verification path changed → verification-integrity
#          routes to REPAIR and exits 1, as it does for any other edit.
#   AC-14  an edit outside both sets → the driver re-enters the same stage;
#          the state token is what it was, and no triage branch skips it.

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
. "$ROOT/scripts/lib/sha256.sh"
GUARD="$ROOT/scripts/lib/triage_guard.py"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
# No stage may reach a real runner from a test: every stage command is a stub that fails.
export UNCLE_CONFIG=/dev/null WORKFLOW_AGENT_CMD=/usr/bin/false WORKFLOW_REVIEWER_CMD=/usr/bin/false WORKFLOW_CODEX_CMD=/usr/bin/false WORKFLOW_SPECULATE=0
unset UNCLE_STATUS_STAGE UNCLE_DRIVER_SUPERVISED UNCLE_PROJECT_ROOT 2>/dev/null || true

FAILED=0
COUNT=0
fail() { echo "FAIL: $1"; FAILED=$((FAILED + 1)); }
check_eq() {
    local name="$1" expected="$2" actual="$3"
    COUNT=$((COUNT + 1))
    [[ "$actual" == "$expected" ]] || fail "$name — expected '$expected', got '$actual'"
}
check_contains() {
    local name="$1" needle="$2" file="$3"
    COUNT=$((COUNT + 1))
    grep -qF -- "$needle" "$file" || fail "$name — expected to find: $needle"
}
check_absent() {
    local name="$1" file="$2"
    COUNT=$((COUNT + 1))
    [[ ! -e "$file" ]] || fail "$name — $file exists"
}

# project <name> -- a git checkout with approved documents and their digests.
project() {
    local dir="$TMP/$1"
    rm -rf "$dir"
    mkdir -p "$dir/.uncle/workflow/approvals" "$dir/tests"
    printf 'assert actual == expected\n' > "$dir/tests/test.txt"
    for doc in CHANGE_REQUEST BASELINE_REPORT CHANGE_SPEC CHANGE_PLAN ADVERSARIAL_REVIEW \
               REQUIREMENTS REQUIREMENTS_INTERPRETATION PROJECT_PLAN UPDATED_PROJECT_PLAN; do
        printf '# %s\n\napproved text\n' "$doc" > "$dir/$doc.md"
        hash_file "$dir/$doc.md" > "$dir/.uncle/workflow/approvals/$doc.sha256"
        printf 'tester\n' > "$dir/.uncle/workflow/approvals/$doc.approved-by"
    done
    git -C "$dir" init -q .
    printf '.uncle/workflow/\n' > "$dir/.gitignore"
    git -C "$dir" add -A
    git -C "$dir" -c user.email=t@t -c user.name=t commit --no-gpg-sign -qm init
    printf '%s' "$dir"
}

# triage_edit <project> <path> <text> -- an accepted /do edit, through the guard.
triage_edit() {
    local dir="$1" path="$2" text="$3" digest
    digest="$(cd "$dir" && python3 "$GUARD" begin --state-dir .uncle/workflow --project "$dir" --root "$TMP/install" --turn 1 --mode execute \
        | python3 -c 'import json,sys; print(json.load(sys.stdin)["digest"])')"
    mkdir -p "$(dirname "$dir/.uncle/workflow/triage/sandbox/$path")"
    printf '%s\n' "$text" > "$dir/.uncle/workflow/triage/sandbox/$path"
    (cd "$dir" && python3 "$GUARD" end --state-dir .uncle/workflow --project "$dir" --root "$TMP/install" --turn 1 --mode execute --digest "$digest" --proposal "Proposal 1: edit $path" > /dev/null)
    COUNT=$((COUNT + 1))
    grep -q "	APPLIED	$path	" "$dir/.uncle/workflow/triage-actions.tsv" || fail "APPLIED row for $path"
}

# drive <driver> <project> <input> -- run the driver, record status and output.
drive() {
    local driver="$1" dir="$2" input="$3"
    STATUS=0
    (cd "$dir" && printf '%s' "$input" | UNCLE_PROJECT_ROOT="$dir" bash "$ROOT/scripts/$driver" > "$dir/out.txt" 2>&1) || STATUS=$?
}

mkdir -p "$TMP/install"
printf 'x\n' > "$TMP/install/marker"

# --- AC-12: change-workflow.sh ------------------------------------------------

P="$(project cw-plan)"
printf 'UPDATED_PLAN\n' > "$P/.uncle/workflow/state"
old="$(cat "$P/.uncle/workflow/approvals/CHANGE_PLAN.sha256")"
triage_edit "$P" CHANGE_PLAN.md '# CHANGE_PLAN edited by triage'
drive change-workflow.sh "$P" ''
check_eq "cw: plan drift exits 0" 0 "$STATUS"
check_contains "cw: says changed after approval" "CHANGE_PLAN.md changed after approval." "$P/out.txt"
check_contains "cw: names the reopened gate" "Reopening WAIT_PLAN_APPROVAL" "$P/out.txt"
check_eq "cw: state is the plan gate" WAIT_PLAN_APPROVAL "$(cat "$P/.uncle/workflow/state")"
check_eq "cw: digest untouched by the driver" "$old" "$(cat "$P/.uncle/workflow/approvals/CHANGE_PLAN.sha256")"
check_absent "cw: exit 0 writes no bundle" "$P/.uncle/workflow/TRIAGE.md"
# Declining keeps the stale digest; accepting records the new bytes.
drive change-workflow.sh "$P" $'n\nn\n'
check_eq "cw: decline exits 0" 0 "$STATUS"
check_eq "cw: decline leaves the digest" "$old" "$(cat "$P/.uncle/workflow/approvals/CHANGE_PLAN.sha256")"
check_eq "cw: decline leaves the state" WAIT_PLAN_APPROVAL "$(cat "$P/.uncle/workflow/state")"
drive change-workflow.sh "$P" $'y\ny\n'
check_eq "cw: accept records the new digest" "$(hash_file "$P/CHANGE_PLAN.md")" "$(cat "$P/.uncle/workflow/approvals/CHANGE_PLAN.sha256")"
check_eq "cw: accept advances to the next stage (stub runner fails there)" UPDATED_PLAN "$(cat "$P/.uncle/workflow/state")"

# The route file sends a plan edited after the second plan gate back there.
P="$(project cw-route)"
printf 'IMPLEMENT\n' > "$P/.uncle/workflow/state"
printf 'WAIT_UPDATED_PLAN_APPROVAL\n' > "$P/.uncle/workflow/approval-route"
triage_edit "$P" CHANGE_PLAN.md '# CHANGE_PLAN edited at IMPLEMENT'
drive change-workflow.sh "$P" ''
check_eq "cw: routed drift exits 0" 0 "$STATUS"
check_eq "cw: routed to the updated-plan gate" WAIT_UPDATED_PLAN_APPROVAL "$(cat "$P/.uncle/workflow/state")"

P="$(project cw-spec)"
printf 'PLAN\n' > "$P/.uncle/workflow/state"
triage_edit "$P" CHANGE_SPEC.md '# CHANGE_SPEC edited by triage'
drive change-workflow.sh "$P" ''
check_eq "cw: spec drift exits 0" 0 "$STATUS"
check_eq "cw: spec drift reopens analysis gate" WAIT_ANALYSIS_APPROVAL "$(cat "$P/.uncle/workflow/state")"

# --- AC-12: stagegate.sh -------------------------------------------------------

P="$(project sg-plan)"
printf 'ADVERSARIAL_REVIEW\n' > "$P/.uncle/workflow/state"
old="$(cat "$P/.uncle/workflow/approvals/PROJECT_PLAN.sha256")"
triage_edit "$P" PROJECT_PLAN.md '# PROJECT_PLAN edited by triage'
drive stagegate.sh "$P" ''
check_eq "sg: plan drift exits 0" 0 "$STATUS"
check_contains "sg: says changed after approval" "PROJECT_PLAN.md changed after approval." "$P/out.txt"
check_eq "sg: state is the plan gate" WAIT_PLAN_APPROVAL "$(cat "$P/.uncle/workflow/state")"
check_eq "sg: digest untouched by the driver" "$old" "$(cat "$P/.uncle/workflow/approvals/PROJECT_PLAN.sha256")"
check_absent "sg: exit 0 writes no bundle" "$P/.uncle/workflow/TRIAGE.md"
drive stagegate.sh "$P" $'n\n'
check_eq "sg: decline exits 0" 0 "$STATUS"
check_eq "sg: decline leaves the digest" "$old" "$(cat "$P/.uncle/workflow/approvals/PROJECT_PLAN.sha256")"
drive stagegate.sh "$P" $'y\n'
check_eq "sg: accept records the new digest" "$(hash_file "$P/PROJECT_PLAN.md")" "$(cat "$P/.uncle/workflow/approvals/PROJECT_PLAN.sha256")"
check_eq "sg: accept advances to the next stage (stub runner fails there)" ADVERSARIAL_REVIEW "$(cat "$P/.uncle/workflow/state")"

P="$(project sg-updated)"
printf 'PREFLIGHT\n' > "$P/.uncle/workflow/state"
triage_edit "$P" UPDATED_PROJECT_PLAN.md '# UPDATED_PROJECT_PLAN edited by triage'
drive stagegate.sh "$P" ''
check_eq "sg: updated plan drift exits 0" 0 "$STATUS"
check_eq "sg: updated plan drift reopens its gate" WAIT_UPDATED_PLAN_APPROVAL "$(cat "$P/.uncle/workflow/state")"

# --- AC-13: a protected verification path ------------------------------------

. "$ROOT/scripts/lib/verification-integrity.sh"
P="$(project sg-protected)"
printf 'TEST_REVIEW\n' > "$P/.uncle/workflow/state"
printf 'tests\n' > "$P/.uncle/workflow/verification.paths"
(cd "$P" && verification_manifest .uncle/workflow/verification.paths > .uncle/workflow/verification.manifest)
triage_edit "$P" tests/test.txt 'assert True  # weakened by triage'
WORKFLOW_DIFF_GATE=0 drive stagegate.sh "$P" ''
check_eq "sg: protected drift exits 1" 1 "$STATUS"
check_contains "sg: integrity path names the change" "Verification inputs changed or are unavailable" "$P/out.txt"
check_eq "sg: routes to REPAIR" REPAIR "$(cat "$P/.uncle/workflow/state")"
check_eq "sg: repair source is the integrity report" ".uncle/workflow/VERIFICATION_INTEGRITY.md" "$(cat "$P/.uncle/workflow/repair-source")"
check_contains "sg: integrity report records the file" "tests/test.txt" "$P/.uncle/workflow/VERIFICATION_INTEGRITY.md"
check_contains "sg: failure writes the bundle" "- state: REPAIR" "$P/.uncle/workflow/TRIAGE.md"

# --- AC-14: an edit outside both sets re-enters the same stage -----------------

P="$(project sg-tolerance)"
printf 'TEST_REVIEW\n' > "$P/.uncle/workflow/state"
printf 'tests\n' > "$P/.uncle/workflow/verification.paths"
(cd "$P" && verification_manifest .uncle/workflow/verification.paths > .uncle/workflow/verification.manifest)
triage_edit "$P" .uncle/defect-tolerance 'tolerance 99'
WORKFLOW_DIFF_GATE=0 drive stagegate.sh "$P" ''
check_eq "sg: tolerance edit re-enters TEST_REVIEW" TEST_REVIEW "$(cat "$P/.uncle/workflow/state")"
check_contains "sg: the test-review stage is what runs" "test-review" "$P/out.txt"
COUNT=$((COUNT + 1))
[[ "$STATUS" -ne 0 ]] || fail "sg: no reviewer configured, so the stage cannot have passed"
# No triage branch touches the state machine: every 'triage' line in the
# drivers is the lib source, the exit hook, the gate reopen, a stop reason,
# or the COMPLETE ledger print.
for driver in stagegate.sh change-workflow.sh; do
    COUNT=$((COUNT + 1))
    if grep -n 'triage' "$ROOT/scripts/$driver" \
        | grep -vE 'lib/triage\.sh|triage_on_exit|triage_reopen_gate|triage_stop_reason|triage_print_actions|^[0-9]+:#|^[0-9]+: *# ' \
        | grep -q .; then
        fail "$driver: an unexpected triage branch exists"
        grep -n 'triage' "$ROOT/scripts/$driver" | grep -vE 'lib/triage\.sh|triage_on_exit|triage_reopen_gate|triage_stop_reason|triage_print_actions|^[0-9]+:#|^[0-9]+: *# '
    fi
done

if [[ "$FAILED" -ne 0 ]]; then
    echo "triage-resume-test.sh: $FAILED of $COUNT checks failed"
    exit 1
fi
echo "triage-resume-test.sh: $COUNT checks passed"
