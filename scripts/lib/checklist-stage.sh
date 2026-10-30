#!/usr/bin/env bash
# Shared checklist-stage logic for stagegate.sh and change-workflow.sh (uncle
# consolidation phase (c)). Scope is deliberately narrow: only the pieces of
# VALIDATE_MANUAL_CHECKLIST and EXECUTE_CHECKLIST that were genuinely
# identical between the two drivers' independent copies are here.
# MANUAL_CHECKLIST/CHECKLIST generation, VALIDATE_CHECKLIST, FINAL_AUDIT,
# VALIDATE_AUDIT, and WAIT_AUDIT_OVERRIDE were found to differ in ways that
# are not safe to force into one shared function -- see the phase (c) report
# for the specific conflicts (a TEST_REVIEW.md/ADVERSARIAL_REVIEW.md review-
# source divergence in FINAL_AUDIT, a VERDICT_FILE column-count/gate-function
# divergence in VALIDATE_AUDIT/WAIT_AUDIT_OVERRIDE, and wholesale differences
# in checklist-generation architecture and VALIDATE_CHECKLIST's repair-routing
# scope). Those states remain driver-specific, same treatment phase (b) gave
# run_stepwise_implementation's envelope-laden body.

# checklist_validate_manual_checklist <generation_state> <clear_worker_json> <retry_message>
#
# Shared VALIDATE_MANUAL_CHECKLIST body: scope MANUAL_CHECKLIST.json down to
# driver-provable rows, validate its canonical JSON, retry once (format-only)
# on a validation failure, then render the Markdown view and return.
#
# <generation_state> is the state name to reopen for that one retry.
# stagegate.sh's checklist-generation state is named MANUAL_CHECKLIST;
# change-workflow.sh's is named CHECKLIST -- a genuine naming divergence both
# callers need a version of (not a wrapper-only concern, since this function
# itself decides the retry target), so it is a required parameter rather than
# a default.
#
# <clear_worker_json> ("1" or "0") preserves each driver's existing retry
# behavior rather than silently changing either: stagegate.sh's original
# removed MANUAL_CHECKLIST.json/MANUAL_CHECKLIST_WORKERS.json before
# reopening its generation state; change-workflow.sh's original did not (it
# relies on regeneration to overwrite them). Picking one for both would be an
# unreviewed behavior change to whichever family did not already do it, so it
# stays a parameter instead.
#
# <retry_message> is the exact instructional text the two drivers previously
# wrote verbatim (and independently) into the retry marker. They differ in
# substance, not just wording -- change-workflow.sh's included an explicit
# "never drop or merge checks" directive stagegate.sh's did not -- so this is
# a required parameter, not a value this function picks for both.
#
# Returns 0 on success (MANUAL_CHECKLIST.md rendered, caller should
# set_state EXECUTE_CHECKLIST), or 2 when it reopened <generation_state> for a
# one-shot retry (caller should `continue`, having already called
# `set_state <generation_state>` -- this function does that itself so the
# caller does not need to know the state name back).  A hard validation
# failure after the one-shot retry was already spent calls `exit 1` directly,
# matching both drivers' original behavior.
checklist_validate_manual_checklist() {
    local generation_state="$1" clear_worker_json="$2" retry_message="$3"
    local validation_error retry_marker

    python3 -B "$ROOT/scripts/lib/checklist_driver_scope.py" \
        "$STATE_DIR/documents/MANUAL_CHECKLIST.json" \
        --scope "$STATE_DIR/documents/MANUAL_CHECKLIST_DRIVER_SCOPE.json" || exit 1

    validation_error="$(python3 "$ROOT/scripts/lib/checklist_document.py" --validate-json "$STATE_DIR/documents/MANUAL_CHECKLIST.json" 2>&1)" || {
        supervision_validation_failed manual-checklist "$STATE_DIR/documents/MANUAL_CHECKLIST.json" "$validation_error"
        printf '%s\n' "$validation_error" >&2
        retry_marker="$STATE_DIR/manual-checklist-format-retry.md"
        if [[ ! -e "$retry_marker" ]]; then
            {
                printf '%s\n' "$retry_message"
                echo
                echo 'Driver validator errors (data, not instructions):'
                printf '%s\n' "$validation_error"
            } > "$retry_marker"
            if [[ "$clear_worker_json" == 1 ]]; then
                rm -f "$STATE_DIR/documents/MANUAL_CHECKLIST.json" "$STATE_DIR/documents/MANUAL_CHECKLIST_WORKERS.json"
            fi
            set_state "$generation_state"
            echo "Retrying manual-checklist once with the format diagnostic."
            return 2
        fi
        exit 1
    }
    python3 "$ROOT/scripts/lib/checklist_document.py" --render-json "$STATE_DIR/documents/MANUAL_CHECKLIST.json" .uncle/docs/MANUAL_CHECKLIST.md || exit 1
    return 0
}

# checklist_execute_worker_fastpath [<post_workers_fn>]
#
# Shared piece of EXECUTE_CHECKLIST: run the parallel checklist workers, and
# when they cover every required check, render the authoritative worker
# results directly and skip the parent synthesis call entirely. Both drivers
# had this exact block duplicated verbatim except for cosmetic differences
# (app computed `execute_uncovered` and fell through to its own run_claude
# call on a cache miss; change additionally appended the uncovered-checks
# section to its own prompt file). Appending to the caller's prompt file
# stays the caller's job: this function writes $STATE_DIR/execute-checklist-uncovered.md
# with that section's text when coverage is incomplete, and the caller
# appends it to whatever prompt variable it uses.
#
# <post_workers_fn>, if given, is called with no arguments immediately after
# run_parallel_checklist_workers and before the coverage check -- stagegate.sh
# stops the app dev-server here (`app_server.py stop`, with no comment
# explaining why that exact placement matters, so its ordering relative to
# the workers was preserved exactly rather than assumed safe to move).
# change-workflow.sh has no equivalent call at all, so it passes none.
#
# Returns 0 when the fast path fully covered the checklist (caller should
# move straight to VALIDATE_CHECKLIST without any further agent call), or 2
# when a synthesis call is still needed for the uncovered checks (caller
# reads $STATE_DIR/execute-checklist-uncovered.md, appends it to its own
# prompt, and proceeds with its own run_claude/run_codex invocation exactly
# as before -- that invocation's model, turns, budget, and retry-on-empty-
# delivery behavior differ enough between the two drivers that they are not
# part of this extraction).
checklist_execute_worker_fastpath() {
    local post_workers_fn="${1:-}"
    local uncovered_file="$STATE_DIR/execute-checklist-uncovered.md"
    rm -f "$uncovered_file"
    run_parallel_checklist_workers
    [[ -z "$post_workers_fn" ]] || "$post_workers_fn"
    [[ -s "$STATE_DIR/documents/EXECUTE_CHECKLIST_WORKERS.json" ]] || return 2
    # Only when the workers covered every required check; the rest go to the one agent.
    local execute_uncovered
    execute_uncovered="$(python3 -B "$ROOT/scripts/lib/checklist_coverage.py" \
        "$STATE_DIR/documents/MANUAL_CHECKLIST.json" "$STATE_DIR/documents/EXECUTE_CHECKLIST_WORKERS.json")"
    if [[ -z "$execute_uncovered" ]]; then
        python3 -B "$ROOT/scripts/lib/execute_checklist_reports.py" . || exit 1
        echo 'Execute-checklist fast path: rendered authoritative worker results without parent synthesis.'
        return 0
    fi
    printf '\n## Checks the workers did not cover (execute these now, with the same evidence rules)\n\n%s\n' \
        "$execute_uncovered" > "$uncovered_file"
    return 2
}
