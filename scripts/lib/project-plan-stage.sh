#!/usr/bin/env bash
# Source from the driver, then call after assembly, before its existing plan check:
# . "$ROOT/scripts/lib/project-plan-stage.sh"; project_plan_stage_finish "$directory" "$output" || return 1
#
# The stage step checks the assembled plan for contradictions between independently written
# sections and completes the .gitignore duties. It used to report a contradiction and stop, and
# a stopped step failed the whole sectioned plan: the driver discarded every worker's output
# and had a model write the plan again from scratch (about 40-50s more, on top of work already
# paid for). Now the step fixes what it finds with a targeted edit, and a step that still did
# not finish gets one repair attempt that is told what went wrong. Only a plan that survives
# neither falls back to the single-pass planner. WORKFLOW_PLAN_STAGE_REPAIR=0 skips the repair.
project_plan_stage_finish() {
    local directory="$1" plan="$2" helper="$ROOT/scripts/lib/project_plan_stage.py" status=0 reason=""
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
        reason="$(python3 -B "$helper" verify "$directory" "$plan" --record 2>&1)" || status=1
    fi
    if [[ "$status" != 0 && "${WORKFLOW_PLAN_STAGE_REPAIR:-1}" != 0 && -s "$plan" ]]; then
        echo "Project plan stage did not finish (${reason:-the step failed}); repairing the assembled plan once."
        status=0
        python3 -B "$helper" prepare-repair "$directory" "$plan" "$directory/stage-duties-repair.md" "$reason" || status=1
        if [[ "$status" == 0 ]]; then
            SESSION_REUSE=0 UNCLE_RUNNER_REUSE=0 PROGRESS_TOTAL=0 \
                run_claude "$directory/stage-duties-repair.md" project-plan-stage-duties \
                > "$LOG_DIR/project-plan-stage-duties-repair.log" 2>&1 || status=1
        fi
        if [[ "$status" == 0 ]]; then
            cp "$LOG_DIR/project-plan-stage-duties.jsonl" "$directory/stage-duties.jsonl" || status=1
        fi
        if [[ "$status" == 0 ]]; then
            python3 -B "$helper" verify "$directory" "$plan" --record || status=1
        fi
    elif [[ "$status" != 0 && -n "$reason" ]]; then
        printf '%s\n' "$reason" >&2
    fi
    rmdir "$directory/stage-duties.lock" || status=1
    return "$status"
}
