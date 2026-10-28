#!/usr/bin/env bash
# The plan's verification commands, run wholly in the background.
#
# They never change the build, and in an unattended run a failure does not change what the run does next, so nothing waits for
# them: they start when implementation ends and run beside the test review, the checklist and its execution.  They run in a
# private copy of the project (isolated_verify.py) with the project's port moved, because the checklist's workers start the same
# application on the same port.  Until they finish, the result files say PENDING (a status no stage counts as a failure and none
# reads as a pass); when they finish, the copy publishes real results over them.
#
# On by default for an unattended run.  WORKFLOW_BACKGROUND_VERIFY=1 turns it on for any run, =0 off.

GREEN_BG_PID=""

green_background_enabled() {
    [[ "${GREEN_CHECK:-1}" == 1 ]] || return 1
    case "${WORKFLOW_BACKGROUND_VERIFY:-}" in
        1) return 0 ;;
        0) return 1 ;;
    esac
    [[ "${UNATTENDED:-0}" == 1 ]]
}

# True while the background run for this driver is still going.
green_pending() {
    [[ -e "$STATE_DIR/green-background.pending" && -n "$GREEN_BG_PID" ]] && kill -0 "$GREEN_BG_PID" 2>/dev/null
}

green_kill_tree() {
    local pid="$1" child
    for child in $(pgrep -P "$pid" 2>/dev/null); do green_kill_tree "$child"; done
    kill "$pid" 2>/dev/null || true
}

# The code is about to change, or the run is ending: whatever is running is of no use.
green_background_cancel() {
    if [[ -n "$GREEN_BG_PID" ]] && kill -0 "$GREEN_BG_PID" 2>/dev/null; then
        green_kill_tree "$GREEN_BG_PID"
        wait "$GREEN_BG_PID" 2>/dev/null || true
    fi
    GREEN_BG_PID=""
    rm -f "$STATE_DIR/green-background.pending"
}

# Replace the result files with a placeholder that says what is happening.
green_background_placeholder() {
    local state="$1" detail="$2"
    awk -v state="$state" 'NF { printf "%s\t%s\n", state, $0 }' "$GREEN_CMDS" > "$GREEN_CLASS.new" && mv -f "$GREEN_CLASS.new" "$GREEN_CLASS"
    {
        echo '## Green check'
        echo
        echo "$detail"
        echo
        echo '| Result | Command |'
        echo '|---|---|'
        awk -v state="$state" 'NF { printf "| %s | `%s` |\n", state, $0 }' "$GREEN_CMDS"
    } > "$GREEN_MD.new" && mv -f "$GREEN_MD.new" "$GREEN_MD"
}

# Start the verification commands in the background.  Returns at once.
green_check_background_start() {
    local background="$STATE_DIR/green-background" fingerprint
    green_background_cancel
    rm -rf "$background"; mkdir -p "$background"
    verify_commands .uncle/docs/UPDATED_PROJECT_PLAN.md > "$GREEN_CMDS" 2>/dev/null || true
    python3 -B "$ROOT/scripts/lib/install_command.py" normalize "$GREEN_CMDS" . > /dev/null 2>&1 || true
    if [[ ! -s "$GREEN_CMDS" ]]; then
        run_green_check          # nothing to run: the foreground path says so
        return
    fi
    fingerprint="$(python3 -B "$ROOT/scripts/lib/tree_fingerprint.py" "$PWD" "$GREEN_CMDS" 2>/dev/null || true)"
    printf '%s\n' "$fingerprint" > "$background/start.fingerprint"
    rm -f "$GREEN_CUR" "$STATE_DIR/green-check.fingerprint" "$GREEN_OVERRIDE_FILE"
    green_background_placeholder PENDING 'PENDING: the verification commands are running in the background. This file is replaced with their results when they finish; no stage waits for them.'
    : > "$STATE_DIR/green-background.pending"
    echo "Verification commands started in the background ($(wc -l < "$GREEN_CMDS" | tr -d ' ') command(s)); nothing waits for them."
    (
        local copy="$background/project" real_class="$GREEN_CLASS" real_md="$GREEN_MD" real_cur="$GREEN_CUR" real_cmds="$GREEN_CMDS" status=0
        local project="$PWD"
        python3 -B "$ROOT/scripts/lib/isolated_verify.py" prepare "$project" "$copy" > "$background/ports.json" 2> "$background/prepare.err" || status=$?
        if [[ "$status" == 0 ]]; then
            (
                cd "$copy" || exit 1
                GREEN_CMDS="$background/green-check.commands"; GREEN_CUR="$background/green-check.current.tsv"
                GREEN_CLASS="$background/green-check.tsv"; GREEN_MD="$background/green-check.md"
                export UNCLE_PROJECT_ROOT="$copy" UNCLE_GREEN_BACKGROUND=1
                # The protected files are checked where they live: the copy's port is moved on purpose, so its hashes differ from
                # the approved ones (noinit: "protected inputs changed", REPAIR, implementation and the checklist run again).
                # The project itself is not touched while this runs, and every later stage checks it.
                eval "$(declare -f green_run | sed '1s/green_run/green_run_guarded/')"
                green_run() { green_run_guarded "$1" "$2" "$3" "" "${5:-}"; }
                check_verification_inputs() { return 0; }
                run_green_check
            ) || status=$?
        fi
        green_background_publish "$project" "$copy" "$status" "$background" "$real_class" "$real_md" "$real_cur" "$real_cmds"
    ) > "$LOG_DIR/green-background.log" 2>&1 < /dev/null &
    GREEN_BG_PID=$!
    declare -f early_checklist_start > /dev/null && early_checklist_start
}

# The run finished: put its results where every stage looks, then clear the pending mark (last, so a reader never sees the
# mark gone and the old placeholder still there).
green_background_publish() {
    local project="$1" copy="$2" status="$3" background="$4" real_class="$5" real_md="$6" real_cur="$7" real_cmds="$8" failures after
    python3 -B "$ROOT/scripts/lib/isolated_verify.py" finish "$project" "$copy" 2>/dev/null || true
    if [[ -s "$background/green-check.tsv" && -s "$background/green-check.md" ]]; then
        cp "$background/green-check.current.tsv" "$real_cur" 2>/dev/null || true
        cp "$background/green-check.commands" "$real_cmds" 2>/dev/null || true
        cp "$background/green-check.md" "$real_md.new" && mv -f "$real_md.new" "$real_md"
        cp "$background/green-check.tsv" "$real_class.new" && mv -f "$real_class.new" "$real_class"
        python3 -B "$ROOT/scripts/lib/test_report.py" from-green . application "$real_cur" "$LOG_DIR/green-check.log" 2>/dev/null || true
        failures="$(green_regressions "$real_class")"
        after="$(python3 -B "$ROOT/scripts/lib/tree_fingerprint.py" "$project" "$real_cmds" 2>/dev/null || true)"
        if [[ "$after" == "$(cat "$background/start.fingerprint" 2>/dev/null)" && -n "$after" ]]; then
            printf '%s %s\n' "$after" "$([[ "$failures" == 0 ]] && echo clean || echo failed)" > "$STATE_DIR/green-check.fingerprint"
        else
            rm -f "$STATE_DIR/green-check.fingerprint"      # the tree moved while the commands ran: the result describes another tree
        fi
        if [[ "$failures" -gt 0 ]]; then
            record_nonblocking_failure green-check "$failures failed verification check(s); they ran in the background and changed nothing"
            record_test_failure_disposition || true
            printf '%s\t%s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$failures failing check(s) continued automatically (background verification)" \
                > "$GREEN_OVERRIDE_FILE"
        fi
        echo "Background verification finished: $failures failed command(s)."
    else
        green_background_placeholder "NOT RUN" "NOT RUN: the verification commands could not run in the background (status $status). See $LOG_DIR/green-background.log."
        echo "Background verification did not produce results (status $status)."
    fi
    rm -f "$STATE_DIR/green-background.pending"
}

# What the stages call instead of run_green_check.  In the foreground (attended) it is run_green_check; in the background it
# starts the commands unless a run for this exact tree is already going or has finished.
run_green_check_auto() {
    green_background_enabled || { run_green_check; return; }
    local now remembered
    verify_commands .uncle/docs/UPDATED_PROJECT_PLAN.md > "$GREEN_CMDS" 2>/dev/null || true
    now="$(python3 -B "$ROOT/scripts/lib/tree_fingerprint.py" "$PWD" "$GREEN_CMDS" 2>/dev/null || true)"
    if green_pending && [[ -n "$now" && "$now" == "$(cat "$STATE_DIR/green-background/start.fingerprint" 2>/dev/null)" ]]; then
        echo 'Verification is already running in the background for this tree.'
        return 0
    fi
    remembered="$(cut -d' ' -f1 "$STATE_DIR/green-check.fingerprint" 2>/dev/null)"
    if ! green_pending && [[ -n "$now" && "$now" == "$remembered" && -s "$GREEN_CLASS" ]] && ! grep -q '^PENDING' "$GREEN_CLASS" 2>/dev/null; then
        echo 'Verification already ran on this exact tree; reusing that result.'
        return 0
    fi
    green_check_background_start
}

# A driver that starts after another one died mid-run finds the placeholder and no process behind it.
green_background_recover() {
    if [[ -e "$STATE_DIR/green-background.pending" && -z "$GREEN_BG_PID" ]]; then
        rm -f "$STATE_DIR/green-background.pending"
        if grep -q '^PENDING' "$GREEN_CLASS" 2>/dev/null; then
            rm -f "$GREEN_CLASS" "$GREEN_MD"
            echo 'A background verification run was cut short; its placeholder was removed. Rerun the implementation stage to verify again.'
        fi
    fi
}
