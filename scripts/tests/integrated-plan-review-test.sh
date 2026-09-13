#!/usr/bin/env bash
set -uo pipefail
export WORKFLOW_EXECUTABILITY_REVIEW=0
UNCLE_TEST_FIXTURES_ONLY=1 source "$(dirname "$0")/gates-test.sh"

for family in change stagegate; do
    if [[ "$family" == change ]]; then
        new_case integrated-change
        green_baseline 0 'bash app/test.sh'
    else
        new_stagegate_case integrated-stagegate
        stagegate_agent
    fi
    # A failed old assessment must not hold a normal resumed build hostage.
    mkdir -p "$REPO/.uncle/workflow/plan-executability"
    printf '{}' > "$REPO/.uncle/workflow/plan-executability/manifest.json"
    printf 'Yes, three blockers remain.' > "$REPO/.uncle/workflow/plan-executability/assessment.json"
    printf '{"phase":"AUTHORITY"}' > "$REPO/.uncle/workflow/plan-recovery.json"
    set_state IMPLEMENT
    if [[ "$family" == change ]]; then
        run_driver FAKE_IMPL='echo implemented > app/added.sh'
    else
        run_stagegate FAKE_IMPL='echo implemented > app/added.sh'
    fi
    expect_status 0
    expect_state WAIT_IMPLEMENT_APPROVAL
    expect_in_file app/added.sh implemented
    expect_no_file .uncle/workflow/approvals/PLAN_EXECUTABILITY.sha256
    if grep -q 'Launching reviewer .*: plan-executability' "$OUT"; then
        fail 'normal build launched standalone assessment'
    fi
    expect_in_file .uncle/workflow/plan-executability/assessment.json 'Yes, three blockers remain.'
done

new_case integrated-missing-runner
set_state IMPLEMENT
run_driver WORKFLOW_AGENT_CMD_IMPLEMENTATION="$CASE/bin/nonexistent"
expect_status 1
expect_out 'Implementation runner is unavailable'
expect_no_file app/added.sh

new_case integrated-review-prompt
(
    cd "$REPO" || exit 1
    ROOT="$REPO"
    LOG_DIR="$REPO/.uncle/workflow/logs"
    mkdir -p "$LOG_DIR"
    source scripts/lib/gates.sh
    for stage in adversarial-review updated-plan updated-change-plan; do
        prompt="$(gated_prompt prompts/change/adversarial-review.md "$stage" reviewer)" || exit 1
        grep -q 'Plan feasibility (part of this review' "$prompt" || exit 1
        grep -q 'Separate missing live-verification prerequisites' "$prompt" || exit 1
        grep -q 'Do not produce a separate assessment.json' "$prompt" || exit 1
    done
) > "$CASE/prompt.log" 2>&1 || { cat "$CASE/prompt.log"; fail 'integrated feasibility instructions missing'; }

if [[ "$FAILED" != 0 ]]; then echo "$FAILED/$COUNT integrated plan review checks failed"; exit 1; fi
echo "$COUNT integrated plan review checks passed"
