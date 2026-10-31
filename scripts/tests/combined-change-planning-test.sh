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
    expect_in_file .uncle/workflow/combined-prompt 'BASELINE_REPORT.json is already written'
    expect_in_file .uncle/workflow/combined-prompt 'do not redo the baseline'
    # This scenario's fake-agent matches the spec-and-plan-only prompt (an
    # already-written .uncle/docs/BASELINE_REPORT.md), which only claims "the same
    # context" for spec+plan together -- "the same model and context" is the
    # with-baseline branch's own wording, for when one pass does all three
    # documents and model continuity across them is the actual guarantee.
    expect_in_file .uncle/workflow/combined-prompt 'the same context, provide a complete replacement canonical bundle'
    grep -q 'the same model and context' "$REPO/.uncle/workflow/combined-prompt" && fail 'spec-and-plan-only prompt wrongly claims "the same model and context" (that wording is reserved for the with-baseline combined pass)'
    expect_not_out ': change-spec'
    if [[ "$edited" == 1 ]]; then
        # Under the canonical-JSON contract, approval and plan-reuse both hash
        # .uncle/workflow/documents/CHANGE_SPEC.json, not the rendered
        # .uncle/docs/CHANGE_SPEC.md view -- editing only the Markdown view
        # (the old pre-canonical-JSON contract's edit path) is invisible to
        # both checks. Edit the canonical packet itself, the same thing a real
        # "user clarification at approval" would have to change, then
        # re-render the view the way publish_change_planning_bundle.py does.
        python3 - "$REPO" <<'PY'
import json, sys
from pathlib import Path
sys.path.insert(0, "scripts/lib")
import artifact_json
repo = Path(sys.argv[1])
spec_path = repo / ".uncle/workflow/documents/CHANGE_SPEC.json"
payload = json.loads(spec_path.read_text(encoding="utf-8"))
payload["narrative"] = payload.get("narrative", "") + "\n\nUser clarification at approval.\n"
spec_path.write_text(json.dumps(payload), encoding="utf-8")
rendered = artifact_json.render_change_spec(payload)
(repo / ".uncle/docs/CHANGE_SPEC.md").write_text(rendered, encoding="utf-8")
PY
    fi
    run_driver_stdin "$(gate_input y)"
    expect_status 0
    expect_state WAIT_PLAN_APPROVAL
    expect_file .uncle/docs/ADVERSARIAL_REVIEW.md
    expect_file .uncle/workflow/approvals/CHANGE_SPEC.sha256
    COUNT=$((COUNT + 1))
    [[ $(wc -l < "$REPO/.uncle/workflow/planning-calls") -eq $((1 + edited)) ]] || fail "incorrect number of planning sessions: got $(wc -l < "$REPO/.uncle/workflow/planning-calls"), wanted $((1 + edited))"
    if [[ "$edited" == 0 ]]; then
        expect_out 'Using the plan drafted with the approved change specification.'
    fi
done
if [[ "$FAILED" != 0 ]]; then echo "$FAILED/$COUNT combined planning checks failed"; exit 1; fi
echo "$COUNT combined planning checks passed"
