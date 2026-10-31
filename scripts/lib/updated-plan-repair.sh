# A structural retry edits the current plan, never reruns synthesis against the old one.
run_updated_plan_structure_repair() {
    local plan="$1" problem="$2" stage="$3" directory="$STATE_DIR/updated-plan-structure-repair" status=0
    local helper="$ROOT/scripts/lib/updated_plan_ops.py"
    local UNCLE_PLAN_KIND="${UNCLE_PLAN_KIND:-}"
    if [[ "$stage" == updated-change-plan ]]; then UNCLE_PLAN_KIND=change-plan; fi
    local UNCLE_UPDATED_PLAN_STRUCTURE_REPAIR=1
    export UNCLE_PLAN_KIND UNCLE_UPDATED_PLAN_STRUCTURE_REPAIR
    python3 -B "$helper" repair-prepare "$plan" "$PWD" "$directory" "$problem" || status=$?
    if [[ "$status" == 3 ]]; then
        local writer_turns answer_tokens
        read -r writer_turns answer_tokens < <(python3 -B "$helper" budget structure)
        rm -f "$directory/packet.json"
        if [[ "$stage" == updated-change-plan ]]; then
            ( UNCLE_WORKER_MAX_TURNS="$writer_turns" UNCLE_UPDATED_PLAN_ANSWER_TOKENS="$answer_tokens" \
              UNCLE_WORKER_PACKET_PATH="$directory/packet.json" SESSION_REUSE=0 UNCLE_RUNNER_REUSE=0 \
                run_claude "$directory/prompt.md" "$stage-worker-edits-structure" "$MODEL_UPDATED_PLAN" "$EFFORT_UPDATED_PLAN" "$writer_turns" "$BUDGET_UPDATED_PLAN" ) || true
        else
            ( UNCLE_WORKER_MAX_TURNS="$writer_turns" UNCLE_UPDATED_PLAN_ANSWER_TOKENS="$answer_tokens" \
              UNCLE_WORKER_PACKET_PATH="$directory/packet.json" SESSION_REUSE=0 UNCLE_RUNNER_REUSE=0 \
                run_claude "$directory/prompt.md" "$stage-worker-edits-structure" ) || true
        fi
        python3 -B "$helper" repair-apply "$directory" "$PWD" || return 1
    elif [[ "$status" != 0 ]]; then
        return "$status"
    fi
    python3 -B "$ROOT/scripts/lib/publish_agent_artifact.py" "$stage" "$LOG_DIR/$stage.jsonl" . "$directory/repaired.json"
}
