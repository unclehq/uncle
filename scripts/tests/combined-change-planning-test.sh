#!/usr/bin/env bash
set -uo pipefail
export WORKFLOW_EXECUTABILITY_REVIEW=0
UNCLE_TEST_FIXTURES_ONLY=1 source "$(dirname "$0")/gates-test.sh"
for edited in 0 1; do
    new_case "combined-planning-$edited"
    cp "$ROOT/prompts/change/change-spec.md" "$REPO/prompts/change/change-spec.md"
    printf 'STUB:baseline\n' > "$REPO/prompts/change/baseline.md"
    cp "$REPO/CHANGE_SPEC.md" "$CASE/spec-template"
    rm "$REPO/CHANGE_SPEC.md" "$REPO/CHANGE_PLAN.md"
    mv "$CASE/bin/fake-agent" "$CASE/bin/original-agent"
    cat > "$CASE/bin/fake-agent" <<'AGENT'
#!/usr/bin/env bash
prompt="$(cat)"
case "$prompt" in
    *STUB:plan*) echo planning >> .uncle/workflow/planning-calls ;;
esac
case "$prompt" in
    *'Combined change specification and planning'*)
        cp "$(dirname "$0")/../spec-template" CHANGE_SPEC.md
        printf '%s' "$prompt" > .uncle/workflow/combined-prompt
        ;;
esac
printf '%s' "$prompt" | "$(dirname "$0")/original-agent" "$@"
AGENT
    chmod +x "$CASE/bin/fake-agent"
    set_state ANALYZE
    run_driver
    expect_status 0
    expect_state WAIT_ANALYSIS_APPROVAL
    expect_file CHANGE_SPEC.md
    expect_file CHANGE_PLAN.md
    expect_file .uncle/workflow/change-plan.draft-key
    expect_in_file .uncle/workflow/combined-prompt 'CHANGE_SPEC.md: at most'
    expect_in_file .uncle/workflow/combined-prompt 'CHANGE_PLAN.md: at most'
    expect_in_file .uncle/workflow/combined-prompt 'same model and context'
    expect_not_out ': change-spec'
    if [[ "$edited" == 1 ]]; then
        printf '\nUser clarification at approval.\n' >> "$REPO/CHANGE_SPEC.md"
    fi
    run_driver_stdin "$(gate_input y)"
    expect_status 0
    expect_state WAIT_PLAN_APPROVAL
    expect_file ADVERSARIAL_REVIEW.md
    expect_file .uncle/workflow/approvals/CHANGE_SPEC.sha256
    COUNT=$((COUNT + 1))
    [[ $(wc -l < "$REPO/.uncle/workflow/planning-calls") -eq $((1 + edited)) ]] || fail 'incorrect number of planning sessions'
    if [[ "$edited" == 0 ]]; then
        expect_out 'Using the plan drafted with the approved change specification.'
    fi
done
if [[ "$FAILED" != 0 ]]; then echo "$FAILED/$COUNT combined planning checks failed"; exit 1; fi
echo "$COUNT combined planning checks passed"
