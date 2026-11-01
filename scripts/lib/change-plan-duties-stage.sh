#!/usr/bin/env bash
# The CHANGE_PLAN_DUTIES state: the change-request counterpart of the new-application project-plan-stage-duties. It runs once, right
# after planning and before the plan reaches anyone for approval, as its own timed stage.
#
# A deterministic check (scripts/lib/change_plan_duties.py) looks for a file the plan mentions that no step owns and that does not
# exist, beside files a step does own: the same mistake the new-application step exists to catch (one file with two names). A
# consistent plan costs no model call. Only when there is a finding is the model asked, once, for a targeted patch, which the
# driver applies to the canonical CHANGE_PLAN.json. There is deliberately no .gitignore duty: a change request must not make unrelated
# edits to an existing repository.
#
# Fail-open: a failing, absent or confused model leaves the plan as it was, with the findings printed, and the run goes on to the
# approval gate where a person sees the plan. WORKFLOW_PLAN_DUTIES=0 turns the stage off.
#
# Needs from the caller: ROOT, STATE_DIR, LOG_DIR, run_claude, change_plan_draft_key.

change_plan_duties_stage() {
    local plan=.uncle/docs/CHANGE_PLAN.md dir="$STATE_DIR/change-plan-duties" py="$ROOT/scripts/lib/change_plan_duties.py"
    local before after count_before count_after called=false
    if [[ "${WORKFLOW_PLAN_DUTIES:-1}" == 0 ]]; then
        echo "Change plan duties are off (WORKFLOW_PLAN_DUTIES=0)."
        return 0
    fi
    [[ -s "$plan" ]] || return 0
    before="$(python3 -B "$py" check . "$plan" 2>/dev/null)" || before=""
    count_before="$(printf '%s' "$before" | grep -c . || true)"
    if [[ "$count_before" == 0 ]]; then
        echo "Change plan duties: the plan is consistent (no mentioned file lacks an owner); no model call needed."
        printf '{"before": 0, "after": 0, "model_called": false}\n' > "$STATE_DIR/change-plan-duties.json"
        return 0
    fi
    echo "Change plan duties: $count_before inconsistenc$([[ "$count_before" == 1 ]] && echo y || echo ies) found in the plan:"
    printf '%s\n' "$before" | sed 's/^/  /'
    rm -rf "$dir"; mkdir -p "$dir"
    python3 -B "$py" prompt . "$plan" "$dir/prompt.md" || return 0
    called=true
    # A subshell: run_claude exits the whole process on a failure it judges unrecoverable, and this stage must not take the run down.
    ( UNCLE_WORKER_PACKET_PATH="$dir/answer.json" run_claude "$dir/prompt.md" change-plan-stage-duties "" "" 20 ) \
        > "$LOG_DIR/change-plan-stage-duties.log" 2>&1 || true
    if after="$(python3 -B "$py" apply . "$dir/answer.json" "$LOG_DIR/change-plan-stage-duties.jsonl" 2>"$dir/error.txt")"; then
        count_after="$(printf '%s' "$after" | grep -c . || true)"
        # The plan changed, so the key that says "this plan was drafted with the approved specification" must follow it, or PLAN
        # would decide the draft is stale and plan again.
        change_plan_draft_key > "$STATE_DIR/change-plan.draft-key" 2>/dev/null || true
        if [[ "$count_after" == 0 ]]; then
            echo "Change plan duties: fixed; the plan is consistent."
        else
            echo "Change plan duties: $count_after inconsistenc$([[ "$count_after" == 1 ]] && echo y || echo ies) remain; the plan goes to review as it stands:"
            printf '%s\n' "$after" | sed 's/^/  /'
        fi
    else
        count_after="$count_before"
        echo "Change plan duties: no usable fix came back ($(head -1 "$dir/error.txt" 2>/dev/null)); the plan is unchanged and goes to review as it stands."
    fi
    printf '{"before": %s, "after": %s, "model_called": %s}\n' "$count_before" "${count_after:-$count_before}" "$called" > "$STATE_DIR/change-plan-duties.json"
    return 0
}
