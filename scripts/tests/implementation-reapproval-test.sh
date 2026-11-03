#!/usr/bin/env bash
set -euo pipefail

# After the implementation was approved, a later stage re-ran the green check and
# rewrote an approved input.  Unattended, the driver then reopened the gate and
# EXITED, and nothing restarts it: the run sat at WAIT_IMPLEMENT_APPROVAL with
# every stage having worked.  Unattended it now re-approves the current tree in
# place and continues; attended it still stops and asks.

ROOT_REAL="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
FAILED=0; COUNT=0
check() { COUNT=$((COUNT + 1)); [[ "$3" == "$2" ]] || { echo "FAIL: $1 — expected '$2', got '$3'"; FAILED=$((FAILED + 1)); }; }

. "$ROOT_REAL/scripts/tests/workflow_fixture.sh"

# A fake approval_snapshot: `check` says the inputs changed, `record` notes the call.
mkdir -p "$TMP/root/scripts/lib" "$TMP/approvals" "$TMP/state"
cat > "$TMP/root/scripts/lib/approval_snapshot.py" <<'PY'
import sys
if sys.argv[1] == 'check':
    sys.exit(1)
open(sys.argv[2] + '/recorded', 'a').write('record\n')
PY
printf 'sha\n' > "$TMP/approvals/IMPLEMENTATION_REVIEW.sha256"
printf '{}\n' > "$TMP/approvals/IMPLEMENTATION_REVIEW.inputs.json"

run() {  # $1 = UNATTENDED value; prints the trace and the exit status
    (
        workflow_fixture_source "$ROOT_REAL/scripts/lib/implementation-gates.sh" \
            "$ROOT_REAL/scripts/lib/implementation-gates-app.sh"
        ROOT="$TMP/root"; APPROVAL_DIR="$TMP/approvals"; STATE_DIR="$TMP/state"; REVIEW_FILE="$TMP/review.md"
        UNATTENDED="$1"; WORKFLOW_UNTRACKED_BASELINE=""
        require_file() { :; }
        build_implementation_review() { echo built; }
        set_state() { echo "state=$1"; }
        review_and_approve() { echo "approved:$2:$3"; }
        record_unattended_gate() { echo "ledger:$1"; }
        verify_implementation_review
        echo "continued"
    ) 2>&1
    echo "exit=$?"
}

rm -f "$TMP/state/recorded"
out="$(run 1)"
check "unattended: the gate is re-approved" yes "$([[ "$out" == *"approved:IMPLEMENTATION_REVIEW:approve"* ]] && echo yes || echo no)"
check "unattended: the new inputs are recorded" record "$(cat "$TMP/state/recorded")"
check "unattended: the unreviewed approval is in the ledger" yes "$([[ "$out" == *"ledger:IMPLEMENTATION_REVIEW"* ]] && echo yes || echo no)"
check "unattended: the stage carries on" yes "$([[ "$out" == *continued* ]] && echo yes || echo no)"
check "unattended: the driver is not sent back to the approval gate" no "$([[ "$out" == *state=WAIT_IMPLEMENT_APPROVAL* ]] && echo yes || echo no)"
check "unattended: the driver finishes normally, not by exiting at the gate" yes "$([[ "$out" == *continued*exit=0* ]] && echo yes || echo no)"

out="$(run 0)"
check "attended: the gate is reopened" yes "$([[ "$out" == *state=WAIT_IMPLEMENT_APPROVAL* ]] && echo yes || echo no)"
check "attended: it stops for the person" yes "$([[ "$out" == *exit=0* ]] && echo yes || echo no)"
check "attended: nothing is approved on their behalf" no "$([[ "$out" == *approved:* ]] && echo yes || echo no)"
check "attended: it does not carry on" no "$([[ "$out" == *continued* ]] && echo yes || echo no)"

# Both approval formats retain each family's unattended policy. The approval functions are each family's real ones: the change driver
# has no review_and_approve (human_gate is its gate), and a stub for it once hid a re-approval that could never succeed there.
run_policy() {
    (
        workflow_fixture_source "$ROOT_REAL/scripts/lib/implementation-gates.sh" \
            "$ROOT_REAL/scripts/lib/implementation-gates-$1.sh"
        ROOT="$TMP/root"; APPROVAL_DIR="$TMP/approvals"; STATE_DIR="$TMP/state"; REVIEW_FILE="$TMP/review.md"
        UNATTENDED="$2"; WORKFLOW_UNTRACKED_BASELINE=""; GREEN_CLASS="$TMP/green.tsv"
        printf 'review\n' > "$REVIEW_FILE"; : > "$GREEN_CLASS"
        printf 'sha\n' > "$APPROVAL_DIR/IMPLEMENTATION_REVIEW.sha256"
        if [[ "$3" == snapshot ]]; then
            printf '{}\n' > "$APPROVAL_DIR/IMPLEMENTATION_REVIEW.inputs.json"
        else
            rm -f "$APPROVAL_DIR/IMPLEMENTATION_REVIEW.inputs.json"
        fi
        require_file() { :; }
        build_implementation_review() { echo built; }
        hash_file() { printf '%s\n' "$digest"; }
        set_state() { echo "state=$1"; }
        record_unattended_gate() { echo "ledger:$1"; }
        green_regressions() { printf '%s' "${REGRESSIONS:-0}"; }
        approval_artifact_path() { printf '%s\n' "$1"; }
        if [[ "$1" == app ]]; then
            review_and_approve() { echo "approved:$2:$3"; }
        else
            . "$ROOT_REAL/scripts/lib/approval-gates-change.sh"
        fi
        verify_implementation_review
        echo continued
    ) 2>&1
    echo "exit=$?"
}
for family in app change; do
    for mode in snapshot legacy; do
        for unattended in 0 1; do
            digest=different
            rm -f "$TMP/approvals/IMPLEMENTATION_REVIEW.gate-action" "$TMP/state/recorded"
            out="$(run_policy "$family" "$unattended" "$mode")"
            if [[ "$unattended" == 1 ]]; then
                check "$family/$mode: unattended continues" yes "$([[ "$out" == *continued*exit=0* ]] && echo yes || echo no)"
                check "$family/$mode: unattended is in the ledger" yes "$([[ "$out" == *ledger:IMPLEMENTATION_REVIEW* ]] && echo yes || echo no)"
                check "$family/$mode: no gate reopening" no "$([[ "$out" == *state=* ]] && echo yes || echo no)"
                check "$family/$mode: no command was missing" no "$([[ "$out" == *'command not found'* ]] && echo yes || echo no)"
                if [[ "$family" == change ]]; then
                    check "$family/$mode: the gate action is recorded" APPROVE "$(cat "$TMP/approvals/IMPLEMENTATION_REVIEW.gate-action" 2>/dev/null)"
                    check "$family/$mode: it is recorded as delegated, not as a person's approval" unattended "$(cat "$TMP/approvals/IMPLEMENTATION_REVIEW.delegated-by" 2>/dev/null)"
                    check "$family/$mode: the new inputs are recorded" record "$(cat "$TMP/state/recorded" 2>/dev/null)"
                fi
            else
                check "$family/$mode/$unattended: reopen and stop" yes "$([[ "$out" == *state=WAIT_IMPLEMENT_APPROVAL*exit=0* ]] && echo yes || echo no)"
                check "$family/$mode/$unattended: no implicit approval" no "$([[ "$out" == *approved:* || "$out" == *continued* ]] && echo yes || echo no)"
            fi
        done
    done
    digest=sha
    out="$(run_policy "$family" 0 legacy)"
    check "$family: matching digest continues" yes "$([[ "$out" == *built*continued*exit=0* ]] && echo yes || echo no)"
    check "$family: matching digest never reopens" no "$([[ "$out" == *state=* || "$out" == *approved:* ]] && echo yes || echo no)"
done
# A check that regressed makes the unattended re-approval an override, exactly as the gate does.
digest=different; REGRESSIONS=1; export REGRESSIONS
out="$(run_policy change 1 snapshot)"
check "change: a regression makes the re-approval an override" OVERRIDE "$(cat "$TMP/approvals/IMPLEMENTATION_REVIEW.gate-action" 2>/dev/null)"
check "change: and it still continues" yes "$([[ "$out" == *continued*exit=0* ]] && echo yes || echo no)"

if [[ "$FAILED" -ne 0 ]]; then echo "implementation-reapproval-test.sh: $FAILED of $COUNT checks failed"; exit 1; fi
echo "implementation-reapproval-test.sh: $COUNT checks passed"
