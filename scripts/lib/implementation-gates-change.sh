#!/usr/bin/env bash
# Change implementation policy bindings. Load implementation-gates.sh first.

implementation_incomplete_choice() {
    change_implementation_incomplete_choice "$@"
}

build_implementation_review() {
    change_build_implementation_review "$@"
}

verify_implementation_review() {
    change_verify_implementation_review "$@"
}

# The change driver approves through human_gate (review_and_approve belongs to the new-application driver and does not exist here), and
# a check that regressed makes the approval an override, as at the gate itself.
reapprove_implementation_unattended() {
    [[ "${UNATTENDED:-0}" == 1 ]] || return 1
    local action=APPROVE
    [[ "$(green_regressions "$GREEN_CLASS")" -gt 0 ]] && action=OVERRIDE
    human_gate "$action" "$REVIEW_FILE" IMPLEMENTATION_REVIEW || return 1
    WORKFLOW_UNTRACKED_BASELINE="$WORKFLOW_UNTRACKED_BASELINE" python3 -B "$ROOT/scripts/lib/approval_snapshot.py" record "$STATE_DIR" || return 1
    record_unattended_gate IMPLEMENTATION_REVIEW "re-approved the current implementation after its inputs changed, without human review"
    echo "Unattended: the approved implementation inputs changed after approval; re-approved the current tree and continuing."
    return 0
}
