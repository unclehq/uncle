# A structural retry edits the current plan, never reruns synthesis against the old one.
run_updated_plan_structure_repair() {
    local plan="$1" problem="$2" stage="$3" directory="$STATE_DIR/updated-plan-structure-repair" status=0
    . "$ROOT/scripts/lib/model-jobs.sh"
    local attempts="$STATE_DIR/updated-plan-edits"
    [[ "$stage" != updated-change-plan ]] || attempts="$STATE_DIR/updated-change-plan-edits"
    local helper="$ROOT/scripts/lib/updated_plan_ops.py"
    local UNCLE_PLAN_KIND="${UNCLE_PLAN_KIND:-}"
    if [[ "$stage" == updated-change-plan ]]; then UNCLE_PLAN_KIND=change-plan; fi
    local UNCLE_UPDATED_PLAN_STRUCTURE_REPAIR=1
    export UNCLE_PLAN_KIND UNCLE_UPDATED_PLAN_STRUCTURE_REPAIR
    python3 -B "$helper" repair-prepare "$plan" "$PWD" "$directory" "$problem" || status=$?
    if [[ "$status" == 3 ]]; then
        local finding_ids=""
        if [[ -f "$attempts/slices.tsv" ]]; then
            finding_ids="$(python3 -B "$ROOT/scripts/lib/updated_plan_defer.py" structure-ids "$attempts" "$directory")" || return 1
        fi
        local writer_turns answer_tokens attempt prompt="$directory/prompt.md"
        read -r writer_turns answer_tokens < <(python3 -B "$helper" budget structure)
        for attempt in 1 2; do
            rm -f "$directory/packet.json"
            ( export UNCLE_UPDATED_PLAN_ATTEMPTS_DIR="$attempts" UNCLE_UPDATED_PLAN_FINDINGS="$finding_ids"
              export UNCLE_WORKER_SCHEMA_FILE="$directory/schema.json"
              if declare -F stage_supports_structured_output >/dev/null \
                 && stage_supports_structured_output "$stage-worker-edits-structure"; then
                  export UNCLE_OUTPUT_SCHEMA_FILE="$directory/schema.json" UNCLE_STRUCTURED_OUTPUT_PATH="$directory/packet.json"
              fi
              export UNCLE_WORKER_MAX_TURNS="$writer_turns" UNCLE_UPDATED_PLAN_ANSWER_TOKENS="$answer_tokens"
              export UNCLE_WORKER_PACKET_PATH="$directory/packet.json" SESSION_REUSE=0 UNCLE_RUNNER_REUSE=0
              if [[ "$stage" == updated-change-plan ]]; then
                  workflow_model_writer "$stage" run_claude "$prompt" "$stage-worker-edits-structure" "$MODEL_UPDATED_PLAN" "$EFFORT_UPDATED_PLAN" "$writer_turns" "$BUDGET_UPDATED_PLAN"
              else
                  workflow_model_writer "$stage" run_claude "$prompt" "$stage-worker-edits-structure"
              fi
            ) || true
            if python3 -B "$helper" repair-apply "$directory" "$PWD" 2>"$directory/apply-error.log"; then
                break
            fi
            if [[ "$attempt" == 2 ]]; then
                cat "$directory/apply-error.log" >&2
                [[ -n "$finding_ids" ]] || return 1
                python3 -B "$ROOT/scripts/lib/updated_plan_defer.py" structure "$attempts" "$directory" "$stage" "$helper" || { workflow_writer_exhausted "$stage"; return 1; }
                workflow_deferred_report "$attempts"
                break
            fi
            prompt="$directory/retry.md"
            cp "$directory/prompt.md" "$prompt"
            printf '\n\n## Your previous answer was rejected\n\n' >> "$prompt"
            cat "$directory/apply-error.log" >> "$prompt"
            printf '\nCorrect only this defect using the supplied ids and return the same packet shape.\n' >> "$prompt"
        done
    elif [[ "$status" != 0 ]]; then
        return "$status"
    fi
    python3 -B "$ROOT/scripts/lib/publish_agent_artifact.py" "$stage" "$LOG_DIR/$stage.jsonl" . "$directory/repaired.json"
}
