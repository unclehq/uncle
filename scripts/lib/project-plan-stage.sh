#!/usr/bin/env bash
# Source from the driver, then call after assembly, before its existing plan check:
# . "$ROOT/scripts/lib/project-plan-stage.sh"; project_plan_stage_finish "$directory" "$output" || return 1
project_plan_stage_finish() {
    local directory="$1" plan="$2" helper="$ROOT/scripts/lib/project_plan_stage.py" status=0
    if [[ -f "$directory/stage-duties.json" ]]; then
        python3 -B "$helper" verify "$directory" "$plan"
        return $?
    fi
    # The driver calls once, serially. Refuse accidental concurrent invocation.
    mkdir "$directory/stage-duties.lock" || return 1
    python3 -B "$helper" prepare "$directory" "$plan" "$directory/stage-duties.md" || status=1
    if [[ "$status" == 0 ]]; then
        SESSION_REUSE=0 UNCLE_RUNNER_REUSE=0 PROGRESS_TOTAL=0 \
            run_claude "$directory/stage-duties.md" project-plan-stage-duties \
            > "$LOG_DIR/project-plan-stage-duties.log" 2>&1 || status=1
    fi
    if [[ "$status" == 0 ]]; then
        cp "$LOG_DIR/project-plan-stage-duties.jsonl" "$directory/stage-duties.jsonl" || status=1
    fi
    if [[ "$status" == 0 ]]; then
        python3 -B "$helper" verify "$directory" "$plan" --record || status=1
    fi
    rmdir "$directory/stage-duties.lock" || status=1
    return "$status"
}
