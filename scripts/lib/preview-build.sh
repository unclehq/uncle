#!/usr/bin/env bash
# Build something viewable from the brief, while the plan, the adversarial
# review and the updated plan are still being written.
#
# It starts as soon as the brief is approved, at the repository root where the
# implementation of record later rewrites it in place -- so the tab opened on
# the first look is the tab that shows the real application. It never runs at
# the same time as implementation (IMPLEMENT joins it first); it does run beside
# planning, whose prompts say what an unexplained page at the root is.
# PROJECT_PLAN.md and REQUIREMENTS_INTERPRETATION.md are used when they already
# exist and skipped when they do not.
#
# The operator asked to see the application before the review stages finish,
# accepting that it is paid for twice. That is the trade: wall clock is never
# worse -- the real implementation still starts where it always did -- and the
# tokens spent here buy an early look, not a shortcut.
#
# Nothing here is evidence. The preview build writes no test report, claims no
# check, and is never the implementation of record: the approved plan is
# implemented afterwards by the stage that always did it. When the review turns
# out not to have changed anything the code depends on, that stage finds the
# work already done and says so.
#
# On by default. WORKFLOW_PREVIEW_BUILD=0 turns it off.
#
# It costs an implementation that is usually thrown away: on the two runs
# measured, the review changed the plan the preview was built from both
# times. What it buys is a working application on screen while the review
# stages run, minutes before the first one would otherwise exist. Wall clock
# is never worse -- the real implementation still starts where it always
# did -- so the whole price is tokens.

# plan_material_hash lives here and is not otherwise sourced by the greenfield
# driver. Without it the survival check silently fails -- safe (it rebuilds) but
# the feature never works.
if ! declare -f plan_material_hash > /dev/null 2>&1; then
    . "${PREVIEW_LIB_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)}/plan-scope.sh"
fi

PREVIEW_BUILD="${WORKFLOW_PREVIEW_BUILD:-1}"
PREVIEW_PID=""
PREVIEW_STARTED=0

# preview_build_model — use the selected preview stage model. `preview-build`
# resolves to the first configured model stage in stage-config.sh, so its
# runner and model stay paired (e.g. an OpenCode `local/...` model runs through
# OpenCode rather than being handed to Cline). A dedicated environment override
# remains useful for one-off preview experiments.
preview_build_model() {
    if [[ -n "${WORKFLOW_MODEL_PREVIEW_BUILD:-}" ]]; then
        printf '%s' "$WORKFLOW_MODEL_PREVIEW_BUILD"
        return 0
    fi

    if declare -f uncle_has_config > /dev/null 2>&1 && uncle_has_config \
            && declare -f uncle_stage_model > /dev/null 2>&1 \
            && declare -f uncle_stage_runner > /dev/null 2>&1; then
        local runner model
        runner="$(uncle_stage_runner preview-build)"
        model="$(uncle_stage_model preview-build "$runner")"
        if [[ -n "$model" ]]; then
            printf '%s' "$model"
            return 0
        fi
    fi
    printf '%s' haiku
}

# preview_build_start — launch it, detached, and return immediately.
preview_build_start() {
    [[ "$PREVIEW_BUILD" == "1" ]] || return 0
    [[ "$PREVIEW_STARTED" == 0 ]] || return 0
    [[ -s PROJECT_PLAN.md || -s "${DOCUMENT_BUDGET_SOURCE:-REQUIREMENTS.md}" ]] || return 0

    # Only a web application or a command line tool has anything to show this
    # early. A library, an API or a daemon would spend an implementation's worth
    # of tokens producing nothing the operator can look at, which is the entire
    # justification for this stage.
    local kind
    kind="$(python3 -B "$ROOT/scripts/lib/preview_kind.py" . 2>/dev/null)" || kind=none
    if [[ "$kind" != webpage && "$kind" != command ]]; then
        echo "No preview build: the brief does not describe a web or command line"
        echo "application, so there would be nothing to show."
        return 0
    fi

    PREVIEW_STARTED=1
    # Taken before the preview writes anything. Otherwise the baseline is
    # captured after it, every preview file reads as something that was already
    # sitting in the directory, and the scope checks stop seeing it as output of
    # this build -- which is exactly what they exist to catch.
    if [[ -n "${UNTRACKED_BASELINE:-}" && ! -e "$UNTRACKED_BASELINE" ]] \
       && declare -f snapshot_untracked > /dev/null 2>&1; then
        snapshot_untracked "$UNTRACKED_BASELINE"
    fi
    # The plan this was built from, so the later stage can tell whether the
    # review changed anything the code depends on. A preview built from the
    # brief alone records nothing, and is never taken as built to the plan.
    rm -f "$STATE_DIR/preview-build.plan"
    if [[ -s PROJECT_PLAN.md ]]; then
        plan_material_hash PROJECT_PLAN.md > "$STATE_DIR/preview-build.plan" 2>/dev/null || true
    fi
    echo
    if [[ -s PROJECT_PLAN.md ]]; then
        echo "Building a $kind preview from the plan while the review runs."
    else
        echo "Building a $kind preview from the brief while planning runs."
    fi
    echo "It is a first look, not the implementation: the approved plan is"
    echo "implemented properly afterwards, and this is rebuilt if the review"
    echo "changes anything it depends on."
    # Two arguments only: the greenfield driver resolves model, effort, turns
    # and budget from the stage name itself. Passing them the way the change
    # driver does referenced variables that do not exist here, and the preview
    # died on an unbound variable before it wrote anything.
    (
        # The gates appended to every implementation prompt ask the agent to
        # record its launch method in .uncle/launch.json, and the preview agent
        # obliges. Nothing it wrote has been verified, and the implementation
        # of record writes the real one; whatever the preview leaves there is
        # put back the way it was.
        launch_before=""
        [[ -f .uncle/launch.json ]] && launch_before="$(cat .uncle/launch.json)"
        status=0
        # A throwaway first look does not need the top tier deliberating over
        # it: the last one spent 124s and ~11,900 output tokens to produce a
        # 2 KB page. Speed is the whole product of this stage.
        UNCLE_PREVIEW_BUILD=true \
        WORKFLOW_MODEL_PREVIEW_BUILD="$(preview_build_model)" \
        WORKFLOW_EFFORT_PREVIEW_BUILD="${WORKFLOW_EFFORT_PREVIEW_BUILD:-low}" \
            run_claude prompts/preview-build.md preview-build || status=$?
        if [[ -n "$launch_before" ]]; then
            printf '%s' "$launch_before" > .uncle/launch.json
        else
            rm -f .uncle/launch.json
        fi
        exit "$status"
    ) > "$LOG_DIR/preview-build.log" 2>&1 < /dev/null &
    PREVIEW_PID=$!
}

# preview_build_wait — join it before anything reads the tree. Never fatal: a
# failed preview is a preview nobody got, not a failed run.
preview_build_wait() {
    [[ -n "$PREVIEW_PID" ]] || return 0
    local status=0 pid="$PREVIEW_PID"
    PREVIEW_PID=""
    echo
    echo "Waiting for the preview build to finish before implementation..."
    wait "$pid" || status=$?
    if [[ "$status" -ne 0 ]]; then
        echo "Preview build did not complete (status $status); continuing."
        echo "Log: $LOG_DIR/preview-build.log"
    fi
    return 0
}

# preview_build_cancel — from the EXIT trap. A preview must not outlive its run.
preview_build_cancel() {
    if [[ -n "$PREVIEW_PID" ]] && kill -0 "$PREVIEW_PID" 2>/dev/null; then
        echo "Cancelling the preview build..."
        kill "$PREVIEW_PID" 2>/dev/null || true
        wait "$PREVIEW_PID" 2>/dev/null || true
    fi
    PREVIEW_PID=""
    return 0
}

# preview_build_survived — 0 when the review left every section the code depends
# on untouched, so the tree already holds work built to the approved design.
preview_build_survived() {
    local recorded
    [[ "$PREVIEW_STARTED" == 1 ]] || return 1
    [[ -s "$STATE_DIR/preview-build.plan" ]] || return 1
    [[ -s UPDATED_PROJECT_PLAN.md ]] || return 1
    recorded="$(cat "$STATE_DIR/preview-build.plan")"
    [[ "$recorded" == "$(plan_material_hash UPDATED_PROJECT_PLAN.md)" ]]
}
