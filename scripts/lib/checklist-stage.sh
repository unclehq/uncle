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

# checklist_bind_worker_template <checklist_input> <workers_output_name> -- the template every checklist worker of one lane set is given,
# in CHECKLIST_WORKER_TEMPLATE: the worker prompt plus two bound sections, where the application is already running (the driver starts
# it) and which checklist file holds the rows. Without them a worker is told only an id and has nothing to run it against, and reports
# BLOCKED-SETUP ("gives no checklist JSON path and no application URL"): that is what the change workflow did, with its own copy of
# this, until it shared this one -- all nine required rows blocked, in twelve seconds, and the change never looked at in a browser.
# Needs from the caller: ROOT, STATE_DIR, PWD (the project).
checklist_bind_worker_template() {
    local checklist_input="$1" output_name="$2"
    # A worker may not start a server (noinit: `npm run start` was denied and five browser checks were BLOCKED-SETUP after 86 s), so the
    # driver starts the application and every worker is told where it is.
    local worker_template="$ROOT/prompts/change/execute-checklist-worker.md" app_url=""
    if [[ "${WORKFLOW_CHECKLIST_APP_SERVER:-1}" == 1 ]] && app_url="$(python3 -B "$ROOT/scripts/lib/app_server.py" start "$PWD" "$STATE_DIR" 2>/dev/null)" && [[ -n "$app_url" ]]; then
        worker_template="$STATE_DIR/execute-checklist-worker-template.md"
        { cat "$ROOT/prompts/change/execute-checklist-worker.md"
          printf '\n## The application is already running (binding)\n\nThe driver started the application and it answers at %s. Drive that URL in the browser and with curl. Do not start, build or install anything yourself, and do not run `npm run start`, `vite` or any server: it is already up, and you are not allowed to start one.\n' "$app_url"
        } > "$worker_template"
        echo "Checklist: the application is running at $app_url for the browser checks."
    elif [[ "${WORKFLOW_CHECKLIST_APP_SERVER:-1}" == 1 ]]; then
        echo 'Checklist: the application could not be started by the driver; browser checks that need a running page may be BLOCKED-SETUP.'
    fi
    # A streamed lens is its own complete, validated checklist slice. Every
    # worker gets its exact immutable input instead of guessing the default.
    local bound_template="$STATE_DIR/execute-checklist-worker-$output_name.md"
    cp "$worker_template" "$bound_template"
    printf '\n## Checklist input (binding)\n\nRead only `%s` for checklist rows in this lane. Do not read any other checklist document.\n' \
        "$checklist_input" >> "$bound_template"
    CHECKLIST_WORKER_TEMPLATE="$bound_template"
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
    # Rows the early run already passed, on the same row and the same application files, are not executed again (early_checklist.py);
    # only the rest run, and the two are merged into the one workers document the rest of the stage reads. Nothing reusable, or any
    # problem with it, and every row runs exactly as it always did.
    # Rows started beside the test review finish (and are recorded against the application they started on) before anything is reused.
    # The rows the reconciliation changed or added cannot reuse anything, so they start now, beside the early rows still running.
    if declare -F early_checklist_changed_start > /dev/null; then early_checklist_changed_start || true; fi
    if declare -F early_checklist_beside_review_finish > /dev/null; then early_checklist_beside_review_finish || true; fi
    if declare -F early_checklist_reuse_prepare > /dev/null && early_checklist_reuse_prepare 2> /dev/null; then
        local early_dir="$STATE_DIR/early-checklist" fresh="$STATE_DIR/documents/EXECUTE_CHECKLIST_WORKERS.fresh.json" fresh_arg=-
        : > "$fresh"
        # Rows already run beside the early rows (changed or added by the reconciliation) are not run again.
        if [[ -s "$early_dir/changed.workers.json" ]]; then
            python3 -B "$ROOT/scripts/lib/early_checklist.py" exclude "$early_dir/reduced.json" "$early_dir/changed.workers.json" "$early_dir/reduced.rest.json" \
                && cp "$early_dir/reduced.rest.json" "$early_dir/reduced.json"
        fi
        if python3 -c 'import json,sys; sys.exit(0 if json.load(open(sys.argv[1])).get("checks") else 1)' "$early_dir/reduced.json" 2> /dev/null; then
            run_parallel_checklist_workers "$early_dir/reduced.json" "$fresh"
        fi
        if [[ -s "$early_dir/changed.workers.json" ]]; then
            if [[ -s "$fresh" ]]; then
                python3 -B "$ROOT/scripts/lib/early_checklist.py" merge-early "$early_dir/changed.workers.json" "$fresh" "$early_dir/fresh.merged.json" \
                    && cp "$early_dir/fresh.merged.json" "$fresh"
            else
                cp "$early_dir/changed.workers.json" "$fresh"
            fi
        fi
        [[ ! -s "$fresh" ]] || fresh_arg="$fresh"
        if python3 -B "$ROOT/scripts/lib/early_checklist.py" merge "$STATE_DIR/documents/MANUAL_CHECKLIST.json" "$early_dir/reused.json" \
                "$fresh_arg" "$STATE_DIR/documents/EXECUTE_CHECKLIST_WORKERS.json"; then
            echo "Checklist: $(python3 -c 'import json,sys; print(len(json.load(open(sys.argv[1]))))' "$early_dir/reused.json") row(s) already passed in the early run on this exact application; executing the rest."
        else
            : > "$STATE_DIR/documents/EXECUTE_CHECKLIST_WORKERS.json"
            run_parallel_checklist_workers
        fi
    else
        run_parallel_checklist_workers
    fi
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
