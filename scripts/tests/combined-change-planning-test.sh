#!/usr/bin/env bash
set -uo pipefail
export WORKFLOW_EXECUTABILITY_REVIEW=0
UNCLE_TEST_FIXTURES_ONLY=1 source "$(dirname "$0")/gates-test.sh"
for edited in 0 1; do
    new_case "combined-planning-$edited"
    cp "$ROOT/prompts/change/change-spec.md" "$REPO/prompts/change/change-spec.md"
    printf 'STUB:baseline\n' > "$REPO/prompts/change/baseline.md"
    # The combined pass produces a bundle, while this scenario deliberately
    # uses the real spec prompt (without the shared stub's STUB:spec token).
    jq -n --slurpfile baseline "$REPO/.uncle/workflow/documents/BASELINE_REPORT.json" \
        --slurpfile spec "$REPO/.uncle/workflow/documents/CHANGE_SPEC.json" \
        --slurpfile plan "$REPO/.uncle/workflow/documents/CHANGE_PLAN.json" \
        '{schema:"uncle.artifact/v1",kind:"change-planning-bundle",
          baseline_report:$baseline[0],change_spec:$spec[0],change_plan:$plan[0]}' > "$CASE/bundle-template.json"
    # Executability review is disabled here. The shared launcher seeds that
    # unrelated fixture before the plan exists; it must not read a future plan.
    printf 'import sys\nassert sys.argv[1] == "--fixture"\n' > "$REPO/scripts/tests/plan-executability-test.py"
    rm "$REPO/.uncle/workflow/documents/CHANGE_SPEC.json" "$REPO/.uncle/workflow/documents/CHANGE_PLAN.json"
    rm "$REPO/.uncle/docs/CHANGE_SPEC.md" "$REPO/.uncle/docs/CHANGE_PLAN.md"
    mv "$CASE/bin/fake-agent" "$CASE/bin/original-agent"
    cat > "$CASE/bin/fake-agent" <<'AGENT'
#!/usr/bin/env bash
prompt="$(cat)"
case "$prompt" in
    *STUB:plan*) echo planning >> .uncle/workflow/planning-calls ;;
esac
case "$prompt" in
    *'Combined change specification and planning'*)
        printf '%s' "$prompt" > .uncle/workflow/combined-prompt
        cp "$(dirname "$0")/../bundle-template.json" "$UNCLE_ARTIFACT_DELIVERY"
        printf '%s\n' '{"type":"result","subtype":"success","is_error":false,"num_turns":1,"duration_ms":5,"total_cost_usd":0}'
        exit 0
        ;;
esac
printf '%s' "$prompt" | "$(dirname "$0")/original-agent" "$@"
AGENT
    chmod +x "$CASE/bin/fake-agent"
    set_state ANALYZE
    run_driver
    expect_status 0
    expect_state WAIT_ANALYSIS_APPROVAL
    expect_file .uncle/docs/CHANGE_SPEC.md
    expect_file .uncle/docs/CHANGE_PLAN.md
    expect_file .uncle/workflow/change-plan.draft-key
    # Compact canonical synthesis no longer appends presentation budgets to
    # its prompt. Keep checking that the combined stage budgets both rendered
    # documents through the budget helper used by the driver's checks.
    (
        cd "$REPO"
        . "$ROOT/scripts/lib/gates.sh"
        DOCUMENT_BUDGET_SOURCE=CHANGE_REQUEST.md
        UNCLE_COMBINED_CHANGE_PLAN=1 document_budget_prompt change-plan
    ) > "$REPO/.uncle/workflow/combined-budgets"
    expect_in_file .uncle/workflow/combined-budgets '.uncle/docs/CHANGE_SPEC.md: at most'
    expect_in_file .uncle/workflow/combined-budgets '.uncle/docs/CHANGE_PLAN.md: at most'
    # The driver now renders the same spec and plan from a single canonical
    # bundle. Assert both packet contracts and their shared-context instruction.
    expect_in_file .uncle/workflow/combined-prompt '"change_spec":{"schema":"uncle.artifact/v1","kind":"change-spec"'
    expect_in_file .uncle/workflow/combined-prompt '"change_plan":{"schema":"uncle.artifact/v1","kind":"change-plan"'
    expect_in_file .uncle/workflow/combined-prompt 'the same context, provide a complete replacement canonical bundle'
    expect_in_file .uncle/workflow/combined-prompt 'are rendered by the driver afterwards, from the bundle.'
    expect_not_out ': change-spec'
    if [[ "$edited" == 1 ]]; then
        printf '\nUser clarification at approval.\n' >> "$REPO/.uncle/docs/CHANGE_SPEC.md"
        sync_canonical CHANGE_SPEC
    fi
    run_driver_stdin "$(gate_input y)"
    expect_status 0
    expect_state WAIT_PLAN_APPROVAL
    expect_file .uncle/docs/ADVERSARIAL_REVIEW.md
    expect_file .uncle/workflow/approvals/CHANGE_SPEC.sha256
    COUNT=$((COUNT + 1))
    [[ $(wc -l < "$REPO/.uncle/workflow/planning-calls") -eq $((1 + edited)) ]] || fail 'incorrect number of planning sessions'
    if [[ "$edited" == 0 ]]; then
        expect_out 'Using the plan drafted with the approved change specification.'
    fi
done
if [[ "$FAILED" != 0 ]]; then echo "$FAILED/$COUNT combined planning checks failed"; exit 1; fi
echo "$COUNT combined planning checks passed"
