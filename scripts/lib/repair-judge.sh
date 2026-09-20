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
    local report
    report="$(cat "$STATE_DIR/repair-source")"
    python3 -B "$ROOT/scripts/lib/repair_check.py" snapshot "$report" "$STATE_DIR/repair-check.json" || return 1
    REPAIR_PROMPT="prompts/repair.md"
    if [[ -e "$STATE_DIR/repair-retry" && -s "$STATE_DIR/REPAIR_BRIEF.md" ]]; then
        {
            cat "$(resolve_prompt prompts/repair.md)"
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
    unrepaired="$(python3 -B "$ROOT/scripts/lib/repair_check.py" judge "$STATE_DIR/repair-check.json" IMPLEMENTATION_NOTES.md)" || status=$?
    if [[ "$status" == 0 ]]; then
        rm -f "$STATE_DIR/repair-retry" "$STATE_DIR/repair-noop-count" "$STATE_DIR/REPAIR_BRIEF.md"
        return 0
    fi
    if [[ "$status" == 4 ]]; then
        # Real work, but not on everything the review blocked on. A review now
        # would only re-state what the hashes already show, so the pass keeps
        # its attempt and the remaining findings are briefed for the next one.
        # WORKFLOW_MAX_REPAIRS bounds this, and reaching it asks a person.
        echo
        echo "Repair pass changed files for some findings but none for: $(printf '%s' "$unrepaired" | tr '\n' ' ')"
        echo "Continuing the repair on what is still open before any review."
        rm -f "$STATE_DIR/repair-noop-count"
        # shellcheck disable=SC2086
        python3 -B "$ROOT/scripts/lib/repair_check.py" brief "$report" "$STATE_DIR/repair-check.json" \
            "$STATE_DIR/REPAIR_BRIEF.md" $unrepaired || return 1
        : > "$STATE_DIR/repair-retry"
        echo "  $STATE_DIR/REPAIR_BRIEF.md"
        return 3
    fi
    if [[ "$status" != 1 ]]; then
        echo "Could not judge the repair pass (repair_check.py exited $status)."
        return 1
    fi
    echo
    echo "Repair pass changed none of the files these findings name: $(printf '%s' "$unrepaired" | tr '\n' ' ')"
    echo "A report is not a repair. This pass is not reviewed and does not count"
    echo "against the repair limit."
    supervision_validation_failed repair IMPLEMENTATION_NOTES.md \
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
