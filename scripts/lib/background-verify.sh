#!/usr/bin/env bash
# The plan's verification commands, run wholly in the background.
#
# They never change the build, and in an unattended run a failure does not change what the run does next, so nothing waits for
# them: they start when implementation ends and run while the implementation
# gate settles. Test-review and checklist workers consume the completed record,
# never the PENDING placeholder. They run in a
# private copy of the project (isolated_verify.py) with the project's port moved, because the checklist's workers start the same
# application on the same port.  Until they finish, the result files say PENDING (a status no stage counts as a failure and none
# reads as a pass); when they finish, the copy publishes real results over them.
#
# On by default for an unattended run.  WORKFLOW_BACKGROUND_VERIFY=1 turns it on for any run, =0 off.

GREEN_BG_PID=""

# The driver process can be resumed while verification keeps running in its
# detached child.  Keep that child's PID durably: an in-memory PID disappears
# on resume, which used to make the new driver start a second Chromium
# download against Playwright's per-user cache lock.
green_background_pid_file() {
    printf '%s' "$STATE_DIR/green-background.pid"
}

green_background_live_pid() {
    local pid_file pid
    pid_file="$(green_background_pid_file)"
    if [[ -n "$GREEN_BG_PID" ]] && kill -0 "$GREEN_BG_PID" 2>/dev/null; then
        printf '%s' "$GREEN_BG_PID"
        return 0
    fi
    [[ -s "$pid_file" ]] || return 1
    pid="$(cat "$pid_file" 2>/dev/null)"
    [[ "$pid" =~ ^[0-9]+$ ]] && kill -0 "$pid" 2>/dev/null || return 1
    GREEN_BG_PID="$pid"
    printf '%s' "$pid"
}

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
    [[ -e "$STATE_DIR/green-background.pending" ]] && green_background_live_pid >/dev/null
}

green_kill_tree() {
    local pid="$1" child
    for child in $(pgrep -P "$pid" 2>/dev/null); do green_kill_tree "$child"; done
    kill "$pid" 2>/dev/null || true
}

# The code is about to change, or the run is ending: whatever is running is of no use.
green_background_cancel() {
    local pid=""
    pid="$(green_background_live_pid 2>/dev/null || true)"
    if [[ -n "$pid" ]]; then
        green_kill_tree "$pid"
        wait "$pid" 2>/dev/null || true
    fi
    GREEN_BG_PID=""
    rm -f "$STATE_DIR/green-background.pending" "$STATE_DIR/green-background.main-done" "$(green_background_pid_file)"
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

# Whether the defect-injection (mutation) command should run after the others have published. It needs a build and passing
# suites first and works in copies of the project, and nothing but the test review and the final audit reads its result, so the
# checklist should not wait for it (it took 88 s in a 771 s run, and the checklist started the moment it ended).
# WORKFLOW_DEFER_MUTATION=0 restores one combined result.
green_defer_mutation() {
    [[ "${WORKFLOW_DEFER_MUTATION:-1}" == 1 ]] || return 1
    grep -qiE 'mutat|defect|inject' "$1" 2>/dev/null && grep -qiEv 'mutat|defect|inject' "$1" 2>/dev/null
}

# One verification phase, run inside the private copy: "" is every command, main the ordinary ones, mutation the defect-injection ones.
green_background_phase() {
    local copy="$1" background="$2" project="$3" phase="$4" prefix="$2"
    cd "$copy" || exit 1
    if [[ "$phase" == mutation ]]; then
        mkdir -p "$background/mutation"; prefix="$background/mutation"
        export GREEN_COMMAND_FILTER=mutation GREEN_LOG="$LOG_DIR/green-check.mutation.log"
    elif [[ "$phase" == main ]]; then
        export GREEN_COMMAND_FILTER=main
    fi
    [[ -z "$phase" ]] || export WORKFLOW_GREEN_CHECK_REUSE=0
    GREEN_CMDS="$prefix/green-check.commands"; GREEN_CUR="$prefix/green-check.current.tsv"
    GREEN_CLASS="$prefix/green-check.tsv"; GREEN_MD="$prefix/green-check.md"
    export UNCLE_PROJECT_ROOT="$copy" UNCLE_GREEN_BACKGROUND=1 UNCLE_ORIGINAL_PROJECT_ROOT="$project"
    # The protected files are checked where they live: the copy's port is moved on purpose, so its hashes differ from
    # the approved ones (noinit: "protected inputs changed", REPAIR, implementation and the checklist run again).
    # The project itself is not touched while this runs, and every later stage checks it.
    eval "$(declare -f green_run | sed '1s/green_run/green_run_guarded/')"
    green_run() { green_run_guarded "$1" "$2" "$3" "" "${5:-}"; }
    check_verification_inputs() { return 0; }
    run_green_check
}

# The ordinary commands have finished: put their result where every stage looks and let the checklist go. The defect-injection
# command is still to run, so the pending mark stays until green_background_publish.
green_background_publish_interim() {
    local project="$1" background="$2" real_class="$3" real_md="$4" real_cur="$5"
    cp "$background/green-check.current.tsv" "$real_cur" 2>/dev/null || true
    {
        cat "$background/green-check.md"
        printf '\nThe defect-injection check is still running; its result is added to this report when it finishes.\n'
    } > "$real_md.new" && mv -f "$real_md.new" "$real_md"
    cp "$background/green-check.tsv" "$real_class.new" && mv -f "$real_class.new" "$real_class"
    python3 -B "$ROOT/scripts/lib/test_report.py" from-green . application "$real_cur" "$LOG_DIR/green-check.log" 2>/dev/null || true
    touch "$STATE_DIR/green-background.main-done"
    echo "Background verification: build, unit and browser commands finished; the defect-injection check continues beside the checklist."
}

# Fold the defect-injection result into the single record every later stage reads.
green_background_merge_mutation() {
    local background="$1" real_cmds="$2" mutation="$1/mutation"
    if [[ -s "$mutation/green-check.current.tsv" ]]; then
        cat "$background/green-check.current.tsv" "$mutation/green-check.current.tsv" > "$background/combined.current.tsv"
    else
        # The phase produced nothing (it could not start): the command was not run, which is not a pass.
        { cat "$background/green-check.current.tsv"; grep -iE 'mutat|defect|inject' "$real_cmds" | awk 'NF { printf "125\t%s\n", $0 }'; } > "$background/combined.current.tsv"
    fi
    mv -f "$background/combined.current.tsv" "$background/green-check.current.tsv"
    if [[ -s "$LOG_DIR/green-check.mutation.log" ]]; then
        cat "$LOG_DIR/green-check.mutation.log" >> "$LOG_DIR/green-check.log"
    fi
    rm -f "$LOG_DIR/green-check.mutation.log"
    cp "$real_cmds" "$background/green-check.commands"
    green_classify "$STATE_DIR/green-check.no-baseline" "$background/green-check.current.tsv" > "$background/green-check.tsv"
    green_report "$background/green-check.tsv" "$background/green-check.md" .uncle/docs/UPDATED_PROJECT_PLAN.md "$LOG_DIR/green-check.log" 0
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
    green_background_placeholder PENDING 'PENDING: the verification commands are running in the background. This file is replaced with their results before checklist work begins.'
    rm -f "$STATE_DIR/green-background.main-done"
    : > "$STATE_DIR/green-background.pending"
    local defer=0
    green_defer_mutation "$GREEN_CMDS" && defer=1
    echo "Verification commands started in the background ($(wc -l < "$GREEN_CMDS" | tr -d ' ') command(s)); test review may overlap, then checklist work waits for the published result."
    [[ "$defer" != 1 ]] || echo "The defect-injection check runs after the other commands publish, beside the checklist."
    (
        local copy="$background/project" real_class="$GREEN_CLASS" real_md="$GREEN_MD" real_cur="$GREEN_CUR" real_cmds="$GREEN_CMDS" status=0
        local project="$PWD"
        python3 -B "$ROOT/scripts/lib/isolated_verify.py" prepare "$project" "$copy" > "$background/ports.json" 2> "$background/prepare.err" || status=$?
        if [[ "$status" == 0 ]]; then
            if [[ "$defer" == 1 ]]; then
                ( green_background_phase "$copy" "$background" "$project" main ) || status=$?
                if [[ -s "$background/green-check.tsv" && -s "$background/green-check.md" ]]; then
                    green_background_publish_interim "$project" "$background" "$real_class" "$real_md" "$real_cur"
                    ( green_background_phase "$copy" "$background" "$project" mutation ) || true
                    green_background_merge_mutation "$background" "$real_cmds"
                fi
            else
                ( green_background_phase "$copy" "$background" "$project" "" ) || status=$?
            fi
        fi
        green_background_publish "$project" "$copy" "$status" "$background" "$real_class" "$real_md" "$real_cur" "$real_cmds"
    ) > "$LOG_DIR/green-background.log" 2>&1 < /dev/null &
    GREEN_BG_PID=$!
    printf '%s\n' "$GREEN_BG_PID" > "$(green_background_pid_file)"
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
            # A failed background run is only a result. It is not a decision to continue: writing the override file here (as this
            # once did) made TEST_REVIEW skip repair and made COMPLETE say "by human override" for a run no human touched. The
            # consumers route it through green_failure_route (repair first, then continue/ask) and record any continuation themselves.
            record_test_failure_disposition || true
        fi
        echo "Background verification finished: $failures failed command(s)."
    else
        green_background_placeholder "NOT RUN" "NOT RUN: the verification commands could not run in the background (status $status). See $LOG_DIR/green-background.log."
        echo "Background verification did not produce results (status $status)."
    fi
    rm -f "$STATE_DIR/green-background.pending" "$STATE_DIR/green-background.main-done" "$(green_background_pid_file)"
}

# What the stages call instead of run_green_check.  In the foreground (attended) it is run_green_check; in the background it
# starts the commands unless a run for this exact tree is already going or has finished.
run_green_check_auto() {
    green_background_enabled || { run_green_check; return; }
    local now remembered
    verify_commands .uncle/docs/UPDATED_PROJECT_PLAN.md > "$GREEN_CMDS" 2>/dev/null || true
    python3 -B "$ROOT/scripts/lib/install_command.py" normalize "$GREEN_CMDS" . > /dev/null 2>&1 || true
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

# Wait for a completed driver record before a consumer needs verification
# evidence. A failed result is still usable evidence; only PENDING is
# incomplete. Callers decide whether a recorded failure is repairable,
# nonblocking, or terminal.
green_wait_final() {
    # Every caller is a consumer of final evidence (test review, the checklists, the audit), none of them the implementation fan-out, so
    # the default is to wait. A review launched against PENDING can only report NOT RUN, and its packet cannot be repaired by publishing
    # the results later: the failing rows it wrote opened a repair that spent an attempt on timing, not on the code.
    # WORKFLOW_WAIT_FOR_GREEN=0 restores continuing without waiting.
    if [[ "${WORKFLOW_WAIT_FOR_GREEN:-1}" != 1 ]]; then
        if green_pending || grep -q '^PENDING' "$GREEN_CLASS" 2>/dev/null; then
            echo 'Verification is pending; continuing without waiting. Pending checks are not passes.'
        fi
        return 0
    fi
    local pid="${GREEN_BG_PID:-}"
    if green_pending; then
        pid="$GREEN_BG_PID"
        echo 'Waiting for the driver green-check before checklist work.'
        # `wait` works for a child of this shell. After an unattended resume
        # it is another driver's child, so poll its durable PID instead.
        wait "$pid" 2>/dev/null || {
            while [[ -e "$STATE_DIR/green-background.pending" ]] && kill -0 "$pid" 2>/dev/null; do
                sleep 0.5
            done
        }
        GREEN_BG_PID=""
    fi
    # A completed failing check is still final evidence.  Only a live
    # placeholder is unsafe for a worker to consume.
    ! grep -q '^PENDING' "$GREEN_CLASS" 2>/dev/null
}

# Like green_wait_final, but returns as soon as the ordinary commands (build, unit, browser) have published. The checklist observes
# the application itself and needs those, not the defect-injection result, which only the test review and the final audit read.
green_wait_main() {
    if [[ "${WORKFLOW_WAIT_FOR_GREEN:-1}" != 1 ]]; then green_wait_final; return; fi
    if green_pending && [[ ! -e "$STATE_DIR/green-background.main-done" ]]; then
        echo 'Waiting for the driver green-check (build, unit and browser commands) before checklist work.'
        while green_pending && [[ ! -e "$STATE_DIR/green-background.main-done" ]]; do sleep 0.5; done
    fi
    ! grep -q '^PENDING' "$GREEN_CLASS" 2>/dev/null
}

# A driver that starts after another one died mid-run finds the placeholder and no process behind it.
green_background_recover() {
    if [[ -e "$STATE_DIR/green-background.pending" ]] && green_pending; then
        echo 'Background verification from this run is still active; reusing it.'
        return 0
    fi
    if [[ -e "$STATE_DIR/green-background.pending" ]]; then
        rm -f "$STATE_DIR/green-background.pending"
        rm -f "$(green_background_pid_file)"
        if grep -q '^PENDING' "$GREEN_CLASS" 2>/dev/null; then
            rm -f "$GREEN_CLASS" "$GREEN_MD"
            echo 'A background verification run was cut short; its placeholder was removed. Rerun the implementation stage to verify again.'
        fi
    fi
}
