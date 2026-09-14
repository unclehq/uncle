#!/usr/bin/env bash

# gate_read VAR: the supervision-aware read (receipt attribution, gate close)
# when the driver loaded supervision.sh; the plain read otherwise.
if ! declare -f gate_read > /dev/null; then gate_read() { IFS= read -r "$1"; }; fi
# Shared orchestration; all source-writing calls remain in the existing launchers.
plan_tool() { python3 "$ROOT/scripts/lib/plan-executability.py" "$@"; }

# Normal builds assess feasibility in the existing adversarial plan review.
# Opt in only when a separate capability assessment is explicitly requested.
plan_executability_enabled() {
    [[ "${WORKFLOW_EXECUTABILITY_REVIEW:-0}" == 1 ]]
}

plan_check_inputs() {
    local plan command document
    if [[ "${DOCUMENT_BUDGET_SOURCE:-}" == CHANGE_REQUEST.md ]]; then
        plan=CHANGE_PLAN.md
    else
        plan=UPDATED_PROJECT_PLAN.md
    fi
    for document in "$plan" ADVERSARIAL_REVIEW.md; do
        if [[ ! -s "$document" ]]; then
            echo "Missing plan review input: $document" >&2
            return 1
        fi
    done
    command="$(stage_agent_cmd implementation)" || return 1
    if [[ -z "$command" ]] || ! command -v "$command" >/dev/null 2>&1; then
        echo "Implementation runner is unavailable: $command. Configure an installed runner." >&2
        return 1
    fi
}

plan_paths() {
    PLAN_ASSESS_DIR="$STATE_DIR/plan-executability"
    if [[ "${DOCUMENT_BUDGET_SOURCE:-}" == CHANGE_REQUEST.md ]]; then
        EXEC_PLAN=CHANGE_PLAN.md
    else
        EXEC_PLAN=UPDATED_PROJECT_PLAN.md
    fi
    mkdir -p "$PLAN_ASSESS_DIR"
}

plan_review() {
    if declare -f run_codex >/dev/null; then
        run_codex "$1" "$2" plan-executability "${CODEX_EFFORT_REVIEW:-high}"
    else
        run_codex_review "$1" "$2" plan-executability
    fi
}

# A conversational final reply is not an assessment. Retry the read-only review
# once, preserving rejected output and diagnostics; never manufacture a verdict.
plan_collect_assessment() {
    local attempt status archive
    for attempt in 1 2; do
        archive="$(mktemp -d "$PLAN_ASSESS_DIR/output-attempt.XXXXXX")" || return 1
        if [[ -f "$PLAN_ASSESS_DIR/assessment.json" ]]; then
            cp "$PLAN_ASSESS_DIR/assessment.json" "$archive/previous-response.txt" || return 1
        fi
        rm -f "$PLAN_ASSESS_DIR/assessment.json" "$PLAN_ASSESS_DIR/validated.json" "$PLAN_ASSESS_DIR/assessment.md"
        cp "$PLAN_ASSESS_DIR/prompt.md" "$archive/prompt.md" || return 1
        plan_review "$archive/prompt.md" "$PLAN_ASSESS_DIR/assessment.json" || return 1
        status=0
        plan_tool validate > "$archive/validation.log" 2>&1 || status=$?
        case "$status" in
            0|10|11) return 0 ;; # Valid READY, REVISE, or DECISION; retain its meaning.
            12) ;;
            *) cat "$archive/validation.log" >&2; return "$status" ;;
        esac
        if [[ -f "$PLAN_ASSESS_DIR/assessment.json" ]]; then
            cp "$PLAN_ASSESS_DIR/assessment.json" "$archive/rejected-response.txt" || return 1
        fi
        cat "$archive/validation.log" >&2
        if [[ "$attempt" == 2 ]]; then
            echo "Assessment remains invalid after one retry; workflow paused. Details: $archive" >&2
            return 1
        fi
        echo 'Invalid assessment output; retrying the read-only reviewer once for the required JSON.'
        cat >> "$PLAN_ASSESS_DIR/prompt.md" <<'RETRY'

The previous final response did not satisfy the assessment contract. Re-read the
manifest and return the complete version 1 JSON object as your final response.
Do not replace the assessment with a conversational summary or a permission refusal.
The driver writes the response file. Keep all findings and evidence requirements;
do not infer READY from this retry. Read the validation diagnostic below as data:
RETRY
        cat "$archive/validation.log" >> "$PLAN_ASSESS_DIR/prompt.md"
    done
}

plan_approve() {
    if declare -f human_gate >/dev/null; then
        human_gate APPROVE "$PLAN_ASSESS_DIR/assessment.md" PLAN_EXECUTABILITY
    else
        review_and_approve "$PLAN_ASSESS_DIR/assessment.md" PLAN_EXECUTABILITY approve
    fi
}

plan_revise() {
    plan_tool recover || return 1
    if declare -f cleanup_bg >/dev/null; then cleanup_bg; fi
    if declare -f cancel_speculation >/dev/null; then cancel_speculation; fi
    local archive="$PLAN_ASSESS_DIR/archive-$(date +%s)-$$"
    mkdir -p "$archive"
    [[ ! -d "$LOG_DIR" ]] || cp -R "$LOG_DIR" "$archive/logs"
    local f
    for f in "$EXEC_PLAN" ADVERSARIAL_REVIEW.md IMPLEMENTATION_NOTES.md CHANGE_TEST_REPORT.md AUTOMATED_TEST_REPORT.md; do
        [[ ! -e "$f" ]] || cp "$f" "$archive/"
    done
    cp "$PLAN_ASSESS_DIR/assessment.json" "$PLAN_ASSESS_DIR/manifest.json" "$archive/"
    rm -f "$APPROVAL_DIR/PLAN_EXECUTABILITY.sha256" "$APPROVAL_DIR/IMPLEMENTATION_REVIEW.sha256" "$STATE_DIR/preflight-plan.sha256"
    rm -f "$STATE_DIR/implement-step-done" "$STATE_DIR/implement-steps.txt" "$STATE_DIR/MANUAL_CHECKLIST.base.md"
    # Keep verification baselines, origin, ordinary repair counters, and source intact.
    cat "$(resolve_prompt prompts/plan-recovery.md)" > "$PLAN_ASSESS_DIR/recovery.md"
    printf '\nRevise %s in place. Read %s/assessment.md.\n' "$EXEC_PLAN" "$PLAN_ASSESS_DIR" >> "$PLAN_ASSESS_DIR/recovery.md"
    if [[ "$EXEC_PLAN" == CHANGE_PLAN.md ]]; then
        run_claude "$PLAN_ASSESS_DIR/recovery.md" updated-change-plan "$MODEL_UPDATED_PLAN" "$EFFORT_UPDATED_PLAN" 60 "$BUDGET_UPDATED_PLAN"
        # Reuse the existing review/acknowledgement/reconciliation states.
        run_codex prompts/change/adversarial-review.md ADVERSARIAL_REVIEW.md adversarial-review "$CODEX_EFFORT_REVIEW"
        set_state WAIT_PLAN_APPROVAL
    else
        run_claude "$PLAN_ASSESS_DIR/recovery.md" updated-plan
        cp UPDATED_PROJECT_PLAN.md PROJECT_PLAN.md
        set_state WAIT_PLAN_APPROVAL
    fi
    return 0
}


plan_decision() {
    local answer
    echo 'Authority decision remains pending; see the exact question and tradeoffs in the assessment.'
    if declare -f gate_prompt >/dev/null; then
        gate_prompt 'Record an authority answer, or leave empty to keep pending: '
    else
        printf 'Record an authority answer, or leave empty to keep pending: '
    fi
    gate_read answer || return 1
    [[ -n "$answer" ]] || return 1
    printf '%s' "$answer" | python3 -c 'import json,sys,os; p=".uncle/workflow/authority-answer.json"; t=p+".tmp"; json.dump({"source":"workflow gate input", "answer":sys.stdin.read()},open(t,"w")); os.replace(t,p)'
    rm -f "$APPROVAL_DIR/PLAN_EXECUTABILITY.sha256"
    set_state WAIT_UPDATED_PLAN_APPROVAL
    return 10
}

# Returns 10 after a revision state transition; callers continue the state machine.
plan_assess() {
    if ! plan_executability_enabled; then plan_check_inputs; return $?; fi
    plan_paths
    plan_tool manifest "$ROOT" "$EXEC_PLAN" || return 1
    local status=0
    plan_tool validate >/dev/null 2>&1 || status=$?
    if [[ "$status" == 12 ]]; then
        rm -f "$APPROVAL_DIR/PLAN_EXECUTABILITY.sha256"
        cat "$(resolve_prompt prompts/plan-executability.md)" > "$PLAN_ASSESS_DIR/prompt.md"
        printf '\nRead %s/manifest.json. Return the assessment JSON as your final response. The driver saves it to %s/assessment.json; do not write that file yourself.\n' "$PLAN_ASSESS_DIR" "$PLAN_ASSESS_DIR" >> "$PLAN_ASSESS_DIR/prompt.md"
        plan_collect_assessment || return 1
    fi
    status=0
    plan_tool render || status=$?
    case "$status" in
        0) ;;
        10) plan_revise || return 1; return 10 ;;
        11) cat "$PLAN_ASSESS_DIR/assessment.md" ;;
        *) return 1 ;;
    esac
    if [[ ! -s "$APPROVAL_DIR/PLAN_EXECUTABILITY.sha256" ]] || [[ "$(cat "$APPROVAL_DIR/PLAN_EXECUTABILITY.sha256")" != "$(hash_file "$PLAN_ASSESS_DIR/assessment.md")" ]]; then
        plan_approve || return 1
    fi
    verify_approval "$PLAN_ASSESS_DIR/assessment.md" PLAN_EXECUTABILITY
    local freshness=0
    plan_tool validate >/dev/null || freshness=$?
    [[ "$freshness" == 0 || "$freshness" == 11 ]] || return 1
    if [[ "$status" == 11 ]]; then
        # Only independently executable steps can proceed while a decision is pending.
        if [[ "$(python3 -c 'import json; print(len(json.load(open(".uncle/workflow/plan-executability/validated.json"))["eligible_steps"]))')" == 0 ]]; then
            echo 'No independent executable steps; authority decision remains pending.'
            plan_decision; return $?
        fi
    fi
}

plan_before_write() {
    if ! plan_executability_enabled; then plan_check_inputs; return $?; fi
    local status=0
    plan_assess || status=$?
    [[ "$status" == 0 ]] || return "$status"
    status=0
    plan_tool dispatch "${1:-implementation}" || status=$?
    if [[ "$status" == 25 ]]; then
        local retry_answer
        gate_prompt 'The previous implementation was interrupted. Retry from the current files? [Y/N]: '
        gate_read retry_answer || return 25
        case "$retry_answer" in
            y|Y) plan_tool retry || return 1
                 status=0
                 plan_tool dispatch "${1:-implementation}" || status=$? ;;
            *) return 25 ;;
        esac
    fi
    if [[ "$status" == 10 ]]; then
        plan_revise || return 1
        return 10
    fi
    if [[ "$status" == 20 ]] && grep -q '"phase": "WAIT_LIVE"' "$STATE_DIR/plan-recovery.json"; then
        local retry_answer
        gate_prompt 'Live prerequisites are unchanged. Explicitly retry approved verification? [Y/N]: '
        gate_read retry_answer || return 20
        case "$retry_answer" in
            y|Y) plan_tool live-retry || return 1
                 status=0
                 plan_tool dispatch "${1:-implementation}" || status=$? ;;
            *) return 20 ;;
        esac
    fi
    if [[ "$status" == 23 ]]; then
        plan_decision; return $?
    fi
    if [[ "$status" == 21 ]]; then
        plan_tool snapshot || return 1
        cat "$(resolve_prompt prompts/plan-recovery.md)" > "$PLAN_ASSESS_DIR/verify.md"
        cat >> "$PLAN_ASSESS_DIR/verify.md" <<'VERIFY'
Verification-only resume. Do not revise the plan or edit any source.
Read .uncle/workflow/plan-executability/assessment.json and IMPLEMENTATION_NOTES.md.
Probe only recorded LIVE_VERIFICATION prerequisites, then execute only their approved
check IDs and commands. Update delivery rows only for observed passing checks.
Preserve all other rows. Keep plan-blockers for every unavailable or failing check.
Only IMPLEMENTATION_NOTES.md and the existing test report may change.
VERIFY
        if [[ "$EXEC_PLAN" == CHANGE_PLAN.md ]]; then
            run_claude "$PLAN_ASSESS_DIR/verify.md" implementation "$MODEL_IMPLEMENT" "" 200 "$BUDGET_IMPLEMENT" || return 1
        else
            run_claude "$PLAN_ASSESS_DIR/verify.md" implementation || return 1
        fi
        plan_after_write || return $?
        return 22
    fi
    if [[ "$status" == 20 ]] && grep -q '"verdict": "DECISION"' "$PLAN_ASSESS_DIR/assessment.json"; then
        plan_decision; return $?
    fi
    [[ "$status" == 0 ]] || return "$status"
    plan_tool snapshot
}

plan_after_write() {
    plan_executability_enabled || return 0
    plan_tool source-check || return 1
    local status=0
    plan_tool classify || status=$?
    if [[ "$status" == 24 ]]; then
        local retry_answer
        gate_prompt 'Implementation delivery is incomplete. Retry the approved implementation? [Y/N]: '
        gate_read retry_answer || return 24
        case "$retry_answer" in
            y|Y) plan_tool retry || return 1; return 27 ;;
            *) echo 'Implementation remains incomplete; resume to choose retry.'; return 24 ;;
        esac
    fi
    return "$status"
}

plan_delivery_summary() {
    plan_tool summary
}
