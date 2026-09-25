#!/usr/bin/env bash
# A repair is judged on the files it changed, not on its report.
#
# On one build the second repair pass ran for eight seconds, wrote nothing, and
# reported every finding fixed -- because its own notes from the first pass said
# so. The independent review then spent minutes proving by hash what the driver
# could have seen for free. So the driver snapshots the files each blocking
# finding names before the pass and compares afterwards: a pass that changed
# none of them is not a repair. It is not reviewed, it consumes no attempt, and
# it is retried once with a driver-written brief of what is still open -- with
# the agent's own reports left out of its packet, since those were the false
# evidence. A second such pass stops the run for a person.
#
# Sourced by stagegate.sh; needs STATE_DIR, LOG_DIR, ROOT, resolve_prompt,
# triage_stop_reason and supervision_validation_failed.

REPAIR_PROMPT="prompts/repair.md"

repair_begin() {
    local report base
    report="$(cat "$STATE_DIR/repair-source")"
    python3 -B "$ROOT/scripts/lib/repair_check.py" snapshot "$report" "$STATE_DIR/repair-check.json" || return 1
    # Self-hosted models get the investigate/format split's base prompt here;
    # a proprietary model gets the original single-pass prompt. Either way,
    # a driver-written retry brief appends on top of whichever base applies.
    if stage_uses_self_hosted repair AGENT; then
        base="prompts/repair-investigate.md"
    else
        base="prompts/repair.md"
    fi
    REPAIR_PROMPT="$base"
    if [[ -e "$STATE_DIR/repair-retry" && -s "$STATE_DIR/REPAIR_BRIEF.md" ]]; then
        {
            cat "$(resolve_prompt "$base")"
            printf '\n\n## Repair brief (written by the driver)\n\n'
            cat "$STATE_DIR/REPAIR_BRIEF.md"
        } > "$LOG_DIR/repair-retry.prompt.md"
        REPAIR_PROMPT="$LOG_DIR/repair-retry.prompt.md"
    fi
}

# 0: every blocking finding saw a change; on to review. 3: the state machine
# re-enters REPAIR -- either a partial pass (some findings changed, the
# attempt counts, the rest are briefed) or a no-op pass (nothing changed, the
# attempt is given back, one retry with the brief). 1: nothing changed twice
# in a row; the run stops for a person.
repair_judge() {
    local report unrepaired status=0 noops count
    report="$(cat "$STATE_DIR/repair-source")"
    # Repair dispositions are canonical JSON. Markdown notes are a human view
    # and must not decide whether a source repair happened.
    unrepaired="$(python3 -B "$ROOT/scripts/lib/repair_check.py" judge "$STATE_DIR/repair-check.json" "$STATE_DIR/documents/IMPLEMENTATION_NOTES.json")" || status=$?
    if [[ "$status" == 0 ]]; then
        rm -f "$STATE_DIR/repair-retry" "$STATE_DIR/repair-noop-count" "$STATE_DIR/REPAIR_BRIEF.md"
        return 0
    fi
    if [[ "$status" == 4 ]]; then
        # Real work occurred. Do not demand a second repair merely because a
        # remaining finding names a file that was already fixed in an earlier
        # pass, or because the correct proof is a transient mutation that was
        # deliberately restored. Both are common for ASSERTIONS/NEGATIVE.
        # The only honest arbiter now is a fresh driver green check and fresh
        # canonical test review, which the caller runs after a successful
        # return. A still-failing row will then open one new repair with fresh
        # evidence rather than looping on stale snapshot paths.
        echo
        echo "Repair pass changed files for some findings but none for: $(printf '%s' "$unrepaired" | tr '\n' ' ')"
        echo "Refreshing verification and canonical review before considering another repair."
        rm -f "$STATE_DIR/repair-noop-count"
        rm -f "$STATE_DIR/repair-retry" "$STATE_DIR/REPAIR_BRIEF.md"
        return 0
    fi
    if [[ "$status" != 1 ]]; then
        echo "Could not judge the repair pass (repair_check.py exited $status)."
        return 1
    fi
    # A protected plan command can fail even when the product tree is already
    # correct.  A non-CODING plan-blockers entry is the repair agent's
    # structured proof of that condition. Source repair cannot amend an
    # approved plan, so return the canonical blocker packet to UPDATED_PLAN.
    if [[ "$report" == "$STATE_DIR/green-check.md" ]] \
        && python3 -B "$ROOT/scripts/lib/repair_plan_route.py" \
            "$STATE_DIR/documents/IMPLEMENTATION_NOTES.json" "$STATE_DIR/green-check.tsv" \
            "$STATE_DIR/documents/REPAIR_PLAN_BLOCKERS.json"; then
        echo 'Repair found a plan-owned verification blocker; returning to UPDATED_PLAN instead of retrying source repair.'
        count="$(cat "$STATE_DIR/repair-count" 2>/dev/null || printf 1)"
        case "$count" in ''|*[!0-9]*) count=1 ;; esac
        count=$((10#$count - 1)); [[ "$count" -ge 0 ]] || count=0
        printf '%s\n' "$count" > "$STATE_DIR/repair-count"
        rm -f "$STATE_DIR/repair-retry" "$STATE_DIR/repair-noop-count" "$STATE_DIR/REPAIR_BRIEF.md"
        set_state UPDATED_PLAN
        return 5
    fi
    echo
    echo "Repair pass changed none of the files these findings name: $(printf '%s' "$unrepaired" | tr '\n' ' ')"
    echo "A report is not a repair. This pass is not reviewed and does not count"
    echo "against the repair limit."
    supervision_validation_failed repair "$STATE_DIR/documents/IMPLEMENTATION_NOTES.json" \
        "Repair changed no file named by: $(printf '%s' "$unrepaired" | tr '\n' ' ')" 0 || true
    count="$(cat "$STATE_DIR/repair-count" 2>/dev/null || printf 1)"
    count=$((10#$count - 1))
    [[ "$count" -ge 0 ]] || count=0
    printf '%s\n' "$count" > "$STATE_DIR/repair-count"
    noops="$(cat "$STATE_DIR/repair-noop-count" 2>/dev/null || printf 0)"
    case "$noops" in ''|*[!0-9]*) noops=0 ;; esac
    if [[ "$noops" -ge 1 ]]; then
        echo "That is the second pass in a row that changed nothing. Stopping for a person:"
        echo "resolve the findings in $report by hand, or set repair.model in .uncle/config"
        echo "to a stronger model, then re-run to resume."
        rm -f "$STATE_DIR/repair-retry"
        triage_stop_reason "$STATE_DIR" human
        return 1
    fi
    printf '%s\n' $((noops + 1)) > "$STATE_DIR/repair-noop-count"
    # shellcheck disable=SC2086
    python3 -B "$ROOT/scripts/lib/repair_check.py" brief "$report" "$STATE_DIR/repair-check.json" \
        "$STATE_DIR/REPAIR_BRIEF.md" $unrepaired || return 1
    : > "$STATE_DIR/repair-retry"
    echo "Retrying once with a driver-written brief of what is still open:"
    echo "  $STATE_DIR/REPAIR_BRIEF.md"
    return 3
}
